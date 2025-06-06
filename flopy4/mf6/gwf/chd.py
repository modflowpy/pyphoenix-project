from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    @define(slots=False)
    class Steps:
        all: bool = field()
        first: bool = field()
        last: bool = field()
        steps: list[int] = field()
        frequency: int = field()

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
    head: Optional[NDArray[np.floating]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    aux: Optional[NDArray[np.floating]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    boundname: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    steps: Optional[NDArray[np.object_]] = array(
        Steps,
        block="period",
        dims=("nper", "nnodes"),
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
        maxhead = len(np.where(self.head != FILL_DNODATA)) if self.head is not None else 0
        maxaux = len(np.where(self.aux != FILL_DNODATA)) if self.aux is not None else 0
        maxboundname = len(np.where(self.boundname != "")) if self.boundname is not None else 0
        # maxsteps = len(np.where(self.steps != None)) if self.steps is not None else 0
        self.maxbound = max(maxhead, maxaux, maxboundname)
