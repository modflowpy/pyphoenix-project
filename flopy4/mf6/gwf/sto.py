from pathlib import Path
from typing import Optional

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
class Sto(Package):
    save_flows: bool = field(block="options", default=False, longname="keyword to save NPF flows")
    storagecoefficient: bool = field(
        block="options",
        default=False,
        longname="keyword to indicate SS is read as storage coefficient",
    )
    ss_confined_only: bool = field(
        block="options",
        default=False,
        longname="keyword to indicate specific storage only applied under confined conditions",
    )
    tvs_filerecord: Optional[Path] = path(
        block="options", default=None, converter=to_path, inout="filein"
    )
    export_array_ascii: bool = field(
        block="options",
        default=False,
        longname="export array variables to layered ascii files.",
    )
    export_array_netcdf: bool = field(
        block="options",
        default=False,
        longname="export array variables to netcdf output files.",
    )
    dev_original_specific_storage: bool = field(
        block="options",
        default=False,
        longname="development option for original specific storage",
    )
    dev_oldstorageformulation: bool = field(
        block="options",
        default=False,
        longname="development option flag for old storage formulation",
    )
    iconvert: NDArray[np.int64] = array(
        block="griddata",
        dims=("nodes",),
        default=0,
        netcdf=True,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="convertible indicator",
    )
    ss: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        netcdf=True,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="specific storage",
    )
    sy: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=None,
        netcdf=True,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="specific yield",
    )
    storage: Optional[NDArray[np.str_]] = array(
        dtype=f"<U{LENBOUNDNAME}",
        block="period",
        dims=("nper",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        on_setattr=update_maxbound,
        longname="storage type",
    )
