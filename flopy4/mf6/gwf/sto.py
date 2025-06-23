from pathlib import Path
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from xattree import dict_to_array_converter

from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


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
        dims=("nnodes",),
        default=0,
        converter=dict_to_array_converter,
    )
    ss: NDArray[np.float64] = array(
        block="griddata",
        dims=("nnodes",),
        default=1e-5,
        converter=dict_to_array_converter,
    )
    sy: NDArray[np.float64] = array(
        block="griddata",
        dims=("nnodes",),
        default=0.15,
        converter=dict_to_array_converter,
    )
    steady_state: Optional[NDArray[np.bool_]] = array(
        block="period",
        dims=("nper",),
        default=None,
        converter=dict_to_array_converter,
        reader="urword",
    )
    transient: Optional[NDArray[np.bool_]] = array(
        block="period",
        dims=("nper",),
        default=None,
        converter=dict_to_array_converter,
        reader="urword",
    )
