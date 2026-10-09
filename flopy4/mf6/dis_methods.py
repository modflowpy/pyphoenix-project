from typing import TYPE_CHECKING, ClassVar

import numpy as np
from flopy.discretization import StructuredGrid as LegacyStructuredGrid

from flopy4.mf6.utils.grid import StructuredGrid

if TYPE_CHECKING:
    from flopy4.mf6.gwf.dis import Dis

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class DisMethods:
    """Methods for the generated structured discretizations (`Dis` in GWF,
    GWT, GWE and PRT); fields come from the DFN."""

    # DFN fields these methods use, checked against the DFNs at sync time.
    _requires: ClassVar[frozenset[str]] = frozenset(
        {
            "angrot",
            "botm",
            "crs",
            "delc",
            "delr",
            "idomain",
            "length_units",
            "ncol",
            "nlay",
            "nrow",
            "top",
            "xorigin",
            "yorigin",
        }
    )

    def to_grid(self: "Dis") -> StructuredGrid:  # type: ignore[misc]
        """Convert the discretization to a `StructuredGrid`."""
        nlay, nrow, ncol = self.nlay, self.nrow, self.ncol
        if nlay is None or nrow is None or ncol is None:
            raise ValueError("to_grid() needs nlay, nrow and ncol")
        top = np.asarray(self.top).reshape(nrow, ncol)
        botm = np.asarray(self.botm).reshape(nlay, nrow, ncol)
        idomain = (
            np.asarray(self.idomain).reshape(nlay, nrow, ncol) if self.idomain is not None else None
        )
        return StructuredGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=np.asarray(self.delr),
            delc=np.asarray(self.delc),
            top=top,
            botm=botm,
            idomain=idomain,
            angrot=self.angrot,
            crs=self.crs,
        )

    @classmethod
    def coerce(cls: type["Dis"], value) -> "Dis | None":  # type: ignore[misc]
        """Convert a `StructuredGrid` to a discretization; `None` for anything else."""
        return cls.from_grid(value) if isinstance(value, LegacyStructuredGrid) else None

    @classmethod
    def from_grid(cls: type["Dis"], grid: StructuredGrid) -> "Dis":  # type: ignore[misc]
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
        if grid.lenuni in _LENGTH_UNITS:
            kwargs["length_units"] = _LENGTH_UNITS[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return cls(**kwargs)
