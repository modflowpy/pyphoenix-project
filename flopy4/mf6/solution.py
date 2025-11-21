from abc import ABC
from typing import ClassVar

import attrs
from xattree import xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    ftype: ClassVar[str] = "sln"
    slntype: ClassVar[str] = "sln"  # Alias for ftype, kept for backward compatibility
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        return f"solution.{self.slntype.lower()}"
