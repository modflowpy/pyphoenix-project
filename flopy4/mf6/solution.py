from abc import ABC
from pathlib import Path
from typing import ClassVar, Optional

import attrs
from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    slntype: ClassVar[str] = "sln"

    slnfname: Optional[Path] = field(default=None)  # type: ignore
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        return str(self.slnfname) if self.slnfname else f"solution.{self.slntype.lower()}"
