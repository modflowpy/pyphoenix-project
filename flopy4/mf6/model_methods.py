from typing import Any

from flopy.discretization.grid import Grid


class ModelMethods:
    """Methods for the generated models; fields come from the DFN."""

    @property
    def grid(self) -> Grid | None:
        """The model's grid, from its discretization package."""
        dis: Any = getattr(self, "dis", None)
        return dis.to_grid() if dis is not None else None
