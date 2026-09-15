from typing import Optional
from warnings import warn

import attrs

from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@attrs.define(kw_only=True, slots=False)
class NcfBase(Package):
    """NetCDF configuration subpackage (UTL-NCF).

    Set ``wkt``/``crs_wkt`` to embed a CRS: ``wkt`` is WKT1 (GDAL-based
    tools), ``crs_wkt`` is WKT2 (CF-required). Applies to both mesh
    (NETCDF_MESH2D) and structured (NETCDF_STRUCTURED) output. The
    ``latitude``/``longitude`` fields are an alternative, explicit
    geographic-coordinate option for structured output.
    """

    wkt: Optional[str] = field(default=None, block="options", optional=True)
    crs_wkt: Optional[str] = field(default=None, block="options", optional=True)

    @classmethod
    def from_grid(cls, grid, netcdf_format: NetCDFFormat, latlon: bool = False) -> "NcfBase":
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
