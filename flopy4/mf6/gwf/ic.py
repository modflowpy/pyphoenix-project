import numpy as np
from attr import field
from numpy.typing import NDArray
from xattree import array, xattree

from flopy4.mf6 import Package


@xattree
class Ic(Package):
    strt: NDArray[np.floating] = array(
        dims=("node",),
        default=1.0,
        metadata={"block": "packagedata"},
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )
