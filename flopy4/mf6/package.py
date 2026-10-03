import operator
from abc import ABC
from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
import pandas as pd
import xarray as xr
from modflow_devtools.dfns.schema import split_bound
from pandas.api.types import is_scalar

from flopy4.dimensions import DimensionProvider
from flopy4.mf6.component import Component
from flopy4.mf6.constants import MF6
from flopy4.mf6.item import (
    Item,
    construct_item,
    construct_union_item,
    count_dim,
    dim_counted_fields,
    item_list_type,
    resolve_dim,
)
from flopy4.mf6.spec import to_field_type
from flopy4.mf6.write_context import WriteContext

# DFN type -> numpy dtype, for broadcasting a scalar griddata default to a
# full array.
_DTYPE_MAP: dict = {
    "integer": np.int64,
    "double": np.float64,
    "double precision": np.float64,
    "string": np.object_,
    "keyword": np.object_,
}

# A list shape's bound operator (DFN "<=maxbound") -> check of row count
# against the dimension. No operator means the shape is exact.
_BOUND_OPS: dict = {
    None: operator.eq,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


@attrs.define(kw_only=True, slots=False)
class Package(Component, ABC):
    # Dimensions counting item columns that aren't fields themselves, name ->
    # DFN expression (utl-ts's {"time_series_names": "len(time_series_names)"}).
    count_dims: ClassVar[dict[str, str]] = {}

    def __attrs_post_init__(self) -> None:
        """Post-init for Package subclasses.

        Handles three concerns in order:
        1. Coerce raw list/block/period data into Item-list fields, and
           set each list's row-count dimension.
        2. Normalize griddata (lists to arrays, per-layer values, flat
           shapes), then broadcast scalar griddata values to their DFN
           shape when dims is supplied (e.g. IC(strt=1.0, dims={"nodes":
           900})) or the package provides its own (a grid package).
        3. Chain to Component.__attrs_post_init__() via super() -- LAST,
           after 1-2, in every exit path (including the two early
           returns below). Several of a package's own fields (e.g.
           griddata arrays default to a bare scalar/dict until step 2
           broadcasts them) aren't in their final shape until steps 1-2
           finish, and Component.__attrs_post_init__() (via
           DimensionResolverMixin's chain and _set_child_parents(),
           which walks every attrs field) reads them -- so chaining
           before they're finalized breaks griddata broadcasting and
           dims resolution.
        """
        import attrs as _attrs

        # Detect schema-driven fields by presence of 'block' in field metadata.
        # Package subclasses with no fields of their own (e.g. the
        # Gwfgwe/Gwfgwt/Gwfprt exchange leaves in flopy4/mf6/exg/ -- just
        # dfn_name, no declared fields) no-op through the rest of this method.
        try:
            fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            super().__attrs_post_init__()
            return
        if not any(f.metadata.get("block") is not None for f in fields):
            super().__attrs_post_init__()
            return

        # 1. Item-list coercion.
        self._init_item_lists(fields)
        self._init_named_arrays(fields)

        # 2. Griddata normalization and broadcasting. A dimension provider
        # (a grid package) sizes its own griddata.
        dims: dict = (
            self.get_dims()
            if isinstance(self, DimensionProvider)
            else (self.__dict__.get("dims") or {})
        )
        self._normalize_griddata(fields, dims)
        if dims:
            self._broadcast_griddata(fields, dims)

        # 3. Chain to Component's own post-init -- see docstring above for
        # why this must run last, not first.
        super().__attrs_post_init__()

    def _init_item_lists(self, fields) -> None:
        """Coerce raw list/dict block+period data into Item-list fields.

        A list field with `dim` metadata (the DIMENSIONS field counting its
        rows, in DFN shape syntax: exact "nper" or bounded "<=maxats") gets
        that dimension set from its row count, unless it was given
        explicitly. An explicit dimension must equal the row count, or
        satisfy the bound, else it is an error. A list left at a one-row
        default (TDIS's perioddata, from the DFN) gets that row repeated
        `dim` times. `maxbound` (where applicable) is a computed property
        instead, not set here.

        Reads/writes the field's real attribute name (f.name) always --
        aliases (e.g. _stress_period_data's "stress_period_data") only name
        the __init__ parameter; the instance attribute (and __dict__ key
        object.__setattr__ writes to) is still the real name.
        """
        for f in fields:
            block = f.metadata.get("block")
            if not block:
                continue
            item_cls = item_list_type(f.type)
            if item_cls is None:
                continue
            bound, dim = split_bound(f.metadata["dim"]) if "dim" in f.metadata else (None, None)
            raw = self.__dict__.get(f.name)
            # Identity, not equality: only the default object itself (never
            # a user value, even an equal one) is repeated to fill `dim`.
            if raw is not None and raw is f.default and len(raw) == 1:
                raw = list(raw) * ((getattr(self, dim) if dim else None) or 1)
            if raw is None:
                continue

            if f.metadata.get("fill_forward"):
                coerced = {
                    kper: self._coerce_item_list(rows, item_cls) for kper, rows in raw.items()
                }
                object.__setattr__(self, f.name, coerced)
                rows = [r for kper_rows in coerced.values() for r in kper_rows]
                if dim:
                    nrows = max((len(r) for r in coerced.values()), default=0)
                    self._set_dim_from_rows(dim, nrows, bound)
            else:
                rows = self._coerce_item_list(raw, item_cls)
                object.__setattr__(self, f.name, rows)
                if dim:
                    self._set_dim_from_rows(dim, len(rows), bound)
            if not isinstance(item_cls, tuple):
                self._set_dims_from_counts(item_cls, rows)

    def _init_named_arrays(self, fields) -> None:
        """Named arrays (RCHA's aux): convert each to an array, and check
        its name is one of the names the field's fk points at."""
        for f in fields:
            if not (f.metadata.get("fill_forward") and (fk := f.metadata.get("fk"))):
                continue
            if (arrays := self.__dict__.get(f.name)) is None:
                continue
            key = fk.rsplit(".", 1)[-1]
            names = getattr(self, key, None)
            allowed = {str(n).lower() for n in np.atleast_1d(names)} if names is not None else set()
            if unknown := sorted(n for n in arrays if str(n).lower() not in allowed):
                raise ValueError(f"{f.name}: {unknown} not in {key}")
            self.__dict__[f.name] = {
                n: a if hasattr(a, "shape") else np.asarray(a) for n, a in arrays.items()
            }

    def _set_dim_from_rows(self, dim: str, nrows: int, bound: str | None = None) -> None:
        declared = getattr(self, dim)
        if declared is None:
            object.__setattr__(self, dim, nrows)
        elif not _BOUND_OPS[bound](nrows, declared):
            raise ValueError(
                f"{dim}={declared} but {nrows} rows were given (need rows {bound or '=='} {dim})"
            )

    def _set_dims_from_counts(self, item_cls: "type[Item]", rows: list) -> None:
        """Set the dimensions counting array columns (GNC's numalphaj counts
        cellidsj and alphasj, EVT's nseg-1 counts pxdp) from the columns'
        lengths, unless given."""
        for f in dim_counted_fields(item_cls):
            dim, offset = count_dim(f.metadata["count"])
            lengths = {len(v) for r in rows if (v := getattr(r, f.name)) is not None}
            if len(lengths) > 1:
                raise ValueError(f"{f.name} lengths differ across rows: {sorted(lengths)}")
            if not lengths:
                continue
            (n,) = lengths
            if dim in self.count_dims:
                values = {a.name: getattr(self, a.name) for a in attrs.fields(type(self))}
                declared = resolve_dim(dim, self.count_dims, values)
                if declared is not None and declared + offset != n:
                    raise ValueError(f"{dim}={declared} but {f.name} has {n} values")
                continue
            declared = getattr(self, dim)
            if declared is None:
                object.__setattr__(self, dim, n - offset)
            elif declared + offset != n:
                raise ValueError(f"{dim}={declared} but {f.name} has {n} values")

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
            return [item_cls(**{name: vals[i] for name, vals in data.items()}) for i in range(n)]
        items = []
        for row in data:
            if isinstance(row, item_cls):
                items.append(row)
            elif isinstance(row, dict):
                items.append(item_cls(**row))
            elif isinstance(row, (list, tuple)):
                items.append(construct_item(item_cls, row))
            else:
                items.append(construct_item(item_cls, list(row)))
        return items

    def _normalize_griddata(self, fields, dims: dict) -> None:
        """Convert list griddata to arrays, repeat a `layered` array's
        per-layer values across each layer's cells, and flatten structured
        arrays to their flat DFN shape (e.g. `(nlay, nrow, ncol)` to
        `(nodes,)`)."""
        nlay = dims.get("nlay")
        ncpl = dims.get("ncpl") or (dims["nodes"] // nlay if nlay and "nodes" in dims else None)
        for f in fields:
            if f.metadata.get("block") != "griddata":
                continue
            val = self.__dict__.get(f.name)
            dtype = _DTYPE_MAP.get(to_field_type(f.type), np.float64)
            if isinstance(val, (list, tuple)):
                val = np.asarray(val, dtype=dtype)
            if not isinstance(val, np.ndarray):
                continue
            if f.metadata.get("layered") and nlay and ncpl and val.shape == (nlay,):
                val = np.repeat(val, ncpl).astype(dtype)
            elif val.ndim > 1 and len(f.metadata.get("shape") or ()) == 1:
                val = val.ravel()
            self.__dict__[f.name] = val

    def _broadcast_griddata(self, fields, dims: dict) -> None:
        """Expand scalar griddata defaults to full arrays when dims is supplied."""
        _par_data = getattr(self, "_par_data", None)
        _is_vertex = (
            _par_data is not None
            and "ncpl" in _par_data.dims
            and _par_data.dims.get("nrow", 0) == 0
        ) or ("ncpl" in dims and "nrow" not in dims)

        for f in fields:
            if f.metadata.get("block") != "griddata":
                continue
            shape_meta = f.metadata.get("shape")
            if not shape_meta:
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            _gd_dtype = _DTYPE_MAP.get(to_field_type(f.type), np.float64)
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
                self.__dict__[f.name] = np.full(shape, val, dtype=_gd_dtype)
            elif isinstance(val, np.ndarray) and val.shape != shape:
                try:
                    self.__dict__[f.name] = val.reshape(shape)
                except ValueError:
                    pass
            elif isinstance(val, dict) and not val:
                default = f.default if isinstance(f.default, (int, float)) else 0
                self.__dict__[f.name] = np.full(shape, default, dtype=_gd_dtype)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        self._sync_subpackage_files()
        super().write(format=format, context=context)

    def _sync_subpackage_files(self) -> None:
        """Name each attached subpackage's file in the parent's path field
        (e.g. DIS's ``NCF6 FILEIN <file>``), unless already given."""
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if (file_field := f.metadata.get("file_field")) is None:
                continue
            if (child := getattr(self, f.name)) is None:
                continue
            child.filename = child.filename or Path(child.default_filename())
            if getattr(self, file_field) is None:
                setattr(self, file_field, Path(child.filename.name))

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
        import attrs as _attrs

        try:
            all_fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            return super().to_dict(blocks=blocks, strict=strict)

        # Fall back for a Package subclass with no schema-driven fields of
        # its own (e.g. the exchange leaves in flopy4/mf6/exg/).
        if not any(f.metadata.get("block") for f in all_fields):
            return super().to_dict(blocks=blocks, strict=strict)

        _exclude = {"name", "parent", "_parent", "dims", "filename", "workspace", "strict"}
        result: dict = {}
        for f in all_fields:
            if f.name in _exclude or f.init is False:
                continue
            block = f.metadata.get("block")
            if not block:
                continue
            key = f.alias if (f.alias and f.name.startswith("_")) else f.name
            val = getattr(self, key, None)
            if blocks:
                result.setdefault(block, {})[key] = val
            else:
                result[key] = val
        return result

    def to_dataframe(self) -> pd.DataFrame:
        """Return stress period data as a tidy DataFrame. Zero cost if not called."""
        _spd = self.__dict__.get("_stress_period_data")
        if not _spd:
            return pd.DataFrame()
        frames = []
        for kper in sorted(_spd):
            df = pd.DataFrame([attrs.asdict(row) for row in _spd[kper]])
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
            # A missing optional column (e.g. boundname) round-trips through
            # pandas as NaN, not absent. Drop it so the Item class's own
            # default applies rather than storing a float in a str field.
            spd[int(kper)] = [
                item_cls(**{k: v for k, v in row.items() if not (is_scalar(v) and pd.isna(v))})
                for row in group.to_dict("records")
            ]
        self.__dict__["_stress_period_data"] = spd

    def _period_item_cls(self) -> "type[Item] | tuple[type[Item], ...]":
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if f.metadata.get("fill_forward"):
                item_cls = item_list_type(f.type)
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
        import attrs as _attrs

        fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        for _block in ("griddata", "period"):
            data_vars = {
                a.name: self.to_dataarray(a.name)
                for a in fields
                if a.metadata.get("block") == _block and getattr(self, a.name) is not None
            }
            if data_vars:
                return xr.Dataset(data_vars)
        return super().to_xarray()  # type: ignore[return-value]
