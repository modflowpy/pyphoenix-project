import collections
from typing import Any

import numpy as np
import xarray as xr
from attrs import fields
from flopy.discretization import StructuredGrid as LegacyStructuredGrid
from xarray.core.indexes import PandasIndex

from flopy4.mf6.constants import FILL_DNODATA


class StructuredGrid(LegacyStructuredGrid):
    """Extend flopy3's StructuredGrid"""

    # TODO de-duplicate array/dataset setup. no need to do it in both __init__ and properties

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dims_coords = {
            "nlay": "k",
            "nrow": "i",
            "ncol": "j",
            "nodes": "node",
        }

        # Compute world coordinates (x, y, z)
        world_coords = self._compute_world_coordinates()

        # Index coordinates
        self._coords = {
            "k": xr.DataArray(np.arange(self.nlay, dtype=int), dims=("nlay",)),
            "i": xr.DataArray(np.arange(self.nrow, dtype=int), dims=("nrow",)),
            "j": xr.DataArray(np.arange(self.ncol, dtype=int), dims=("ncol",)),
            "node": xr.DataArray(np.arange(self.nnodes, dtype=int), dims=("nodes",)),
        }

        # Add world coordinates
        self._coords.update(world_coords)

        data_vars = {
            "delr": self.delr,
            "delc": self.delc,
            "delz": self.delz,
            "top": self.top,
            "botm": self.botm,
            "idomain": self.idomain,
        }
        self._dataset = (
            xr.Dataset({k: v for k, v in data_vars.items() if v is not None}, coords=self._coords)
            .set_xindex("k", PandasIndex)
            .set_xindex("i", PandasIndex)
            .set_xindex("j", PandasIndex)
            .set_xindex("node", PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            .set_xindex("z", PandasIndex)
        )

    def _compute_world_coordinates(self) -> dict:
        """
        Compute x, y, z world coordinates from grid geometry.

        Returns
        -------
        dict
            Dictionary with 'x', 'y', 'z' coordinate DataArrays
        """
        # Get grid extent
        xmin, xmax, ymin, ymax = self.extent

        # Compute x coordinates (cell centers)
        delr = np.atleast_1d(self.delr[0] if hasattr(self.delr, '__getitem__') and not isinstance(self.delr, np.ndarray) else self.delr)
        if delr.size == 1:
            delr = np.full(self.ncol, delr[0])
        x = xmin + np.cumsum(delr) - 0.5 * delr

        # Compute y coordinates (cell centers)
        delc = np.atleast_1d(self.delc[0] if hasattr(self.delc, '__getitem__') and not isinstance(self.delc, np.ndarray) else self.delc)
        if delc.size == 1:
            delc = np.full(self.nrow, delc[0])
        y = ymax - np.cumsum(delc) + 0.5 * delc

        # Compute z coordinates (layer centers)
        # Use top and botm to compute layer centers
        top_2d = np.atleast_2d(self.top)
        botm_3d = np.atleast_3d(self.botm).reshape(self.nlay, self.nrow, self.ncol)

        # Layer center z coordinates: average of top and bottom per layer
        z = np.zeros(self.nlay)
        for k in range(self.nlay):
            if k == 0:
                layer_top = top_2d.mean()
            else:
                layer_top = botm_3d[k - 1].mean()
            layer_bot = botm_3d[k].mean()
            z[k] = (layer_top + layer_bot) / 2.0

        return {
            "x": xr.DataArray(x, dims=("ncol",)),
            "y": xr.DataArray(y, dims=("nrow",)),
            "z": xr.DataArray(z, dims=("nlay",)),
        }

    @property
    def dataset(self) -> xr.Dataset:
        return self._dataset

    @property
    def delc(self):
        if self.__delc is None:
            return None
        dims = ("ncol",)
        coord_name = self._dims_coords[dims[0]]
        coords = {coord_name: self._coords[coord_name], "x": self._coords["x"]}
        return xr.DataArray(super().delc, coords=coords, dims=dims).set_xindex(
            coord_name, PandasIndex
        ).set_xindex("x", PandasIndex)

    @property
    def delr(self):
        if self.__delr is None:
            return None
        dims = ("nrow",)
        coord_name = self._dims_coords[dims[0]]
        coords = {coord_name: self._coords[coord_name], "y": self._coords["y"]}
        return xr.DataArray(super().delr, coords=coords, dims=dims).set_xindex(
            coord_name, PandasIndex
        ).set_xindex("y", PandasIndex)

    @property
    def delz(self):
        dims = ("nlay", "nrow", "ncol")
        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(super().delz, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            .set_xindex("z", PandasIndex)
        )

    @property
    def top(self):
        dims = ("nrow", "ncol")
        coord_names = (self._dims_coords[dims[0]], self._dims_coords[dims[1]])
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"]})
        return (
            xr.DataArray(super().top, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
        )

    @property
    def botm(self):
        dims = ("nlay", "nrow", "ncol")
        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(super().botm, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            .set_xindex("z", PandasIndex)
        )

    @property
    def idomain(self):
        dims = ("nlay", "nrow", "ncol")
        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(super().idomain, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            .set_xindex("z", PandasIndex)
        )


def get_coords(grid: StructuredGrid) -> dict[str, Any]:
    # unpack tuples
    xmin, xmax, ymin, ymax = grid.extent
    dx, dy = (grid.delr, -grid.delc)  # type: ignore
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
