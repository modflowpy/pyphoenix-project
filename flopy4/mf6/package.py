from abc import ABC
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from pydantic import field_validator
from pydantic.dataclasses import dataclass

from flopy4.mf6.component import CFG, Component
from flopy4.mf6.item import (
    Item,
    construct_item,
    construct_union_item,
    item_list_type,
    normalize_aux_keys,
)
from flopy4.mf6.spec import to_field_type

# DFN type -> numpy dtype, for broadcasting a scalar griddata default to a
# full array.
_DTYPE_MAP: dict = {
    "integer": np.int64,
    "double": np.float64,
    "double precision": np.float64,
    "string": np.object_,
    "keyword": np.object_,
}


def _is_dask_array(v: Any) -> bool:
    try:
        from dask.array import Array as _DaskArray
    except ImportError:
        return False
    return isinstance(v, _DaskArray)


@dataclass(config=CFG, kw_only=True)
class Package(Component, ABC):
    # A griddata field's *declared* type is an array type (NDArray[...]/
    # FloatArrayLike/IntArrayLike), but its *default value* in the real DFN
    # corpus is often a bare scalar (e.g. `strt: FloatArrayLike =
    # field(default=1.0, ...)`) that only becomes a real array once dims
    # are known -- attrs never type-checks this mismatch (no per-field
    # validator declared), so a scalar sails through construction
    # untouched until __post_init__'s _broadcast_griddata expands it.
    # Pydantic DOES enforce it: confirmed empirically that
    # `IcLike(strt=1.0, dims=...)` raises `ValidationError: Input should be
    # an instance of _ArrayLike` without this coercion step -- the
    # unvalidated *default* (not explicitly passed) doesn't hit this,
    # since pydantic doesn't validate field defaults unless
    # validate_default=True (not set here), but any *explicit* scalar
    # override does. One shared `field_validator("*", mode="before")`,
    # driven by each field's own `json_schema_extra["shape"]` (which
    # `spec.field()` already emits today), covers every griddata field on
    # every subclass -- not one per field, not one per generated class.
    @field_validator("*", mode="before")
    @classmethod
    def _coerce_arrays(cls, v: Any, info) -> Any:
        finfo = cls.__pydantic_fields__.get(info.field_name)
        if finfo is None or v is None:
            return v
        meta = finfo.json_schema_extra or {}
        if not (isinstance(meta, dict) and meta.get("block") == "griddata" and meta.get("shape")):
            return v
        if isinstance(v, np.ndarray) or _is_dask_array(v):
            # Already a real ndarray, or specifically a dask.array.Array
            # (the one duck array actually exercised here -- see
            # codec/writer/filters.py's array2chunks). np.asarray() below
            # would materialize a dask array into a real ndarray, losing
            # its laziness (confirmed by running the real dask-array
            # griddata test), so it's passed through untouched. Anything
            # ELSE duck-array-shaped (an xr.DataArray, notably -- confirmed
            # by running Disv.from_grid() with a DataArray-backed grid) is
            # NOT preserved as-is: some hand-written fields (Dis/Disv's
            # own top/botm/delr/delc/iv/xv/yv) declare the stricter
            # NDArray[...] rather than the _ArrayLike Protocol most
            # generated griddata fields use, and only real np.ndarray
            # satisfies that -- so it still needs materializing below.
            return v
        dtype = _DTYPE_MAP.get(to_field_type(finfo.annotation), np.float64)
        if isinstance(v, dict):
            # An empty-dict griddata value (e.g. Chd(dims={}) with no
            # explicit scalar override) is _broadcast_griddata's own
            # "use the field's own scalar default" signal -- attrs let it
            # reach __post_init__ as a raw {} unchanged; pydantic's
            # NDArray/_ArrayLike type check has no such carve-out (and
            # np.asarray({}, ...) itself raises, confirmed by running the
            # real empty-dict-griddata test). Pre-resolve it into the same
            # 0-d default-valued array a bare scalar default produces here
            # -- _broadcast_griddata's existing size==1 branch (added for
            # that scalar case) picks it up and broadcasts it exactly the
            # same way.
            default = finfo.default if isinstance(finfo.default, (int, float)) else 0
            return np.asarray(default, dtype=dtype)
        return np.asarray(v, dtype=dtype)

    def __post_init__(self) -> None:
        """Post-init for Package subclasses.

        Handles three concerns in order:
        1. Coerce raw list/block/period data into Item-list fields, and
           auto-set n<block>s.
        2. Broadcast scalar griddata values to their DFN shape when dims
           is supplied (e.g. IC(strt=1.0, dims={"nodes": 900})).
        3. Chain to Component.__post_init__() via super() -- LAST, after
           1-2, in every exit path (including the early return below).
           Several of a package's own fields (e.g. griddata arrays
           default to a bare scalar/dict until step 2 broadcasts them)
           aren't in their final shape until steps 1-2 finish, and
           Component.__post_init__() (via DimensionResolverMixin's chain
           and _set_child_parents(), which walks every field) reads them
           -- so chaining before they're finalized breaks griddata
           broadcasting and dims resolution. Matches the ordering
           DisBase/Dis already use for their own __post_init__ chaining
           (super() called last, after their own field setup).
        """
        # Detect schema-driven fields by presence of 'block' in field
        # json_schema_extra. Package subclasses with no fields of their
        # own (e.g. the Gwfgwe/Gwfgwt/Gwfprt exchange leaves in
        # flopy4/mf6/exg/ -- just dfn_name, no declared fields) still
        # inherit Component's own fields (filename, name, ...), none of
        # which carry block metadata, so this simply no-ops through the
        # rest of this method for them -- no NotAnAttrsClassError-style
        # guard needed (every Package subclass is a pydantic dataclass,
        # unconditionally, unlike attrs' optional per-class opt-in).
        fields = type(self).__pydantic_fields__
        if not any((f.json_schema_extra or {}).get("block") is not None for f in fields.values()):
            super().__post_init__()
            return

        # 1. Item-list coercion.
        self._init_item_lists(fields)

        # 2. Griddata broadcasting.
        dims: dict = self.__dict__.get("dims") or {}
        if dims:
            self._broadcast_griddata(fields, dims)

        # 3. Chain to Component's own post-init -- see docstring above for
        # why this must run last, not first.
        super().__post_init__()

    def _init_item_lists(self, fields) -> None:
        """Coerce raw list/dict block+period data into Item-list fields;
        auto-set n<block>s from the resulting list lengths. `maxbound`
        (where applicable) is a computed property instead, not set here.

        Reads/writes the field's real attribute name (the dict key)
        always -- aliases (e.g. _stress_period_data's "stress_period_data")
        only name the __init__ parameter; the instance attribute (and
        __dict__ key object.__setattr__ writes to) is still the real name.
        """
        for name, f in fields.items():
            meta = f.json_schema_extra or {}
            block = meta.get("block")
            if not block:
                continue
            item_cls = item_list_type(f.annotation)
            if item_cls is None:
                continue
            raw = self.__dict__.get(name)
            if raw is None:
                continue

            if meta.get("fill_forward"):
                coerced = {
                    kper: self._coerce_item_list(rows, item_cls) for kper, rows in raw.items()
                }
                object.__setattr__(self, name, coerced)
            else:
                coerced_list = self._coerce_item_list(raw, item_cls)
                object.__setattr__(self, name, coerced_list)
                if getattr(self, f"n{block}s", 0) == 0:
                    object.__setattr__(self, f"n{block}s", len(coerced_list))

    @staticmethod
    def _coerce_item_list(data, item_cls: "type[Item] | tuple[type[Item], ...]") -> list:
        """Convert user-supplied list/dict data to a list of Item instances.

        For a plain (non-union) item_cls, accepts:
          - list of item_cls instances → returned as-is
          - list of tuples/lists       → positional, matching item_cls's
                                          own field declaration order
          - list of dicts              → named columns
          - dict of lists              → column-oriented {col_name: [values]}

        For a keystring-union item_cls (a tuple of arm classes, e.g. LAK's
        (LakStatus, LakStage, ...)): existing arm instances pass through;
        tuples/lists are dispatched to the right arm by their keyword token
        and built positionally (see flopy4.mf6.item.construct_union_item --
        NOT from_tokens, since these values are already Python-side, not
        raw 1-based/string file tokens); dicts are dispatched by a
        "keyword" key. Ambiguous columnar dict-of-lists input isn't
        supported (no single arm to build columns from).
        """
        if isinstance(item_cls, tuple):
            items = []
            for row in data:
                if isinstance(row, item_cls):
                    items.append(row)
                elif isinstance(row, dict):
                    kw = str(row.get("keyword", "")).upper()
                    arm = next(
                        (c for c in item_cls if c.__dict__.get("_keyword", "").upper() == kw), None
                    )
                    if arm is not None:
                        items.append(arm(**{k: v for k, v in row.items() if k != "keyword"}))
                else:
                    item = construct_union_item(row, item_cls)
                    if item is not None:
                        items.append(item)
            return items
        if isinstance(data, dict):
            n = len(next(iter(data.values()))) if data else 0
            return [
                item_cls(**normalize_aux_keys({name: vals[i] for name, vals in data.items()}))
                for i in range(n)
            ]
        items = []
        for row in data:
            if isinstance(row, item_cls):
                items.append(row)
            elif isinstance(row, dict):
                items.append(item_cls(**normalize_aux_keys(row)))
            elif isinstance(row, (list, tuple)):
                items.append(construct_item(item_cls, row))
            else:
                items.append(construct_item(item_cls, list(row)))
        return items

    def _broadcast_griddata(self, fields, dims: dict) -> None:
        """Expand scalar griddata defaults to full arrays when dims is supplied."""
        _par_data = getattr(self, "_par_data", None)
        _is_vertex = (
            _par_data is not None
            and "ncpl" in _par_data.dims
            and _par_data.dims.get("nrow", 0) == 0
        ) or ("ncpl" in dims and "nrow" not in dims)

        for name, f in fields.items():
            meta = f.json_schema_extra or {}
            if meta.get("block") != "griddata":
                continue
            shape_meta = meta.get("shape")
            if not shape_meta:
                continue
            val = self.__dict__.get(name)
            if val is None:
                continue
            _gd_dtype = _DTYPE_MAP.get(to_field_type(f.annotation), np.float64)
            try:
                resolved = []
                for d in shape_meta:
                    if d == "ncelldim":
                        resolved.append(2 if _is_vertex else 3)
                    else:
                        resolved.append(dims[d])
                shape = tuple(resolved)
            except KeyError:
                continue
            if isinstance(val, (int, float)):
                self.__dict__[name] = np.full(shape, val, dtype=_gd_dtype)
            elif isinstance(val, np.ndarray) and val.size == 1 and val.shape != shape:
                # A scalar that already passed through _coerce_arrays'
                # mode="before" validator (needed so pydantic's own type
                # check on an _ArrayLike-typed field accepts it at all --
                # see that validator's docstring) arrives here as a 0-d
                # ndarray, not a bare int/float, so the branch above
                # doesn't match. Same broadcast, just unwrapped first.
                self.__dict__[name] = np.full(shape, val.item(), dtype=_gd_dtype)
            elif isinstance(val, np.ndarray) and val.shape != shape:
                try:
                    self.__dict__[name] = val.reshape(shape)
                except ValueError:
                    pass
            elif isinstance(val, dict) and not val:
                default = f.default if isinstance(f.default, (int, float)) else 0
                self.__dict__[name] = np.full(shape, default, dtype=_gd_dtype)

    @classmethod
    def load(  # type: ignore[override]
        cls,
        path: Path,
        dims: "dict[str, int] | None" = None,
        name: "str | None" = None,
    ) -> "Package":
        """Load from an MF6 text input file.

        Parameters
        ----------
        path :
            Path to the package input file.
        dims :
            Grid dimension values required to resolve array shapes,
            e.g. ``{"nlay": 3, "nodes": 900}``.  Required for griddata
            packages (NPF, IC, STO, etc.); may be omitted for list-input
            packages (WEL, DRN, etc.).
        name :
            Explicit component name (e.g. a namefile binding row's
            pname), overriding the default auto-assigned name.
        """
        from flopy4.mf6.codec.reader import load as _codec_load
        from flopy4.mf6.converter.ingress.structure import structure_component

        with open(path) as _f:
            _raw = _codec_load(_f)
        _pkg = structure_component(_raw, cls, dims=dims, workspace=path.parent, name=name)

        # Pre-populate dimension cache so to_xarray()/to_dataarray() work
        # on standalone packages (not attached to a parent model).
        if dims:
            _pkg._dimension_cache.update(dims)

        return _pkg

    def default_filename(self) -> str:
        name = self._parent.name if self._parent else self.name  # type: ignore
        cls_name = self.__class__.__name__.lower()
        return f"{name}.{cls_name}"

    def to_dict(self, blocks: bool = False, strict: bool = False) -> dict:
        """Convert to a dictionary of field values.

        Parameters
        ----------
        blocks : bool
            If True, return nested dict keyed by DFN block name.
        strict : bool
            If True, only include fields with ``block`` metadata.
        """
        all_fields = type(self).__pydantic_fields__

        # Fall back for a Package subclass with no schema-driven fields of
        # its own (e.g. the exchange leaves in flopy4/mf6/exg/).
        if not any((f.json_schema_extra or {}).get("block") for f in all_fields.values()):
            return super().to_dict(blocks=blocks, strict=strict)

        _exclude = {"name", "parent", "_parent", "dims", "filename", "workspace", "strict"}
        result: dict = {}
        for name, f in all_fields.items():
            if name in _exclude or f.init is False:
                continue
            meta = f.json_schema_extra or {}
            block = meta.get("block")
            if not block:
                continue
            key = f.alias if (f.alias and name.startswith("_")) else name
            val = getattr(self, key, None)
            if blocks:
                result.setdefault(block, {})[key] = val
            else:
                result[key] = val
        return result

    def to_dataframe(self) -> pd.DataFrame:
        """Return stress period data as a tidy DataFrame. Zero cost if not called."""
        import dataclasses as _dc

        _spd = self.__dict__.get("_stress_period_data")
        if not _spd:
            return pd.DataFrame()
        frames = []
        for kper in sorted(_spd):
            df = pd.DataFrame([_dc.asdict(row) for row in _spd[kper]])
            df.insert(0, "kper", kper)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def from_dataframe(self, df: pd.DataFrame) -> None:
        """Set stress_period_data from a tidy DataFrame.

        The DataFrame must have a ``kper`` column and data columns matching
        the period Item class's own fields (as produced by ``to_dataframe()``).
        """
        if df.empty:
            self.__dict__["_stress_period_data"] = {}
            return
        if "kper" not in df.columns:
            raise ValueError("DataFrame must have a 'kper' column")
        item_cls = self._period_item_cls()
        if isinstance(item_cls, tuple):
            raise ValueError(
                f"{type(self).__name__}.from_dataframe() doesn't support a keystring-union "
                "period field (multiple possible row shapes) -- construct arm instances directly."
            )
        spd: dict[int, list] = {}
        for kper, group in df.groupby("kper"):
            group = group.drop(columns=["kper"])
            rows = []
            for row in group.to_dict("records"):
                # A missing optional column (e.g. boundname) round-trips
                # through pandas as NaN, not absent -- drop it so the
                # Item class's own default applies instead of failing
                # pydantic's real type validation (unlike attrs, which
                # applied none here and silently accepted a stray float
                # in a str-typed field).
                rows.append(item_cls(**{k: v for k, v in row.items() if not pd.isna(v)}))
            spd[int(kper)] = rows
        self.__dict__["_stress_period_data"] = spd

    def _period_item_cls(self) -> "type[Item] | tuple[type[Item], ...]":
        for f in type(self).__pydantic_fields__.values():
            meta = f.json_schema_extra or {}
            if meta.get("fill_forward"):
                item_cls = item_list_type(f.annotation)
                if item_cls is not None:
                    return item_cls
        raise ValueError(f"{type(self).__name__} has no period Item-list field")

    @property
    def stress_period_data(self):  # type: ignore[override]
        """Stress period data as ``dict[int, list[Item]]`` keyed by 0-based kper."""
        return self.__dict__.get("_stress_period_data")

    @stress_period_data.setter  # type: ignore[attr-defined, no-redef]
    def stress_period_data(self, value) -> None:  # type: ignore[override]
        self.__dict__["_stress_period_data"] = value

    def to_dataarray(self, field_name: str) -> "xr.DataArray":
        """Single griddata field as xr.DataArray. Stays lazy if dask-backed."""
        arr = getattr(self, field_name)
        if arr is None:
            raise ValueError(f"{field_name!r} is not set")
        _d = self.resolve_dims("nlay", "nrow", "ncol", "ncpl", "nodes")
        _nlay = _d.get("nlay", 1)
        _nrow = _d.get("nrow")
        _ncol = _d.get("ncol")
        _ncpl = _d.get("ncpl")
        if _ncpl is None and "nodes" in _d and _nlay > 0:
            _ncpl = _d["nodes"] // _nlay
        if _nrow is not None and _ncol is not None:
            arr = arr.reshape(_nlay, _nrow, _ncol)
            dims: tuple[str, ...] = ("layer", "y", "x")
        elif _ncpl is not None:
            arr = arr.reshape(_nlay, _ncpl)
            dims = ("layer", "face")
        else:
            dims = ("node",)
        return xr.DataArray(arr, dims=dims, name=field_name)

    def to_xarray(self) -> "xr.Dataset":  # type: ignore[override]
        """All set griddata (or period-array) fields as xr.Dataset.

        Stays lazy if dask-backed. For packages with no array fields this
        falls through to ``Component.to_xarray()``, which returns whatever
        ``attrs_to_dataset()`` finds -- empty for a package with no
        griddata fields of its own.
        """
        fields = type(self).__pydantic_fields__
        for _block in ("griddata", "period"):
            data_vars = {
                name: self.to_dataarray(name)
                for name, f in fields.items()
                if (f.json_schema_extra or {}).get("block") == _block
                and getattr(self, name) is not None
            }
            if data_vars:
                return xr.Dataset(data_vars)
        return super().to_xarray()  # type: ignore[return-value]
