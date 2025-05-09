from pathlib import Path
from typing import Optional

from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Exchange(Package):
    exgtype: type = field()
    exgfile: Path = field()
    exgmnamea: Optional[str] = field(default=None)
    exgmnameb: Optional[str] = field(default=None)
