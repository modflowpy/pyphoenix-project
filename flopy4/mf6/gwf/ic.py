import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, setattribute
from flopy4.mf6 import Package


@component
@define(slots=False, on_setattr=setattribute)
class Ic(Package):
    strt: NDArray[np.floating] = field(
        default=1.0,
        metadata={"block": "packagedata", "dims": ("nnodes",)},
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )
