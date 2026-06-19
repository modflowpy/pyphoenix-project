from typing import Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.utils.grid import StructuredGrid


@attrs.define(kw_only=True, slots=False)
class Dis(DisBase):
    length_units: Optional[str] = attrs.field(
        default=None,
        metadata={"dfn_block": "options", "dfn_type": "string", "optional": True},
    )
    nogrb: bool = attrs.field(
        default=False,
        metadata={"dfn_block": "options", "dfn_type": "keyword", "optional": True},
    )
    xorigin: float = attrs.field(
        default=0.0,
        metadata={"dfn_block": "options", "dfn_type": "double", "optional": True},
    )
    yorigin: float = attrs.field(
        default=0.0,
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
    nlay: int = attrs.field(
        default=1,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    ncol: int = attrs.field(
        default=2,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    nrow: int = attrs.field(
        default=2,
        metadata={"dfn_block": "dimensions", "dfn_type": "integer"},
    )
    delr: NDArray[np.float64] = attrs.field(
        default=1.0,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("ncol",),
            "layered": False,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    delc: NDArray[np.float64] = attrs.field(
        default=1.0,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("nrow",),
            "layered": False,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    top: NDArray[np.float64] = attrs.field(
        default=1.0,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("ncpl",),
            "layered": False,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    botm: NDArray[np.float64] = attrs.field(
        default=0.0,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "double",
            "shape": ("nodes",),
            "layered": True,
            "netcdf": True,
        },
    )  # type: ignore[assignment]
    idomain: Optional[NDArray[np.int64]] = attrs.field(
        default=1,
        metadata={
            "dfn_block": "griddata",
            "dfn_type": "integer",
            "shape": ("nodes",),
            "layered": True,
            "netcdf": True,
        },
    )  # type: ignore[assignment]

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
        top = (
            self.top.reshape(self.nrow, self.ncol) if isinstance(self.top, np.ndarray) else self.top
        )
        botm = (
            self.botm.reshape(self.nlay, self.nrow, self.ncol)
            if isinstance(self.botm, np.ndarray)
            else self.botm
        )
        idomain = (
            self.idomain.reshape(self.nlay, self.nrow, self.ncol)
            if isinstance(self.idomain, np.ndarray)
            else self.idomain
        )
        return StructuredGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            nlay=self.nlay,
            nrow=self.nrow,
            ncol=self.ncol,
            delr=self.delr,
            delc=self.delc,
            top=top,
            botm=botm,
            idomain=idomain,
            crs=self.crs,
        )

    @classmethod
    def from_grid(cls, grid: StructuredGrid) -> "Dis":
        """Create a discretization from a `StructuredGrid`."""
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
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return Dis(**kwargs)
