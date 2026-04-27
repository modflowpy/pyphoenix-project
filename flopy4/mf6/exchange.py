from abc import ABC
from pathlib import Path
from typing import Optional

from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Exchange(Package, ABC):
    exgtype: Optional[type] = field(default=None)  # type: ignore
    exgfile: Optional[Path] = field(default=None)  # type: ignore
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)

    def default_filename(self) -> str:
        return f"{self.name}.exg"  # type: ignore


@xattree
class GwfGwt(Exchange):
    """GWF-GWT flow-transport exchange (declares coupling in mfsim.nam)."""


@xattree
class GwfGwe(Exchange):
    """GWF-GWE flow-energy exchange (declares coupling in mfsim.nam)."""
