from typing import TYPE_CHECKING

import numpy as np

from flopy4.mf6.utils.grid import VertexGrid

if TYPE_CHECKING:
    from flopy4.mf6.gwf.disv import Disv

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class DisvMethods:
    """Methods for the generated vertex discretizations (`Disv` in GWF, GWT,
    GWE and PRT); fields come from the DFN."""

    def grid_vertices(self: "Disv") -> list:  # type: ignore[misc]
        """`vertices` in flopy's grid format, `[[iv, xv, yv], ...]`."""
        return [[v.iv, v.xv, v.yv] for v in self.vertices or []]

    def grid_cell2d(self: "Disv") -> list:  # type: ignore[misc]
        """`cell2d` in flopy's grid format, `[[icell2d, xc, yc, ncvert,
        iv1, iv2, ...], ...]`."""
        return [[c.icell2d, c.xc, c.yc, len(c.icvert), *c.icvert] for c in self.cell2d or []]

    def to_grid(self: "Disv") -> VertexGrid:  # type: ignore[misc]
        """Convert the discretization to a `VertexGrid`."""
        nlay, ncpl = self.nlay, self.ncpl
        if nlay is None or ncpl is None:
            raise ValueError("to_grid() needs nlay and ncpl")
        return VertexGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            angrot=self.angrot,
            crs=self.crs,
            nlay=nlay,
            ncpl=ncpl,
            top=self.top,
            botm=np.asarray(self.botm).reshape(nlay, ncpl) if self.botm is not None else None,
            idomain=(
                np.asarray(self.idomain).reshape(nlay, ncpl) if self.idomain is not None else None
            ),
            vertices=self.grid_vertices(),
            cell2d=self.grid_cell2d(),
        )

    @classmethod
    def from_grid(cls: type["Disv"], grid: VertexGrid) -> "Disv":  # type: ignore[misc]
        """Create a discretization from a `VertexGrid`. Each cell's vertex
        ring is closed (its first vertex repeated last) if it isn't already."""
        cell2d = []
        for icell2d, xc, yc, _, *icvert in grid.cell2d:
            if icvert[0] != icvert[-1]:
                icvert.append(icvert[0])
            cell2d.append(cls.Cell2d(icell2d=icell2d, xc=xc, yc=yc, icvert=tuple(icvert)))
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nlay": grid.nlay,
            "ncpl": grid.ncpl,
            "nvert": grid.nvert,
            "top": grid.top,
            "botm": grid.botm,
            "idomain": np.asarray(grid.idomain) if grid.idomain is not None else None,
            # model (local) coordinates; xorigin/yorigin/angrot place them
            "vertices": [tuple(v[:3]) for v in grid._vertices],
            "cell2d": cell2d,
        }
        if grid.lenuni in _LENGTH_UNITS:
            kwargs["length_units"] = _LENGTH_UNITS[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return cls(**kwargs)
