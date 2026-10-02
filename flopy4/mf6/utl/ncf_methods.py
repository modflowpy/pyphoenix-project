from typing import TYPE_CHECKING, Optional
from warnings import warn

import attrs

from flopy4.mf6.constants import MF6
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.write_context import WriteContext

if TYPE_CHECKING:
    from flopy4.mf6.utl.ncf import Ncf


class NcfMethods:
    """Methods for the generated `Ncf`; fields come from the DFN."""

    def write(  # type: ignore[misc]
        self: "Ncf", format: str = MF6, context: Optional[WriteContext] = None
    ) -> None:
        """Write the NCF file. Latitude/longitude coordinates are always
        written at full float64 precision, even if the context asks for
        rounding."""
        context = attrs.evolve(context or WriteContext.current(), float_precision=None)
        super().write(format=format, context=context)  # type: ignore[misc]

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
