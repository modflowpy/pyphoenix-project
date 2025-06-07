from abc import ABC

from xattree import xattree

from flopy4.mf6.component import Component


@xattree
class Model(Component, ABC):
    """Base class for MF6 models."""

    def default_filename(self) -> str:
        return f"{self.name}.nam"  # type: ignore
