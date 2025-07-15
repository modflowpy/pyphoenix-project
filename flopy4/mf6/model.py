from abc import ABC

from xattree import xattree

from flopy4.mf6.context import Context


@xattree
class Model(Context, ABC):
    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore
