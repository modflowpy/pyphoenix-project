from abc import ABC
from typing import ClassVar

import attrs
from xattree import xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    slntype: ClassVar[str] = "sln"
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        return f"solution.{self.slntype.lower()}"
