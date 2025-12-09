from typing import Optional

import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field
from flopy4.mf6.utils.grid import StructuredGrid


@xattree
class Dis(Package):
    length_units: str = field(
        block="options",
        default=None,
    )
    nogrb: bool = field(block="options", default=False)
    xorigin: float = field(block="options", default=None)
    yorigin: float = field(block="options", default=None)
    angrot: float = field(block="options", default=None)
    export_array_netcdf: bool = field(block="options", default=False)
    nlay: int = dim(
        block="dimensions",
        coord="lay",
        scope="gwf",
        default=1,
    )
    ncol: int = dim(
        block="dimensions",
        coord="col",
        scope="gwf",
        default=2,
    )
    nrow: int = dim(
        block="dimensions",
        coord="row",
        scope="gwf",
        default=2,
    )
    delr: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("ncol",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    delc: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("nrow",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    top: NDArray[np.float64] = array(
        block="griddata",
        default=1.0,
        netcdf=True,
        dims=("nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    botm: NDArray[np.float64] = array(
        block="griddata",
        default=0.0,
        netcdf=True,
        dims=("nlay", "nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    idomain: Optional[NDArray[np.int64]] = array(
        block="griddata",
        default=1,
        netcdf=True,
        dims=("nlay", "nrow", "ncol"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
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

    def __attrs_post_init__(self):
        self.nodes = self.ncol * self.nrow * self.nlay
        self.ncpl = self.ncol * self.nrow
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
