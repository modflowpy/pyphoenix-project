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
        Load the context component and children.

        Children are loaded relative to the parent's workspace directory,
        so their paths are resolved within that workspace.
        """
        # Load the instance first
        instance = cls._load(path, format=format)

        # Load children within the workspace context
        with cd(instance.workspace):
            for child in instance.children.values():  # type: ignore
                child.__class__.load(child.path, format=format)

    def write(self, format=MF6, context=None):
        with cd(self.workspace):
            super().write(format=format, context=context)

    def to_xarray(self):
        """DataTree for this context, with codegen v2 child packages populated.

        The raw xattree DataTree has empty dataset nodes for codegen v2 packages
        (those decorated with @attrs.define rather than @xattree) because they
        bypass xattree's __setattr__ hook.  This override walks the context's
        children, finds any codegen v2 packages that have griddata fields, calls
        their generated to_xarray(), and merges the result into the corresponding
        node in a deep copy of the tree so that gwf.to_xarray()["npf"]["k"]
        returns the expected DataArray.
        """
        import attrs as _attrs

        tree = self.data  # type: ignore
        patches: dict = {}
        try:
            for name, child in (self.children or {}).items():  # type: ignore
                try:
                    _fields = _attrs.fields(type(child))
                except _attrs.exceptions.NotAnAttrsClassError:
                    continue
                if not any(f.metadata.get("dfn_block") == "griddata" for f in _fields):
                    continue
                try:
                    ds = child.to_xarray()
                    if ds is not None and hasattr(ds, "data_vars") and ds.data_vars:
                        patches[name] = ds
                except Exception:
                    pass
        except Exception:
            pass

        if not patches:
            return tree

        result = tree.copy(deep=True)
        for name, ds in patches.items():
            try:
                result[name].update(ds)
            except Exception:
                pass
        return result
