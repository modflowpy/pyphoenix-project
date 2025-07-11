from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.attr_hooks import update_maxbound
from flopy4.mf6.converters import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Rch(Package):
    multi_package: ClassVar[bool] = True
    fixed_cell: bool = field(block="options", default=False)
    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    maxbound: Optional[int] = field(block="dimensions", default=None, init=False)
    recharge: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
        reader="urword",
        on_setattr=update_maxbound,
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
        on_setattr=update_maxbound,
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
        on_setattr=update_maxbound,
    )

    def __attrs_post_init__(self):
        if self.recharge is not None or self.aux is not None or self.boundname is not None:
            update_maxbound(self, None, None)
