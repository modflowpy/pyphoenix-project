from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.utils import to_path


@xattree
class Drng(Package):
    multi_package: ClassVar[bool] = True
    auxiliary: Optional[list[str]] = array(
        block="options", default=None, longname="keyword to specify aux variables"
    )
    auxmultname: Optional[str] = field(
        block="options",
        default=None,
        longname="name of auxiliary variable for multiplier",
    )
    print_input: bool = field(
        block="options", default=False, longname="print input to listing file"
    )
    print_flows: bool = field(
        block="options", default=False, longname="print calculated flows to listing file"
    )
    readarraygrid: bool = field(
        block="options", default=True, longname="use array-based grid input"
    )
    save_flows: bool = field(
        block="options", default=False, longname="save DRNG flows to budget file"
    )
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    export_array_netcdf: bool = field(
        block="options",
        default=False,
        longname="export array variables to netcdf output files.",
    )
    mover: bool = field(block="options", default=False)
    dev_cubic_scaling: bool = field(default=False, block="options", longname="cubic-scaling")
    maxbound: Optional[int] = field(
        block="dimensions",
        default=None,
        init=False,
        longname="maximum number of drain cells in any stress period",
    )
    elev: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        netcdf=True,
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="drain elevation",
    )
    cond: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        netcdf=True,
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="drain conductance",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "nodes",
        ),
        default=None,
        netcdf=True,
        on_setattr=update_maxbound,
        longname="drain auxiliary variable iaux",
    )
