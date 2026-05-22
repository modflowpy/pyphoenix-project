from typing import Literal, Optional
from warnings import warn

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field


@xattree(kw_only=True)
class Ncf(Package):
    """NetCDF configuration subpackage (UTL-NCF).

    Two distinct use cases:

    - **Mesh (NETCDF_MESH2D)**: set ``wkt`` to embed CRS metadata in UGRID output.
      Use :meth:`from_grid` with ``NetCDFFormat.LAYERED_MESH`` to derive the WKT
      string from a grid's CRS.
    - **Structured (NETCDF_STRUCTURED)**: set ``latitude`` / ``longitude`` to
      provide explicit geographic cell-centre coordinates for CF output.
      Use :meth:`from_grid` with ``NetCDFFormat.STRUCTURED`` to derive them from
      a grid's CRS.  ``wkt`` is ignored when lat/lon arrays are present.
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
    def from_grid(
        cls,
        grid,
        netcdf_format: NetCDFFormat,
        wkt_version: Literal[1, 2] = 1,
    ) -> "Ncf":
        """Build an Ncf configured for the given NetCDF output format.

        For ``NetCDFFormat.LAYERED_MESH``: embeds a WKT CRS string in
        the OPTIONS block so MODFLOW can label the coordinate system in the
        UGRID output metadata.

        For ``NetCDFFormat.STRUCTURED``: derives lat/lon cell-centre arrays
        from the grid's CRS and stores them in the GRIDDATA block so the CF
        output has explicit geographic coordinate axes.

        In either case, if the grid has no CRS the method returns an
        unconfigured ``Ncf()`` and emits a ``UserWarning``.

        Parameters
        ----------
        wkt_version : {1, 2}
            WKT version for the CRS string in LAYERED_MESH format.
            1 (default) writes WKT1_GDAL; 2 writes WKT2_2019.
        """
        if netcdf_format == NetCDFFormat.LAYERED_MESH:
            from pyproj import CRS
            from pyproj.enums import WktVersion

            if grid.crs is None:
                warn(
                    "Grid has no CRS; Ncf will have no WKT. "
                    "Set grid.crs before calling Ncf.from_grid().",
                    UserWarning,
                    stacklevel=2,
                )
                return cls()
            _wkt_version = WktVersion.WKT1_GDAL if wkt_version == 1 else WktVersion.WKT2_2019
            wkt = CRS.from_user_input(grid.crs).to_wkt(_wkt_version)
            return cls(wkt=wkt)
        else:
            lats, lons = grid.latlon()
            if lats is None:
                warn(
                    "Grid has no CRS or latlon() failed; Ncf will have no lat/lon. "
                    "Set grid.crs before calling Ncf.from_grid().",
                    UserWarning,
                    stacklevel=2,
                )
                return cls()
            return cls(ncpl=len(lats), latitude=lats, longitude=lons)
