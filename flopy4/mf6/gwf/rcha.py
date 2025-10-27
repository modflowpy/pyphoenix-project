from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.utils import to_path


@xattree
class Rcha(Package):
    multi_package: ClassVar[bool] = True
    fixed_cell: bool = field(block="options", default=False)
    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    irch: Optional[NDArray[np.int64]] = array(
        block="period",
        dims=(
            "nper",
            # "ncpl",
            "nrow",
            "ncol",
        ),
        default=1,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    recharge: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            # "ncpl",
            "nrow",
            "ncol",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            # "ncpl",
            "nrow",
            "ncol",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
