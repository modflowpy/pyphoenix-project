from typing import TYPE_CHECKING

import numpy as np

from flopy4._imports import isinstance_of

if TYPE_CHECKING:
    from flopy4.mf6.olf.dis2d import Dis2d
    from flopy4.mf6.utils.grid import StructuredGrid

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class Dis2dMethods:
    """Methods for the generated layerless structured discretizations
    (`Dis2d` in OLF); fields come from the DFN.

    `to_grid()`/`from_grid()` map to/from `StructuredGrid` with an
    implicit single layer, the same mapping flopy3 itself uses for a
    `DIS2D` model's `.modelgrid` (`flopy.mf6.mfmodel.py`'s
    `DiscretizationType.DIS2D` branch) -- `Dis2d` has no `nlay`/`top` at
    all, unlike `Dis`."""

    def to_grid(self: "Dis2d") -> "StructuredGrid":  # type: ignore[misc]
        """Convert the discretization to a `StructuredGrid` (1 implicit
        layer, no top)."""
        from flopy4.mf6.utils.grid import StructuredGrid

        nrow, ncol = self.nrow, self.ncol
        if nrow is None or ncol is None:
            raise ValueError("to_grid() needs nrow and ncol")
        botm = np.asarray(self.bottom).reshape(1, nrow, ncol) if self.bottom is not None else None
        idomain = (
            np.asarray(self.idomain).reshape(1, nrow, ncol) if self.idomain is not None else None
        )
        return StructuredGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            nlay=1,
            nrow=nrow,
            ncol=ncol,
            delr=np.asarray(self.delr),
            delc=np.asarray(self.delc),
            top=None,
            botm=botm,
            idomain=idomain,
            angrot=self.angrot,
            crs=self.crs,
        )

    @classmethod
    def coerce(cls: type["Dis2d"], value) -> "Dis2d | None":  # type: ignore[misc]
        """Convert a single-layer `StructuredGrid` to a discretization;
        `None` for anything else (including a multi-layer one)."""
        if (
            isinstance_of(value, "flopy.discretization.structuredgrid", "StructuredGrid")
            and getattr(value, "nlay", None) == 1
        ):
            return cls.from_grid(value)
        return None

    @classmethod
    def from_grid(cls: type["Dis2d"], grid: "StructuredGrid") -> "Dis2d":  # type: ignore[misc]
        """Create a discretization from a single-layer `StructuredGrid`."""
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nrow": grid.nrow,
            "ncol": grid.ncol,
            "delr": grid.delr,
            "delc": grid.delc,
            "bottom": (np.asarray(grid.botm).reshape(-1) if grid.botm is not None else None),
            "idomain": (np.asarray(grid.idomain).reshape(-1) if grid.idomain is not None else None),
        }
        if grid.lenuni in _LENGTH_UNITS:
            kwargs["length_units"] = _LENGTH_UNITS[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return cls(**kwargs)
