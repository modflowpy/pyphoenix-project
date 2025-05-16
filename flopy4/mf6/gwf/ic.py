import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.decorators import array, field
from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package


@xattree
class Ic(Package):
    strt: NDArray[np.floating] = array(
        block="packagedata",
        dims=("nnodes",),
        default=1.0,
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    export_array_ascii: bool = field(block="options", default=False)
    export_array_netcdf: bool = field(block="options", default=False)
