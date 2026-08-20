from typing import ClassVar, Literal, Optional
from warnings import warn

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@attrs.define(kw_only=True, slots=False)
class Ncf(Package):
    dfn_name: ClassVar[str] = "utl-ncf"

    """NetCDF configuration subpackage (UTL-NCF).

    Two distinct use cases:

    - **Mesh (NETCDF_MESH2D)**: set ``wkt`` to embed CRS metadata in UGRID output.
    - **Structured (NETCDF_STRUCTURED)**: set ``wkt`` to embed CRS metadata in
      CF-structured output.  The ``latitude`` / ``longitude`` fields are available
      for explicit geographic coordinates when needed.
    """

    wkt: Optional[str] = field(default=None, block="options", optional=True)
    deflate: Optional[int] = field(default=None, block="options", optional=True)
    shuffle: bool = field(default=False, block="options", optional=True)
    chunk_time: Optional[int] = field(default=None, block="options", optional=True)
    chunk_face: Optional[int] = field(default=None, block="options", optional=True)
    chunk_z: Optional[int] = field(default=None, block="options", optional=True)
    chunk_y: Optional[int] = field(default=None, block="options", optional=True)
    chunk_x: Optional[int] = field(default=None, block="options", optional=True)
    modflow6_attr_off: bool = field(default=False, block="options", optional=True)
    ncpl: Optional[int] = field(default=None, block="dimensions", optional=True)
    latitude: Optional[NDArray[np.float64]] = field(
        default=None, block="griddata", shape=("ncpl",), layered=False
    )
    longitude: Optional[NDArray[np.float64]] = field(
        default=None, block="griddata", shape=("ncpl",), layered=False
    )

    @classmethod
    def from_grid(
        cls, grid, netcdf_format: NetCDFFormat, wkt_version: Literal[1, 2] = 1, latlon: bool = False
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
        latlon : bool
            When ``True``, derive cell-centre lat/lon arrays from the grid
            CRS and store them in the GRIDDATA block.
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
