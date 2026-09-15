from abc import ABC
from pathlib import Path

import attrs
from modflow_devtools.misc import cd

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

    for child in instance._children.values():
        if hasattr(child, attribute.name):
            setattr(child, attribute.name, new_value)

    return new_value


@attrs.define(kw_only=True, slots=False)
class Context(Component, ABC):
    workspace: Path = field(default=None, converter=to_path, on_setattr=update_child_attr)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # By the time this runs, `super().__attrs_post_init__()`
        # (Component's) has already resolved `_parent`/`.parent` for both
        # top-down and bottom-up construction (see `Component._parent`'s
        # docstring).
        if self.workspace is None:
            self.workspace = (
                self._parent.workspace
                if self._parent and hasattr(self._parent, "workspace")
                else Path.cwd()
            )

    @property
    def path(self) -> Path:
        self.filename = self.filename or self.default_filename()
        return self.workspace / self.filename

    @classmethod
    def load(cls, path, format=MF6, name=None):
        """
        Load a context from a file.

        `name`, if given, overrides the default auto-assigned name.
        """
        with cd(Path(path).parent):
            return cls._load(path, format=format, name=name)

    def write(self, format=MF6, context=None):
        with cd(self.workspace):
            super().write(format=format, context=context)

    def to_xarray(self):
        """DataTree for this context and its full child hierarchy.

        Built directly from live attribute values via flopy4.attrs_xarray's
        attrs_to_datatree. Each child node, leaf packages included, is
        built from its own fields directly, so griddata appears natively.
        """
        from flopy4.attrs_xarray import attrs_to_datatree

        return attrs_to_datatree(self)
