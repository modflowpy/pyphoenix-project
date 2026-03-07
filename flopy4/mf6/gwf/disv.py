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
        default=0,
        longname="number of layers",
    )
    ncpl: int = dim(
        block="dimensions",
        coord="icpl",
        scope="gwf",
        default=0,
        longname="number of cells per layer",
    )
    nvert: int = dim(
        block="dimensions",
        coord="vert",
        scope="gwf",
        default=0,
        longname="number of vertices",
    )
    nodes: int = dim(
        coord="node",
        scope="gwf",
        default=0,
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
        self.ncol = 0
        self.nrow = 0
        super().__attrs_post_init__()

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions.

        Returns both explicit dimensions (nlay, ncpl, nvert) and computed
        dimensions (nodes).

        Returns
        -------
        dict[str, int]
            Mapping of dimension names to their integer sizes.
        """
        return {
            "nlay": self.nlay,
            "ncpl": self.ncpl,
            "nvert": self.nvert,
            "nodes": self.nlay * self.ncpl,
        }

    def to_grid(self) -> VertexGrid:
        """
        Convert the discretization to a `VertexGrid`.

        Returns
        -------
        VertexGrid
            A `VertexGrid` with the same dimensions and data as the `Disv`.
        """
        vertices = []
        for i in range(len(self.iv.values)):  # type: ignore
            vert = []
            vert.append(self.iv.values[i])  # type: ignore
            vert.append(self.xv.values[i])  # type: ignore
            vert.append(self.yv.values[i])  # type: ignore
            vertices.append(vert)
        return VertexGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            crs=self.crs,
            nlay=self.nlay,
            top=self.top,
            botm=self.botm,
            idomain=self.idomain,
            vertices=vertices,
            cell2d=Disv.disv_to_grid_cell2d(self.cell2ddata),
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
            xorigin=grid.xoffset,
            yorigin=grid.yoffset,
            nlay=grid.nlay,
            ncpl=grid.ncpl,
            nvert=grid.nvert,
            top=grid.top,
            botm=grid.botm,
            idomain=np.asarray(grid.idomain).reshape(grid.nlay, grid.ncpl)
            if grid.idomain is not None
            else None,
            iv=np.array([v[0] for v in grid._vertices], dtype=int),
            xv=grid.verts[:, 0].ravel(),
            yv=grid.verts[:, 1].ravel(),
            cell2ddata=Disv.grid_to_disv_cell2d(grid.cell2d),
        )

    @staticmethod
    def disv_to_grid_cell2d(cell2ddata) -> list:
        cell2d = []
        iverts = []
        xcenters = []
        ycenters = []
        for rec in cell2ddata.values:  # type: ignore
            iverts.append(list(rec.icvert))
            xcenters.append(rec.xc)
            ycenters.append(rec.yc)
        for n in range(len(iverts)):
            cell2d_n = [
                n,
                xcenters[n],
                ycenters[n],
            ] + iverts[n]
            cell2d.append(cell2d_n)
        return cell2d

    @staticmethod
    def grid_to_disv_cell2d(cell2d):
        cell2ddata = []
        for cell in cell2d:
            verts = cell[4:]
            if verts[0] != verts[-1]:
                verts.append(cell[4])
            rec = Disv.Cell2dRecord(
                cell[0],
                cell[1],
                cell[2],
                len(verts),  # ncvert includes the closing (repeated) vertex
                tuple(verts),
            )
            cell2ddata.append(rec)
        return cell2ddata
