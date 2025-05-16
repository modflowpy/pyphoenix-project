import numpy as np
from attrs import Converter
from flopy.discretization.structuredgrid import StructuredGrid
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.decorators import array, dim, field
from flopy4.mf6.package import Package


@xattree
class Dis(Package):
    length_units: str = field(
        default=None,
        metadata={"block": "options"},
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
    delr: NDArray[np.floating] = array(
        block="griddata",
        default=1.0,
        dims=("ncol",),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    delc: NDArray[np.floating] = array(
        block="griddata",
        default=1.0,
        dims=("nrow",),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    top: NDArray[np.floating] = array(
        block="griddata",
        default=1.0,
        dims=("ncol", "nrow"),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    botm: NDArray[np.floating] = array(
        block="griddata",
        default=0.0,
        dims=("ncol", "nrow", "nlay"),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    idomain: NDArray[np.integer] = array(
        block="griddata",
        default=1,
        dims=("ncol", "nrow", "nlay"),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    nnodes: int = dim(
        coord="node",
        scope="gwf",
        init=False,
    )

    def __attrs_post_init__(self):
        self.nnodes = self.ncol * self.nrow * self.nlay

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
