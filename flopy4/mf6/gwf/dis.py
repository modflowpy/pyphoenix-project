from pathlib import Path
from typing import Optional

import attrs
import numpy as np
from numpy.typing import NDArray

from flopy4.mf6.gwf.disbase import DisBase
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utl.ncf import Ncf
from flopy4.utils import to_path


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
    ncf6_filerecord: Optional[Path] = attrs.field(
        default=None,
        converter=lambda v: None if v is None else to_path(v),
        metadata={
            "dfn_block": "options",
            "dfn_type": "record",
            "optional": True,
            "inout": "filein",
        },
    )
    ncf: Optional[Ncf] = attrs.field(default=None)
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
        # Coerce list/tuple griddata values to ndarray, then broadcast scalars.
        import attrs as _attrs

        fields = _attrs.fields(type(self))
        dims = self.get_dims()
        ncpl = dims.get("ncpl", 0)
        nlay = dims.get("nlay", 1)
        for f in fields:
            if f.metadata.get("dfn_block") != "griddata":
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            dtype = self._DTYPE_MAP.get(f.metadata.get("dfn_type", "double"), np.float64)
            if isinstance(val, (list, tuple)):
                val = np.asarray(val, dtype=dtype)
                self.__dict__[f.name] = val
            if isinstance(val, np.ndarray):
                # Per-layer scalars: e.g. botm=[-10, -20] for 2 layers → expand
                if f.metadata.get("layered") and val.size == nlay and nlay > 0 and ncpl > 0:
                    self.__dict__[f.name] = np.repeat(val, ncpl).astype(dtype)
                elif val.ndim > 1:
                    self.__dict__[f.name] = val.ravel()
        self._broadcast_griddata(fields, dims)
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
        # Reshape flat arrays to grid shape for StructuredGrid constructor.
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
