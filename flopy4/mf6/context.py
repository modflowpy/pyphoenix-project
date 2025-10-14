from abc import ABC
from pathlib import Path

from modflow_devtools.misc import cd
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import MF6
from flopy4.mf6.spec import field


@xattree
class Context(Component, ABC):
    workspace: Path = field(default=None)

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

    def load(self, format=MF6):
        with cd(self.workspace):
            super().load(format=format)

    def write(self, format=MF6):
        with cd(self.workspace):
            super().write(format=format)
