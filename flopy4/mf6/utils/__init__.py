# Import submodules to make them accessible via flopy4.mf6.utils.*
from flopy4.mf6.utils import grid, time

from .cbc_reader import open_cbc
from .heads_reader import open_hds
from .netcdf_postprocess import postprocess_mesh_nc, postprocess_structured_nc

__all__ = [
    "open_hds",
    "open_cbc",
    "postprocess_mesh_nc",
    "postprocess_structured_nc",
    "grid",
    "time",
]
