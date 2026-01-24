from typing import Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.spec import array, dim, field
from flopy4.mf6.utils.grid import StructuredGrid


@xattree
class Dis(DisBase):
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
    nlay: int = dim(
        block="dimensions",
        coord="lay",
        scope="gwf",
        default=1,
        longname="number of layers",
    )
    ncol: int = dim(
        block="dimensions",
        coord="col",
        scope="gwf",
        default=2,
        longname="number of columns",
    )
    nrow: int = dim(
        block="dimensions",
        coord="row",
        scope="gwf",
        default=2,
        longname="number of rows",
    )
    delr: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("ncol",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="spacing along a row",
    )
    delc: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("nrow",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="spacing along a column",
    )
    top: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell top elevation",
    )
    botm: NDArray[np.float64] = array(
        block="griddata",
        default=0.0,
        netcdf=True,
        dims=("nlay", "nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell bottom elevation",
    )
    idomain: Optional[NDArray[np.int64]] = array(
        block="griddata",
        default=1,
        netcdf=True,
        dims=("nlay", "nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="idomain existence array",
    )
    nodes: int = dim(
        coord="node",
        scope="gwf",
        init=False,
    )
    ncpl: int = dim(
        coord="lnode",
        scope="gwf",
        init=False,
    )
    nvert: int = dim(
        coord="vert",
        scope="gwf",
        init=False,
    )

    def __attrs_post_init__(self):
        self.nodes = self.ncol * self.nrow * self.nlay
        self.ncpl = self.ncol * self.nrow
        self.nvert = (self.ncol + 1) * (self.nrow + 1)
        super().__attrs_post_init__()

    def to_grid(self) -> StructuredGrid:
        """
        Convert the discretization to a `StructuredGrid`.

        Returns
        -------
        StructuredGrid
            A `StructuredGrid` with the same dimensions and data as the `Dis`.
        """
        return StructuredGrid(
            nlay=self.nlay,
            nrow=self.nrow,
            ncol=self.ncol,
            delr=self.delr,
            delc=self.delc,
            top=self.top,
            botm=self.botm,
            idomain=self.idomain,
        )

    @classmethod
    def from_grid(cls, grid: StructuredGrid) -> "Dis":
        """
        Create a discretization from a `StructuredGrid`.

        Parameters
        ----------
        grid : StructuredGrid
            A structured grid.

        Returns
        -------
        Dis
            A discretization with the same dimensions and data as the grid.
        """
        return Dis(
            nlay=grid.nlay,
            nrow=grid.nrow,
            ncol=grid.ncol,
            delr=grid.delr,
            delc=grid.delc,
            top=grid.top,
            botm=grid.botm,
            idomain=grid.idomain,
        )
