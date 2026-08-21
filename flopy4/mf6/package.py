from abc import ABC
from pathlib import Path

import attrs
import numpy as np
import pandas as pd
import xarray as xr
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.row import Row, construct_row, dispatch_union_row, normalize_aux_keys, row_list_type
from flopy4.mf6.spec import to_field_type

# DFN type -> numpy dtype, for broadcasting a scalar griddata default to a
# full array (unrelated to the old Schema/Column row-parsing machinery).
_DTYPE_MAP: dict = {
    "integer": np.int64,
    "double": np.float64,
    "double precision": np.float64,
    "string": np.object_,
    "keyword": np.object_,
}


@xattree
class Package(Component, ABC):
    def __attrs_post_init__(self) -> None:
        """Post-init for codegen v2 packages.

        Handles three concerns in order:
        1. Fix xattree name registration (concrete class name, not 'package').
        2. Coerce raw list/block/period data into Row-list fields (the
           generated field's own type annotation -- Optional[list[RowClass]]
           or Optional[dict[int, list[RowClass]]] -- is the schema; no
           separate Schema/Column description), auto-set maxbound/n<block>s.
        3. Broadcast scalar griddata values to their DFN shape when dims
           is supplied (e.g. IC(strt=1.0, dims={"nodes": 900})).
        """
        import attrs as _attrs

        # Detect schema-driven (codegen v2 style) fields by presence of 'block'
        # in field metadata. Package subclasses with no such fields (rare) just
        # no-op through the rest of this method.
        try:
            fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            return
        if not any(f.metadata.get("block") is not None for f in fields):
            return

        # 1. Fix xattree name registration.
        if self.__dict__.get("name") == "package":
            self.__dict__["name"] = type(self).__name__.lower()

        # 2. Row-list coercion.
        self._init_row_lists(fields)

        # 3. Griddata broadcasting.
        dims: dict = self.__dict__.get("dims") or {}
        if dims:
            self._broadcast_griddata(fields, dims)

    def _init_row_lists(self, fields) -> None:
        """Coerce raw list/dict block+period data into Row-list fields;
        auto-set maxbound / n<block>s from the resulting list lengths.

        Reads/writes the field's real attribute name (f.name) always --
        aliases (e.g. _stress_period_data's "stress_period_data") only name
        the __init__ parameter; the instance attribute (and __dict__ key
        object.__setattr__ writes to) is still the real name.
        """
        for f in fields:
            block = f.metadata.get("block")
            if not block:
                continue
            row_cls = row_list_type(f.type)
            if row_cls is None:
                continue
            raw = self.__dict__.get(f.name)
            if raw is None:
                continue

            if block == "period" or f.metadata.get("fill_forward"):
                coerced = {kper: self._coerce_row_list(rows, row_cls) for kper, rows in raw.items()}
                object.__setattr__(self, f.name, coerced)
                if coerced and getattr(self, "maxbound", None) == 0:
                    object.__setattr__(self, "maxbound", max(len(v) for v in coerced.values()))
            else:
                coerced_list = self._coerce_row_list(raw, row_cls)
                object.__setattr__(self, f.name, coerced_list)
                if getattr(self, f"n{block}s", 0) == 0:
                    object.__setattr__(self, f"n{block}s", len(coerced_list))

    @staticmethod
    def _coerce_row_list(data, row_cls: "type[Row] | tuple[type[Row], ...]") -> list:
        """Convert user-supplied list/dict data to a list of Row instances.

        For a plain (non-union) row_cls, accepts:
          - list of row_cls instances  → returned as-is
          - list of tuples/lists       → positional, matching row_cls's
                                          own field declaration order
          - list of dicts              → named columns
          - dict of lists              → column-oriented {col_name: [values]}

        For a keystring-union row_cls (a tuple of arm classes, e.g. LAK's
        (LakStatusItem, LakStageItem, ...)): existing arm instances pass
        through; tuples/lists/dicts are dispatched to the right arm by
        their keyword token/"keyword" key, the same way file rows are (see
        flopy4.mf6.row.dispatch_union_row) -- ambiguous columnar dict-of-
        lists input isn't supported (no single arm to build columns from).
        """
        if isinstance(row_cls, tuple):
            rows = []
            for row in data:
                if isinstance(row, row_cls):
                    rows.append(row)
                elif isinstance(row, dict):
                    kw = str(row.get("keyword", "")).upper()
                    arm = next(
                        (c for c in row_cls if c.__dict__.get("_keyword", "").upper() == kw), None
                    )
                    if arm is not None:
                        rows.append(arm(**{k: v for k, v in row.items() if k != "keyword"}))
                else:
                    tokens = list(row)
                    arm = dispatch_union_row(tokens, row_cls)
                    if arm is not None:
                        rows.append(arm.from_row(tokens))
            return rows
        if isinstance(data, dict):
            n = len(next(iter(data.values()))) if data else 0
            return [
                row_cls(**normalize_aux_keys({name: vals[i] for name, vals in data.items()}))
                for i in range(n)
            ]
        rows = []
        for row in data:
            if isinstance(row, row_cls):
                rows.append(row)
            elif isinstance(row, dict):
                rows.append(row_cls(**normalize_aux_keys(row)))
            elif isinstance(row, (list, tuple)):
                rows.append(construct_row(row_cls, row))
            else:
                rows.append(construct_row(row_cls, list(row)))
        return rows

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
            pname), overriding xattree's default auto-assigned name.
        """
        from flopy4.mf6.codec.reader import load as _codec_load
        from flopy4.mf6.converter.ingress.structure import structure_component

        with open(path) as _f:
            _raw = _codec_load(_f)
        _pkg = structure_component(_raw, cls, dims=dims, name=name)

        # Pre-populate dimension cache so to_xarray()/to_dataarray() work
        # on standalone packages (not attached to a parent model).
        if dims:
            _pkg._dimension_cache.update(dims)

        return _pkg

    def default_filename(self) -> str:
        name = self.parent.name if self.parent else self.name  # type: ignore
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

        # Check if this is a codegen v2 class
        if not any(f.metadata.get("block") for f in all_fields):
            return super().to_dict(blocks=blocks, strict=strict)

        _exclude = {"name", "parent", "dims", "filename", "workspace", "strict"}
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
        the period Row class's own fields (as produced by ``to_dataframe()``).
        """
        if df.empty:
            self.__dict__["_stress_period_data"] = {}
            return
        if "kper" not in df.columns:
            raise ValueError("DataFrame must have a 'kper' column")
        row_cls = self._period_row_cls()
        if isinstance(row_cls, tuple):
            raise ValueError(
                f"{type(self).__name__}.from_dataframe() doesn't support a keystring-union "
                "period field (multiple possible row shapes) -- construct arm instances directly."
            )
        spd: dict[int, list] = {}
        for kper, group in df.groupby("kper"):
            group = group.drop(columns=["kper"])
            spd[int(kper)] = [row_cls(**row) for row in group.to_dict("records")]
        self.__dict__["_stress_period_data"] = spd

    def _period_row_cls(self) -> "type[Row] | tuple[type[Row], ...]":
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if f.metadata.get("block") == "period" or f.metadata.get("fill_forward"):
                row_cls = row_list_type(f.type)
                if row_cls is not None:
                    return row_cls
        raise ValueError(f"{type(self).__name__} has no period Row-list field")

    @property
    def stress_period_data(self):  # type: ignore[override]
        """Stress period data as ``dict[int, list[Row]]`` keyed by 0-based kper."""
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
        falls through to ``Component.to_xarray()`` which returns the xattree
        DataTree dataset (empty for codegen v2 packages — see §9.2 of
        dask1.scope.md).
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
