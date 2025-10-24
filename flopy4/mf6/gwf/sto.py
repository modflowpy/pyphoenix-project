from pathlib import Path
from typing import Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field, path
from flopy4.utils import to_path


@xattree
class Sto(Package):
    save_flows: bool = field(block="options", default=False)
    storagecoefficient: bool = field(block="options", default=False)
    ss_confined_only: bool = field(block="options", default=False)
    tvs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
    dev_original_specific_storage: bool = field(block="options", default=False)
    dev_oldstorageformulation: bool = field(block="options", default=False)
    iconvert: NDArray[np.int64] = array(
        block="griddata",
        dims=("nodes",),
        default=0,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    ss: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=1e-5,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    sy: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=0.15,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    steady_state: Optional[NDArray[np.bool_]] = array(
        block="period",
        dims=("nper",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    transient: Optional[NDArray[np.bool_]] = array(
        block="period",
        dims=("nper",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
