from pathlib import Path
from typing import Optional

import attrs
import numpy as np
from flopy.discretization.grid import Grid as LegacyGrid

from flopy4.mf6.constants import MF6
from flopy4.mf6.package import Package
from flopy4.mf6.write_context import WriteContext


@attrs.define(kw_only=True, slots=False)
class DisBase(Package):
    # Derived dimensions — not read/written by the codec, set by subclass post_init.
    nlay: Optional[int] = attrs.field(default=None, init=False)
    nrow: Optional[int] = attrs.field(default=None, init=False)
    ncol: Optional[int] = attrs.field(default=None, init=False)
    ncpl: Optional[int] = attrs.field(default=None, init=False)
    nvert: Optional[int] = attrs.field(default=None, init=False)
    nodes: Optional[int] = attrs.field(default=None, init=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

    def _coerce_griddata(self) -> None:
        """Coerce griddata fields: list→ndarray, per-layer expansion, flatten.

        Must be called after derived dimensions (nodes, ncpl) are set and
        before _broadcast_griddata / super().__attrs_post_init__().
        """
        import attrs as _attrs

        fields = _attrs.fields(type(self))
        dims = self.get_dims()
        ncpl = dims.get("ncpl", 0)
        nlay = dims.get("nlay", 1)
        for f in fields:
            if f.metadata.get("dfn_block") != "griddata":
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            dtype = self._DTYPE_MAP.get(f.metadata.get("dfn_type", "double"), np.float64)
            if isinstance(val, (list, tuple)):
                val = np.asarray(val, dtype=dtype)
                self.__dict__[f.name] = val
            if isinstance(val, np.ndarray):
                if f.metadata.get("layered") and val.size == nlay and nlay > 0 and ncpl > 0:
                    self.__dict__[f.name] = np.repeat(val, ncpl).astype(dtype)
                elif val.ndim > 1:
                    self.__dict__[f.name] = val.ravel()
        self._broadcast_griddata(fields, dims)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        # If an Ncf child is attached, sync ncf6_filerecord from its filename
        # before writing so the OPTIONS block includes "NCF6 FILEIN <path>".
        ncf = getattr(self, "ncf", None)
        if ncf is not None:
            if getattr(self, "ncf6_filerecord", None) is None and ncf.filename is not None:
                setattr(self, "ncf6_filerecord", Path(Path(ncf.filename).name))
        super().write(format=format, context=context)
        if ncf is not None:
            # NCF lat/lon coordinate arrays require full float64 precision.
            ncf.write(format=format, context=WriteContext(float_precision=15))

    def to_grid(self) -> LegacyGrid:
        pass

    def get_dims(self) -> dict[str, int]:
        """Return grid dimensions. Implemented by subclasses."""
        return {}
