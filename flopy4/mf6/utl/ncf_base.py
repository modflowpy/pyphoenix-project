from typing import Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@attrs.define(kw_only=True, slots=False)
class NcfBase(Package):
    """Field-type overrides for the utl-ncf CRS options; see Ncf for the rest."""

    wkt: Optional[str] = field(default=None, block="options", optional=True)
    crs_wkt: Optional[str] = field(default=None, block="options", optional=True)
