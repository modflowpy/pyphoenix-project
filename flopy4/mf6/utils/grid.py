import collections
from typing import Any

import numpy as np
import xarray as xr
from attrs import fields
from flopy.discretization import StructuredGrid as LegacyStructuredGrid
from flopy.discretization import VertexGrid as LegacyVertexGrid
from xarray.core.indexes import PandasIndex
from xattree import Scalar

from flopy4.mf6.constants import FILL_DNODATA, FILL_INT64


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
            length_units=dis.length_units,
            xoff=dis.xorigin,
            yoff=dis.yorigin,
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
        self._legacy = False
        if (units := kwargs.pop("length_units", None)) is not None:
            kwargs["lenuni"] = units.lower()
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
    def legacy(self) -> bool:
        return self._legacy

    @legacy.setter
    def legacy(self, value):
        self._legacy = value

    @property
    def dataset(self) -> xr.Dataset:
        return self._dataset

    @property
    def delc(self):
        if self.legacy:
            return super().delc

        if self.__delc is None:
            return None
        dims = ("nrow",)
        coord_name = self._dims_coords[dims[0]]
        coords = {coord_name: self._coords[coord_name], "y": self._coords["y"]}
        return (
            xr.DataArray(super().delc, coords=coords, dims=dims)
            .set_xindex(coord_name, PandasIndex)
            .set_xindex("y", PandasIndex)
        )

    @property
    def delr(self):
        if self.legacy:
            return super().delr

        if self.__delr is None:
            return None
        dims = ("ncol",)
        coord_name = self._dims_coords[dims[0]]
        coords = {coord_name: self._coords[coord_name], "x": self._coords["x"]}
        return (
            xr.DataArray(super().delr, coords=coords, dims=dims)
            .set_xindex(coord_name, PandasIndex)
            .set_xindex("x", PandasIndex)
        )

    @property
    def delz(self):
        if self.legacy:
            return super().delz

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
        if self.legacy:
            return super().top

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
        if self.legacy:
            return super().botm

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
        if self.legacy:
            return super().idomain

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

    def latlon(self):
        try:
            import warnings

            from pyproj import Proj

            epsg = None
            if self.crs is not None:
                epsg = self.crs.to_epsg()

            proj = Proj(
                f"EPSG:{epsg}",
            )

            lats = []
            lons = []
            x_local = []
            y_local = []
            for y in self.xycenters[1]:
                for x in self.xycenters[0]:
                    x_local.append(x)
                    y_local.append(y)

            x_global, y_global = self.get_coords(x_local, y_local)

            for i, x in enumerate(x_global):
                lon, lat = proj(x, y_global[i], inverse=True)
                lats.append(lat)
                lons.append(lon)

            return np.array(lats), np.array(lons)

        except Exception as e:
            warnings.warn(
                f"Cannot create coordinates from CRS: {e}",
                UserWarning,
            )

            return None, None

    def to_xarray(self, modeltime=None, mesh_type=None, configuration=None):
        """
        modeltime : FloPy ModelTime object
        mesh_type : dataset mesh type
               valid mesh types are "layered" or None (i.e. "structured")
        configuration : configuration dictionary
        """
        self.legacy = True

        if modeltime is None:
            raise ValueError("modeltime required for dataset timeseries")

        ds = xr.Dataset()
        ds.attrs["modflow_grid"] = "STRUCTURED"

        if mesh_type and mesh_type.upper() == "LAYERED":
            ds = self._layered_mesh_dataset(ds, modeltime, configuration)
        elif mesh_type is None:
            ds = self._structured_dataset(ds, modeltime, configuration)

        self.legacy = False
        return ds

    def _layered_mesh_dataset(self, ds, modeltime=None, configuration=None):
        lenunits = {0: "u", 1: "ft", 2: "m", 3: "cm"}

        # create dataset coordinate vars
        var_d = {
            "time": (["time"], np.cumsum(modeltime.perlen)),
        }
        ds = ds.assign(var_d)
        ds["time"].attrs["calendar"] = "standard"
        ds["time"].attrs["units"] = f"{modeltime.time_units} since {modeltime.start_datetime}"
        ds["time"].attrs["axis"] = "T"
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs["long_name"] = "time"

        # mesh container variable
        ds = ds.assign({"mesh": ([], np.int64(1))})
        ds["mesh"].attrs["cf_role"] = "mesh_topology"
        ds["mesh"].attrs["long_name"] = "2D mesh topology"
        ds["mesh"].attrs["topology_dimension"] = np.int64(2)
        ds["mesh"].attrs["face_dimension"] = "nmesh_face"
        ds["mesh"].attrs["node_coordinates"] = "mesh_node_x mesh_node_y"
        ds["mesh"].attrs["face_coordinates"] = "mesh_face_x mesh_face_y"
        ds["mesh"].attrs["face_node_connectivity"] = "mesh_face_nodes"

        # mesh node x and y
        var_d = {
            "mesh_node_x": (["nmesh_node"], self.verts[:, 0]),
            "mesh_node_y": (["nmesh_node"], self.verts[:, 1]),
        }
        ds = ds.assign(var_d)
        ds["mesh_node_x"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_node_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_node_x"].attrs["long_name"] = "Easting"
        ds["mesh_node_y"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_node_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_node_y"].attrs["long_name"] = "Northing"

        # mesh face x and y
        x_bnds = []
        x_verts = self.verts[:, 0].reshape(self.nrow + 1, self.ncol + 1)
        for i in range(self.nrow):
            if i + 1 > self.nrow:
                break
            for j in range(self.ncol):
                if j + 1 <= self.ncol:
                    bnd = []
                    bnd.append(x_verts[i + 1][j])
                    bnd.append(x_verts[i + 1][j + 1])
                    bnd.append(x_verts[i][j + 1])
                    bnd.append(x_verts[i][j])
                    x_bnds.append(bnd)

        y_bnds = []
        y_verts = self.verts[:, 1].reshape(self.nrow + 1, self.ncol + 1)
        for i in range(self.nrow):
            if i + 1 > self.nrow:
                break
            for j in range(self.ncol):
                if j + 1 <= self.ncol:
                    bnd = []
                    bnd.append(y_verts[i + 1][j])
                    bnd.append(y_verts[i + 1][j + 1])
                    bnd.append(y_verts[i][j + 1])
                    bnd.append(y_verts[i][j])
                    y_bnds.append(bnd)

        var_d = {
            "mesh_face_x": (["nmesh_face"], self.xcellcenters.flatten()),
            "mesh_face_xbnds": (["nmesh_face", "max_nmesh_face_nodes"], x_bnds),
            "mesh_face_y": (["nmesh_face"], self.ycellcenters.flatten()),
            "mesh_face_ybnds": (["nmesh_face", "max_nmesh_face_nodes"], y_bnds),
        }
        ds = ds.assign(var_d)
        ds["mesh_face_x"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_face_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_face_x"].attrs["long_name"] = "Easting"
        ds["mesh_face_x"].attrs["bounds"] = "mesh_face_xbnds"
        ds["mesh_face_y"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_face_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_face_y"].attrs["long_name"] = "Northing"
        ds["mesh_face_y"].attrs["bounds"] = "mesh_face_ybnds"

        # mesh face nodes
        max_face_nodes = 4
        face_nodes = []
        for r in self.iverts:
            nodes = [np.int64(x + 1) for x in r]
            nodes.reverse()
            face_nodes.append(nodes)

        var_d = {
            "mesh_face_nodes": (["nmesh_face", "max_nmesh_face_nodes"], face_nodes),
        }
        ds = ds.assign(var_d)
        ds["mesh_face_nodes"].attrs["cf_role"] = "face_node_connectivity"
        ds["mesh_face_nodes"].attrs["long_name"] = "Vertices bounding cell (counterclockwise)"
        ds["mesh_face_nodes"].attrs["_FillValue"] = FILL_INT64
        ds["mesh_face_nodes"].attrs["start_index"] = np.int64(1)

        # create grid index auxiliary coordinate variables
        ds = ds.assign_coords(k=("z", np.arange(self.nlay, dtype=int)))
        ds = ds.assign_coords(i=("y", np.arange(self.nrow, dtype=int)))
        ds = ds.assign_coords(j=("x", np.arange(self.ncol, dtype=int)))
        ds = ds.set_xindex("k", PandasIndex)
        ds = ds.set_xindex("i", PandasIndex)
        ds = ds.set_xindex("j", PandasIndex)
        ds["k"].attrs["long_name"] = "layer index auxiliary coordinate"
        ds["i"].attrs["long_name"] = "row index auxiliary coordinate"
        ds["j"].attrs["long_name"] = "column index auxiliary coordinate"

        wkt_configured = (
            configuration is not None
            and "wkt" in configuration
            and configuration["wkt"] is not None
        )

        if wkt_configured or self.crs is not None:
            ds["mesh_node_x"].attrs["grid_mapping"] = "projection"
            ds["mesh_node_y"].attrs["grid_mapping"] = "projection"
            ds["mesh_face_x"].attrs["grid_mapping"] = "projection"
            ds["mesh_face_y"].attrs["grid_mapping"] = "projection"
            ds = ds.assign({"projection": ([], np.int64(1))})
            if wkt_configured:
                # wkt override to existing crs
                ds["projection"].attrs["wkt"] = configuration["wkt"]
            else:
                from pyproj.enums import WktVersion

                ds["projection"].attrs["wkt"] = self.crs.to_wkt(WktVersion.WKT1_GDAL)

        return ds

    def _structured_dataset(self, ds, modeltime=None, configuration=None):
        lenunits = {0: "u", 1: "ft", 2: "m", 3: "cm"}

        xc = self.xoffset + self.xycenters[0]
        yc = self.yoffset + self.xycenters[1]
        # z = [float(x) for x in range(1, self.nlay + 1)]

        # set coordinate var bounds
        x_bnds = []
        xv = self.xoffset + self.xyedges[0]
        for idx, val in enumerate(xv):
            if idx + 1 < len(xv):
                bnd = []
                bnd.append(xv[idx])
                bnd.append(xv[idx + 1])
                x_bnds.append(bnd)

        y_bnds = []
        yv = self.yoffset + self.xyedges[1]
        for idx, val in enumerate(yv):
            if idx + 1 < len(yv):
                bnd = []
                bnd.append(yv[idx + 1])
                bnd.append(yv[idx])
                y_bnds.append(bnd)

        # create dataset coordinate vars
        var_d = {
            "time": (["time"], np.cumsum(modeltime.perlen)),
            "y": (["y"], yc),
            "x": (["x"], xc),
        }
        ds = ds.assign_coords(var_d)

        # create grid index auxiliary coordinate variables
        ds = ds.assign_coords(k=("z", np.arange(self.nlay, dtype=int)))
        ds = ds.assign_coords(i=("y", np.arange(self.nrow, dtype=int)))
        ds = ds.assign_coords(j=("x", np.arange(self.ncol, dtype=int)))
        ds = ds.set_xindex("k", PandasIndex)
        ds = ds.set_xindex("i", PandasIndex)
        ds = ds.set_xindex("j", PandasIndex)
        ds["k"].attrs["long_name"] = "layer index auxiliary coordinate"
        ds["i"].attrs["long_name"] = "row index auxiliary coordinate"
        ds["j"].attrs["long_name"] = "column index auxiliary coordinate"

        # create bound vars
        var_d = {"x_bnds": (["x", "bnd"], x_bnds), "y_bnds": (["y", "bnd"], y_bnds)}
        ds = ds.assign(var_d)

        ds["time"].attrs["calendar"] = "standard"
        ds["time"].attrs["units"] = f"{modeltime.time_units} since {modeltime.start_datetime}"
        ds["time"].attrs["axis"] = "T"
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs["long_name"] = "time"
        ds["z"].attrs["units"] = "layer"
        ds["z"].attrs["long_name"] = "layer number"
        ds["y"].attrs["units"] = lenunits[self.lenuni]
        ds["y"].attrs["axis"] = "Y"
        ds["y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["y"].attrs["long_name"] = "Northing"
        ds["y"].attrs["bounds"] = "y_bnds"
        ds["x"].attrs["units"] = lenunits[self.lenuni]
        ds["x"].attrs["axis"] = "X"
        ds["x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["x"].attrs["long_name"] = "Easting"
        ds["x"].attrs["bounds"] = "x_bnds"

        latlon_cfg = (
            configuration is not None
            and "latitude" in configuration
            and configuration["latitude"] is not None
            and "longitude" in configuration
            and configuration["longitude"] is not None
        )

        lats = None
        lons = None
        if latlon_cfg:
            lats = configuration["latitude"]
            lons = configuration["longitude"]
        elif self.crs is not None:
            lats, lons = self.latlon()

        if lats is not None and lons is not None:
            # create coordinate vars
            var_d = {
                "lat": (["y", "x"], lats.reshape(yc.size, xc.size)),
                "lon": (["y", "x"], lons.reshape(yc.size, xc.size)),
            }
            ds = ds.assign(var_d)

            # set coordinate attributes
            ds["lat"].attrs["units"] = "degrees_north"
            ds["lat"].attrs["standard_name"] = "latitude"
            ds["lat"].attrs["long_name"] = "latitude"
            ds["lon"].attrs["units"] = "degrees_east"
            ds["lon"].attrs["standard_name"] = "longitude"
            ds["lon"].attrs["long_name"] = "longitude"

        elif (
            configuration is not None
            and "wkt" in configuration
            and configuration["wkt"] is not None
        ):
            ds["x"].attrs["grid_mapping"] = "projection"
            ds["y"].attrs["grid_mapping"] = "projection"
            ds = ds.assign({"projection": ([], np.int64(1))})
            ds["projection"].attrs["crs_wkt"] = configuration["wkt"]

        return ds


class VertexGrid(LegacyVertexGrid):
    """
    Extend flopy3's VertexGrid with xarray coordinate support.

    A vertex grid can be created in several ways:

    1. **Dimensions only** (abstract/index-based grid):
       - Required: nlay, ncpl
       - Uses unit spacing and default elevations

    2. **From discretization package**:
       - Use `dis.to_grid()` or `VertexGrid.from_dis(dis)`

    3. **Complete spatial definition**:
       - Required: nlay, ncpl, top, botm

    Optional parameters for all cases: idomain, xoff, yoff, angrot, lenuni, proj4, epsg
    """

    # TODO de-duplicate array/dataset setup. no need to do it in both __init__ and properties

    @classmethod
    def from_dis(cls, dis, **kwargs):
        """
        Create a VertexGrid from a Disv package.

        Parameters
        ----------
        dis : Disv
            A MODFLOW 6 Disv package

        Returns
        -------
        VertexGrid
            A vertex grid with the same geometry as the Disv package

        Examples
        --------
        >>> from flopy4.mf6.gwf.disv import Disv
        >>> dis = Disv(nlay=3, ncpl=1, nvert=4, top=30.0, botm=[20.0, 10.0, 0.0]
        ...            iv=[0, 1, 2, 3], xv=[0.0, 0.0, 1.0, 1.0], yv=[0.0, 1.0, 1.0, 0.0],
        ...            cell2ddata=[Disv.Cell2dRecord(
        ...                 0, 0.50000000, 0.50000000, 5, (0, 1, 2, 3, 0)
        ...            )]
        >>> grid = VertexGrid.from_dis(dis)
        """
        return cls(
            length_units=dis.length_units,
            nlay=dis.nlay,
            ncpl=dis.ncpl,
            top=dis.top,
            botm=dis.botm,
            idomain=getattr(dis, "idomain", None),
            iv=dis.iv,
            xv=dis.xv,
            yv=dis.yv,
            cell2d=dis.disv_to_grid_cell2d(dis.cell2ddata),
            **kwargs,
        )

    def __init__(self, *args, **kwargs):
        # Convert scalar inputs to arrays to support the legacy grid
        self._legacy = False
        if (units := kwargs.pop("length_units", None)) is not None:
            kwargs["lenuni"] = units.lower()
        if (top := kwargs.get("top", None)) is not None and isinstance(top, Scalar):
            ncpl = kwargs.get("ncpl", None)
            kwargs["top"] = np.full((ncpl), float(top))

        if (botm := kwargs.get("botm", None)) is not None:
            if isinstance(botm, (list, tuple)) and all(isinstance(b, Scalar) for b in botm):
                nlay = kwargs.get("nlay", len(botm))
                ncpl = kwargs.get("ncpl", None)
                kwargs["botm"] = np.array([np.full((ncpl), float(b)) for b in botm])

        if "iv" in kwargs and "xv" in kwargs and "yv" in kwargs:
            kwargs["vertices"] = []
            for i in range(len(kwargs["iv"].values)):
                vert = []
                vert.append(kwargs["iv"].values[i])
                vert.append(kwargs["xv"].values[i])
                vert.append(kwargs["yv"].values[i])
                kwargs["vertices"].append(vert)
            kwargs.pop("iv")
            kwargs.pop("xv")
            kwargs.pop("yv")

        super().__init__(*args, **kwargs)
        self._dims_coords = {
            "nlay": "k",
            "ncpl": "icpl",
            "nodes": "node",
        }
        self._coords = {
            "k": xr.DataArray(np.arange(self.nlay, dtype=int), dims=("nlay",)),
            "icpl": xr.DataArray(np.arange(self.ncpl, dtype=int), dims=("ncpl",)),
            "node": xr.DataArray(np.arange(self.nnodes, dtype=int), dims=("nodes",)),
        }
        self._coords.update(self._get_world_coords())

        data_vars = {}
        for prop_name in ["top", "botm", "idomain"]:
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
            .set_xindex("icpl", PandasIndex)
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
        # Access the parent class's properties directly
        self.legacy = True
        xcellcenters = self.xcellcenters
        ycellcenters = self.ycellcenters
        legacy_top = self.top
        legacy_botm = self.botm
        self.legacy = False

        # If spatial data is not provided, use default coordinates (indices)
        if xcellcenters is None:
            x = np.arange(self.ncpl, dtype=float)
        else:
            x = xcellcenters

        if ycellcenters is None:
            y = np.arange(self.ncpl, dtype=float)
        else:
            y = ycellcenters

        # Compute z coordinates (cell centers in 3D)
        if legacy_top is None or legacy_botm is None:
            # Use default z coordinates (layer indices)
            z = np.zeros((self.nlay, self.ncpl))
            for k in range(self.nlay):
                z[k, :] = float(k)
        else:
            # Ensure top and botm are proper arrays
            top_1d = np.atleast_1d(legacy_top)
            if top_1d.size == 1:
                top_1d = np.full((self.ncpl), top_1d[0])
            elif top_1d.shape != (self.ncpl):
                top_1d = top_1d.reshape(self.ncpl)

            botm_2d = np.atleast_2d(legacy_botm).reshape(self.nlay, self.ncpl)

            # Compute cell-centered z for each cell
            z = np.zeros((self.nlay, self.ncpl))
            for k in range(self.nlay):
                if k == 0:
                    layer_top = top_1d
                else:
                    layer_top = botm_2d[k - 1]
                layer_bot = botm_2d[k]
                z[k] = (layer_top + layer_bot) / 2.0

        return {
            "x": xr.DataArray(x, dims=("ncpl",)),
            "y": xr.DataArray(y, dims=("ncpl",)),
            "z": xr.DataArray(z, dims=("nlay", "ncpl")),
        }

    @property
    def legacy(self) -> bool:
        return self._legacy

    @legacy.setter
    def legacy(self, value):
        self._legacy = value

    @property
    def dataset(self) -> xr.Dataset:
        return self._dataset

    @property
    def delz(self):
        if self.legacy:
            return super().delz

        legacy_delz = super().delz
        if legacy_delz is None:
            return None

        dims = ("nlay", "ncpl")
        # Check if data shape matches expected grid dimensions
        if legacy_delz.shape != (self.nlay, self.ncpl):
            return legacy_delz

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_delz, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    @property
    def top(self):
        if self.legacy:
            return super().top

        legacy_top = super().top
        if legacy_top is None:
            return None

        dims = "ncpl"
        # Check if data shape matches expected grid dimensions
        # If not, return the raw legacy data without coordinates
        if legacy_top.shape != (self.ncpl):
            return legacy_top

        coord_names = self._dims_coords[dims[0]]
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
        if self.legacy:
            return super().botm

        legacy_botm = super().botm
        if legacy_botm is None:
            return None

        dims = ("nlay", "ncpl")
        # Check if data shape matches expected grid dimensions
        if legacy_botm.shape != (self.nlay, self.ncpl):
            return legacy_botm

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_botm, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    @property
    def idomain(self):
        if self.legacy:
            return super().idomain

        legacy_idomain = super().idomain
        # return legacy_idomain
        if legacy_idomain is None:
            return None

        dims = ("nlay", "ncpl")
        # Check if data shape matches expected grid dimensions
        if legacy_idomain.shape != (self.nlay, self.ncpl):
            return legacy_idomain

        coord_names = (
            self._dims_coords[dims[0]],
            self._dims_coords[dims[1]],
        )
        coords = {coord_name: self._coords[coord_name] for coord_name in coord_names}
        coords.update({"x": self._coords["x"], "y": self._coords["y"], "z": self._coords["z"]})
        return (
            xr.DataArray(legacy_idomain, coords=coords, dims=dims)
            .set_xindex(coord_names[0], PandasIndex)
            .set_xindex(coord_names[1], PandasIndex)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    def to_xarray(self, modeltime=None, mesh_type=None, configuration=None):
        """
        modeltime : FloPy ModelTime object
        mesh_type : dataset mesh type
               valid mesh types are "layered" or None (i.e. "structured")
               VertexGrid objects only support layered mesh
        configuration : configuration dictionary
        """
        self.legacy = True

        lenunits = {0: "u", 1: "ft", 2: "m", 3: "cm"}

        if mesh_type is None or mesh_type.upper() != "LAYERED":
            raise ValueError("Vextex grid only supports layered mesh datasets")

        if modeltime is None:
            raise ValueError("modeltime required for dataset timeseries")

        ds = xr.Dataset()
        ds.attrs["modflow_grid"] = "VERTEX"

        # create dataset coordinate vars
        var_d = {
            "time": (["time"], modeltime.totim),
        }
        ds = ds.assign(var_d)
        ds["time"].attrs["calendar"] = "standard"
        ds["time"].attrs["units"] = f"{modeltime.time_units} since {modeltime.start_datetime}"
        ds["time"].attrs["axis"] = "T"
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs["long_name"] = "time"

        # mesh container variable
        ds = ds.assign({"mesh": ([], np.int64(1))})
        ds["mesh"].attrs["cf_role"] = "mesh_topology"
        ds["mesh"].attrs["long_name"] = "2D mesh topology"
        ds["mesh"].attrs["topology_dimension"] = np.int64(2)
        ds["mesh"].attrs["face_dimension"] = "nmesh_face"
        ds["mesh"].attrs["node_coordinates"] = "mesh_node_x mesh_node_y"
        ds["mesh"].attrs["face_coordinates"] = "mesh_face_x mesh_face_y"
        ds["mesh"].attrs["face_node_connectivity"] = "mesh_face_nodes"

        # mesh node x and y
        var_d = {
            "mesh_node_x": (["nmesh_node"], self.verts[:, 0]),
            "mesh_node_y": (["nmesh_node"], self.verts[:, 1]),
        }
        ds = ds.assign(var_d)
        ds["mesh_node_x"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_node_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_node_x"].attrs["long_name"] = "Easting"
        ds["mesh_node_y"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_node_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_node_y"].attrs["long_name"] = "Northing"

        # determine max number of cell vertices
        # cell_nverts = [cell2d[3] for cell2d in self.cell2d]
        cell_nverts = [len(cell2d) - 3 for cell2d in self.cell2d]
        max_face_nodes = max(cell_nverts)

        # mesh face x and y
        x_bnds = []
        for x in self.xvertices:
            x = x[::-1]
            if len(x) < max_face_nodes:
                # TODO: set fill value?
                x.extend([FILL_INT64] * (max_face_nodes - len(x)))
            x_bnds.append(x)

        y_bnds = []
        for y in self.yvertices:
            y = y[::-1]
            if len(y) < max_face_nodes:
                # TODO: set fill value?
                y.extend([FILL_INT64] * (max_face_nodes - len(y)))
            y_bnds.append(y)

        var_d = {
            "mesh_face_x": (["nmesh_face"], self.xcellcenters),
            "mesh_face_xbnds": (["nmesh_face", "max_nmesh_face_nodes"], x_bnds),
            "mesh_face_y": (["nmesh_face"], self.ycellcenters),
            "mesh_face_ybnds": (["nmesh_face", "max_nmesh_face_nodes"], y_bnds),
        }
        ds = ds.assign(var_d)
        ds["mesh_face_x"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_face_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_face_x"].attrs["long_name"] = "Easting"
        ds["mesh_face_x"].attrs["bounds"] = "mesh_face_xbnds"
        ds["mesh_face_y"].attrs["units"] = lenunits[self.lenuni]
        ds["mesh_face_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_face_y"].attrs["long_name"] = "Northing"
        ds["mesh_face_y"].attrs["bounds"] = "mesh_face_ybnds"

        # mesh face nodes
        face_nodes = []
        for idx, r in enumerate(self.cell2d):
            nodes = self.cell2d[idx][3:]
            nodes = [np.int64(x + 1) for x in nodes]
            nodes.reverse()
            if nodes[0] == nodes[-1]:
                nodes.pop()
            if len(nodes) < max_face_nodes:
                # TODO set fill value?
                nodes.extend([FILL_INT64] * (max_face_nodes - len(nodes)))
            face_nodes.append(nodes)

        var_d = {
            "mesh_face_nodes": (["nmesh_face", "max_nmesh_face_nodes"], face_nodes),
        }
        ds = ds.assign(var_d)
        ds["mesh_face_nodes"].attrs["cf_role"] = "face_node_connectivity"
        ds["mesh_face_nodes"].attrs["long_name"] = "Vertices bounding cell (counterclockwise)"
        ds["mesh_face_nodes"].attrs["_FillValue"] = FILL_INT64
        ds["mesh_face_nodes"].attrs["start_index"] = np.int64(1)

        # create grid index auxiliary coordinate variables
        ds = ds.assign_coords(k=("z", np.arange(self.nlay, dtype=int)))
        ds = ds.assign_coords(icpl=("nmesh_face", np.arange(self.ncpl, dtype=int)))
        ds = ds.set_xindex("k", PandasIndex)
        ds = ds.set_xindex("icpl", PandasIndex)
        ds["k"].attrs["long_name"] = "layer index auxiliary coordinate"
        ds["icpl"].attrs["long_name"] = "cell index auxiliary coordinate"

        wkt_configured = (
            configuration is not None
            and "wkt" in configuration
            and configuration["wkt"] is not None
        )

        if wkt_configured or self.crs is not None:
            ds["mesh_node_x"].attrs["grid_mapping"] = "projection"
            ds["mesh_node_y"].attrs["grid_mapping"] = "projection"
            ds["mesh_face_x"].attrs["grid_mapping"] = "projection"
            ds["mesh_face_y"].attrs["grid_mapping"] = "projection"
            ds = ds.assign({"projection": ([], np.int64(1))})
            if wkt_configured:
                # wkt override to existing crs
                ds["projection"].attrs["wkt"] = configuration["wkt"]
            else:
                from pyproj.enums import WktVersion

                ds["projection"].attrs["wkt"] = self.crs.to_wkt(WktVersion.WKT1_GDAL)

        self.legacy = False
        return ds


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
            # Check if the underlying data is sparse and densify if needed
            import sparse

            if isinstance(array_val.data, sparse.SparseArray):
                array_data = array_val.data.todense()
            else:
                # Convert to numpy array to handle memoryview and other array-like objects
                array_data = np.asarray(array_val.data)

            if array_data.dtype.kind in ["U", "S"]:  # String arrays
                non_default_count = len(np.where(array_data != "")[0])
            else:  # Numeric arrays
                non_default_count = len(np.where(array_data != FILL_DNODATA)[0])

            maxbound_values.append(non_default_count)
    if maxbound_values:
        instance.maxbound = max(maxbound_values)

    return new_value
