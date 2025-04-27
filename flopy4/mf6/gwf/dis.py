import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import array, dim, field, xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package


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
        coord="lay",
        scope="gwf",
        default=1,
        metadata={
            "block": "dimensions",
        },
    )
    ncol: int = dim(
        coord="col",
        scope="gwf",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    nrow: int = dim(
        coord="row",
        scope="gwf",
        default=2,
        metadata={
            "block": "dimensions",
        },
    )
    delr: NDArray[np.floating] = array(
        default=1.0,
        dims=("ncol",),
        metadata={"block": "griddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    delc: NDArray[np.floating] = array(
        default=1.0,
        dims=("nrow",),
        metadata={"block": "griddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    top: NDArray[np.floating] = array(
        default=1.0,
        dims=("ncol", "nrow"),
        metadata={"block": "griddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    botm: NDArray[np.floating] = array(
        default=0.0,
        dims=("ncol", "nrow", "nlay"),
        metadata={"block": "griddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    idomain: NDArray[np.integer] = array(
        default=1,
        dims=("ncol", "nrow", "nlay"),
        metadata={"block": "griddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    nnodes: int = dim(
        coord="node",
        scope="gwf",
        init=False,
    )

    def __attrs_post_init__(self):
        self.nnodes = self.ncol * self.nrow * self.nlay
