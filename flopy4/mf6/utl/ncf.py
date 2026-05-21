from typing import Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field


@xattree(kw_only=True)
class Ncf(Package):
    """NetCDF configuration subpackage (UTL-NCF).

    Two distinct use cases:

    - **Mesh (NETCDF_MESH2D)**: set ``wkt`` to embed CRS metadata in UGRID output.
      Use :meth:`from_grid_wkt` to derive the WKT string from a grid's CRS.
    - **Structured (NETCDF_STRUCTURED)**: set ``latitude`` / ``longitude`` to
      provide explicit geographic cell-centre coordinates for CF output.
      Use :meth:`from_grid_latlon` to derive them from a grid's CRS.
      ``wkt`` is ignored when lat/lon arrays are present.
    """

    # lenbigline in the DFN is a Fortran string-length artifact; Python uses plain str.
    wkt: Optional[str] = field(
        block="options",
        default=None,
        longname="crs well-known text (wkt) string",
    )
    # Compression: deflate activates per-variable compression; shuffle only has
    # effect when deflate is also set.
    deflate: Optional[int] = field(
        block="options", default=None, longname="variable compression deflate level"
    )
    shuffle: bool = field(block="options", default=False)
    # Chunking: chunk_time is shared. Pair it with chunk_face for NETCDF_MESH2D,
    # or with chunk_z/chunk_y/chunk_x for NETCDF_STRUCTURED.
    chunk_time: Optional[int] = field(
        block="options", default=None, longname="chunking parameter for the time dimension"
    )
    chunk_face: Optional[int] = field(
        block="options", default=None, longname="chunking parameter for the mesh face dimension"
    )
    chunk_z: Optional[int] = field(
        block="options", default=None, longname="chunking parameter for structured z"
    )
    chunk_y: Optional[int] = field(
        block="options", default=None, longname="chunking parameter for structured y"
    )
    chunk_x: Optional[int] = field(
        block="options", default=None, longname="chunking parameter for structured x"
    )
    modflow6_attr_off: bool = field(block="options", default=False)
    ncpl: Optional[int] = dim(
        block="dimensions", coord=False, default=None, longname="number of cells in layer"
    )
    latitude: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("ncpl",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell center latitude",
    )
    longitude: Optional[NDArray[np.float64]] = array(
        block="griddata",
        dims=("ncpl",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell center longitude",
    )

    @classmethod
    def from_grid_wkt(cls, grid) -> "Ncf":
        """Build Ncf with a WKT1_GDAL CRS string; applies to both mesh and structured NetCDF."""
        from pyproj import CRS
        from pyproj.enums import WktVersion

        if grid.crs is None:
            raise ValueError("Grid has no CRS; set grid.crs before calling from_grid_wkt().")
        wkt = CRS.from_user_input(grid.crs).to_wkt(WktVersion.WKT1_GDAL)
        return cls(wkt=wkt)

    @classmethod
    def from_grid_latlon(cls, grid) -> "Ncf":
        """Build Ncf with lat/lon cell-centre arrays for CF-structured NetCDF output."""
        lats, lons = grid.latlon()
        if lats is None:
            raise ValueError(
                "Grid has no CRS or latlon() failed; cannot derive lat/lon coordinates."
            )
        return cls(ncpl=len(lats), latitude=lats, longitude=lons)
