from abc import ABC
from pathlib import Path
from typing import Any, Optional

from modflow_devtools.misc import cd
from pydantic import Field
from pydantic.dataclasses import dataclass

from flopy4.mf6.component import CFG, Component
from flopy4.mf6.constants import MF6
from flopy4.utils import to_path


@dataclass(config=CFG, kw_only=True)
class Context(Component, ABC):
    # `_workspace`/`workspace` mirrors `Component._parent`/`.parent`'s
    # private-field-plus-property pattern: pydantic has no per-field
    # `on_setattr=` hook (attrs' `update_child_attr`, ported into the
    # setter below), so the propagate-to-children side effect needs an
    # explicit property instead of a declarative field option.
    _workspace: Any = Field(default=None, alias="workspace", repr=False)

    @property
    def workspace(self) -> Optional[Path]:
        return self._workspace

    @workspace.setter
    def workspace(self, value) -> None:
        """Coerce `value` to a `Path` (attrs' `converter=to_path`, ported),
        then propagate it to every child that has its own `workspace`
        attribute (attrs' `on_setattr=update_child_attr`, ported)."""
        value = to_path(value)
        self._workspace = value
        for child in self._children.values():
            if hasattr(child, "workspace"):
                child.workspace = value

    def __post_init__(self):
        super().__post_init__()
        # By the time this runs, `super().__post_init__()` (Component's)
        # has already resolved `_parent`/`.parent` for both top-down and
        # bottom-up construction (see `Component._parent`'s docstring).
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
