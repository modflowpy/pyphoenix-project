from typing import TYPE_CHECKING

import numpy as np

from flopy4._imports import isinstance_of

if TYPE_CHECKING:
    from flopy4.mf6.olf.disv2d import Disv2d
    from flopy4.mf6.utils.grid import VertexGrid

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class Disv2dMethods:
    """Methods for the generated layerless vertex discretizations
    (`Disv2d` in OLF); fields come from the DFN.

    `to_grid()`/`from_grid()` map to/from `VertexGrid` via its `cell2d=`
    argument (the same `(icell2d, xc, yc, ncvert, icvert...)` shape as
    `Disv`'s own `Cell2d`, not `Disv1d`'s `cell1d`), with an implicit
    single layer -- the same mapping flopy3 itself uses for a `DISV2D`
    model's `.modelgrid` (`flopy.mf6.mfmodel.py`'s
    `DiscretizationType.DISV2D` branch). Unlike `Disv1dMethods`, there's
    no world-coordinate caveat here: `Cell2d` carries real `xc`/`yc`
    positions, so `VertexGrid`'s cell-center geometry is meaningful."""

    def grid_vertices(self: "Disv2d") -> list:  # type: ignore[misc]
        """`vertices` in flopy's grid format, `[[iv, xv, yv], ...]`."""
        return [[v.iv, v.xv, v.yv] for v in self.vertices or []]

    def grid_cell2d(self: "Disv2d") -> list:  # type: ignore[misc]
        """`cell2d` in flopy's grid format, `[[icell2d, xc, yc, ncvert,
        iv1, iv2, ...], ...]`."""
        return [[c.icell2d, c.xc, c.yc, len(c.icvert), *c.icvert] for c in self.cell2d or []]

    def to_grid(self: "Disv2d") -> "VertexGrid":  # type: ignore[misc]
        """Convert the discretization to a `VertexGrid` (1 implicit
        layer, no top)."""
        from flopy4.mf6.utils.grid import VertexGrid

        nodes = self.nodes
        if nodes is None:
            raise ValueError("to_grid() needs nodes")
        return VertexGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            angrot=self.angrot,
            crs=self.crs,
            nlay=1,
            ncpl=nodes,
            top=None,
            botm=np.asarray(self.bottom).reshape(1, nodes) if self.bottom is not None else None,
            idomain=(
                np.asarray(self.idomain).reshape(1, nodes) if self.idomain is not None else None
            ),
            vertices=self.grid_vertices(),
            cell2d=self.grid_cell2d(),
        )

    @classmethod
    def coerce(cls: type["Disv2d"], value) -> "Disv2d | None":  # type: ignore[misc]
        """Convert a single-layer, `cell2d`-form `VertexGrid` to a
        discretization; `None` for anything else."""
        if (
            isinstance_of(value, "flopy.discretization.vertexgrid", "VertexGrid")
            and getattr(value, "cell2d", None)
            and getattr(value, "nlay", None) == 1
        ):
            return cls.from_grid(value)
        return None

    @classmethod
    def from_grid(cls: type["Disv2d"], grid: "VertexGrid") -> "Disv2d":  # type: ignore[misc]
        """Create a discretization from a single-layer, `cell2d`-form
        `VertexGrid`. Each cell's vertex ring is closed (its first vertex
        repeated last) if it isn't already."""
        cell2d = []
        for icell2d, xc, yc, _, *icvert in grid.cell2d:
            if icvert[0] != icvert[-1]:
                icvert.append(icvert[0])
            cell2d.append(cls.Cell2d(icell2d=icell2d, xc=xc, yc=yc, icvert=tuple(icvert)))
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nodes": grid.ncpl,
            "nvert": grid.nvert,
            "bottom": np.asarray(grid.botm).reshape(-1),
            "idomain": (np.asarray(grid.idomain).reshape(-1) if grid.idomain is not None else None),
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
