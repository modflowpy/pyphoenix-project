from pathlib import Path
from typing import Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import dict_to_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Sto(Package):
    save_flows: bool = field(block="options", default=False)
    storagecoefficient: bool = field(block="options", default=False)
    ss_confined_only: bool = field(block="options", default=False)
    tvs_filerecord: Optional[Path] = field(block="options", default=None)
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
    dev_original_specific_storage: bool = field(block="options", default=False)
    dev_oldstorageformulation: bool = field(block="options", default=False)
    iconvert: NDArray[np.int32] = array(
        block="griddata",
        dims=("nodes",),
        default=0,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    ss: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=1e-5,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    sy: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=0.15,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
    storage: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=("nper",),
        default=None,
        converter=Converter(dict_to_array, takes_self=True, takes_field=True),
    )
