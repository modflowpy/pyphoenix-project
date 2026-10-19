from typing import TYPE_CHECKING

import numpy as np

from flopy4._imports import isinstance_of

if TYPE_CHECKING:
    from flopy4.mf6.chf.disv1d import Disv1d
    from flopy4.mf6.utils.grid import VertexGrid

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class Disv1dMethods:
    """Methods for the generated 1D vertex (channel-network) discretizations
    (`Disv1d` in CHF, OLF); fields come from the DFN.

    `to_grid()`/`from_grid()` map to/from `VertexGrid` via its `cell1d=`
    argument, the same mapping flopy3 itself uses for a `DISV1D` model's
    `.modelgrid` (`flopy.mf6.mfmodel.py`'s `DiscretizationType.DISV1D`
    branch) -- there's no separate 1D grid class. Note: flopy3's own
    `cell1d`-based `xcellcenters`/`ycellcenters` (which `VertexGrid.__init__`
    calls to build its xarray coordinates) puts `fdc` and `ncvert` in as
    x/y, not real spatial coordinates -- a channel network's cells have no
    polygon centroid the way a 2D vertex grid's do. That's an upstream
    flopy3 limitation, not something fixed here; real world x/y for a
    channel network is a `follow-on` item alongside `Dis2d`/`Disv2d`."""

    def grid_vertices(self: "Disv1d") -> list:  # type: ignore[misc]
        """`vertices` in flopy's grid format, `[[iv, xv, yv], ...]`."""
        return [[v.iv, v.xv, v.yv] for v in self.vertices or []]

    def grid_cell1d(self: "Disv1d") -> list:  # type: ignore[misc]
        """`cell1d` in flopy's grid format, `[[icell1d, fdc, ncvert, iv1,
        iv2, ...], ...]`."""
        return [[c.icell1d, c.fdc, c.ncvert, *c.icvert] for c in self.cell1d or []]

    def to_grid(self: "Disv1d") -> "VertexGrid":  # type: ignore[misc]
        """Convert the discretization to a `VertexGrid` (its `cell1d`
        form)."""
        from flopy4.mf6.utils.grid import VertexGrid

        if self.nodes is None:
            raise ValueError("to_grid() needs nodes")
        return VertexGrid(
            length_units=self.length_units,
            xoff=self.xorigin,
            yoff=self.yorigin,
            angrot=self.angrot,
            crs=self.crs,
            top=None,
            botm=np.asarray(self.bottom) if self.bottom is not None else None,
            idomain=(np.asarray(self.idomain) if self.idomain is not None else None),
            vertices=self.grid_vertices(),
            cell1d=self.grid_cell1d(),
        )

    @classmethod
    def coerce(cls: type["Disv1d"], value) -> "Disv1d | None":  # type: ignore[misc]
        """Convert a `cell1d`-form `VertexGrid` to a discretization; `None`
        for anything else (including a `cell2d`-form `VertexGrid`)."""
        if isinstance_of(value, "flopy.discretization.vertexgrid", "VertexGrid") and getattr(
            value, "cell1d", None
        ):
            return cls.from_grid(value)
        return None

    @classmethod
    def from_grid(cls: type["Disv1d"], grid: "VertexGrid") -> "Disv1d":  # type: ignore[misc]
        """Create a discretization from a `cell1d`-form `VertexGrid`."""
        cell1d = [
            cls.Cell1d(icell1d=icell1d, fdc=fdc, ncvert=ncvert, icvert=tuple(icvert))
            for icell1d, fdc, ncvert, *icvert in grid.cell1d
        ]
        kwargs = {
            "xorigin": grid.xoffset,
            "yorigin": grid.yoffset,
            "nodes": len(cell1d),
            "nvert": grid.nvert,
            "bottom": grid.botm,
            "idomain": (np.asarray(grid.idomain) if grid.idomain is not None else None),
            # model (local) coordinates; xorigin/yorigin/angrot place them
            "vertices": [tuple(v[:3]) for v in grid._vertices],
            "cell1d": cell1d,
        }
        if grid.lenuni in _LENGTH_UNITS:
            kwargs["length_units"] = _LENGTH_UNITS[grid.lenuni]
        if grid.angrot:
            kwargs["angrot"] = grid.angrot
        if grid.crs is not None:
            kwargs["crs"] = f"EPSG:{grid.crs.to_epsg()}"
        return cls(**kwargs)
