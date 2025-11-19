import collections
from typing import Any

import numpy as np
import xarray as xr
from attrs import fields
from flopy.discretization import StructuredGrid as LegacyStructuredGrid
from xarray.core.indexes import PandasIndex
from xattree import Scalar

from flopy4.mf6.constants import FILL_DNODATA


class StructuredGrid(LegacyStructuredGrid):
    """
    Extend flopy3's StructuredGrid with xarray coordinate support.

    A structured grid can be created in several ways:

    1. **Dimensions only** (abstract/index-based grid):
       - Required: nlay, nrow, ncol
       - Uses unit spacing and default elevations

    2. **Uniform grid** (recommended via classmethod):
       - Use `StructuredGrid.uniform(nlay, nrow, ncol, delr, delc, top, thickness)`

    3. **From discretization package**:
       - Use `dis.to_grid()` or `StructuredGrid.from_dis(dis)`

    4. **Complete spatial definition**:
       - Required: nlay, nrow, ncol, delr, delc, top, botm

    Optional parameters for all cases: idomain, xoff, yoff, angrot, lenuni, proj4, epsg
    """

    # TODO de-duplicate array/dataset setup. no need to do it in both __init__ and properties

    @classmethod
    def uniform(
        cls,
        nlay: int,
        nrow: int,
        ncol: int,
        delr: float = 1.0,
        delc: float = 1.0,
        top: float = 1.0,
        thickness: float = 1.0,
        **kwargs,
    ):
        """
        Create a uniform structured grid with constant spacing and layer thickness.

        Parameters
        ----------
        nlay : int
            Number of layers
        nrow : int
            Number of rows
        ncol : int
            Number of columns
        delr : float, default 1.0
            Cell width along rows (constant)
        delc : float, default 1.0
            Cell width along columns (constant)
        top : float, default 1.0
            Top elevation (constant across all cells)
        thickness : float, default 1.0
            Layer thickness (constant for all layers)
        **kwargs
            Additional parameters: idomain, xoff, yoff, angrot, lenuni, proj4, epsg

        Returns
        -------
        StructuredGrid
            A uniform structured grid

        Examples
        --------
        >>> grid = StructuredGrid.uniform(3, 10, 10, delr=100.0, delc=100.0,
        ...                                top=10.0, thickness=5.0)
        """
        return cls(
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=delr,
            delc=delc,
            top=top,
            botm=[top - thickness * (i + 1) for i in range(nlay)],
            **kwargs,
        )

    @classmethod
    def from_dis(cls, dis):
        """
        Create a StructuredGrid from a Dis package.

        Parameters
        ----------
        dis : Dis
            A MODFLOW 6 discretization package

        Returns
        -------
        StructuredGrid
            A structured grid with the same geometry as the Dis package

        Examples
        --------
        >>> from flopy4.mf6.gwf.dis import Dis
        >>> dis = Dis(nlay=3, nrow=10, ncol=10, delr=100.0, delc=100.0,
        ...           top=10.0, botm=[0.0, -10.0, -20.0])
        >>> grid = StructuredGrid.from_dis(dis)
        """
        return cls(
            nlay=dis.nlay,
            nrow=dis.nrow,
            ncol=dis.ncol,
            delr=dis.delr,
            delc=dis.delc,
            top=dis.top,
            botm=dis.botm,
            idomain=getattr(dis, "idomain", None),
        )

    def __init__(self, *args, **kwargs):
        # Convert scalar inputs to arrays to support the legacy grid
        # The legacy StructuredGrid doesn't handle scalar top/botm well
        if (top := kwargs.get("top", None)) is not None and isinstance(top, Scalar):
            nrow = kwargs.get("nrow", 1)
            ncol = kwargs.get("ncol", 1)
            kwargs["top"] = np.full((nrow, ncol), float(top))

        if (botm := kwargs.get("botm", None)) is not None:
            if isinstance(botm, (list, tuple)) and all(isinstance(b, Scalar) for b in botm):
                nlay = kwargs.get("nlay", len(botm))
                nrow = kwargs.get("nrow", 1)
                ncol = kwargs.get("ncol", 1)
                kwargs["botm"] = np.array([np.full((nrow, ncol), float(b)) for b in botm])

        if (delr := kwargs.get("delr", None)) is not None and isinstance(delr, Scalar):
            ncol = kwargs.get("ncol", 1)
            kwargs["delr"] = np.full(ncol, float(delr))

        if (delc := kwargs.get("delc", None)) is not None and isinstance(delc, Scalar):
            nrow = kwargs.get("nrow", 1)
            kwargs["delc"] = np.full(nrow, float(delc))

        super().__init__(*args, **kwargs)
        self._dims_coords = {
            "nlay": "k",
            "nrow": "i",
            "ncol": "j",
            "nodes": "node",
        }
        self._coords = {
            "k": xr.DataArray(np.arange(self.nlay, dtype=int), dims=("nlay",)),
            "i": xr.DataArray(np.arange(self.nrow, dtype=int), dims=("nrow",)),
            "j": xr.DataArray(np.arange(self.ncol, dtype=int), dims=("ncol",)),
            "node": xr.DataArray(np.arange(self.nnodes, dtype=int), dims=("nodes",)),
        }
        self._coords.update(self._get_world_coords())

        data_vars = {}
        for prop_name in ["delr", "delc", "delz", "top", "botm", "idomain"]:
            try:
                prop_value = getattr(self, prop_name)
                if prop_value is not None:
                    data_vars[prop_name] = prop_value
            except (AttributeError, ValueError):
                # Property doesn't exist or can't be computed yet
                pass

        self._dataset = (
            xr.Dataset(data_vars, coords=self._coords)
            # TODO: alias k/i/j to lay(er)/row/col(umn)?
            .set_xindex("k", PandasIndex)
            .set_xindex("i", PandasIndex)
            .set_xindex("j", PandasIndex)
            .set_xindex("node", PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is a 3D non-dimension coordinate, so it doesn't get indexed
        )

    def _get_world_coords(self) -> dict:
        """
        Compute x, y, z world coordinates from grid geometry.

        Returns
        -------
        dict
            Dictionary with 'x', 'y', 'z' coordinate DataArrays
        """
        # Access the parent class's properties directly to get delr, delc, top, botm
        # Use LegacyStructuredGrid.delr.fget to avoid triggering our overridden property
        legacy_delr = LegacyStructuredGrid.delr.fget(self)
        legacy_delc = LegacyStructuredGrid.delc.fget(self)
        legacy_top = LegacyStructuredGrid.top.fget(self)
        legacy_botm = LegacyStructuredGrid.botm.fget(self)

        # If spatial data is not provided, use default coordinates (indices)
        # This handles grids created with only dimensions (nlay, nrow, ncol)
        if legacy_delr is None:
            x = np.arange(self.ncol, dtype=float)
        else:
            # Compute x coordinates (cell centers)
            delr = np.atleast_1d(legacy_delr)
            if delr.size == 1:
                delr = np.full(self.ncol, delr[0])
            x = self._xoff + np.cumsum(delr) - 0.5 * delr

        if legacy_delc is None:
            y = np.arange(self.nrow, dtype=float)
        else:
            # Compute y coordinates (cell centers)
            delc = np.atleast_1d(legacy_delc)
            if delc.size == 1:
                delc = np.full(self.nrow, delc[0])
            # Calculate ymax from grid dimensions
            ymax = self._yoff + np.sum(delc)
            y = ymax - np.cumsum(delc) + 0.5 * delc

        # Compute z coordinates (cell centers in 3D)
        if legacy_top is None or legacy_botm is None:
            # Use default z coordinates (layer indices)
            z = np.zeros((self.nlay, self.nrow, self.ncol))
            for k in range(self.nlay):
                z[k, :, :] = float(k)
        else:
            # Ensure top and botm are proper arrays
            top_2d = np.atleast_2d(legacy_top)
            if top_2d.size == 1:
                top_2d = np.full((self.nrow, self.ncol), top_2d[0, 0])
            elif top_2d.shape != (self.nrow, self.ncol):
                top_2d = top_2d.reshape(self.nrow, self.ncol)

            botm_3d = np.atleast_3d(legacy_botm).reshape(self.nlay, self.nrow, self.ncol)

            # Compute cell-centered z for each cell
            z = np.zeros((self.nlay, self.nrow, self.ncol))
            for k in range(self.nlay):
                if k == 0:
                    layer_top = top_2d
                else:
                    layer_top = botm_3d[k - 1]
                layer_bot = botm_3d[k]
                z[k] = (layer_top + layer_bot) / 2.0

        return {
            "x": xr.DataArray(x, dims=("ncol",)),
            "y": xr.DataArray(y, dims=("nrow",)),
            "z": xr.DataArray(z, dims=("nlay", "nrow", "ncol")),
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
        return (
            xr.DataArray(super().delc, coords=coords, dims=dims)
            .set_xindex(coord_name, PandasIndex)
            .set_xindex("x", PandasIndex)
        )

    @property
    def delr(self):
        if self.__delr is None:
            return None
        dims = ("nrow",)
        coord_name = self._dims_coords[dims[0]]
        coords = {coord_name: self._coords[coord_name], "y": self._coords["y"]}
        return (
            xr.DataArray(super().delr, coords=coords, dims=dims)
            .set_xindex(coord_name, PandasIndex)
            .set_xindex("y", PandasIndex)
        )

    @property
    def delz(self):
        legacy_delz = super().delz
        if legacy_delz is None:
            return None

        dims = ("nlay", "nrow", "ncol")
        # Check if data shape matches expected grid dimensions
        if legacy_delz.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_delz

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_delz, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    @property
    def top(self):
        legacy_top = super().top
        if legacy_top is None:
            return None

        dims = ("nrow", "ncol")
        # Check if data shape matches expected grid dimensions
        # If not, return the raw legacy data without coordinates
        if legacy_top.shape != (self.nrow, self.ncol):
            return legacy_top

        coord_names = (self._dims_coords[dims[0]], self._dims_coords[dims[1]])
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"]})
        return (
            xr.DataArray(legacy_top, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
        )

    @property
    def botm(self):
        legacy_botm = super().botm
        if legacy_botm is None:
            return None

        dims = ("nlay", "nrow", "ncol")
        # Check if data shape matches expected grid dimensions
        if legacy_botm.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_botm

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_botm, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    @property
    def idomain(self):
        legacy_idomain = super().idomain
        if legacy_idomain is None:
            return None

        dims = ("nlay", "nrow", "ncol")
        # Check if data shape matches expected grid dimensions
        if legacy_idomain.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_idomain

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
            self._dims_coords[dims[2]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_idomain, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex(coord_names[2], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
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
