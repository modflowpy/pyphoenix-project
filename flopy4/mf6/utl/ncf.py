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
    - **Structured (NETCDF_STRUCTURED)**: set ``wkt`` to embed CRS metadata in
      CF-structured output.  Use :meth:`from_grid` with ``NetCDFFormat.STRUCTURED``
      to derive the WKT string from a grid's CRS.  The ``latitude`` / ``longitude``
      fields are available for explicit geographic coordinates when needed.
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
        latlon: bool = False,
    ) -> "Ncf":
        """Build an Ncf configured for the given NetCDF output format.

        By default embeds a WKT CRS string (``wkt=``) for both
        ``LAYERED_MESH`` and ``STRUCTURED`` formats.  Pass ``latlon=True``
        to write cell-centre latitude/longitude arrays instead; this is
        mutually exclusive with ``wkt`` — when ``latlon=True`` no WKT is set.

        If the grid has no CRS the method returns an unconfigured ``Ncf()``
        and emits a ``UserWarning``.

        Parameters
        ----------
        wkt_version : {1, 2}
            WKT version for the CRS string (ignored when ``latlon=True``).
            1 (default) writes WKT1_GDAL; 2 writes WKT2_2019.
        latlon : bool
            When ``True``, derive cell-centre lat/lon arrays from the grid
            CRS and store them in the GRIDDATA block.  When ``False``
            (default), embed a WKT string in the OPTIONS block instead.
        """
        if latlon:
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
