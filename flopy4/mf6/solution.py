from abc import ABC
from typing import ClassVar

import attrs

from flopy4.mf6.package import Package


@attrs.define(kw_only=True, slots=False)
class Solution(Package, ABC):
    slntype: ClassVar[str] = "sln"
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        return f"solution.{self.slntype.lower()}"
