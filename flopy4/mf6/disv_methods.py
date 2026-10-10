from abc import ABCMeta
from typing import TYPE_CHECKING, Any

import numpy as np
from flopy.discretization import VertexGrid as LegacyVertexGrid

from flopy4.mf6.utils.grid import VertexGrid

if TYPE_CHECKING:
    from flopy4.mf6.gwf.disv import Disv

_LENGTH_UNITS = {1: "FEET", 2: "METERS", 3: "CENTIMETERS"}


class _Cell2dRecord:
    """`Disv.Cell2dRecord`, the earlier name of `Disv.Cell2d`."""

    def __get__(self, instance: Any, owner: type) -> type:
        return owner.Cell2d  # type: ignore[attr-defined]


class _LegacyInputs(ABCMeta):
    """Accept the earlier array-style constructor inputs `iv`, `xv`, `yv` and
    `cell2ddata` (0-based) and convert them into `vertices` and `cell2d`,
    which are what `Disv` stores."""

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        iv, xv, yv, cell2ddata = (kwargs.pop(k, None) for k in ("iv", "xv", "yv", "cell2ddata"))
        if xv is not None or yv is not None or iv is not None:
            if xv is None or yv is None:
                raise ValueError("xv and yv are both required to build vertices from arrays")
            if kwargs.get("vertices") is not None:
                raise ValueError("give vertices, or iv/xv/yv, not both")
            xv, yv = np.asarray(xv, dtype=float), np.asarray(yv, dtype=float)
            iv = np.arange(len(xv)) if iv is None else np.asarray(iv)
            kwargs["vertices"] = [(int(i), float(x), float(y)) for i, x, y in zip(iv, xv, yv)]
        if cell2ddata is not None:
            if kwargs.get("cell2d") is not None:
                raise ValueError("give cell2d, or cell2ddata, not both")
            kwargs["cell2d"] = list(cell2ddata)
        return super().__call__(*args, **kwargs)


class DisvMethods(metaclass=_LegacyInputs):
    """Methods for the generated vertex discretizations (`Disv` in GWF, GWT,
    GWE and PRT); fields come from the DFN."""

    Cell2dRecord = _Cell2dRecord()

    @property
    def iv(self: "Disv") -> "np.ndarray | None":  # type: ignore[misc]
        """Vertex numbers (0-based), a view of `vertices`."""
        if self.vertices is None:
            return None
        return np.array([v.iv for v in self.vertices], dtype=np.int64)

    @property
    def xv(self: "Disv") -> "np.ndarray | None":  # type: ignore[misc]
        """Vertex x coordinates, a view of `vertices`."""
        if self.vertices is None:
            return None
        return np.array([v.xv for v in self.vertices], dtype=np.float64)

    @property
    def yv(self: "Disv") -> "np.ndarray | None":  # type: ignore[misc]
        """Vertex y coordinates, a view of `vertices`."""
        if self.vertices is None:
            return None
        return np.array([v.yv for v in self.vertices], dtype=np.float64)

    @property
    def cell2ddata(self: "Disv") -> "list | None":  # type: ignore[misc]
        """The cell records, an alias of `cell2d`."""
        return self.cell2d

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
    def coerce(cls: type["Disv"], value) -> "Disv | None":  # type: ignore[misc]
        """Convert a `VertexGrid` to a discretization; `None` for anything else."""
        return cls.from_grid(value) if isinstance(value, LegacyVertexGrid) else None

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
