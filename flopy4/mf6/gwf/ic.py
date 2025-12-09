import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree(kw_only=True)
class Ic(Package):
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
    strt: NDArray[np.float64] = array(
        block="griddata",
        dims=("nodes",),
        default=1.0,
        netcdf=True,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
