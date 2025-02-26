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
        name="lay",
        scope="gwf",
        default=1,
        metadata={
            "block": "dimensions",
        },
    )
    ncol: int = dim(
        name="col",
        scope="gwf",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    nrow: int = dim(
        name="row",
        scope="gwf",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    delr: NDArray[np.floating] = array(
        dims=("col",),
        default=1.0,
        metadata={"block": "griddata"},
    )
    delc: NDArray[np.floating] = array(
        dims=("row",),
        default=1.0,
        metadata={"block": "griddata"},
    )
    top: NDArray[np.floating] = array(
        dims=("col", "row"),
        default=1.0,
        metadata={"block": "griddata"},
    )
    botm: NDArray[np.floating] = array(
        dims=("col", "row", "lay"),
        default=0.0,
        metadata={"block": "griddata"},
    )
    idomain: NDArray[np.integer] = array(
        dims=("col", "row", "lay"),
        default=1,
        metadata={"block": "griddata"},
    )
    nnodes: int = dim(name="node", scope="gwf", init=False)

    def __attrs_post_init__(self):
        self.nnodes = self.ncol * self.nrow * self.nlay
