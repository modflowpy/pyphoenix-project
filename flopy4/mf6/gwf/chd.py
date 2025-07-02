from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converters import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    dev_no_newton: bool = field(default=False, block="options")
    maxbound: Optional[int] = field(block="dimensions", default=None, init=False)
    head: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
    )
    boundname: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
    )

    def __attrs_post_init__(self):
        # TODO set up on_setattr hooks for period block
        # arrays to update maxbound? for now do it here
        # in post init. but this only works when values
        # are set in the initializer, not when they are
        # set later.
        if self.head is None:
            maxhead = 0
        else:
            head = self.head if self.head.data.shape == self.head.shape else self.head.todense()
            maxhead = len(np.where(head != FILL_DNODATA))
        if self.aux is None:
            maxaux = 0
        else:
            aux = self.aux if self.aux.data.shape == self.aux.shape else self.aux.todense()
            maxaux = len(np.where(aux != FILL_DNODATA))
        if self.boundname is None:
            maxboundname = 0
        else:
            boundname = (
                self.boundname
                if self.boundname.data.shape == self.boundname.shape
                else self.boundname.todense()
            )
            maxboundname = len(np.where(boundname != ""))

        self.maxbound = max(maxhead, maxaux, maxboundname)
