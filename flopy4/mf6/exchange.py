from abc import ABC
from pathlib import Path
from typing import ClassVar, Optional

import attrs

from flopy4.mf6.package import Package
from flopy4.mf6.spec import field


@attrs.define(kw_only=True, slots=False)
class Exchange(Package, ABC):
    exgtype: Optional[type] = field(default=None)  # type: ignore
    exgfile: Optional[Path] = field(default=None)  # type: ignore
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)

    def default_filename(self) -> str:
        return f"{self.name}.exg"  # type: ignore


@attrs.define(kw_only=True, slots=False)
class GwfGwt(Exchange):
    """GWF-GWT flow-transport exchange (declares coupling in mfsim.nam)."""

    dfn_name: ClassVar[str] = "exg-gwfgwt"


@attrs.define(kw_only=True, slots=False)
class GwfGwe(Exchange):
    """GWF-GWE flow-energy exchange (declares coupling in mfsim.nam)."""

    dfn_name: ClassVar[str] = "exg-gwfgwe"
