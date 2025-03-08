from pathlib import Path
from typing import Optional

from attrs import define
from xattree import field

from flopy4.mf6.package import Package


@define
class Exchange(Package):
    exgtype: type = field()
    exgfile: Path = field()
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)
