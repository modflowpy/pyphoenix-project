import collections
from typing import Any

import numpy as np
from flopy.discretization import StructuredGrid


def get_coords(grid: StructuredGrid) -> dict[str, Any]:
    # unpack tuples
    xmin, xmax, ymin, ymax = grid.extent
    dx, dy = (grid.delr, -grid.delc)
    coords: collections.OrderedDict[str, Any] = collections.OrderedDict()
    # from cell size to x and y coordinates
    if isinstance(dx, (int, float, np.int_)):  # equidistant
        coords["x"] = np.arange(xmin + dx / 2.0, xmax, dx)
        coords["y"] = np.arange(ymax + dy / 2.0, ymin, dy)
        coords["dx"] = np.array(float(dx))
        coords["dy"] = np.array(float(dy))
    else:  # nonequidistant
        # even though IDF may store them as float32,
        # we always convert them to float64
        dx = dx.astype(np.float64)
        dy = dy.astype(np.float64)
        coords["x"] = xmin + np.cumsum(dx) - 0.5 * dx
        coords["y"] = ymax + np.cumsum(dy) - 0.5 * dy
        if np.allclose(dx, dx[0]) and np.allclose(dy, dy[0]):
            coords["dx"] = np.array(float(dx[0]))
            coords["dy"] = np.array(float(dy[0]))
        else:
            coords["dx"] = ("x", dx)
            coords["dy"] = ("y", dy)
    coords["layer"] = np.arange(1, grid.nlay + 1)
    return coords
