from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.utils import to_path


@xattree
class Evta(Package):
    multi_package: ClassVar[bool] = True
    fixed_cell: bool = field(
        block="options",
        default=False,
        longname="if cell is dry do not apply recharge to underlying cell",
    )
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
        block="options", default=False, longname="print recharge rates to listing file"
    )
    readasarrays: bool = field(block="options", default=True, longname="use array-based input")
    save_flows: bool = field(
        block="options", default=False, longname="save CHD flows to budget file"
    )
    tas_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    obs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="fileout"
    )
    ievt: Optional[NDArray[np.int64]] = array(
        block="period",
        dims=(
            "nper",
            "ncpl",
        ),
        default=None,
        netcdf=True,
        longname="layer number for evapotranspiration",
    )
    surface: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "ncpl",
        ),
        default=None,
        netcdf=True,
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
        longname="evapotranspiration surface",
    )
    rate: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "ncpl",
        ),
        default=None,
        netcdf=True,
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
        longname="evapotranspiration rate",
    )
    depth: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "ncpl",
        ),
        default=None,
        netcdf=True,
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
        longname="extinction depth",
    )
    aux: Optional[NDArray[np.float64]] = array(
        block="period",
        dims=(
            "nper",
            "ncpl",
        ),
        default=None,
        netcdf=True,
        longname="recharge auxiliary variable iaux",
    )
