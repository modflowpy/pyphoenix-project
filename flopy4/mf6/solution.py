from abc import ABC
from pathlib import Path
from typing import Optional

import attrs
from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    slnfname: Optional[Path] = field(default=None)  # type: ignore
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        ftype = self.slntype.lower() if self.slntype else "sln"
        return str(self.slnfname) if self.slnfname else f"solution.{ftype}"
