from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6._types import _optional_path
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.schema import Column, Schema
from flopy4.mf6.utils.grid import VertexGrid
from flopy4.mf6.utl.ncf import Ncf


@attrs.define(kw_only=True, slots=False)
class Disv(DisBase):
    @attrs.define(slots=False)
    class Cell2dRecord:
        icell2d: int = attrs.field()
        xc: float = attrs.field()
        yc: float = attrs.field()
        ncvert: int = attrs.field()
        icvert: tuple[int, ...] = attrs.field()

    class _VerticesSchema(Schema):
        iv = Column("iv", role="value", dfn_type="integer")
        xv = Column("xv", role="value", dfn_type="double")
        yv = Column("yv", role="value", dfn_type="double")

    __vertices_schema__: ClassVar[type[Schema]] = _VerticesSchema

    length_units: Optional[str] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "string", "optional": True},
    )
    nogrb: bool = attrs.field(
        default=False,
        metadata={"dfn_block": "options", "dfn_type": "keyword", "optional": True},
    )
    xorigin: Optional[float] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "double", "optional": True},
    )
    yorigin: Optional[float] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "double", "optional": True},
    )
    angrot: Optional[float] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "double", "optional": True},
    )
    export_array_netcdf: bool = attrs.field(
        default=False,
        metadata={"dfn_block": "options", "dfn_type": "keyword", "optional": True},
    )
    crs: Optional[str] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "string", "optional": True},
    )
    ncf6_filerecord: Optional[Path] = attrs.field(
        default=None,
        converter=_optional_path,
        metadata={
            "dfn_block": "options",
            "dfn_type": "record",
            "optional": True,
            "inout": "filein",
        },
    )
    ncf: Optional[Ncf] = attrs.field(default=None)
    nlay: int = attrs.field(
        default=0,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    ncpl: int = attrs.field(
        default=0,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    nvert: int = attrs.field(
        default=0,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    top: NDArray[np.float64] = attrs.field(
        default=None,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("ncpl",),
            "layered": False,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    botm: NDArray[np.float64] = attrs.field(
        default=None,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("nodes",),
            "layered": True,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    idomain: Optional[NDArray[np.int64]] = attrs.field(
        default=None,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "integer",
            "shape": ("nodes",),
            "layered": True,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    # User-facing parallel arrays for vertices.
    iv: Optional[NDArray[np.int64]] = attrs.field(default=None)  # type: ignore[assignment]
    xv: Optional[NDArray[np.float64]] = attrs.field(default=None)  # type: ignore[assignment]
    yv: Optional[NDArray[np.float64]] = attrs.field(default=None)  # type: ignore[assignment]
    # Combined vertices recarray for the codec (built in __attrs_post_init__).
    vertices: Optional[np.recarray] = attrs.field(
        default=None,
        metadata={"dfn_block": "vertices", "schema": "__vertices_schema__"},
    )  # type: ignore[assignment]
    # Cell2d data — list of Cell2dRecord objects (user-facing).
    cell2ddata: Optional[list] = attrs.field(default=None)
    # Pre-formatted cell2d rows for the codec (built in __attrs_post_init__).
    cell2d: Optional[list] = attrs.field(
        default=None,
        init=False,
        metadata={"dfn_block": "cell2d"},
    )

    def __attrs_post_init__(self):
        # Coerce list inputs to numpy arrays for vertices.
        if self.iv is not None and not isinstance(self.iv, np.ndarray):
            object.__setattr__(self, "iv", np.asarray(self.iv, dtype=np.int64))
        if self.xv is not None and not isinstance(self.xv, np.ndarray):
            object.__setattr__(self, "xv", np.asarray(self.xv, dtype=np.float64))
        if self.yv is not None and not isinstance(self.yv, np.ndarray):
            object.__setattr__(self, "yv", np.asarray(self.yv, dtype=np.float64))
        # Build combined vertices recarray for the codec.
        if self.iv is not None and self.xv is not None and self.yv is not None:
            dtype = np.dtype([("iv", np.int64), ("xv", np.float64), ("yv", np.float64)])
            n = len(self.iv)
            arr = np.zeros(n, dtype=dtype)
            arr["iv"] = self.iv + 1  # MF6 uses 1-based vertex IDs
            arr["xv"] = self.xv
            arr["yv"] = self.yv
            object.__setattr__(self, "vertices", arr.view(np.recarray))
        # Build cell2d list of tuples for the codec.
        if self.cell2ddata is not None:
            rows = []
            for rec in self.cell2ddata:
                row = (rec.icell2d + 1, rec.xc, rec.yc, rec.ncvert) + tuple(
                    v + 1 for v in rec.icvert
                )
                rows.append(row)
            object.__setattr__(self, "cell2d", rows)
        # Set derived dimensions.
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
        for i in range(len(self.iv)):  # type: ignore[arg-type]
            vertices.append([self.iv[i], self.xv[i], self.yv[i]])  # type: ignore[index]
        # VertexGrid expects top as 1D (ncpl,) and botm as 2D (nlay, ncpl).
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
                len(verts),
                tuple(verts),
            )
            cell2ddata.append(rec)
        return cell2ddata
