from abc import ABC
from pathlib import Path
from typing import Optional

import attrs
from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    slntype: Optional[str] = field(default=None)  # type: ignore
    slnfname: Optional[Path] = field(default=None)  # type: ignore
    models: list[str] = attrs.field(default=attrs.Factory(list))
    mxiter: int = field(default=1)

    def default_filename(self) -> str:
        name = self.slntype.lower() if self.slntype else "sln"
        cls_name = self.__class__.__name__.lower()
        return self.slnfname if self.slnfname else f"{cls_name}.{name}"
