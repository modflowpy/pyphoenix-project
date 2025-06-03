import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Ic(Package):
    strt: NDArray[np.floating] = array(
        block="packagedata",
        dims=("nnodes",),
        default=1.0,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
