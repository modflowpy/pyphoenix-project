from typing import Optional

import numpy as np
from attr import field
from numpy.typing import NDArray
from xattree import array, dim, xattree

from flopy4.mf6 import Package


@xattree
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
    nlay: int = dim(
        coord="k",
        scope="simulation",
        default=1,
        metadata={
            "block": "dimensions",
        },
    )
    ncol: int = dim(
        coord="i",
        scope="simulation",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    nrow: int = dim(
        coord="j",
        scope="simulation",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    delr: NDArray[np.floating] = array(
        dims=("ncol",),
        default=1.0,
        metadata={"block": "griddata"},
    )
    delc: NDArray[np.floating] = array(
        dims=("nrow",),
        default=1.0,
        metadata={"block": "griddata"},
    )
    top: NDArray[np.floating] = array(
        dims=("ncol", "nrow"),
        default=1.0,
        metadata={"block": "griddata"},
    )
    botm: NDArray[np.floating] = array(
        dims=("ncol", "nrow", "nlay"),
        default=0.0,
        metadata={"block": "griddata"},
    )
    idomain: NDArray[np.integer] = array(
        dims=("ncol", "nrow", "nlay"),
        default=1,
        metadata={"block": "griddata"},
    )
    nnodes: Optional[int] = dim(default=None, coord="node", scope="simulation")

    def __attrs_post_init__(self):
        self.nnodes = self.ncol * self.nrow * self.nlay
