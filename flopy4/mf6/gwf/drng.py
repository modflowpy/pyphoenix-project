from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.utils import to_path


@xattree
class Drng(Package):
    multi_package: ClassVar[bool] = True
    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    readarraygrid: bool = field(block="options", default=True)
    save_flows: bool = field(block="options", default=False)
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    export_array_netcdf: bool = field(block="options", default=False)
    mover: bool = field(block="options", default=False)
    dev_cubic_scaling: bool = field(default=False, block="options")
    maxbound: Optional[int] = field(block="dimensions", default=None, init=False)
    elev: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        on_setattr=update_maxbound,
    )
    cond: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        on_setattr=update_maxbound,
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        on_setattr=update_maxbound,
    )
