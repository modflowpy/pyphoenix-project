from pathlib import Path
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6._types import _optional_path
from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.spec import field, path
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utl.ncf import Ncf


@attrs.define(kw_only=True, slots=False)
class Dis(DisBase):
    dfn_name: ClassVar[str] = "gwf-dis"

    length_units: Optional[str] = field(default=None, block="options", optional=True)
    nogrb: bool = field(default=False, block="options", optional=True)
    xorigin: float = field(default=0.0, block="options", optional=True)
    yorigin: float = field(default=0.0, block="options", optional=True)
    angrot: Optional[float] = field(default=None, block="options", optional=True)
    export_array_netcdf: bool = field(default=False, block="options", optional=True)
    crs: Optional[str] = field(default=None, block="options", optional=True)
    ncf6_filerecord: Optional[Path] = path(
        default=None,
        converter=_optional_path,
        block="options",
        optional=True,
        inout="filein",
    )
    ncf: Optional[Ncf] = attrs.field(default=None)
    nlay: int = field(default=1, block="dimensions")
    ncol: int = field(default=2, block="dimensions")
    nrow: int = field(default=2, block="dimensions")
    delr: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        shape=("ncol",),
        layered=False,
        netcdf=True,
    )
    delc: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        shape=("nrow",),
        layered=False,
        netcdf=True,
    )
    top: NDArray[np.float64] = field(
        default=1.0,
        block="griddata",
        shape=("ncpl",),
        layered=False,
        netcdf=True,
    )
    botm: NDArray[np.float64] = field(
        default=0.0,
        block="griddata",
        shape=("nodes",),
        layered=True,
        netcdf=True,
    )
    idomain: Optional[NDArray[np.int64]] = field(
        default=1, block="griddata", shape=("nodes",), layered=True, netcdf=True
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
