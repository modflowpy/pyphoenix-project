from typing import TYPE_CHECKING

import numpy as np
from flopy.discretization.unstructuredgrid import UnstructuredGrid

if TYPE_CHECKING:
    from flopy4.mf6.gwf.disu import Disu


class DisuMethods:
    """Methods for the generated unstructured discretizations (`Disu` in GWF,
    GWT and GWE); fields come from the DFN."""

    def to_grid(self: "Disu") -> UnstructuredGrid:  # type: ignore[misc]
        """Convert the discretization to an `UnstructuredGrid`."""
        if self.nodes is None:
            raise ValueError("to_grid() needs nodes")
        cell2d = self.cell2d or []
        return UnstructuredGrid(
            vertices=[[v.iv, v.xv, v.yv] for v in self.vertices] if self.vertices else None,
            iverts=[list(c.icvert) for c in cell2d] if cell2d else None,
            xcenters=np.array([c.xc for c in cell2d]) if cell2d else None,
            ycenters=np.array([c.yc for c in cell2d]) if cell2d else None,
            top=np.asarray(self.top),
            botm=np.asarray(self.bot),
            idomain=np.asarray(self.idomain) if self.idomain is not None else None,
            lenuni=self.length_units,
            ncpl=np.array([self.nodes]),
            crs=self.crs,
            xoff=self.xorigin or 0.0,
            yoff=self.yorigin or 0.0,
            angrot=self.angrot or 0.0,
            iac=np.asarray(self.iac),
            # 1-based in the file, 0-based in flopy
            ja=np.asarray(self.ja) - 1,
            ihc=np.asarray(self.ihc),
        )
