from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6._types import _optional_path
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.item import Item
from flopy4.mf6.spec import field, path
from flopy4.mf6.utils.grid import VertexGrid
from flopy4.mf6.utl.ncf import Ncf


@attrs.define(kw_only=True, slots=False)
class Disv(DisBase):
    dfn_name: ClassVar[str] = "gwt-disv"

    @attrs.define(slots=False)
    class Cell2dRecord:
        icell2d: int = attrs.field()
        xc: float = attrs.field()
        yc: float = attrs.field()
        ncvert: int = attrs.field()
        icvert: tuple[int, ...] = attrs.field()

    @attrs.define
    class Vertices(Item):
        iv: int
        xv: float
        yv: float

    length_units: Optional[str] = field(default=None, block="options", optional=True)
    nogrb: bool = field(default=False, block="options", optional=True)
    xorigin: Optional[float] = field(default=None, block="options", optional=True)
    yorigin: Optional[float] = field(default=None, block="options", optional=True)
    angrot: Optional[float] = field(default=None, block="options", optional=True)
    export_array_netcdf: bool = field(default=False, block="options", optional=True)
    crs: Optional[str] = field(default=None, block="options", optional=True)
    ncf6_filerecord: Optional[Path] = path(
        default=None,
        converter=_optional_path,
        block="options",
        optional=True,
        direction="in",
    )
    ncf: Optional[Ncf] = attrs.field(default=None)
    nlay: int = field(default=0, block="dimensions")
    ncpl: int = field(default=0, block="dimensions")
    nvert: int = field(default=0, block="dimensions")
    top: NDArray[np.float64] = field(
        default=None,
        block="griddata",
        shape=("ncpl",),
        layered=False,
        netcdf=True,
    )
    botm: NDArray[np.float64] = field(
        default=None,
        block="griddata",
        shape=("nodes",),
        layered=True,
        netcdf=True,
    )
    idomain: Optional[NDArray[np.int64]] = field(
        default=None,
        block="griddata",
        shape=("nodes",),
        layered=True,
        netcdf=True,
    )
    iv: Optional[NDArray[np.int64]] = attrs.field(default=None)
    xv: Optional[NDArray[np.float64]] = attrs.field(default=None)
    yv: Optional[NDArray[np.float64]] = attrs.field(default=None)
    vertices: Optional[list[Vertices]] = field(default=None, block="vertices")
    cell2ddata: Optional[list] = attrs.field(default=None)
    cell2d: Optional[list] = field(default=None, init=False, block="cell2d")

    def __attrs_post_init__(self):
        if self.iv is not None and (not isinstance(self.iv, np.ndarray)):
            object.__setattr__(self, "iv", np.asarray(self.iv, dtype=np.int64))
        if self.xv is not None and (not isinstance(self.xv, np.ndarray)):
            object.__setattr__(self, "xv", np.asarray(self.xv, dtype=np.float64))
        if self.yv is not None and (not isinstance(self.yv, np.ndarray)):
            object.__setattr__(self, "yv", np.asarray(self.yv, dtype=np.float64))
        if self.iv is not None and self.xv is not None and (self.yv is not None):
            rows = [
                self.Vertices(iv=int(iv) + 1, xv=float(xv), yv=float(yv))
                for iv, xv, yv in zip(self.iv, self.xv, self.yv)
            ]
            object.__setattr__(self, "vertices", rows)
        if self.cell2ddata is not None:
            rows = []
            for rec in self.cell2ddata:
                row = (rec.icell2d + 1, rec.xc, rec.yc, rec.ncvert) + tuple(
                    (v + 1 for v in rec.icvert)
                )
                rows.append(row)
            object.__setattr__(self, "cell2d", rows)
        self.nodes = self.ncpl * self.nlay
        self.nrow = 0
        self.ncol = 0
        self._coerce_griddata()
        super().__attrs_post_init__()

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions."""
        return {
            "nlay": self.nlay,
            "ncpl": self.ncpl,
            "nvert": self.nvert,
            "nodes": self.nlay * self.ncpl,
        }

    def to_grid(self) -> VertexGrid:
        """Convert the discretization to a `VertexGrid`."""
        vertices = []
        assert self.iv is not None and self.xv is not None and self.yv is not None
        for i in range(len(self.iv)):
            vertices.append([self.iv[i], self.xv[i], self.yv[i]])
        botm = (
            self.botm.reshape(self.nlay, self.ncpl)
            if isinstance(self.botm, np.ndarray)
            else self.botm
        )
        idomain = (
            self.idomain.reshape(self.nlay, self.ncpl)
            if isinstance(self.idomain, np.ndarray) and self.idomain is not None
            else self.idomain
        )
        return VertexGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            angrot=self.angrot,
            crs=self.crs,
            nlay=self.nlay,
            ncpl=self.ncpl,
            top=self.top,
            botm=botm,
            idomain=idomain,
            vertices=vertices,
            cell2d=Disv.disv_to_grid_cell2d(self.cell2ddata),
        )

    @classmethod
    def from_grid(cls, grid: VertexGrid) -> "Disv":
        """Create a discretization from a `VertexGrid`."""
        _lenunits = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nlay": grid.nlay,
            "ncpl": grid.ncpl,
            "nvert": grid.nvert,
            "top": grid.top,
            "botm": grid.botm,
            "idomain": np.asarray(grid.idomain).reshape(grid.nlay, grid.ncpl)
            if grid.idomain is not None
            else None,
            "iv": np.array([v[0] for v in grid._vertices], dtype=int),
            "xv": grid.verts[:, 0].ravel(),
            "yv": grid.verts[:, 1].ravel(),
            "cell2ddata": Disv.grid_to_disv_cell2d(grid.cell2d),
        }
        if grid.lenuni in _lenunits:
            kwargs["length_units"] = _lenunits[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return Disv(**kwargs)

    @staticmethod
    def disv_to_grid_cell2d(cell2ddata) -> list:
        cell2d = []
        iverts = []
        xcenters = []
        ycenters = []
        for rec in cell2ddata:
            iverts.append(list(rec.icvert))
            xcenters.append(rec.xc)
            ycenters.append(rec.yc)
        for n in range(len(iverts)):
            cell2d_n = [n, xcenters[n], ycenters[n]] + iverts[n]
            cell2d.append(cell2d_n)
        return cell2d

    @staticmethod
    def grid_to_disv_cell2d(cell2d):
        cell2ddata = []
        for cell in cell2d:
            verts = cell[4:]
            if verts[0] != verts[-1]:
                verts.append(cell[4])
            rec = Disv.Cell2dRecord(cell[0], cell[1], cell[2], len(verts), tuple(verts))
            cell2ddata.append(rec)
        return cell2ddata
