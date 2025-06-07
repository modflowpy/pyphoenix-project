from abc import ABC
from pathlib import Path

from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.spec import field


@xattree
class Context(Component, ABC):
    """Base class for MF6 components associated with a workspace directory on disk."""

    workspace: Path = field(default=None)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if self.workspace is None:
            self.workspace = Path.cwd()

    @property
    def path(self) -> Path:
        return self.workspace / self.filename
