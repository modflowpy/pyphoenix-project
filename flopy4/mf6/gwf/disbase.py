from pathlib import Path
from typing import Optional

from flopy.discretization.grid import Grid as LegacyGrid
from xattree import xattree

from flopy4.mf6.constants import MF6
from flopy4.mf6.package import Package
from flopy4.mf6.spec import dim
from flopy4.mf6.write_context import WriteContext


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

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        # If an Ncf child is attached, sync ncf6_filerecord from its filename
        # before writing so the OPTIONS block includes "NCF6 FILEIN <path>".
        # Explicit write because ncf is a plain attrs field (no xattree metadata),
        # so it is not in self.children.
        # TODO (codegen): subpackage tier should emit typed ncf child fields,
        # removing this override.
        ncf = getattr(self, "ncf", None)
        if ncf is not None:
            if getattr(self, "ncf6_filerecord", None) is None and ncf.filename is not None:
                setattr(self, "ncf6_filerecord", Path(Path(ncf.filename).name))
        super().write(format=format, context=context)
        if ncf is not None:
            # NCF lat/lon coordinate arrays require full float64 precision.
            ncf.write(format=format, context=WriteContext(float_precision=15))

    def to_grid(self) -> LegacyGrid:
        pass
