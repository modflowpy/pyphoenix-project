import collections
from typing import Any

import numpy as np
from attrs import fields
from flopy.discretization import StructuredGrid

from flopy4.mf6.constants import FILL_DNODATA


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


def update_maxbound(instance, attribute, new_value):
    """
    Generalized function to update maxbound when period block arrays change.

    This function automatically finds all period block arrays in the instance
    and calculates maxbound based on the maximum number of non-default values
    across all arrays.

    Args:
        instance: The package instance
        attribute: The attribute being set (from attrs on_setattr)
        new_value: The new value being set

    Returns:
        The new_value (unchanged)
    """

    period_arrays = []
    instance_fields = fields(instance.__class__)
    for f in instance_fields:
        if (
            f.metadata
            and f.metadata.get("block") == "period"
            and f.metadata.get("xattree", {}).get("dims")
        ):
            period_arrays.append(f.name)

    maxbound_values = []
    for array_name in period_arrays:
        if attribute and attribute.name == array_name:
            array_val = new_value
        else:
            array_val = getattr(instance, array_name, None)

        if array_val is not None:
            array_data = (
                array_val if array_val.data.shape == array_val.shape else array_val.todense()
            )

            if array_data.dtype.kind in ["U", "S"]:  # String arrays
                non_default_count = len(np.where(array_data != "")[0])
            else:  # Numeric arrays
                non_default_count = len(np.where(array_data != FILL_DNODATA)[0])

            maxbound_values.append(non_default_count)
    if maxbound_values:
        instance.maxbound = max(maxbound_values)

    return new_value
