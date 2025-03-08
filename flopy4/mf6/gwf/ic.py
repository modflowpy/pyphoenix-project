import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import array, field, xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package


@xattree
class Ic(Package):
    strt: NDArray[np.floating] = array(
        dims=("node",),
        default=1.0,
        metadata={"block": "packagedata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )
