from abc import ABC
from pathlib import Path

import attrs

from flopy4.mf6.component import Component
from flopy4.mf6.spec import field
from flopy4.utils import to_path


@attrs.define(kw_only=True, slots=False)
class Context(Component, ABC):
    workspace: Path = field(default=None, converter=to_path)
    """The directory the context's files are written to and read from.
    A model under a simulation has the simulation's (see
    `Model.workspace`)."""

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if self.workspace is None:
            self.workspace = Path.cwd()

    @property
    def path(self) -> Path:
        self.filename = self.filename or Path(self.default_filename())
        return self.workspace / self.filename

    def to_xarray(self):
        """DataTree for this context and its full child hierarchy.

        Built directly from live attribute values via flopy4.attrs_xarray's
        attrs_to_datatree. Each child node, leaf packages included, is
        built from its own fields directly, so griddata appears natively.
        """
        from flopy4.attrs_xarray import attrs_to_datatree

        return attrs_to_datatree(self)
