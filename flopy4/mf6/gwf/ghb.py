from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.constants import LENBOUNDNAME
from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.utils import to_path


@xattree
class Ghb(Package):
    multi_package: ClassVar[bool] = True
    auxiliary: Optional[list[str]] = array(
        block="options", default=None, longname="keyword to specify aux variables"
    )
    auxmultname: Optional[str] = field(
        block="options",
        default=None,
        longname="name of auxiliary variable for multiplier",
    )
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(
        block="options", default=False, longname="print input to listing file"
    )
    print_flows: bool = field(
        block="options", default=False, longname="print GHB flows to listing file"
    )
    save_flows: bool = field(
        block="options", default=False, longname="save GHB flows to budget file"
    )
    ts_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    dev_no_newton: bool = field(
        default=False, block="options", longname="turn off Newton for unconfined cells"
    )
    maxbound: Optional[int] = field(
        block="dimensions",
        default=None,
        init=False,
        longname="maximum number of general head boundaries",
    )
    bhead: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="value assigned to general head boundary",
    )
    cond: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="conductance",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="auxiliary variables",
    )
    boundname: Optional[NDArray[np.str_]] = array(
        dtype=f"<U{LENBOUNDNAME}",
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="general head boundary name",
    )
