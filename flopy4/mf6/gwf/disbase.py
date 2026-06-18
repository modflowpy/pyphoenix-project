from pathlib import Path
from typing import Optional

import attrs
from flopy.discretization.grid import Grid as LegacyGrid

from flopy4.mf6.constants import MF6
from flopy4.mf6.package import Package
from flopy4.mf6.write_context import WriteContext


@attrs.define(kw_only=True, slots=False)
class DisBase(Package):
    # Derived dimensions — not read/written by the codec, set by subclass post_init.
    nlay: Optional[int] = attrs.field(default=None, init=False)
    nrow: Optional[int] = attrs.field(default=None, init=False)
    ncol: Optional[int] = attrs.field(default=None, init=False)
    ncpl: Optional[int] = attrs.field(default=None, init=False)
    nvert: Optional[int] = attrs.field(default=None, init=False)
    nodes: Optional[int] = attrs.field(default=None, init=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        # If an Ncf child is attached, sync ncf6_filerecord from its filename
        # before writing so the OPTIONS block includes "NCF6 FILEIN <path>".
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
