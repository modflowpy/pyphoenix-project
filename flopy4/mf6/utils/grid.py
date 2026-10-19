from typing import Any

import numpy as np
import xarray as xr
import xugrid as xu
from flopy.discretization import StructuredGrid as LegacyStructuredGrid
from flopy.discretization import VertexGrid as LegacyVertexGrid
from xarray.core.indexes import PandasIndex
from xarray.core.indexing import IndexSelResult
from xarray.core.variable import Variable

from flopy4.mf6._types import Scalar
from flopy4.mf6.constants import FILL_FLOAT64, FILL_INT64
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.utils.vertical import sel_z, z_coords


def _coord_units(lenuni: int, crs) -> str | None:
    """Return a CF-valid coordinate units string, or None to omit the attribute.

    Priority: explicit lenuni → CRS linear unit via pyproj → omit.
    Never writes "unknown".
    """
    _lenunits = {1: "ft", 2: "m", 3: "cm"}
    if lenuni in _lenunits:
        return _lenunits[lenuni]
    if crs is not None:
        try:
            from pyproj import CRS as ProjCRS

            unit = ProjCRS.from_user_input(crs).axis_info[0].unit_name.lower()
            return {"metre": "m", "meter": "m", "foot": "ft", "feet": "ft"}.get(unit, unit)
        except Exception:
            pass
    return None


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
            angrot=getattr(dis, "angrot", None),
            crs=dis.crs,
            nlay=dis.nlay,
            nrow=dis.nrow,
            ncol=dis.ncol,
            delr=dis.delr,
            delc=dis.delc,
            top=dis.top.reshape(dis.nrow, dis.ncol)
            if hasattr(dis.top, "reshape") and dis.top.ndim == 1
            else dis.top,
            botm=dis.botm.reshape(dis.nlay, dis.nrow, dis.ncol)
            if hasattr(dis.botm, "reshape") and dis.botm.ndim == 1
            else dis.botm,
            idomain=getattr(dis, "idomain", None),
        )

    def __init__(self, *args, **kwargs):
        # Convert scalar inputs to arrays to support the legacy grid
        # The legacy StructuredGrid doesn't handle scalar top/botm well
        self._legacy = False
        if (units := kwargs.pop("length_units", None)) is not None:
            kwargs["lenuni"] = units.lower()
        if (xoff := kwargs.pop("xoff", None)) is not None:
            kwargs["xoff"] = xoff
        else:
            kwargs["xoff"] = 0.0
        if (yoff := kwargs.pop("yoff", None)) is not None:
            kwargs["yoff"] = yoff
        else:
            kwargs["yoff"] = 0.0
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

        if (delr := kwargs.get("delr", None)) is not None:
            if isinstance(delr, Scalar):
                ncol = kwargs.get("ncol", 1)
                kwargs["delr"] = np.full(ncol, float(delr))
            else:
                kwargs["delr"] = np.asarray(delr)

        if (delc := kwargs.get("delc", None)) is not None:
            if isinstance(delc, Scalar):
                nrow = kwargs.get("nrow", 1)
                kwargs["delc"] = np.full(nrow, float(delc))
            else:
                kwargs["delc"] = np.asarray(delc)

        super().__init__(*args, **kwargs)
        # Dims are the grid's axes (layer, row, col), and carry no index
        # coordinates: a position is the index (isel), and k would clash
        # with NPF's k. The DFNs' sizing names are in dims.
        self._coords = self._get_world_coords()

        data_vars = {}
        for prop_name in ["delr", "delc", "delz", "top", "botm", "idomain"]:
            try:
                prop_value = getattr(self, prop_name)
                if prop_value is not None:
                    data_vars[prop_name] = prop_value
            except (AttributeError, ValueError):
                # Property doesn't exist or can't be computed yet
                pass

        # z is a 3D non-dimension coordinate, so it doesn't get indexed
        self._dataset = index_xy(xr.Dataset(data_vars, coords=self._coords))

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
        sizes: dict[str, Any] = {}
        if legacy_delr is None or legacy_delc is None:
            xy = {
                "x": ("col", np.arange(self.ncol, dtype=float)),
                "y": ("row", np.arange(self.nrow, dtype=float)),
            }
        else:
            delr = np.broadcast_to(np.asarray(legacy_delr, dtype=np.float64), (self.ncol,))
            delc = np.broadcast_to(np.asarray(legacy_delc, dtype=np.float64), (self.nrow,))
            xy = structured_centers(delr, delc, self._xoff, self._yoff, self.angrot)
            sizes = cell_sizes(delr, delc)

        # Cell elevations: centres z, and tops and bottoms z_top/z_bot for
        # selecting by elevation (see flopy4.mf6.utils.vertical). Without
        # top/botm, z is the layer index, and there are no bounds.
        dims = ("layer", "row", "col")
        if legacy_top is None or legacy_botm is None:
            z = np.zeros((self.nlay, self.nrow, self.ncol))
            for k in range(self.nlay):
                z[k, :, :] = float(k)
            zs = {"z": xr.DataArray(z, dims=dims)}
        else:
            botm = np.reshape(legacy_botm, (self.nlay, self.nrow, self.ncol))
            zs = {
                k: xr.DataArray(v, dims=d, attrs=a)
                for k, (d, v, a) in z_coords(legacy_top, botm, dims).items()
            }

        return {
            "x": xr.DataArray(xy["x"][1], dims=xy["x"][0]),
            "y": xr.DataArray(xy["y"][1], dims=xy["y"][0]),
            **sizes,
            **zs,
            "projection": xr.Variable(*grid_mapping(self._xoff, self._yoff, self.angrot, self.crs)),
        }

    def _cell_coords(self) -> dict:
        """The coordinates of an array on the grid's cells: x/y, and the
        cells' elevations."""
        return {k: v for k, v in self._coords.items() if k in ("x", "y", "z", "z_top", "z_bot")}

    @property
    def legacy(self) -> bool:
        return self._legacy

    @legacy.setter
    def legacy(self, value):
        self._legacy = value
        if value:
            # Flopy caches xycenters/xyedges using self.delr/delc, which return
            # DataArrays when legacy=False.  Invalidate so properties recompute
            # as plain numpy arrays on the next access.
            self._require_cache_updates()

    @property
    def dataset(self) -> xr.Dataset:
        return self._dataset

    @property
    def dims(self) -> dict[str, int]:
        """The grid's sizes by their DFN names, for a package's ``dims=``."""
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "ncpl": self.nrow * self.ncol,
            "nodes": self.nnodes,
        }

    @property
    def delc(self):
        if self.legacy:
            return super().delc

        if self.__delc is None:
            return None
        dims = ("row",)
        coords = {"y": self._coords["y"]}
        return xr.DataArray(super().delc, coords=coords, dims=dims).set_xindex("y", PandasIndex)

    @property
    def delr(self):
        if self.legacy:
            return super().delr

        if self.__delr is None:
            return None
        dims = ("col",)
        coords = {"x": self._coords["x"]}
        return xr.DataArray(super().delr, coords=coords, dims=dims).set_xindex("x", PandasIndex)

    @property
    def delz(self):
        if self.legacy:
            return super().delz

        legacy_delz = super().delz
        if legacy_delz is None:
            return None

        dims = ("layer", "row", "col")
        # Check if data shape matches expected grid dimensions
        if legacy_delz.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_delz

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_delz, coords=coords, dims=dims)
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

        dims = ("row", "col")
        # Check if data shape matches expected grid dimensions
        # If not, return the raw legacy data without coordinates
        if legacy_top.shape != (self.nrow, self.ncol):
            return legacy_top

        # top is the top layer's cells' tops, so it gets their elevations
        coords = {
            k: v.isel(layer=0) if "layer" in v.dims else v for k, v in self._cell_coords().items()
        }
        return (
            xr.DataArray(legacy_top, coords=coords, dims=dims)
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

        dims = ("layer", "row", "col")
        # Check if data shape matches expected grid dimensions
        if legacy_botm.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_botm

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_botm, coords=coords, dims=dims)
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

        dims = ("layer", "row", "col")
        # Check if data shape matches expected grid dimensions
        if legacy_idomain.shape != (self.nlay, self.nrow, self.ncol):
            return legacy_idomain

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_idomain, coords=coords, dims=dims)
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

    def to_xarray(
        self,
        modeltime=None,
        netcdf_format: NetCDFFormat = NetCDFFormat.STRUCTURED,
        configuration=None,
    ):
        """
        modeltime    : FloPy ModelTime object
        netcdf_format: NetCDFFormat.LAYERED_MESH or NetCDFFormat.STRUCTURED
        configuration: configuration dictionary
        """
        if modeltime is None:
            raise ValueError("modeltime required for dataset timeseries")

        self.legacy = True
        try:
            ds = xr.Dataset()
            ds.attrs["modflow_grid"] = "structured"

            if netcdf_format == NetCDFFormat.LAYERED_MESH:
                ds = self._layered_mesh_dataset(ds, modeltime, configuration)
            else:
                ds = self._structured_dataset(ds, modeltime, configuration)

            return ds
        finally:
            self.legacy = False

    def _layered_mesh_dataset(self, ds, modeltime=None, configuration=None):
        _units = _coord_units(self.lenuni, self.crs)

        # All topology arrays computed once; self.legacy is already True here.
        topo = self._topology()

        # create dataset coordinate vars
        # Use cumulative per-period time (one value per stress period)
        var_d = {
            "time": (["time"], np.cumsum(modeltime.perlen)),
        }
        ds = ds.assign(var_d)
        ds["time"].attrs["calendar"] = "standard"
        _tunits = modeltime.time_units if modeltime.time_units not in (None, "unknown") else "days"
        ds["time"].attrs["units"] = f"{_tunits} since {modeltime.start_datetime}"
        ds["time"].attrs["axis"] = "T"
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs["long_name"] = "time"
        ds["time"].encoding["_FillValue"] = None
        ds = ds.assign_coords({"layer": ("layer", np.arange(1, self.nlay + 1))})
        ds["layer"].attrs["long_name"] = "model layer"
        ds["layer"].attrs["units"] = "1"
        ds["layer"].attrs["positive"] = "down"
        ds["layer"].attrs["axis"] = "Z"
        ds["layer"].encoding["_FillValue"] = None

        # z_l1, z_l2, ...: per-layer cell center elevation, always written.
        # Split per layer because face-indexed variables have no layer
        # dimension to reference a combined z(layer, nmesh_face) (CF-1.13 5.2).
        _z = self._coords["z"].values
        for k in range(self.nlay):
            _varname = f"z_l{k + 1}"
            ds = ds.assign({_varname: (["nmesh_face"], _z[k].flatten())})
            if _units is not None:
                ds[_varname].attrs["units"] = _units
            ds[_varname].attrs["standard_name"] = "altitude"
            ds[_varname].attrs["positive"] = "up"
            ds[_varname].attrs["long_name"] = f"cell center elevation (layer {k + 1})"
            ds[_varname].attrs["layer"] = k + 1
            ds[_varname].encoding["_FillValue"] = None

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
            "mesh_node_x": (["nmesh_node"], topo["node_x"]),
            "mesh_node_y": (["nmesh_node"], topo["node_y"]),
        }
        ds = ds.assign(var_d)
        if _units is not None:
            ds["mesh_node_x"].attrs["units"] = _units
        ds["mesh_node_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_node_x"].attrs["long_name"] = "Easting"
        ds["mesh_node_x"].encoding["_FillValue"] = None
        if _units is not None:
            ds["mesh_node_y"].attrs["units"] = _units
        ds["mesh_node_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_node_y"].attrs["long_name"] = "Northing"
        ds["mesh_node_y"].encoding["_FillValue"] = None

        # mesh face x, y and bounds
        var_d = {
            "mesh_face_x": (["nmesh_face"], topo["face_x"]),
            "mesh_face_xbnds": (["nmesh_face", "max_nmesh_face_nodes"], topo["x_bnds"]),
            "mesh_face_y": (["nmesh_face"], topo["face_y"]),
            "mesh_face_ybnds": (["nmesh_face", "max_nmesh_face_nodes"], topo["y_bnds"]),
        }
        ds = ds.assign(var_d)
        if _units is not None:
            ds["mesh_face_x"].attrs["units"] = _units
        ds["mesh_face_x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["mesh_face_x"].attrs["long_name"] = "Easting"
        ds["mesh_face_x"].attrs["bounds"] = "mesh_face_xbnds"
        ds["mesh_face_x"].encoding["_FillValue"] = None
        if _units is not None:
            ds["mesh_face_y"].attrs["units"] = _units
        ds["mesh_face_y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["mesh_face_y"].attrs["long_name"] = "Northing"
        ds["mesh_face_y"].attrs["bounds"] = "mesh_face_ybnds"
        ds["mesh_face_y"].encoding["_FillValue"] = None
        # No explicit _FillValue attribute: matches MF6 (MeshNCModel.f90), which
        # pads with NF90_FILL_DOUBLE in the data itself but never declares the
        # attribute on mesh_face_xbnds/ybnds.
        ds["mesh_face_xbnds"].encoding["_FillValue"] = None
        ds["mesh_face_ybnds"].encoding["_FillValue"] = None

        # mesh face nodes
        var_d = {
            "mesh_face_nodes": (["nmesh_face", "max_nmesh_face_nodes"], topo["face_nodes"]),
        }
        ds = ds.assign(var_d)
        ds["mesh_face_nodes"].attrs["cf_role"] = "face_node_connectivity"
        ds["mesh_face_nodes"].attrs["long_name"] = "Vertices bounding cell (counterclockwise)"
        ds["mesh_face_nodes"].attrs["start_index"] = np.int64(1)
        ds["mesh_face_nodes"].encoding["_FillValue"] = FILL_INT64

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
            from pyproj import CRS as ProjCRS
            from pyproj.enums import WktVersion

            _crs = ProjCRS.from_wkt(configuration["wkt"]) if wkt_configured else self.crs
            _wkt1 = _crs.to_wkt(WktVersion.WKT1_GDAL)
            _wkt2 = _crs.to_wkt(WktVersion.WKT2_2019)
            ds["projection"].attrs["wkt"] = _wkt1
            ds["projection"].attrs["crs_wkt"] = _wkt2
            _gmn = _crs.to_cf().get("grid_mapping_name")
            if _gmn:
                ds["projection"].attrs["grid_mapping_name"] = _gmn

        return ds

    def _structured_dataset(self, ds, modeltime=None, configuration=None):
        # Produces a conventional CF structured dataset (x/y dimension coords,
        # no UGRID mesh variable).
        _units = _coord_units(self.lenuni, self.crs)

        # For a rotated grid, x/y (and their bounds) are grid-local -- zero
        # offset, not xoffset/yoffset -- matching MF6's DisNCStructured.f90
        # convention exactly. wrap_rotated_crs's derived-CRS parameters are
        # anchored to this same zero-based local coordinate system, so x/y
        # must stay zero-based here for that wrap to resolve the correct
        # real-world position; offsetting them would silently break it.
        _xoff = 0.0 if self.angrot else self.xoffset
        _yoff = 0.0 if self.angrot else self.yoffset

        xc = _xoff + self.xycenters[0]
        yc = _yoff + self.xycenters[1]

        # set coordinate var bounds
        x_bnds = []
        xv = _xoff + self.xyedges[0]
        for idx, val in enumerate(xv):
            if idx + 1 < len(xv):
                bnd = []
                bnd.append(xv[idx])
                bnd.append(xv[idx + 1])
                x_bnds.append(bnd)

        y_bnds = []
        yv = _yoff + self.xyedges[1]
        for idx, val in enumerate(yv):
            if idx + 1 < len(yv):
                bnd = []
                bnd.append(yv[idx + 1])
                bnd.append(yv[idx])
                y_bnds.append(bnd)

        # create dataset coordinate vars
        # Use cumulative per-period time (one value per stress period)
        var_d = {
            "time": (["time"], np.cumsum(modeltime.perlen)),
            "y": (["y"], yc),
            "x": (["x"], xc),
            "layer": (["layer"], np.arange(1, self.nlay + 1)),
        }
        ds = ds.assign_coords(var_d)

        # create bound vars
        var_d = {"x_bnds": (["x", "bnd"], x_bnds), "y_bnds": (["y", "bnd"], y_bnds)}
        ds = ds.assign(var_d)

        ds["time"].attrs["calendar"] = "standard"
        _tunits = modeltime.time_units if modeltime.time_units not in (None, "unknown") else "days"
        ds["time"].attrs["units"] = f"{_tunits} since {modeltime.start_datetime}"
        ds["time"].attrs["axis"] = "T"
        ds["time"].attrs["standard_name"] = "time"
        ds["time"].attrs["long_name"] = "time"
        ds["time"].encoding["_FillValue"] = None
        # Resolve the CRS (if any) once, up front, and attempt the
        # rotation wrap once -- both the x/y axis/standard_name decision
        # below and the projection variable's crs_wkt (further down) need
        # the result, and pyproj.CRS.to_cf()/is_projected do not "see
        # through" a wrapped DerivedProjectedCRS, so grid_mapping_name and
        # any CF numeric grid_mapping parameters must always come from the
        # original, unwrapped CRS.
        _crs = None
        if (
            configuration is not None
            and "wkt" in configuration
            and configuration["wkt"] is not None
        ):
            from pyproj import CRS as ProjCRS

            _crs = ProjCRS.from_wkt(configuration["wkt"])
        elif self.crs is not None:
            _crs = self.crs

        _wrapped_crs = None
        if self.angrot:
            import warnings

            from flopy4.mf6.utils.crs import wrap_rotated_crs

            if _crs is not None:
                _wrapped_crs = wrap_rotated_crs(_crs, self.xoffset, self.yoffset, self.angrot)
            if _wrapped_crs is None:
                warnings.warn(
                    "rotated grid: no rotation-positioning information will "
                    "be written to the output CRS; x/y coordinate values "
                    "will not reflect the true rotated position "
                    + (
                        "(CRS is not a projected CRS)"
                        if _crs is not None
                        else "(no CRS configured)"
                    )
                )

        # axis/standard_name assert that x/y hold the true projected
        # position, which only holds once crs_wkt encodes the rotation
        # (see wrap_rotated_crs above); otherwise x/y are grid-local.
        _axis_ok = not self.angrot or _wrapped_crs is not None

        if _units is not None:
            ds["y"].attrs["units"] = _units
        if _axis_ok:
            ds["y"].attrs["axis"] = "Y"
            ds["y"].attrs["standard_name"] = "projection_y_coordinate"
        ds["y"].attrs["long_name"] = "Northing"
        ds["y"].attrs["bounds"] = "y_bnds"
        if _units is not None:
            ds["x"].attrs["units"] = _units
        if _axis_ok:
            ds["x"].attrs["axis"] = "X"
            ds["x"].attrs["standard_name"] = "projection_x_coordinate"
        ds["x"].attrs["long_name"] = "Easting"
        ds["x"].attrs["bounds"] = "x_bnds"
        ds["x"].encoding["_FillValue"] = None
        ds["y"].encoding["_FillValue"] = None
        ds["layer"].attrs["long_name"] = "model layer"
        ds["layer"].attrs["units"] = "1"
        ds["layer"].attrs["positive"] = "down"
        ds["layer"].attrs["axis"] = "Z"
        ds["layer"].encoding["_FillValue"] = None
        ds["x_bnds"].encoding["_FillValue"] = None
        ds["y_bnds"].encoding["_FillValue"] = None

        # z: cell center elevation, distinct from the discrete layer index.
        # Always written, independent of CRS/NCF configuration.
        ds = ds.assign({"z": (["layer", "y", "x"], self._coords["z"].values)})
        if _units is not None:
            ds["z"].attrs["units"] = _units
        ds["z"].attrs["standard_name"] = "altitude"
        ds["z"].attrs["positive"] = "up"
        ds["z"].attrs["long_name"] = "cell center elevation"
        ds["z"].encoding["_FillValue"] = None

        # Write projection variable whenever CRS is available (_crs and
        # _wrapped_crs were already resolved above, for the x/y
        # axis/standard_name decision).
        # Lat/lon auxiliary coordinates are intentionally omitted: GDAL-based
        # tools (QGIS, ArcGIS) misplace projected rasters when 2D lat/lon arrays
        # coexist with projected x/y dimension coordinates. The NCF subpackage
        # (separate text file) still carries lat/lon for MODFLOW 6 output.
        if _crs is not None:
            from pyproj.enums import WktVersion

            # wkt (WKT1) is always the original, unwrapped CRS -- WKT1 has
            # no derived-CRS syntax, so it cannot encode grid rotation.
            _wkt1 = _crs.to_wkt(WktVersion.WKT1_GDAL)
            _wkt2 = (_wrapped_crs or _crs).to_wkt(WktVersion.WKT2_2019)
            ds["x"].attrs["grid_mapping"] = "projection"
            ds["y"].attrs["grid_mapping"] = "projection"
            ds = ds.assign({"projection": ([], np.int64(1))})
            ds["projection"].attrs["crs_wkt"] = _wkt2
            ds["projection"].attrs["wkt"] = _wkt1
            _gmn = _crs.to_cf().get("grid_mapping_name")
            if _gmn:
                ds["projection"].attrs["grid_mapping_name"] = _gmn

            from flopy4.mf6.utils.crs import cf_grid_mapping_params

            _params, _warning = cf_grid_mapping_params(_crs)
            if _warning:
                import warnings

                warnings.warn(_warning)
            for k, v in _params.items():
                ds["projection"].attrs[k] = v

        return ds

    def _topology(self) -> dict:
        """
        Compute UGRID mesh topology arrays.

        Returns node coordinates, face centroids, 1-based CCW face-node
        connectivity, and face-vertex bound arrays.  Must be called while
        ``self.legacy`` is ``True`` so that ``iverts`` and ``verts`` return
        raw arrays rather than xarray-wrapped values.
        """
        node_x = self.verts[:, 0]
        node_y = self.verts[:, 1]

        # 1-based CCW face-node connectivity (structured cells always have 4 nodes)
        face_nodes_list = []
        for r in self.iverts:
            nodes = [np.int64(x + 1) for x in r]
            nodes.reverse()
            face_nodes_list.append(nodes)
        face_nodes = np.array(face_nodes_list, dtype=np.int64)  # (nfaces, 4)

        # Face-vertex bounds: x/y coordinates of each face's nodes in CCW order.
        # Vectorized indexing replaces the nested vertex loops.
        x_bnds = node_x[face_nodes - 1]  # (nfaces, 4)
        y_bnds = node_y[face_nodes - 1]  # (nfaces, 4)

        return {
            "node_x": node_x,
            "node_y": node_y,
            "face_x": self.xcellcenters.flatten(),
            "face_y": self.ycellcenters.flatten(),
            "face_nodes": face_nodes,
            "x_bnds": x_bnds,
            "y_bnds": y_bnds,
        }

    @property
    def ugrid(self) -> xu.Ugrid2d:
        """
        Build a :class:`xugrid.Ugrid2d` mesh from this structured grid.

        Returns
        -------
        xu.Ugrid2d
            A 2-D unstructured grid object whose faces correspond to the
            structured grid cells in row-major order.
        """
        self.legacy = True
        try:
            topo = self._topology()
            return xu.Ugrid2d(
                topo["node_x"],
                topo["node_y"],
                FILL_INT64,
                topo["face_nodes"],
                is_projected=True,
                crs=self.crs,
                start_index=1,
            )
        finally:
            self.legacy = False


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
        >>> dis = Disv(nlay=3, ncpl=1, nvert=4, top=30.0, botm=[20.0, 10.0, 0.0],
        ...            vertices=[(0, 0.0, 0.0), (1, 0.0, 1.0), (2, 1.0, 1.0), (3, 1.0, 0.0)],
        ...            cell2d=[(0, 0.5, 0.5, 5, (0, 1, 2, 3, 0))])
        >>> grid = VertexGrid.from_dis(dis)
        """
        _top = dis.top
        _botm = dis.botm
        if hasattr(_top, "reshape") and hasattr(_top, "ndim") and _top.ndim == 1:
            _top = _top  # VertexGrid expects top as 1D (ncpl,)
        if hasattr(_botm, "reshape") and hasattr(_botm, "ndim") and _botm.ndim == 1:
            _botm = _botm.reshape(dis.nlay, dis.ncpl)
        return cls(
            length_units=dis.length_units,
            xoff=dis.xorigin,
            yoff=dis.yorigin,
            angrot=getattr(dis, "angrot", None),
            crs=dis.crs,
            nlay=dis.nlay,
            ncpl=dis.ncpl,
            top=_top,
            botm=_botm,
            idomain=getattr(dis, "idomain", None),
            vertices=dis.grid_vertices(),
            cell2d=dis.grid_cell2d(),
            **kwargs,
        )

    def __init__(self, *args, **kwargs):
        # Convert scalar inputs to arrays to support the legacy grid
        self._legacy = False
        if (units := kwargs.pop("length_units", None)) is not None:
            kwargs["lenuni"] = units.lower()
        if (xoff := kwargs.pop("xoff", None)) is not None:
            kwargs["xoff"] = xoff
        else:
            kwargs["xoff"] = 0.0
        if (yoff := kwargs.pop("yoff", None)) is not None:
            kwargs["yoff"] = yoff
        else:
            kwargs["yoff"] = 0.0
        if (top := kwargs.get("top", None)) is not None and isinstance(top, Scalar):
            ncpl = kwargs.get("ncpl", None)
            kwargs["top"] = np.full((ncpl,), float(top))

        if (botm := kwargs.get("botm", None)) is not None:
            if isinstance(botm, (list, tuple)) and all(isinstance(b, Scalar) for b in botm):
                nlay = kwargs.get("nlay", len(botm))
                ncpl = kwargs.get("ncpl", None)
                kwargs["botm"] = np.array([np.full((ncpl,), float(b)) for b in botm])

        if "iv" in kwargs and "xv" in kwargs and "yv" in kwargs:
            iv = np.asarray(kwargs.pop("iv"))
            xv = np.asarray(kwargs.pop("xv"))
            yv = np.asarray(kwargs.pop("yv"))
            kwargs["vertices"] = [[iv[i], xv[i], yv[i]] for i in range(len(iv))]

        super().__init__(*args, **kwargs)
        # As for StructuredGrid: dims (layer, cell), cell the cell within its
        # layer, with no index coordinates.
        self._coords = self._get_world_coords()

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
        # Access the parent class's properties directly, guarding with
        # try/finally so _legacy is always reset even if an exception occurs.
        self.legacy = True
        try:
            xcellcenters = self.xcellcenters
            ycellcenters = self.ycellcenters
            legacy_top = self.top
            legacy_botm = self.botm
        finally:
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

        # Cell elevations, as for StructuredGrid.
        dims = ("layer", "cell")
        if legacy_top is None or legacy_botm is None:
            z = np.zeros((self.nlay, self.ncpl))
            for k in range(self.nlay):
                z[k, :] = float(k)
            zs = {"z": xr.DataArray(z, dims=dims)}
        else:
            botm = np.reshape(legacy_botm, (self.nlay, self.ncpl))
            zs = {
                k: xr.DataArray(v, dims=d, attrs=a)
                for k, (d, v, a) in z_coords(legacy_top, botm, dims).items()
            }

        return {
            "x": xr.DataArray(x, dims=("cell",)),
            "y": xr.DataArray(y, dims=("cell",)),
            **zs,
        }

    def _cell_coords(self) -> dict:
        """The coordinates of an array on the grid's cells: x/y, and the
        cells' elevations."""
        return {k: v for k, v in self._coords.items() if k in ("x", "y", "z", "z_top", "z_bot")}

    @property
    def legacy(self) -> bool:
        return self._legacy

    @legacy.setter
    def legacy(self, value):
        self._legacy = value
        if value:
            self._require_cache_updates()

    @property
    def dataset(self) -> xr.Dataset:
        return self._dataset

    @property
    def dims(self) -> dict[str, int]:
        """The grid's sizes by their DFN names, for a package's ``dims=``."""
        return {"nlay": self.nlay, "ncpl": self.ncpl, "nodes": self.nnodes}

    @property
    def delz(self):
        if self.legacy:
            return super().delz

        legacy_delz = super().delz
        if legacy_delz is None:
            return None

        dims = ("layer", "cell")
        # Check if data shape matches expected grid dimensions
        if legacy_delz.shape != (self.nlay, self.ncpl):
            return legacy_delz

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_delz, coords=coords, dims=dims)
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

        dims = ("cell",)
        # Check if data shape matches expected grid dimensions
        # If not, return the raw legacy data without coordinates
        if legacy_top.shape != (self.ncpl,):
            return legacy_top

        # top is the top layer's cells' tops, so it gets their elevations
        coords = {
            k: v.isel(layer=0) if "layer" in v.dims else v for k, v in self._cell_coords().items()
        }
        return (
            xr.DataArray(legacy_top, coords=coords, dims=dims)
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

        dims = ("layer", "cell")
        # Check if data shape matches expected grid dimensions
        if legacy_botm.shape != (self.nlay, self.ncpl):
            return legacy_botm

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_botm, coords=coords, dims=dims)
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

        dims = ("layer", "cell")
        # Check if data shape matches expected grid dimensions
        if legacy_idomain.shape != (self.nlay, self.ncpl):
            return legacy_idomain

        coords = self._cell_coords()
        return (
            xr.DataArray(legacy_idomain, coords=coords, dims=dims)
            .set_xindex("x", PandasIndex)
            .set_xindex("y", PandasIndex)
            # z is 3D, not 1D, so don't set as index
        )

    def to_xarray(
        self,
        modeltime=None,
        netcdf_format: NetCDFFormat = NetCDFFormat.LAYERED_MESH,
        configuration=None,
    ):
        """
        modeltime    : FloPy ModelTime object
        netcdf_format: must be NetCDFFormat.LAYERED_MESH; VertexGrid only
                       supports UGRID layered-mesh output
        configuration: configuration dictionary
        """
        if netcdf_format != NetCDFFormat.LAYERED_MESH:
            raise ValueError("VertexGrid only supports NetCDFFormat.LAYERED_MESH output")

        if modeltime is None:
            raise ValueError("modeltime required for dataset timeseries")

        _units = _coord_units(self.lenuni, self.crs)

        self.legacy = True
        try:
            # All topology arrays computed once from cell2d/verts.
            topo = self._topology()

            ds = xr.Dataset()
            ds.attrs["modflow_grid"] = "vertex"

            # create dataset coordinate vars
            # Use cumulative per-period time (one value per stress period)
            var_d = {
                "time": (["time"], np.cumsum(modeltime.perlen)),
            }
            ds = ds.assign(var_d)
            ds["time"].attrs["calendar"] = "standard"
            _tu = modeltime.time_units
            _tunits = _tu if _tu not in (None, "unknown") else "days"
            ds["time"].attrs["units"] = f"{_tunits} since {modeltime.start_datetime}"
            ds["time"].attrs["axis"] = "T"
            ds["time"].attrs["standard_name"] = "time"
            ds["time"].attrs["long_name"] = "time"
            ds["time"].encoding["_FillValue"] = None
            ds = ds.assign_coords({"layer": ("layer", np.arange(1, self.nlay + 1))})
            ds["layer"].attrs["long_name"] = "model layer"
            ds["layer"].attrs["units"] = "1"
            ds["layer"].attrs["positive"] = "down"
            ds["layer"].attrs["axis"] = "Z"
            ds["layer"].encoding["_FillValue"] = None

            # z_l1, z_l2, ...: per-layer cell center elevation, always written.
            # Split per layer because face-indexed variables have no layer
            # dimension to reference a combined z(layer, nmesh_face) (CF-1.13 5.2).
            _z = self._coords["z"].values
            for k in range(self.nlay):
                _varname = f"z_l{k + 1}"
                ds = ds.assign({_varname: (["nmesh_face"], _z[k])})
                if _units is not None:
                    ds[_varname].attrs["units"] = _units
                ds[_varname].attrs["standard_name"] = "altitude"
                ds[_varname].attrs["positive"] = "up"
                ds[_varname].attrs["long_name"] = f"cell center elevation (layer {k + 1})"
                ds[_varname].attrs["layer"] = k + 1
                ds[_varname].encoding["_FillValue"] = None

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
                "mesh_node_x": (["nmesh_node"], topo["node_x"]),
                "mesh_node_y": (["nmesh_node"], topo["node_y"]),
            }
            ds = ds.assign(var_d)
            if _units is not None:
                ds["mesh_node_x"].attrs["units"] = _units
            ds["mesh_node_x"].attrs["standard_name"] = "projection_x_coordinate"
            ds["mesh_node_x"].attrs["long_name"] = "Easting"
            ds["mesh_node_x"].encoding["_FillValue"] = None
            if _units is not None:
                ds["mesh_node_y"].attrs["units"] = _units
            ds["mesh_node_y"].attrs["standard_name"] = "projection_y_coordinate"
            ds["mesh_node_y"].attrs["long_name"] = "Northing"
            ds["mesh_node_y"].encoding["_FillValue"] = None

            # mesh face x, y and bounds
            var_d = {
                "mesh_face_x": (["nmesh_face"], topo["face_x"]),
                "mesh_face_xbnds": (["nmesh_face", "max_nmesh_face_nodes"], topo["x_bnds"]),
                "mesh_face_y": (["nmesh_face"], topo["face_y"]),
                "mesh_face_ybnds": (["nmesh_face", "max_nmesh_face_nodes"], topo["y_bnds"]),
            }
            ds = ds.assign(var_d)
            if _units is not None:
                ds["mesh_face_x"].attrs["units"] = _units
            ds["mesh_face_x"].attrs["standard_name"] = "projection_x_coordinate"
            ds["mesh_face_x"].attrs["long_name"] = "Easting"
            ds["mesh_face_x"].attrs["bounds"] = "mesh_face_xbnds"
            ds["mesh_face_x"].encoding["_FillValue"] = None
            if _units is not None:
                ds["mesh_face_y"].attrs["units"] = _units
            ds["mesh_face_y"].attrs["standard_name"] = "projection_y_coordinate"
            ds["mesh_face_y"].attrs["long_name"] = "Northing"
            ds["mesh_face_y"].attrs["bounds"] = "mesh_face_ybnds"
            ds["mesh_face_y"].encoding["_FillValue"] = None
            # No explicit _FillValue attribute: matches MF6 (MeshNCModel.f90), which
            # pads with NF90_FILL_DOUBLE in the data itself but never declares the
            # attribute on mesh_face_xbnds/ybnds.
            ds["mesh_face_xbnds"].encoding["_FillValue"] = None
            ds["mesh_face_ybnds"].encoding["_FillValue"] = None

            # mesh face nodes
            var_d = {
                "mesh_face_nodes": (["nmesh_face", "max_nmesh_face_nodes"], topo["face_nodes"]),
            }
            ds = ds.assign(var_d)
            ds["mesh_face_nodes"].attrs["cf_role"] = "face_node_connectivity"
            ds["mesh_face_nodes"].attrs["long_name"] = "Vertices bounding cell (counterclockwise)"
            ds["mesh_face_nodes"].attrs["start_index"] = np.int64(1)
            ds["mesh_face_nodes"].encoding["_FillValue"] = FILL_INT64

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
                from pyproj import CRS as ProjCRS
                from pyproj.enums import WktVersion

                _crs = ProjCRS.from_wkt(configuration["wkt"]) if wkt_configured else self.crs
                _wkt1 = _crs.to_wkt(WktVersion.WKT1_GDAL)
                _wkt2 = _crs.to_wkt(WktVersion.WKT2_2019)
                ds["projection"].attrs["wkt"] = _wkt1
                ds["projection"].attrs["crs_wkt"] = _wkt2
                _gmn = _crs.to_cf().get("grid_mapping_name")
                if _gmn:
                    ds["projection"].attrs["grid_mapping_name"] = _gmn

            return ds
        finally:
            self.legacy = False

    def _topology(self) -> dict:
        """
        Compute UGRID mesh topology arrays.

        Returns node coordinates, face centroids, 1-based CCW face-node
        connectivity (padded with ``FILL_INT64``), and face-vertex bound
        arrays.  Must be called while ``self.legacy`` is ``True`` so that
        ``cell2d`` and ``verts`` return raw arrays rather than xarray-wrapped
        values.
        """
        if not self.cell2d:
            raise ValueError("VertexGrid has no cell2d data; cannot build mesh topology.")

        node_x = self.verts[:, 0]
        node_y = self.verts[:, 1]

        # 1-based CCW face-node connectivity, padded to max_face_nodes. Each
        # cell2d row is [icell2d, xc, yc, ncvert, iv1, iv2, ...].
        cell_nverts = [len(cell) - 4 for cell in self.cell2d]
        max_face_nodes = max(cell_nverts)
        face_nodes_list = []
        for cell in self.cell2d:
            nodes = [np.int64(x + 1) for x in cell[4:]]
            nodes.reverse()
            if nodes[0] == nodes[-1]:
                nodes.pop()
            if len(nodes) < max_face_nodes:
                nodes.extend([FILL_INT64] * (max_face_nodes - len(nodes)))
            face_nodes_list.append(nodes)
        face_nodes = np.array(face_nodes_list, dtype=np.int64)  # (ncpl, max_face_nodes)

        # Face-vertex bounds: x/y coordinates of each face's nodes in CCW order.
        # Padding slots (FILL_INT64) must not be used as array indices, so mask them.
        mask = face_nodes == FILL_INT64
        idx = np.where(mask, 0, face_nodes - 1)
        x_bnds = node_x[idx].copy()
        y_bnds = node_y[idx].copy()
        x_bnds[mask] = FILL_FLOAT64
        y_bnds[mask] = FILL_FLOAT64

        return {
            "node_x": node_x,
            "node_y": node_y,
            "face_x": self.xcellcenters,
            "face_y": self.ycellcenters,
            "face_nodes": face_nodes,
            "x_bnds": x_bnds,
            "y_bnds": y_bnds,
        }

    @property
    def ugrid(self) -> xu.Ugrid2d:
        """
        Build a :class:`xugrid.Ugrid2d` mesh from this vertex grid.

        Returns
        -------
        xu.Ugrid2d
            A 2-D unstructured grid object whose faces correspond to the
            vertex grid cells.
        """
        self.legacy = True
        try:
            topo = self._topology()
            return xu.Ugrid2d(
                topo["node_x"],
                topo["node_y"],
                FILL_INT64,
                topo["face_nodes"],
                is_projected=True,
                crs=self.crs,
                start_index=1,
            )
        finally:
            self.legacy = False


def to_world(x, y, xorigin=None, yorigin=None, angrot=None) -> tuple[np.ndarray, np.ndarray]:
    """Model coordinates (relative to the grid's origin) to world
    coordinates. As in MF6, the grid is rotated counter-clockwise by
    ``angrot`` degrees about its origin, the lower-left corner."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if angrot:
        t = np.deg2rad(angrot)
        x, y = x * np.cos(t) - y * np.sin(t), x * np.sin(t) + y * np.cos(t)
    return (xorigin or 0.0) + x, (yorigin or 0.0) + y


def to_local(x, y, xorigin=None, yorigin=None, angrot=None):
    """World coordinates to model coordinates, relative to the grid's
    origin: the inverse of ``to_world``. DataArrays stay DataArrays, so
    their dims survive for point-wise selection."""
    if not isinstance(x, xr.DataArray):
        x = np.asarray(x, dtype=np.float64)
    if not isinstance(y, xr.DataArray):
        y = np.asarray(y, dtype=np.float64)
    x = x - (xorigin or 0.0)
    y = y - (yorigin or 0.0)
    if angrot:
        t = np.deg2rad(angrot)
        x, y = x * np.cos(t) + y * np.sin(t), -x * np.sin(t) + y * np.cos(t)
    return x, y


def structured_centers(delr, delc, xorigin=None, yorigin=None, angrot=None) -> dict[str, Any]:
    """A structured grid's cell centres in its CRS: ``x`` on ``col`` and
    ``y`` on ``row``. Unrotated, they're world coordinates, offset by the
    origin. Rotated, the grid's CRS is the world's rotated about the
    origin, so they're local, zero at the lower-left corner, as MF6 writes
    them to netCDF; the rotation is in ``grid_mapping``."""
    delr = np.asarray(delr, dtype=np.float64)
    delc = np.asarray(delc, dtype=np.float64)
    x = np.cumsum(delr) - 0.5 * delr
    # row 0 is the north edge
    y = delc.sum() - np.cumsum(delc) + 0.5 * delc
    if not angrot:
        x, y = to_world(x, y, xorigin, yorigin)
    return {"x": ("col", x), "y": ("row", y)}


def grid_mapping(xorigin=None, yorigin=None, angrot=None, crs=None) -> tuple:
    """A structured grid's ``projection`` coordinate: a scalar whose attrs
    place the grid in the world, so x/y can be read without the model. As
    in a CF grid mapping variable, which MF6 and ``to_xarray()`` write
    under the same name, and which arrays name in their ``grid_mapping``
    attr. With a CRS, it has the grid's CRS as ``crs_wkt``, as they write
    it: the CRS itself, or wrapped with the rotation if the grid's rotated
    (see ``wrap_rotated_crs``)."""
    attrs: dict[str, Any] = {
        "xorigin": float(xorigin or 0.0),
        "yorigin": float(yorigin or 0.0),
        "angrot": float(angrot or 0.0),
    }
    if crs is not None:
        from pyproj import CRS
        from pyproj.enums import WktVersion

        from flopy4.mf6.utils.crs import wrap_rotated_crs

        crs = CRS.from_user_input(crs)
        wrapped = (
            wrap_rotated_crs(crs, attrs["xorigin"], attrs["yorigin"], attrs["angrot"])
            if angrot
            else None
        )
        attrs["crs_wkt"] = (wrapped or crs).to_wkt(WktVersion.WKT2_2019)
        if gmn := crs.to_cf().get("grid_mapping_name"):
            attrs["grid_mapping_name"] = gmn
    return ((), np.int64(1), attrs)


def get_coords(grid: LegacyStructuredGrid) -> dict[str, Any]:
    """A structured grid's world coordinates, as for package arrays (see
    ``cell_centers``), its cell sizes as ``dx``/``dy``, and its cells'
    elevations if it has them (see ``z_coords``). No layer coordinate: a
    position is the index."""
    dx = np.broadcast_to(np.asarray(grid.delr, dtype=np.float64), (grid.ncol,))
    dy = np.broadcast_to(np.asarray(grid.delc, dtype=np.float64), (grid.nrow,))
    coords: dict[str, Any] = structured_centers(dx, dy, grid.xoffset, grid.yoffset, grid.angrot)
    coords["projection"] = grid_mapping(
        grid.xoffset, grid.yoffset, grid.angrot, getattr(grid, "crs", None)
    )
    if grid.top is not None and grid.botm is not None:
        botm = np.reshape(np.asarray(grid.botm), (grid.nlay, grid.nrow, grid.ncol))
        coords |= z_coords(np.asarray(grid.top), botm, ("layer", "row", "col"))
    return coords | cell_sizes(dx, dy)


def cell_sizes(delr, delc) -> dict[str, Any]:
    """A structured grid's cell sizes, ``dx`` on ``col`` and ``dy`` on
    ``row``, negative as y decreases along rows; scalars if uniform.
    ``index_xy`` finds the cells' edges from them."""
    dx = np.asarray(delr, dtype=np.float64)
    dy = np.asarray(delc, dtype=np.float64)
    if np.allclose(dx, dx[0]) and np.allclose(dy, dy[0]):
        return {"dx": np.array(float(dx[0])), "dy": np.array(-float(dy[0]))}
    return {"dx": ("col", dx.copy()), "dy": ("row", -dy)}


def cell_centers(dis) -> dict[str, Any]:
    """A discretization's cell centres in world coordinates: from
    ``delr``/``delc`` for DIS (see ``structured_centers``), and on the
    cells from ``cell2d`` for DISV and DISU, rotated by ``angrot`` about
    the origin. Empty if the geometry isn't set."""
    if dis is None:
        return {}
    xorigin = getattr(dis, "xorigin", None)
    yorigin = getattr(dis, "yorigin", None)
    angrot = getattr(dis, "angrot", None)
    if hasattr(dis, "delr"):
        if dis.delr is None or dis.delc is None:
            return {}
        delr = np.broadcast_to(np.asarray(dis.delr, dtype=np.float64), (dis.ncol,))
        delc = np.broadcast_to(np.asarray(dis.delc, dtype=np.float64), (dis.nrow,))
        return structured_centers(delr, delc, xorigin, yorigin, angrot)
    cell2d = getattr(dis, "cell2d", None)
    if not cell2d:
        return {}
    dim = "cell" if hasattr(dis, "ncpl") else "node"
    x, y = to_world([c.xc for c in cell2d], [c.yc for c in cell2d], xorigin, yorigin, angrot)
    return {"x": (dim, x), "y": (dim, y)}


class CellIndex(PandasIndex):
    """A structured grid's ``x`` (on ``col``) or ``y`` (on ``row``): the cell
    centres, indexed as by ``PandasIndex``, with the cells' edges, so that
    ``sel`` without a ``method`` gives the cell containing each point, not
    just one centred on it. A point on the edge between two cells gets the
    one with the lower index (on a DIS grid, the west or north cell), as
    with flopy's ``StructuredGrid.intersect``; a point outside the grid
    raises ``KeyError``. Edges are widened by ``tolerance``, by default a
    billionth of the axis's extent, so rounding (e.g. from rotating) doesn't
    put a point on an edge outside, or in the wrong cell. With a
    ``method``, or a slice, it's selection by centre, as with
    ``PandasIndex``. Aligning (e.g. ``a + b``) and concatenating keep each
    cell's edges; aligning grids with a cell at the same centre but with
    different edges raises ``ValueError``."""

    __slots__ = ("bounds",)

    def __init__(self, array, dim, coord_dtype=None, *, fastpath=False, bounds=None):
        super().__init__(array, dim, coord_dtype, fastpath=fastpath)
        # each cell's lower and upper edge, (n, 2), or None to select by centre
        self.bounds = bounds

    @classmethod
    def from_variables(cls, variables, *, options):
        obj = super().from_variables(variables, options=options)
        bounds = options.get("bounds")
        obj.bounds = None if bounds is None else np.asarray(bounds, dtype=np.float64)
        return obj

    def _replace(self, index, dim=None, coord_dtype=None, bounds=None):
        new = super()._replace(index, dim, coord_dtype)
        new.bounds = self.bounds if bounds is None else bounds
        return new

    def _bounds_at(self, indexer):
        if self.bounds is None:
            return None
        if isinstance(indexer, Variable):
            indexer = indexer.data
        return self.bounds[indexer]

    def isel(self, indexers):
        new = super().isel(indexers)
        if new is not None:
            new.bounds = self._bounds_at(indexers[self.dim])
        return new

    def __getitem__(self, indexer):
        return self._replace(self.index[indexer], bounds=self._bounds_at(indexer))

    def roll(self, shifts):
        new = super().roll(shifts)
        if self.bounds is not None:
            new.bounds = np.roll(self.bounds, shifts[self.dim] % len(self.bounds), axis=0)
        return new

    @classmethod
    def concat(cls, indexes, dim, positions=None):
        new = super().concat(indexes, dim, positions)
        if indexes and all(getattr(idx, "bounds", None) is not None for idx in indexes):
            bounds = np.concatenate([idx.bounds for idx in indexes])
            if positions is not None:
                bounds = bounds[np.argsort(np.concatenate(positions))]
            new.bounds = bounds
        return new

    def join(self, other, how="inner"):
        # each centre keeps its cell's edges, from whichever side has it
        new = super().join(other, how)
        if self.bounds is None or getattr(other, "bounds", None) is None:
            return new
        common = self.index.intersection(other.index)
        mine = self.bounds[self.index.get_indexer(common)]
        theirs = other.bounds[other.index.get_indexer(common)]
        extent = float(np.ptp(np.concatenate([self.bounds, other.bounds]))) or 1.0
        if not np.allclose(mine, theirs, rtol=0.0, atol=1e-9 * extent):
            raise ValueError(
                f"can't align {self.dim!r}: the grids have cells with the same "
                "centre but different edges"
            )
        pos = self.index.get_indexer(new.index)
        bounds = self.bounds[np.maximum(pos, 0)]
        theirs = other.bounds[other.index.get_indexer(new.index)]
        new.bounds = np.where((pos < 0)[:, None], theirs, bounds)
        return new

    def equals(self, other, *, exclude=None):
        if not isinstance(other, CellIndex) or not super().equals(other):
            return False
        if self.bounds is None or other.bounds is None:
            return self.bounds is other.bounds
        return np.array_equal(self.bounds, other.bounds)

    def sel(self, labels, method=None, tolerance=None):
        coord_name, label = next(iter(labels.items()))
        if method is not None or self.bounds is None or isinstance(label, slice):
            return super().sel(labels, method, tolerance)
        values = label.data if isinstance(label, (xr.DataArray, Variable)) else label
        values = np.asarray(values)
        if values.dtype.kind not in "iuf":
            return super().sel(labels, method, tolerance)
        lo, hi = self.bounds.min(axis=1), self.bounds.max(axis=1)
        order = np.argsort(lo, kind="stable")
        lo, hi = lo[order], hi[order]
        if tolerance is None:
            tolerance = 1e-9 * (float(hi[-1] - lo[0]) or 1.0)
        pos = np.searchsorted(lo, values, side="right") - 1
        pos = np.where((pos < 0) & (values >= lo[0] - tolerance), 0, pos)
        inside = (pos >= 0) & (values <= hi[np.maximum(pos, 0)] + tolerance)
        if not np.all(inside):
            raise KeyError(f"not all values found in index {coord_name!r}: outside the grid")
        # on an edge (within tolerance), the neighbouring cell with the lower index
        n = len(order)
        prev, nxt = np.maximum(pos - 1, 0), np.minimum(pos + 1, n - 1)
        indexer = order[pos]
        in_prev = (pos > 0) & (values <= hi[prev] + tolerance)
        indexer = np.where(in_prev, np.minimum(indexer, order[prev]), indexer)
        in_next = (pos < n - 1) & (values >= lo[nxt] - tolerance)
        indexer = np.where(in_next, np.minimum(indexer, order[nxt]), indexer)
        if isinstance(label, Variable):
            indexer = Variable(label.dims, indexer)
        elif isinstance(label, xr.DataArray):
            indexer = xr.DataArray(indexer, coords=label._coords, dims=label.dims)
        elif indexer.ndim == 0:
            indexer = int(indexer)
        return IndexSelResult({self.dim: indexer})

    def __repr__(self):
        return f"CellIndex({self.index!r})"


def _cell_bounds(obj, name: str, size: str) -> np.ndarray | None:
    """Edges for ``CellIndex``: the centres -/+ half the cells' sizes
    (``dx``/``dy``), or, without those, midway between centres, the outer
    edges as far out as the inner. None for a single cell of no size."""
    c = obj[name].values.astype(np.float64)
    if size in obj.coords and obj[size].dims in ((), obj[name].dims):
        half = 0.5 * np.abs(np.broadcast_to(obj[size].values, c.shape))
        return np.stack([c - half, c + half], axis=1)
    if len(c) < 2:
        return None
    mid = 0.5 * (c[1:] + c[:-1])
    edges = np.concatenate([[2 * c[0] - mid[0]], mid, [2 * c[-1] - mid[-1]]])
    return np.stack([edges[:-1], edges[1:]], axis=1)


def index_xy(obj):
    """Index a structured array's (or dataset's) x and y coordinates, so it
    can be selected by them: ``sel(x=..., y=...)`` gives the cell containing
    the point, from the cells' edges, by their sizes ``dx``/``dy`` if it has
    them (see ``CellIndex``), and ``method="nearest"`` the nearest centre.
    Point its gridded variables to its ``projection`` coordinate, if it has
    one. If that says the grid's rotated, x/y are local, so give it the
    cells' world coordinates too, as ``x_world``/``y_world`` on
    ``(row, col)``; select by those with ``sel_world``.

    xarray compares ``projection`` by its value, which is always 1, not
    its attrs, so combining arrays on grids placed differently (``a + b``)
    keeps the first's ``projection``, and drops whichever of
    ``x_world``/``y_world`` differ."""
    if "x" not in obj.coords or "y" not in obj.coords:
        return obj
    for name, size in (("x", "dx"), ("y", "dy")):
        if obj[name].ndim == 1:  # not, e.g., a single row's y
            obj = obj.set_xindex(name, CellIndex, bounds=_cell_bounds(obj, name, size))
    if "projection" not in obj.coords:
        return obj
    for da in [obj] if isinstance(obj, xr.DataArray) else obj.data_vars.values():
        if "row" in da.dims and "col" in da.dims:
            da.attrs["grid_mapping"] = "projection"
    proj = obj.coords["projection"].attrs
    if proj.get("angrot") and obj.x.dims == ("col",) and obj.y.dims == ("row",):
        x, y = np.meshgrid(obj.x.values, obj.y.values)
        xw, yw = to_world(x, y, proj["xorigin"], proj["yorigin"], proj["angrot"])
        obj = obj.assign_coords(x_world=(("row", "col"), xw), y_world=(("row", "col"), yw))
    return obj


def sel_world(obj, x, y, z=None, **kwargs):
    """Select from an array (or dataset) by world coordinates. On a rotated
    structured grid, x/y are local, so convert to them through the
    ``projection`` coordinate first; otherwise, x/y are already world
    coordinates, so it's just ``sel``. ``kwargs`` go to ``sel``, e.g.
    ``method="nearest"``. For point-wise selection, pass x and y (and z)
    as DataArrays sharing a dim. Also ``obj.grid.sel_world(x, y)``.

    With ``z``, then select the cell containing that elevation from the
    vertical column (see ``flopy4.mf6.utils.vertical.sel_z``), raising
    ``KeyError`` if there's none. That's always containment: ``method``
    only applies to x/y.

    On a rotated grid, a range of world x or y isn't a range of rows or
    columns, and lists' combinations in the grid's frame aren't those in
    the world's, so slices and lists raise ``ValueError``: mask on
    ``x_world``/``y_world``, or pass points as DataArrays, instead."""
    proj = obj.coords["projection"].attrs if "projection" in obj.coords else {}
    if proj.get("angrot"):
        if isinstance(x, slice) or isinstance(y, slice):
            raise ValueError(
                "can't slice a rotated grid by world x/y: mask on x_world/y_world, "
                "e.g. obj.where(obj.x_world >= x0)"
            )
        if any(not isinstance(c, xr.DataArray) and np.ndim(c) for c in (x, y)):
            raise ValueError(
                "lists of world x/y on a rotated grid: pass points as DataArrays "
                'on a shared dim, e.g. xr.DataArray(xs, dims="point")'
            )
        x, y = to_local(x, y, proj["xorigin"], proj["yorigin"], proj["angrot"])
        if not isinstance(x, xr.DataArray) and np.ndim(x) == 0:
            x, y = float(x), float(y)
    obj = obj.sel(x=x, y=y, **kwargs)
    return obj if z is None else sel_z(obj, z, outside="raise")


def dims_from_grb(grb_path) -> dict:
    """Extract grid dimension dict from a binary grid file (.grb).

    Returns a dict suitable for ``Package.load(dims=...)``:
    - DIS grids:  ``{"nlay", "nrow", "ncol", "nodes"}``
    - DISV grids: ``{"nlay", "ncpl", "nodes"}``
    """
    from flopy4.adapters import read_binary_grid_file

    grb_info = read_binary_grid_file(grb_path)
    grid = grb_info["grid"]
    nlay = grid.nlay
    if grb_info["grid_type"] == "DIS":
        nrow, ncol = grid.nrow, grid.ncol
        return {"nlay": nlay, "nrow": nrow, "ncol": ncol, "nodes": nlay * nrow * ncol}
    else:
        ncpl = grb_info["ncells_per_layer"]
        return {"nlay": nlay, "ncpl": ncpl, "nodes": nlay * ncpl}
