import numpy as np
from numpy.typing import NDArray
from xattree import dict_to_array_converter, xattree

from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Ic(Package):
    strt: NDArray[np.float64] = array(
        block="packagedata",
        dims=("nnodes",),
        default=1.0,
        converter=dict_to_array_converter,
    )
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
