from typing import Optional

import numpy as np
from attr import define, field
from numpy.typing import NDArray

from flopy4 import component, setattribute
from flopy4.mf6 import Package


@component(align=["nlay", "ncol", "nrow"])
@define(slots=False, on_setattr=setattribute)
class Dis(Package):
    length_units: str = field(
        default=None,
        metadata={"block": "options"},
    )
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    nlay: int = field(default=1, metadata={"block": "dimensions"})
    ncol: int = field(default=2, metadata={"block": "dimensions"})
    nrow: int = field(default=2, metadata={"block": "dimensions"})
    delr: NDArray[np.floating] = field(
        default=1.0,
        metadata={"block": "griddata", "dims": ("ncol",)},
    )
    delc: NDArray[np.floating] = field(
        default=1.0,
        metadata={"block": "griddata", "dims": ("nrow",)},
    )
    top: NDArray[np.floating] = field(
        default=1.0,
        metadata={"block": "griddata", "dims": ("ncol", "nrow")},
    )
    botm: NDArray[np.floating] = field(
        default=0.0,
        metadata={"block": "griddata", "dims": ("ncol", "nrow", "nlay")},
    )
    idomain: Optional[NDArray[np.integer]] = field(
        default=1,
        metadata={"block": "griddata", "dims": ("ncol", "nrow", "nlay")},
    )
    nodes: Optional[int] = field(default=None)

    def __attrs_post_init__(self):
        self.nodes = self.ncol * self.nrow * self.nlay
