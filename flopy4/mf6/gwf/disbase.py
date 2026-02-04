from typing import Optional

from flopy.discretization.grid import Grid as LegacyGrid
from xattree import xattree

from flopy4.mf6.package import Package
from flopy4.mf6.spec import dim


@xattree
class DisBase(Package):
    nlay: Optional[int] = dim(
        coord="lay",
        scope="gwf",
        default=None,
        init=False,
    )
    nrow: Optional[int] = dim(
        coord="row",
        scope="gwf",
        default=None,
        init=False,
    )
    ncol: Optional[int] = dim(
        coord="col",
        scope="gwf",
        default=None,
        init=False,
    )
    ncpl: Optional[int] = dim(
        coord="icpl",
        scope="gwf",
        default=None,
        init=False,
    )
    nvert: int = dim(
        coord="vert",
        scope="gwf",
        default=None,
        init=False,
    )
    nodes: int = dim(
        coord="node",
        scope="gwf",
        default=None,
        init=False,
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

    def to_grid(self) -> LegacyGrid:
        pass
