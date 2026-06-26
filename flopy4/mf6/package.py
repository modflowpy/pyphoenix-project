from abc import ABC
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd
import xarray as xr
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.schema import Schema


@xattree
class Package(Component, ABC):
    _DTYPE_MAP: ClassVar[dict] = {
        "integer": np.int64,
        "double": np.float64,
        "double precision": np.float64,
        "string": np.object_,
        "keyword": np.object_,
        "object": np.object_,
        "np.object_": np.object_,
        "np.int64": np.int64,
        "np.float64": np.float64,
    }

    def __attrs_post_init__(self) -> None:
        """Post-init for codegen v2 packages.

        Handles three concerns in order:
        1. Fix xattree name registration (concrete class name, not 'package').
        2. Build dtypes from __*_schema__ / __period_schema__ ClassVars,
           coerce raw SPD/block data to recarrays, auto-set maxbound.
        3. Broadcast scalar griddata values to their DFN shape when dims
           is supplied (e.g. IC(strt=1.0, dims={"nodes": 900})).
        """
        import attrs as _attrs

        # Detect codegen v2 by presence of 'dfn_block' in any field metadata.
        try:
            fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            return
        if not any(f.metadata.get("dfn_block") is not None for f in fields):
            return

        # 1. Fix xattree name registration.
        if self.__dict__.get("name") == "package":
            self.__dict__["name"] = type(self).__name__.lower()

        # 2. Schema-driven dtype construction.
        self._init_schemas()

        # 3. Griddata broadcasting.
        dims: dict = self.__dict__.get("dims") or {}
        if dims:
            self._broadcast_griddata(fields, dims)

    def _init_schemas(self) -> None:
        """Build dtypes from schema ClassVars; coerce raw data to recarrays."""
        _aux_tmp = getattr(self, "auxiliary", None)
        naux = len(_aux_tmp) if _aux_tmp is not None else 0
        ncelldim = self._compute_ncelldim()

        # Process block schemas (packagedata, connectiondata, etc.)
        cls = type(self)
        for attr_name in dir(cls):
            if not attr_name.startswith("__") or not attr_name.endswith("_schema__"):
                continue
            if attr_name == "__period_schema__":
                continue
            block_name = attr_name[2:-9]  # strip __ and _schema__
            schema = getattr(cls, attr_name)
            if not (isinstance(schema, type) and issubclass(schema, Schema)):
                continue
            self._init_block_dtype(block_name, schema, naux, ncelldim)

        # Process period schema.
        period_schema = getattr(cls, "__period_schema__", None)
        if period_schema is not None:
            self._init_period_dtype(period_schema, naux, ncelldim)

    def _init_block_dtype(
        self, block_name: str, schema: type[Schema], naux: int, ncelldim: int
    ) -> None:
        """Build dtype for a static block (packagedata, connectiondata, etc.)."""
        dtype_fields: list[tuple] = []
        for col in schema.columns():
            dt = (
                self._DTYPE_MAP.get(col.dtype, np.object_)
                if col.dtype
                else self._DTYPE_MAP.get(col.dfn_type, np.object_)
            )
            if col.role == "cellid":
                dtype_fields.append((col.name, np.int64, (ncelldim,)))
            elif col.role == "feature_id":
                dtype_fields.append((col.name, np.int64))
            elif col.role == "boundname":
                if getattr(self, "boundnames", False):
                    dtype_fields.append((col.name, np.object_))
            else:
                dtype_fields.append((col.name, dt))
        if block_name == "packagedata":
            for i in range(naux):
                dtype_fields.append((f"aux{i}", np.object_))
        dtype = np.dtype(dtype_fields)
        setattr(self, f"{block_name}_dtype", dtype)
        raw = getattr(self, block_name, None)
        if raw is not None:
            setattr(self, block_name, self._coerce_to_recarray(raw, dtype))
        if getattr(self, block_name, None) is not None and getattr(self, f"n{block_name}s", 0) == 0:
            object.__setattr__(self, f"n{block_name}s", len(getattr(self, block_name)))

    def _init_period_dtype(self, schema: type[Schema], naux: int, ncelldim: int) -> None:
        """Build period dtype; coerce SPD to recarrays; auto-set maxbound."""
        cols = schema.columns()
        has_keystring = any(col.role in ("keystring", "keystring_value") for col in cols)
        dtype_fields: list[tuple] = []
        for col in cols:
            if col.role == "cellid":
                dtype_fields.append((col.name, np.int64, (ncelldim,)))
            elif col.role in ("keystring", "keystring_value"):
                dtype_fields.append((col.name, np.object_))
            elif col.time_series:
                dtype_fields.append((col.name, np.object_))
            elif not col.optional:
                col_dt = (
                    self._DTYPE_MAP.get(col.dtype, np.float64)
                    if col.dtype
                    else self._DTYPE_MAP.get(col.dfn_type, np.float64)
                )
                dtype_fields.append((col.name, col_dt))
        if not has_keystring:
            for i in range(naux):
                dtype_fields.append((f"aux{i}", np.object_))
            if getattr(self, "boundnames", False):
                dtype_fields.append(("boundname", np.object_))
        self.period_dtype = np.dtype(dtype_fields)
        if self._stress_period_data is not None:  # type: ignore[attr-defined]
            object.__setattr__(
                self,
                "_stress_period_data",
                {
                    kper: self._coerce_to_recarray(rows, self.period_dtype)
                    for kper, rows in self._stress_period_data.items()  # type: ignore[attr-defined]
                },
            )
        spd = self._stress_period_data  # type: ignore[attr-defined]
        if spd and getattr(self, "maxbound", None) == 0:
            object.__setattr__(self, "maxbound", max(len(v) for v in spd.values()))

    def _broadcast_griddata(self, fields, dims: dict) -> None:
        """Expand scalar griddata defaults to full arrays when dims is supplied."""
        _par_data = getattr(self, "_par_data", None)
        _is_vertex = (
            _par_data is not None
            and "ncpl" in _par_data.dims
            and _par_data.dims.get("nrow", 0) == 0
        ) or ("ncpl" in dims and "nrow" not in dims)

        for f in fields:
            if f.metadata.get("dfn_block") != "griddata":
                continue
            shape_meta = f.metadata.get("shape")
            if not shape_meta:
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            _gd_dtype = self._DTYPE_MAP.get(f.metadata.get("dfn_type", "double"), np.float64)
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

    def _compute_ncelldim(self) -> int:
        """Return 2 for vertex grids, 3 for structured grids.

        Checks dims first; falls back to the parent's .dis type if dims is absent.
        Must be called from __attrs_post_init__ before xattree pops __dict__.
        """
        _dims = self.__dict__.get("dims") or {}
        if "ncpl" in _dims and "nrow" not in _dims:
            return 2
        if _dims:
            return 3
        _parent = self.__dict__.get("parent")
        if _parent is not None:
            _dis = getattr(_parent, "dis", None)
            if _dis is not None and type(_dis).__name__ == "Disv":
                return 2
        return 3

    @classmethod
    def load(  # type: ignore[override]
        cls,
        path: Path,
        dims: "dict[str, int] | None" = None,
        chunks: "int | str | None" = None,
    ):
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
        chunks :
            None   → eager numpy arrays.
            "auto" → one dask chunk per layer (griddata packages only).
            int    → approximate chunk size in elements.
        """
        from flopy4.mf6.codec.reader import load as _codec_load
        from flopy4.mf6.converter.ingress.structure import structure_component

        with open(path) as _f:
            _raw = _codec_load(_f)
        _pkg = structure_component(_raw, cls, dims=dims)

        # Pre-populate dimension cache so to_xarray()/to_dataarray() work
        # on standalone packages (not attached to a parent model).
        if dims:
            _pkg._dimension_cache.update(dims)

        if chunks is not None:
            try:
                import dask.array as _da
            except ImportError:
                raise ImportError(
                    "dask is required for chunked loading; install with 'pip install dask[array]'"
                ) from None
            import attrs as _attrs

            _nlay = (dims or {}).get("nlay", 1)
            _nodes = (dims or {}).get("nodes", _nlay)
            _ncpl = _nodes // _nlay if _nlay > 1 else _nodes
            _chunk_shape = (1, _ncpl) if chunks == "auto" else (max(1, int(chunks) // _ncpl), _ncpl)
            for _fld in _attrs.fields(cls):  # type: ignore[arg-type]
                if _fld.metadata.get("dfn_block") != "griddata":
                    continue
                _arr = getattr(_pkg, _fld.name)
                if _arr is None or not isinstance(_arr, np.ndarray):
                    continue
                setattr(
                    _pkg,
                    _fld.name,
                    _da.from_array(_arr.reshape(_nlay, _ncpl), chunks=_chunk_shape).reshape(-1),
                )

            # READARRAY period fields (G/A variants: Rcha, Chdg, etc.)
            # Shape is (nper, ncpl) for non-layered or (nper, nlay, ncpl) for layered.
            # Chunk 1 period at a time along the first axis.
            for _fld in _attrs.fields(cls):  # type: ignore[arg-type]
                if _fld.metadata.get("dfn_block") != "period":
                    continue
                if _fld.metadata.get("reader") != "readarray":
                    continue
                _arr = getattr(_pkg, _fld.name)
                if _arr is None or not isinstance(_arr, np.ndarray):
                    continue
                setattr(_pkg, _fld.name, _da.from_array(_arr, chunks=(1,) + _arr.shape[1:]))

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
            If True, only include fields with ``dfn_block`` metadata.
        """
        import attrs as _attrs

        try:
            all_fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            return super().to_dict(blocks=blocks, strict=strict)

        # Check if this is a codegen v2 class
        if not any(f.metadata.get("dfn_block") for f in all_fields):
            return super().to_dict(blocks=blocks, strict=strict)

        _exclude = {"name", "parent", "dims", "filename", "workspace", "strict"}
        result: dict = {}
        for f in all_fields:
            if f.name in _exclude or f.init is False:
                continue
            block = f.metadata.get("dfn_block")
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
            arr = _spd[kper]
            rows = {}
            for nm in arr.dtype.names or ():
                col = arr[nm]
                rows[nm] = [tuple(v) for v in col] if col.ndim > 1 else col.tolist()
            df = pd.DataFrame(rows)
            df.insert(0, "kper", kper)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def from_dataframe(self, df: "pd.DataFrame") -> None:
        """Set stress_period_data from a tidy DataFrame.

        The DataFrame must have a ``kper`` column and data columns matching
        the period schema (as produced by ``to_dataframe()``).
        """
        if df.empty:
            self.__dict__["_stress_period_data"] = {}
            return
        if "kper" not in df.columns:
            raise ValueError("DataFrame must have a 'kper' column")
        dtype = self.period_dtype
        spd: dict[int, np.recarray] = {}
        for kper, group in df.groupby("kper"):
            group = group.drop(columns=["kper"])
            n = len(group)
            arr = np.zeros(n, dtype=dtype)
            for col_name in dtype.names or ():
                if col_name in group.columns:
                    col_data = group[col_name].values
                    if dtype[col_name].shape:
                        # Multi-dim field (cellid) — stored as tuples in DataFrame
                        for i, val in enumerate(col_data):
                            arr[col_name][i] = val
                    else:
                        arr[col_name] = col_data
            spd[int(kper)] = arr.view(np.recarray)
        self.__dict__["_stress_period_data"] = spd

    @property
    def stress_period_data(self):  # type: ignore[override]
        """Stress period data as ``dict[int, np.recarray]`` keyed by 0-based kper."""
        return self.__dict__.get("_stress_period_data")

    @stress_period_data.setter  # type: ignore[attr-defined, no-redef]
    def stress_period_data(self, value) -> None:  # type: ignore[override]
        self.__dict__["_stress_period_data"] = value

    @staticmethod
    def _coerce_to_recarray(data, dtype: np.dtype) -> np.recarray:
        """Convert user-supplied list/dict data to a structured recarray.

        Accepts:
          - np.ndarray / np.recarray  → returned as-is
          - list of tuples/lists      → row-oriented, positional matching dtype.names
          - list of dicts             → row-oriented, named columns
          - dict of lists             → column-oriented {col_name: [values]}
        """
        if isinstance(data, np.ndarray):
            return data.view(np.recarray)
        if isinstance(data, dict):
            n = len(next(iter(data.values())))
            arr = np.zeros(n, dtype=dtype)
            for name, vals in data.items():
                arr[name] = vals
            return arr.view(np.recarray)
        rows = list(data)
        n = len(rows)
        arr = np.zeros(n, dtype=dtype)
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                for name, val in row.items():
                    arr[name][i] = val
            else:
                if not hasattr(row, "__getitem__"):
                    row = list(row)
                for j, name in enumerate(dtype.names or ()):  # type: ignore[arg-type]
                    arr[name][i] = row[j]
        return arr.view(np.recarray)

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
                if a.metadata.get("dfn_block") == _block and getattr(self, a.name) is not None
            }
            if data_vars:
                return xr.Dataset(data_vars)
        return super().to_xarray()  # type: ignore[return-value]
