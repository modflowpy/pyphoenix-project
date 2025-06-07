from abc import ABC

from xattree import xattree

from flopy4.mf6.component import Component


@xattree
class Package(Component, ABC):
    """Base class for MF6 packages."""

    def default_filename(self) -> str:
        name = self.parent.name if self.parent else self.name  # type: ignore
        cls_name = self.__class__.__name__.lower()
        return f"{name}.{cls_name}"
