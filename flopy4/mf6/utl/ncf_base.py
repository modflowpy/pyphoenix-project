from typing import Optional

from pydantic.dataclasses import dataclass

from flopy4.mf6.package import CFG, Package
from flopy4.mf6.spec import field


@dataclass(config=CFG, kw_only=True)
class NcfBase(Package):
    """Field-type overrides for the utl-ncf CRS options; see Ncf for the rest."""

    wkt: Optional[str] = field(default=None, block="options", optional=True)
    crs_wkt: Optional[str] = field(default=None, block="options", optional=True)
