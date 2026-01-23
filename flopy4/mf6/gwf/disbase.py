from typing import Optional

from xattree import xattree

from flopy4.mf6.package import Package
from flopy4.mf6.spec import dim, field


@xattree
class DisBase(Package):
    length_units: str = field(
        block="options",
        default=None,
        longname="model length units",
    )
    nogrb: bool = field(block="options", default=None, longname="do not write binary grid file")
    xorigin: float = field(
        block="options", default=None, longname="x-position of the model grid origin"
    )
    yorigin: float = field(
        block="options", default=None, longname="y-position of the model grid origin"
    )
    angrot: float = field(block="options", default=None, longname="rotation angle")
    export_array_netcdf: bool = field(
        block="options",
        default=None,
        longname="export array variables to netcdf output files.",
    )
    crs: str = field(
        block="options",
        default=None,
        longname="CRS user input string",
    )
    nlay: Optional[int] = dim(
        coord="lay",
        scope="gwf",
        default=None,
        init=False,
    )
    nrow: Optional[int] = dim(
        coord="row",
        scope="gwf",
        default=None,
        init=False,
    )
    ncol: Optional[int] = dim(
        coord="col",
        scope="gwf",
        default=None,
        init=False,
    )
    ncpl: Optional[int] = dim(
        coord="cpl",
        scope="gwf",
        default=None,
        init=False,
    )
    nvert: int = dim(
        coord="vert",
        scope="gwf",
        default=None,
        init=False,
    )
    nodes: int = dim(
        coord="node",
        scope="gwf",
        default=None,
        init=False,
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
