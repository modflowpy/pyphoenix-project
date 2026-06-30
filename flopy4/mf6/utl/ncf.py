from typing import Literal, Optional
from warnings import warn

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.package import Package


@attrs.define(kw_only=True, slots=False)
class Ncf(Package):
    """NetCDF configuration subpackage (UTL-NCF).

    Two distinct use cases:

    - **Mesh (NETCDF_MESH2D)**: set ``wkt`` to embed CRS metadata in UGRID output.
    - **Structured (NETCDF_STRUCTURED)**: set ``wkt`` to embed CRS metadata in
      CF-structured output.  The ``latitude`` / ``longitude`` fields are available
      for explicit geographic coordinates when needed.
    """

    wkt: Optional[str] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "string", "optional": True},
    )
    deflate: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    shuffle: bool = attrs.field(
        default=False,
        metadata={"dfn_block": "options", "dfn_type": "keyword", "optional": True},
    )
    chunk_time: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    chunk_face: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    chunk_z: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    chunk_y: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    chunk_x: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "integer", "optional": True},
    )
    modflow6_attr_off: bool = attrs.field(
        default=False,
        metadata={"dfn_block": "options", "dfn_type": "keyword", "optional": True},
    )
    ncpl: Optional[int] = attrs.field(
        default=None,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer", "optional": True},
    )
    latitude: Optional[NDArray[np.float64]] = attrs.field(
        default=None,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("ncpl",),
            "layered": False,
        },
    )  # type: ignore[assignment]
    longitude: Optional[NDArray[np.float64]] = attrs.field(
        default=None,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("ncpl",),
            "layered": False,
        },
    )  # type: ignore[assignment]

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
