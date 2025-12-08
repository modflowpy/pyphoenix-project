from abc import ABC

import xarray as xr
from xattree import xattree

from flopy4.mf6.context import Context


@xattree
class Model(Context, ABC):
    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore

    def to_xarray(self, format: str | None = None) -> xr.Dataset:
        from flopy4.mf6.converter.egress.dataset import xarray_flat

        dt = super().to_xarray()
        if format is not None:
            mesh_type = None
            if format.lower() == "layered":
                mesh_type = "layered"
            return xarray_flat(dt, mesh_type)
        else:
            return dt
