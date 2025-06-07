from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    @define(slots=False)
    class PeriodData:
        head: float = field()
        aux: Optional[tuple[np.floating]] = field(default=None)
        boundname: Optional[str] = field(default=None)

    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    dev_no_newton: bool = field(default=False, metadata={"block": "options"})
    maxbound: Optional[int] = field(block="dimensions", default=None)
    perioddata: Optional[NDArray[np.object_]] = array(
        PeriodData,
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )

    def __attrs_post_init__(self):
        # TODO set up on_setattr hooks for period block
        # arrays to update maxbound? for now do it here
        # in post init. but this only works when values
        # are set in the initializer, not when they are
        # set later.
        self.maxbound = len(np.where(self.perioddata != None)) if self.perioddata is not None else 0  # noqa: E711
