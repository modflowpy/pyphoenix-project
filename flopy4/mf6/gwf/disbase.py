from typing import Optional

import attrs
import numpy as np
from flopy.discretization.grid import Grid as LegacyGrid

from flopy4.mf6.package import _DTYPE_MAP as _PKG_DTYPE_MAP
from flopy4.mf6.package import Package
from flopy4.mf6.spec import to_field_type


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
            if f.metadata.get("block") != "griddata":
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            dtype = _PKG_DTYPE_MAP.get(to_field_type(f.type), np.float64)
            if isinstance(val, (list, tuple)):
                val = np.asarray(val, dtype=dtype)
                self.__dict__[f.name] = val
            if isinstance(val, np.ndarray):
                if f.metadata.get("layered") and val.size == nlay and nlay > 0 and ncpl > 0:
                    self.__dict__[f.name] = np.repeat(val, ncpl).astype(dtype)
                elif val.ndim > 1:
                    self.__dict__[f.name] = val.ravel()
        self._broadcast_griddata(fields, dims)

    def to_grid(self) -> LegacyGrid:
        pass

    def get_dims(self) -> dict[str, int]:
        """Return grid dimensions. Implemented by subclasses."""
        return {}
