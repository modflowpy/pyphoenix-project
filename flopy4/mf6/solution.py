from abc import ABC
from typing import ClassVar

from pydantic import Field
from pydantic.dataclasses import dataclass

from flopy4.mf6.package import CFG, Package


@dataclass(config=CFG, kw_only=True)
class Solution(Package, ABC):
    slntype: ClassVar[str] = "sln"
    models: list[str] = Field(default_factory=list)

    def default_filename(self) -> str:
        return f"solution.{self.slntype.lower()}"
