from typing import Optional

import attrs
import numpy as np
from attrs import Converter
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.spec import array, dim, field
from flopy4.mf6.utils.grid import VertexGrid


@xattree
class Disv(DisBase):
    @attrs.define(slots=False)
    class Cell2dRecord:
        icell2d: int = attrs.field()
        xc: float = attrs.field()
        yc: float = attrs.field()
        ncvert: int = attrs.field()
        icvert: tuple[int, ...] = attrs.field()

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
    ncpl: int = dim(
        block="dimensions",
        coord="cpl",
        scope="gwf",
        default=4,
        longname="number of cells per layer",
    )
    nvert: int = dim(
        block="dimensions",
        coord="vert",
        scope="gwf",
        default=9,
        longname="number of vertices",
    )
    nodes: int = dim(
        coord="node",
        scope="gwf",
        default=None,
        init=False,
    )
    top: NDArray[np.float64] = array(
        block="griddata",
        default=None,
        netcdf=True,
        dims=("ncpl",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell top elevation",
    )
    botm: NDArray[np.float64] = array(
        block="griddata",
        default=None,
        netcdf=True,
        dims=("nlay", "ncpl"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="cell bottom elevation",
    )
    idomain: Optional[NDArray[np.int64]] = array(
        block="griddata",
        default=None,
        netcdf=True,
        dims=("nlay", "ncpl"),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="idomain existence array",
    )
    iv: NDArray[np.int64] = array(
        block="vertices",
        dims=("nvert",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="vertex number",
    )
    xv: NDArray[np.float64] = array(
        block="vertices",
        dims=("nvert",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="x-coordinate for vertex",
    )
    yv: NDArray[np.float64] = array(
        block="vertices",
        dims=("nvert",),
        default=None,
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        longname="y-coordinate for vertex",
    )
    cell2ddata: Optional[NDArray[np.object_]] = array(
        dtype=Cell2dRecord,
        block="cell2d",
        default=None,
        dims=("ncpl",),
        converter=attrs.Converter(structure_array, takes_self=True, takes_field=True),
    )

    def __attrs_post_init__(self):
        self.nodes = self.ncpl * self.nlay
        self.ncol = -1
        self.nrow = -1
        super().__attrs_post_init__()

    def to_grid(self) -> VertexGrid:
        """
        Convert the discretization to a `VertexGrid`.

        Returns
        -------
        VertexGrid
            A `VertexGrid` with the same dimensions and data as the `Disv`.
        """
        return VertexGrid(
            nlay=self.nlay,
            # nrow=self.nrow,
            # ncol=self.ncol,
            # delr=self.delr,
            # delc=self.delc,
            top=self.top,
            botm=self.botm,
            idomain=self.idomain,
        )

    @classmethod
    def from_grid(cls, grid: VertexGrid) -> "Disv":
        """
        Create a discretization from a `VertexGrid`.

        Parameters
        ----------
        grid : VertexGrid
            A structured grid.

        Returns
        -------
        Disv
            A discretization with the same dimensions and data as the grid.
        """
        return Disv(
            nlay=grid.nlay,
            # nrow=grid.nrow,
            # ncol=grid.ncol,
            # delr=grid.delr,
            # delc=grid.delc,
            top=grid.top,
            botm=grid.botm,
            idomain=grid.idomain,
        )
