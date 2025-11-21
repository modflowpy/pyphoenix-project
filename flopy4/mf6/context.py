from abc import ABC
from pathlib import Path

from modflow_devtools.misc import cd
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import MF6
from flopy4.mf6.spec import field
from flopy4.utils import to_path


def update_child_attr(instance, attribute, new_value):
    """
    Generalized function to update child attribute (e.g. workspace).

    Args:
        instance: The model instance
        attribute: The attribute being set (from attrs on_setattr)
        new_value: The new value being set

    Returns:
        The new_value (unchanged)
    """

    for child in instance.children.values():  # type: ignore
        if hasattr(child, attribute.name):
            setattr(child, attribute.name, new_value)

    return new_value


@xattree
class Context(Component, ABC):
    workspace: Path = field(default=None, converter=to_path, on_setattr=update_child_attr)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if self.workspace is None:
            self.workspace = (
                self.parent.workspace
                if self.parent and hasattr(self.parent, "workspace")
                else Path.cwd()
            )

    @property
    def path(self) -> Path:
        self.filename = self.filename or self.default_filename()
        return self.workspace / self.filename

    @classmethod
    def load(cls, path, format=MF6):
        """
        Load the context component from the given path.

        Children are loaded via binding resolution during structuring,
        with the workspace as the current working directory so that
        relative paths in child files resolve correctly.
        """
        # Load the instance (binding resolution in structure() handles children)
        instance = cls._load(path, format=format)

        return instance

    def write(self, format=MF6, context=None):
        with cd(self.workspace):
            super().write(format=format, context=context)

    def to_xarray(self):
        return self.data  # type: ignore
