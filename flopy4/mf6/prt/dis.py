from typing import Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.spec import field
from flopy4.mf6.utils.grid import StructuredGrid


@attrs.define(kw_only=True, slots=False)
class Dis(DisBase):
    length_units: Optional[str] = field(
        default=None, block="options", dfn_type="string", optional=True
    )
    nogrb: bool = field(default=False, block="options", dfn_type="keyword", optional=True)
    xorigin: float = field(default=0.0, block="options", dfn_type="double", optional=True)
    yorigin: float = field(default=0.0, block="options", dfn_type="double", optional=True)
    angrot: Optional[float] = field(default=None, block="options", dfn_type="double", optional=True)
    export_array_netcdf: bool = field(
        default=False, block="options", dfn_type="keyword", optional=True
    )
    crs: Optional[str] = field(default=None, block="options", dfn_type="string", optional=True)
    nlay: int = field(default=1, block="dimensions", dfn_type="integer")
    ncol: int = field(default=2, block="dimensions", dfn_type="integer")
    nrow: int = field(default=2, block="dimensions", dfn_type="integer")
    delr: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        dfn_type="double",
        shape=("ncol",),
        layered=False,
        netcdf=False,
    )
    delc: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        dfn_type="double",
        shape=("nrow",),
        layered=False,
        netcdf=False,
    )
    top: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        dfn_type="double",
        shape=("ncpl",),
        layered=False,
        netcdf=False,
    )
    botm: NDArray[np.float64] = field(
        default=0.0,
        block="griddata",
        dfn_type="double",
        shape=("nodes",),
        layered=True,
        netcdf=False,
    )
    idomain: Optional[NDArray[np.int64]] = field(
        default=1,
        block="griddata",
        dfn_type="integer",
        shape=("nodes",),
        layered=True,
        netcdf=False,
    )

    def __attrs_post_init__(self):
        self.nodes = self.ncol * self.nrow * self.nlay
        self.ncpl = self.ncol * self.nrow
        self.nvert = (self.ncol + 1) * (self.nrow + 1)
        self._coerce_griddata()
        super().__attrs_post_init__()

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions."""
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
            "ncpl": self.nrow * self.ncol,
        }

    def to_grid(self) -> StructuredGrid:
        """Convert the discretization to a `StructuredGrid`."""
        top = np.asarray(self.top).reshape(self.nrow, self.ncol)
        botm = np.asarray(self.botm).reshape(self.nlay, self.nrow, self.ncol)
        idomain = (
            np.asarray(self.idomain).reshape(self.nlay, self.nrow, self.ncol)
            if self.idomain is not None
            else None
        )
        return StructuredGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            nlay=self.nlay,
            nrow=self.nrow,
            ncol=self.ncol,
            delr=np.asarray(self.delr),
            delc=np.asarray(self.delc),
            top=top,
            botm=botm,
            idomain=idomain,
            angrot=self.angrot,
            crs=self.crs,
        )

    @classmethod
    def from_grid(cls, grid: StructuredGrid) -> "Dis":
        """Create a discretization from a `StructuredGrid`."""
        _lenunits = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nlay": grid.nlay,
            "nrow": grid.nrow,
            "ncol": grid.ncol,
            "delr": grid.delr,
            "delc": grid.delc,
            "top": grid.top,
            "botm": grid.botm,
            "idomain": grid.idomain,
        }
        if grid.lenuni in _lenunits:
            kwargs["length_units"] = _lenunits[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return Dis(**kwargs)
