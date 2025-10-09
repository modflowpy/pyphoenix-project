from abc import ABC

import attrs
from xattree import xattree

from flopy4.mf6.package import Package


@xattree
class Solution(Package, ABC):
    models: list[str] = attrs.field(default=attrs.Factory(list))

    def default_filename(self) -> str:
        return f"{self.name}.ims"  # type: ignore
