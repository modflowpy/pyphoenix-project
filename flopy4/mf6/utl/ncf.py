from typing import ClassVar, Optional
from warnings import warn

import numpy as np
from numpy.typing import NDArray
from pydantic.dataclasses import dataclass

from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.spec import field
from flopy4.mf6.utl.ncf_base import CFG, NcfBase


@dataclass(config=CFG, kw_only=True)
class Ncf(NcfBase):
    dfn_name: ClassVar[str] = "utl-ncf"

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
    def from_grid(cls, grid, netcdf_format: NetCDFFormat, latlon: bool = False) -> "Ncf":
        """Build an Ncf from a grid's CRS.

        Sets both ``wkt`` (WKT1) and ``crs_wkt`` (WKT2). If ``latlon=True``,
        derives cell-centre latitude/longitude arrays instead and leaves
        both WKT attributes unset. Returns an empty ``Ncf`` and emits a
        ``UserWarning`` if the grid has no CRS.
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
        crs = CRS.from_user_input(grid.crs)
        return cls(
            wkt=crs.to_wkt(WktVersion.WKT1_GDAL),
            crs_wkt=crs.to_wkt(WktVersion.WKT2_2019),
        )
