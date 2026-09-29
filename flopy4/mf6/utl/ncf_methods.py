from typing import TYPE_CHECKING
from warnings import warn

from flopy4.mf6.enums import NetCDFFormat

if TYPE_CHECKING:
    from flopy4.mf6.utl.ncf import Ncf


class NcfMethods:
    """Methods for the generated `Ncf`; fields come from the DFN."""

    @classmethod
    def from_grid(  # type: ignore[misc]
        cls: type["Ncf"], grid, netcdf_format: NetCDFFormat, latlon: bool = False
    ) -> "Ncf":
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
