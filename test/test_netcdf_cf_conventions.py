"""
Verify CF-1.11 and UGRID-1.0 attribute compliance on flopy4-generated
NetCDF input datasets for each supported grid/format combination:

  - Structured DIS  (CF-1.11, NetCDFFormat.STRUCTURED)
  - Layered Mesh DIS  (CF-1.11 + UGRID-1.0, NetCDFFormat.LAYERED_MESH via StructuredGrid)
  - Layered Mesh DISV (CF-1.11 + UGRID-1.0, NetCDFFormat.LAYERED_MESH via VertexGrid)

These are unit-level tests that exercise grid.to_xarray() and
NetCDFParam.to_xarray() directly — no MODFLOW 6 simulation required.
"""

import numpy as np
import pytest
import xarray as xr
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.constants import FILL_DNODATA, FILL_FLOAT64, FILL_INT64
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.netcdf import NetCDFModel, NetCDFParam
from flopy4.mf6.utils.grid import StructuredGrid, VertexGrid

CRS = "EPSG:32611"  # UTM Zone 11N — a common projected CRS for western US models


@pytest.fixture(scope="module")
def modeltime():
    return ModelTime(
        perlen=np.array([1.0, 1.0]),
        nstp=np.array([1, 1]),
        tsmult=np.array([1.0, 1.0]),
        time_units="days",
        start_datetime="01-01-2001",
    )


@pytest.fixture(scope="module")
def structured_grid():
    return StructuredGrid.uniform(
        nlay=2,
        nrow=3,
        ncol=3,
        delr=100.0,
        delc=100.0,
        top=10.0,
        thickness=5.0,
        xoff=300_000.0,
        yoff=4_000_000.0,
        crs=CRS,
    )


@pytest.fixture(scope="module")
def vertex_grid():
    # 2 quad cells in a 1×2 strip: 6 nodes, 2 faces
    vertices = [
        [0, 0.0, 100.0],
        [1, 100.0, 100.0],
        [2, 200.0, 100.0],
        [3, 0.0, 0.0],
        [4, 100.0, 0.0],
        [5, 200.0, 0.0],
    ]
    cell2d = [
        [0, 50.0, 50.0, 0, 1, 4, 3],
        [1, 150.0, 50.0, 1, 2, 5, 4],
    ]
    return VertexGrid(
        nlay=2,
        ncpl=2,
        vertices=vertices,
        cell2d=cell2d,
        xoff=300_000.0,
        yoff=4_000_000.0,
        crs=CRS,
    )


def _mesh_param_ds(grid, gridtype, ncpl):
    """Return a dataset for NPF-K layer 1 in layered-mesh context with grid injected."""
    dims = [2, 2] + ([ncpl] if gridtype == "vertex" else [3, 3])
    context = {
        "mesh": "layered",
        "modelname": "gwfmodel",
        "gridtype": gridtype,
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": dims,
    }
    param = NetCDFParam.from_dict({"name": "k", "attrs": {"layer": 1}}, context=context)
    param._context["grid"] = grid
    return param.to_xarray()


def test_structured_dis_projection_variable(structured_grid, modeltime):
    """projection variable must exist whenever a CRS is set on the grid."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert "projection" in ds, "projection variable missing in structured dataset"


def test_structured_dis_crs_wkt_attrs(structured_grid, modeltime):
    """crs_wkt must be WKT2 and wkt must be WKT1 on the projection variable (CF-1.11)."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs, "crs_wkt missing from projection variable"
    assert "wkt" in proj.attrs, "wkt missing from projection variable"
    # crs_wkt must be WKT2 (PROJCRS keyword); wkt must be WKT1 (PROJCS keyword)
    assert proj.attrs["crs_wkt"].startswith("PROJCRS["), "crs_wkt must be WKT2"
    assert proj.attrs["wkt"].startswith("PROJCS["), "wkt must be WKT1"
    assert proj.attrs["crs_wkt"] != proj.attrs["wkt"], "crs_wkt and wkt must differ"
    assert "grid_mapping_name" in proj.attrs, "grid_mapping_name missing from projection variable"
    assert len(proj.attrs["grid_mapping_name"]) > 0


def test_structured_dis_grid_mapping_on_xy(structured_grid, modeltime):
    """x and y dimension coordinates must declare the projection variable as their grid mapping."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["x"].attrs.get("grid_mapping") == "projection", "x missing grid_mapping"
    assert ds["y"].attrs.get("grid_mapping") == "projection", "y missing grid_mapping"


def test_structured_dis_no_latlon(structured_grid, modeltime):
    """lat/lon arrays must not be written to the structured NC file — GDAL misplaces
    projected rasters when 2D geographic arrays coexist with projected dimension coordinates."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert "lat" not in ds, "lat should not be present in structured dataset"
    assert "lon" not in ds, "lon should not be present in structured dataset"


def test_mesh_dis_topology_variable(structured_grid, modeltime):
    """Mesh topology variable must be present with cf_role = mesh_topology."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "mesh" in ds, "mesh topology variable missing"
    assert ds["mesh"].attrs.get("cf_role") == "mesh_topology"


def test_mesh_dis_projection_crs_attrs(structured_grid, modeltime):
    """crs_wkt must be WKT2 and wkt must be WKT1 on the projection variable (CF-1.11)."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "projection" in ds
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs
    assert "wkt" in proj.attrs
    assert proj.attrs["crs_wkt"].startswith("PROJCRS["), "crs_wkt must be WKT2"
    assert proj.attrs["wkt"].startswith("PROJCS["), "wkt must be WKT1"
    assert proj.attrs["crs_wkt"] != proj.attrs["wkt"]
    assert "grid_mapping_name" in proj.attrs, "grid_mapping_name missing from projection variable"
    assert len(proj.attrs["grid_mapping_name"]) > 0


def test_mesh_dis_data_var_mesh_attr(structured_grid):
    """Face-indexed data vars must reference the mesh topology variable via mesh attr."""
    ds = _mesh_param_ds(structured_grid, gridtype="structured", ncpl=9)
    var = "npf_k_l1"
    assert var in ds
    assert "nmesh_face" in ds[var].dims, "expected nmesh_face dimension for layered param"
    assert ds[var].attrs.get("mesh") == "mesh", "mesh attr missing or wrong on data variable"


def test_mesh_dis_data_var_location_attr(structured_grid):
    """Face-indexed data variables must declare location = 'face' per UGRID convention."""
    ds = _mesh_param_ds(structured_grid, gridtype="structured", ncpl=9)
    var = "npf_k_l1"
    assert ds[var].attrs.get("location") == "face", "location attr missing on data variable"


def test_mesh_disv_topology_variable(vertex_grid, modeltime):
    """Mesh topology variable must be present with cf_role = mesh_topology."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "mesh" in ds
    assert ds["mesh"].attrs.get("cf_role") == "mesh_topology"


def test_mesh_disv_projection_crs_attrs(vertex_grid, modeltime):
    """crs_wkt must be WKT2 and wkt must be WKT1 on the projection variable (CF-1.11)."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "projection" in ds
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs
    assert "wkt" in proj.attrs
    assert proj.attrs["crs_wkt"].startswith("PROJCRS["), "crs_wkt must be WKT2"
    assert proj.attrs["wkt"].startswith("PROJCS["), "wkt must be WKT1"
    assert proj.attrs["crs_wkt"] != proj.attrs["wkt"]
    assert "grid_mapping_name" in proj.attrs, "grid_mapping_name missing from projection variable"
    assert len(proj.attrs["grid_mapping_name"]) > 0


def test_mesh_disv_data_var_mesh_attr(vertex_grid):
    """Face-indexed data vars must reference the mesh topology variable via mesh attr."""
    ds = _mesh_param_ds(vertex_grid, gridtype="vertex", ncpl=2)
    var = "npf_k_l1"
    assert var in ds
    assert "nmesh_face" in ds[var].dims
    assert ds[var].attrs.get("mesh") == "mesh", "mesh attr missing or wrong on data variable"


def test_mesh_disv_data_var_location_attr(vertex_grid):
    """Face-indexed data variables must declare location = 'face' per UGRID convention."""
    ds = _mesh_param_ds(vertex_grid, gridtype="vertex", ncpl=2)
    var = "npf_k_l1"
    assert ds[var].attrs.get("location") == "face", "location attr missing on data variable"


def test_structured_dis_layer_coord(structured_grid, modeltime):
    """layer must be a dimension coordinate with CF vertical attrs and label indexing."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert "layer" in ds.coords, "layer coordinate missing from structured dataset"
    assert list(ds["layer"].values) == [1, 2]
    assert ds["layer"].attrs.get("axis") == "Z"
    assert ds["layer"].attrs.get("positive") == "down"
    assert int(ds.sel(layer=1)["layer"].values) == 1
    assert int(ds.sel(layer=2)["layer"].values) == 2


def test_mesh_dis_layer_coord(structured_grid, modeltime):
    """layer must be a dimension coordinate in the layered-mesh (DIS) dataset."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "layer" in ds.coords, "layer coordinate missing from layered-mesh DIS dataset"
    assert list(ds["layer"].values) == [1, 2]
    assert ds["layer"].attrs.get("axis") == "Z"
    assert ds["layer"].attrs.get("positive") == "down"


def test_mesh_disv_layer_coord(vertex_grid, modeltime):
    """layer must be a dimension coordinate in the layered-mesh (DISV) dataset."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "layer" in ds.coords, "layer coordinate missing from layered-mesh DISV dataset"
    assert list(ds["layer"].values) == [1, 2]
    assert ds["layer"].attrs.get("axis") == "Z"
    assert ds["layer"].attrs.get("positive") == "down"


def test_mesh_dis_face_nodes_fill_in_encoding(structured_grid, modeltime):
    """mesh_face_nodes _FillValue must be in encoding, not attrs (DIS path).

    xarray only writes a proper NetCDF _FillValue declaration when the fill
    value is in encoding.  If it lands in attrs it becomes a plain variable
    attribute and NetCDF4/UGRID readers will not recognise padding slots.
    """
    from flopy4.mf6.constants import FILL_INT64

    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "_FillValue" not in ds["mesh_face_nodes"].attrs, "_FillValue must not be in attrs"
    assert ds["mesh_face_nodes"].encoding.get("_FillValue") == FILL_INT64


def test_mesh_disv_face_nodes_fill_in_encoding(vertex_grid, modeltime):
    """mesh_face_nodes _FillValue must be in encoding, not attrs (DISV path)."""
    from flopy4.mf6.constants import FILL_INT64

    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "_FillValue" not in ds["mesh_face_nodes"].attrs, "_FillValue must not be in attrs"
    assert ds["mesh_face_nodes"].encoding.get("_FillValue") == FILL_INT64


def test_structured_merged_sel_layer(structured_grid, modeltime):
    """sel(layer=N) on a merged structured model dataset selects from data variables."""
    import xarray as xr

    grid_ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    dims = [2, 2, 3, 3]
    context = {
        "mesh": None,
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": dims,
    }
    param = NetCDFParam.from_dict({"name": "k", "attrs": {}}, context=context)
    param._context["grid"] = structured_grid
    merged = xr.merge([grid_ds, param.to_xarray()])
    assert "layer" in merged.dims
    assert "npf_k" in merged
    assert merged["npf_k"].dims == ("layer", "y", "x")
    sliced = merged.sel(layer=1)
    assert "layer" not in sliced.dims, "layer dim should be dropped after sel"
    assert sliced["npf_k"].dims == ("y", "x")


def _raw_var_attrs(path, varname: str) -> dict:
    """Read raw NetCDF variable attributes bypassing xarray's CF decoder."""
    nc4 = pytest.importorskip("netCDF4")
    ds = nc4.Dataset(path)
    try:
        return {a: ds.variables[varname].getncattr(a) for a in ds.variables[varname].ncattrs()}
    finally:
        ds.close()


def test_structured_data_var_no_redundant_coordinates(structured_grid, modeltime, tmp_path):
    """Structured data vars must not carry a coordinates attr pointing to dimension coords.

    y and x are dimension coordinates — CF tools find them via the dimension names.
    A redundant coordinates attr would rely on xarray encoding internals to survive
    to_netcdf and adds no information for any CF-aware consumer.
    """
    grid_ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    context = {
        "mesh": None,
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": [2, 2, 3, 3],
    }
    param = NetCDFParam.from_dict({"name": "k", "attrs": {}}, context=context)
    param._context["grid"] = structured_grid
    merged = xr.merge([grid_ds, param.to_xarray()])
    path = tmp_path / "structured_roundtrip.nc"
    merged.to_netcdf(path)
    attrs = _raw_var_attrs(path, "npf_k")
    coords_attr = attrs.get("coordinates", "")
    assert coords_attr == "" or all(
        c not in coords_attr for c in ["y", "x"]
    ), f"structured data var should not carry redundant coordinates attr: {coords_attr!r}"


def test_mesh_data_var_coordinates_survives_roundtrip(structured_grid, modeltime, tmp_path):
    """coordinates = 'mesh_face_x mesh_face_y' on mesh face vars must survive round-trip.

    Verified via raw netCDF4 because xarray strips the coordinates attr when reopening.
    """
    grid_ds = structured_grid.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH
    )
    context = {
        "mesh": "layered",
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": [2, 2, 3, 3],
    }
    param = NetCDFParam.from_dict({"name": "k", "attrs": {"layer": 1}}, context=context)
    param._context["grid"] = structured_grid
    merged = xr.merge([grid_ds, param.to_xarray()])
    path = tmp_path / "mesh_roundtrip.nc"
    merged.to_netcdf(path)
    attrs = _raw_var_attrs(path, "npf_k_l1")
    coords_attr = attrs.get("coordinates", "")
    assert (
        "mesh_face_x" in coords_attr and "mesh_face_y" in coords_attr
    ), f"coordinates attr missing or wrong on raw disk: {coords_attr!r}"


def test_mesh_data_var_cf_attrs_survive_roundtrip(structured_grid, modeltime, tmp_path):
    """mesh, location, and grid_mapping attrs on face data vars must survive round-trip."""
    grid_ds = structured_grid.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH
    )
    context = {
        "mesh": "layered",
        "modelname": "gwfmodel",
        "gridtype": "structured",
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": [2, 2, 3, 3],
    }
    param = NetCDFParam.from_dict({"name": "k", "attrs": {"layer": 1}}, context=context)
    param._context["grid"] = structured_grid
    merged = xr.merge([grid_ds, param.to_xarray()])
    path = tmp_path / "mesh_cf_attrs_roundtrip.nc"
    merged.to_netcdf(path)
    attrs = _raw_var_attrs(path, "npf_k_l1")
    assert attrs.get("mesh") == "mesh", f"mesh attr missing after round-trip: {attrs}"
    assert attrs.get("location") == "face", f"location attr missing after round-trip: {attrs}"
    assert attrs.get("grid_mapping") == "projection", f"grid_mapping missing: {attrs}"


def test_structured_dis_gdal_geotransform(structured_grid, modeltime, tmp_path):
    """GDAL reads the correct GeoTransform from the projection variable."""
    gdal = pytest.importorskip("osgeo.gdal")

    import xarray as xr

    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    ds["data"] = xr.Variable(
        ["y", "x"],
        np.zeros((3, 3), dtype=np.float32),
        attrs={"grid_mapping": "projection"},
    )
    path = tmp_path / "structured.nc"
    ds.to_netcdf(path)

    gds = gdal.Open(f"NETCDF:{path}:data")
    assert gds is not None, "GDAL could not open NetCDF file"
    gt = gds.GetGeoTransform()
    # xoff=300_000, yoff=4_000_000, delr=delc=100, nrow=ncol=3
    # x_left = xoff,  y_top = yoff + nrow * delc = 4_000_300
    assert gt[0] == pytest.approx(300_000.0)  # x origin (left edge)
    assert gt[1] == pytest.approx(100.0)  # dx
    assert gt[3] == pytest.approx(4_000_300.0)  # y origin (top edge)
    assert gt[5] == pytest.approx(-100.0)  # dy (negative = north-up)
    gds = None


def test_structured_dis_gdal_crs(structured_grid, modeltime, tmp_path):
    """GDAL recognizes the CRS from the projection variable crs_wkt."""
    gdal = pytest.importorskip("osgeo.gdal")

    import xarray as xr

    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    ds["data"] = xr.Variable(
        ["y", "x"],
        np.zeros((3, 3), dtype=np.float32),
        attrs={"grid_mapping": "projection"},
    )
    path = tmp_path / "structured_crs.nc"
    ds.to_netcdf(path)

    gds = gdal.Open(f"NETCDF:{path}:data")
    assert gds is not None, "GDAL could not open NetCDF file"
    srs = gds.GetSpatialRef()
    assert srs is not None, "GDAL could not read spatial reference"
    assert "32611" in srs.ExportToWkt()
    gds = None


# fixtures
@pytest.fixture(scope="module")
def flopy4_time():
    """Time instance (flopy4 subclass of ModelTime) required by NetCDFModel."""
    from flopy4.mf6.utils.time import Time

    return Time(
        perlen=np.array([1.0, 1.0]),
        nstp=np.array([1, 1]),
        tsmult=np.array([1.0, 1.0]),
        time_units="days",
        start_datetime="01-01-2001",
    )


@pytest.fixture(scope="module")
def structured_grid_no_crs():
    return StructuredGrid.uniform(
        nlay=2,
        nrow=3,
        ncol=3,
        delr=100.0,
        delc=100.0,
        top=10.0,
        thickness=5.0,
        xoff=300_000.0,
        yoff=4_000_000.0,
        crs=None,
    )


@pytest.fixture(scope="module")
def vertex_grid_no_crs():
    vertices = [
        [0, 0.0, 100.0],
        [1, 100.0, 100.0],
        [2, 200.0, 100.0],
        [3, 0.0, 0.0],
        [4, 100.0, 0.0],
        [5, 200.0, 0.0],
    ]
    cell2d = [
        [0, 50.0, 50.0, 0, 1, 4, 3],
        [1, 150.0, 50.0, 1, 2, 5, 4],
    ]
    return VertexGrid(
        nlay=2,
        ncpl=2,
        vertices=vertices,
        cell2d=cell2d,
        xoff=300_000.0,
        yoff=4_000_000.0,
        crs=None,
    )


@pytest.fixture(scope="module")
def vertex_grid_mixed_poly():
    """VertexGrid with one triangle + one quad cell — triggers face-bounds padding.

    max_face_nodes=4; the triangle (face 0) has one padding slot at column 3.
    Used to verify that padding values are FILL_FLOAT64, not FILL_INT64.
    """
    #   0:(0,1)   1:(1,2)
    #                    3:(2,2)
    #   2:(1,0)         4:(2,0)
    vertices = [
        [0, 0.0, 1.0],
        [1, 1.0, 2.0],
        [2, 1.0, 0.0],
        [3, 2.0, 2.0],
        [4, 2.0, 0.0],
    ]
    cell2d = [
        [0, 0.667, 1.0, 0, 1, 2],  # triangle: 3 vertices (len-3=3)
        [1, 1.5, 1.0, 1, 3, 4, 2],  # quad: 4 vertices (len-3=4)
    ]
    return VertexGrid(nlay=2, ncpl=2, vertices=vertices, cell2d=cell2d)


def _model_ds(grid, flopy4_time, gridtype, mesh=None):
    """Minimal NetCDFModel dataset exercising the full to_xarray() pipeline.

    Used for global attribute tests that require Conventions, modflow_model,
    and the mesh global attribute — all set at the NetCDFModel level, not at
    the grid.to_xarray() level.
    """
    dims = [2, 2, 3, 3] if gridtype == "structured" else [2, 2, 2]
    attrs = {"mesh": "layered"} if mesh == "layered" else {}
    nc_model = NetCDFModel.from_dict(
        meta={
            "modeltype": "gwf6",
            "modelname": "testmodel",
            "gridtype": gridtype,
            "attrs": attrs,
            "packages": [],
        },
        context={"dims": dims},
    )
    nc_model.grid = grid
    nc_model.time = flopy4_time
    return nc_model.to_xarray()


def _structured_param_ds(grid, name, mesh=None, layer=None):
    """NetCDFParam dataset for a single NPF parameter (structured or mesh DIS)."""
    context = {
        "mesh": mesh,
        "modelname": "testmodel",
        "gridtype": "structured",
        "package_name": "npf",
        "package_type": "gwf-npf",
        "dims": [2, 2, 3, 3],
    }
    attrs = {}
    if layer is not None:
        attrs["layer"] = layer
    param = NetCDFParam.from_dict({"name": name, "attrs": attrs}, context=context)
    param._context["grid"] = grid
    return param.to_xarray()


# global attributes
def test_structured_global_attrs(structured_grid, flopy4_time):
    """modflow_grid, modflow_model, and Conventions must be set correctly for structured DIS."""
    ds = _model_ds(structured_grid, flopy4_time, gridtype="structured")
    assert ds.attrs.get("modflow_grid") == "structured"
    assert ds.attrs.get("modflow_model") == "gwf6: testmodel"
    assert ds.attrs.get("Conventions") == "CF-1.11"
    assert "mesh" not in ds.attrs, "mesh global attr must be absent for structured format"


def test_mesh_dis_global_attrs(structured_grid, flopy4_time):
    """modflow_grid, modflow_model, Conventions, and mesh must be set for layered-mesh DIS."""
    ds = _model_ds(structured_grid, flopy4_time, gridtype="structured", mesh="layered")
    assert ds.attrs.get("modflow_grid") == "structured"
    assert ds.attrs.get("modflow_model") == "gwf6: testmodel"
    assert ds.attrs.get("Conventions") == "CF-1.11 UGRID-1.0"
    assert ds.attrs.get("mesh") == "layered", "mesh global attr must be 'layered' (lowercase)"


def test_mesh_disv_global_attrs(vertex_grid, flopy4_time):
    """modflow_grid must be 'vertex' and Conventions must include UGRID for DISV layered mesh."""
    ds = _model_ds(vertex_grid, flopy4_time, gridtype="vertex", mesh="layered")
    assert ds.attrs.get("modflow_grid") == "vertex"
    assert ds.attrs.get("Conventions") == "CF-1.11 UGRID-1.0"
    assert ds.attrs.get("mesh") == "layered", "mesh global attr must be 'layered' (lowercase)"


# time coordinate attrs
def test_structured_time_coord_attrs(structured_grid, modeltime):
    """time coordinate must carry CF-required attrs: calendar, axis, standard_name, units."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    t = ds["time"]
    assert t.attrs.get("calendar") == "standard"
    assert t.attrs.get("axis") == "T"
    assert t.attrs.get("standard_name") == "time"
    assert str(t.attrs.get("units", "")).startswith(
        "days since"
    ), f"time units must be a CF datetime offset, got {t.attrs.get('units')!r}"


def test_mesh_dis_time_coord_attrs(structured_grid, modeltime):
    """time coordinate attrs must be the same in layered-mesh DIS format."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    t = ds["time"]
    assert t.attrs.get("calendar") == "standard"
    assert t.attrs.get("axis") == "T"
    assert t.attrs.get("standard_name") == "time"
    assert str(t.attrs.get("units", "")).startswith("days since")


def test_mesh_disv_time_coord_attrs(vertex_grid, modeltime):
    """time coordinate attrs must be the same in layered-mesh DISV format."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    t = ds["time"]
    assert t.attrs.get("calendar") == "standard"
    assert t.attrs.get("axis") == "T"
    assert t.attrs.get("standard_name") == "time"
    assert str(t.attrs.get("units", "")).startswith("days since")


def test_structured_time_fill_value_suppressed(structured_grid, modeltime):
    """time _FillValue must be suppressed in encoding — time has no missing values."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["time"].encoding.get("_FillValue") is None


def test_mesh_dis_time_fill_value_suppressed(structured_grid, modeltime):
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert ds["time"].encoding.get("_FillValue") is None


def test_mesh_disv_time_fill_value_suppressed(vertex_grid, modeltime):
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert ds["time"].encoding.get("_FillValue") is None


# layer coordinate attrs
def test_structured_layer_units(structured_grid, modeltime):
    """layer units must be '1' (dimensionless integer index) per CF convention."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["layer"].attrs.get("units") == "1"


def test_mesh_dis_layer_units(structured_grid, modeltime):
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert ds["layer"].attrs.get("units") == "1"


def test_mesh_disv_layer_units(vertex_grid, modeltime):
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert ds["layer"].attrs.get("units") == "1"


def test_structured_layer_fill_value_suppressed(structured_grid, modeltime):
    """layer _FillValue must be suppressed in encoding — no missing layer indices."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["layer"].encoding.get("_FillValue") is None


def test_mesh_dis_layer_fill_value_suppressed(structured_grid, modeltime):
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert ds["layer"].encoding.get("_FillValue") is None


def test_mesh_disv_layer_fill_value_suppressed(vertex_grid, modeltime):
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert ds["layer"].encoding.get("_FillValue") is None


# structured x/y coordinate attrs
def test_structured_x_coord_attrs(structured_grid, modeltime):
    """x dimension coordinate must carry axis, standard_name, units, and bounds."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    x = ds["x"]
    assert x.attrs.get("axis") == "X"
    assert x.attrs.get("standard_name") == "projection_x_coordinate"
    assert x.attrs.get("units") == "m"
    assert x.attrs.get("bounds") == "x_bnds"


def test_structured_y_coord_attrs(structured_grid, modeltime):
    """y dimension coordinate must carry axis, standard_name, units, and bounds."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    y = ds["y"]
    assert y.attrs.get("axis") == "Y"
    assert y.attrs.get("standard_name") == "projection_y_coordinate"
    assert y.attrs.get("units") == "m"
    assert y.attrs.get("bounds") == "y_bnds"


def test_structured_xy_fill_value_suppressed(structured_grid, modeltime):
    """x and y _FillValue must be suppressed — all cells have defined coordinates."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["x"].encoding.get("_FillValue") is None
    assert ds["y"].encoding.get("_FillValue") is None


def test_structured_bnds_fill_value_suppressed(structured_grid, modeltime):
    """x_bnds and y_bnds _FillValue must be suppressed — bounds arrays are fully defined."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    assert ds["x_bnds"].encoding.get("_FillValue") is None
    assert ds["y_bnds"].encoding.get("_FillValue") is None


# projection variable: GeoTransform and spatial_ref
def test_structured_projection_gdal_attrs(structured_grid, modeltime):
    """GeoTransform and spatial_ref must be present on the structured projection variable.

    GeoTransform is required for GDAL-based tools (QGIS, ArcGIS) to place the
    raster correctly. spatial_ref is GDAL's companion WKT1 attribute.
    """
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    proj = ds["projection"]
    assert "GeoTransform" in proj.attrs, "GeoTransform missing from structured projection variable"
    gt_parts = str(proj.attrs["GeoTransform"]).split()
    assert (
        len(gt_parts) == 6
    ), f"GeoTransform must have 6 values, got: {proj.attrs['GeoTransform']!r}"
    assert "spatial_ref" in proj.attrs, "spatial_ref missing from structured projection variable"
    assert proj.attrs["spatial_ref"].startswith("PROJCS["), "spatial_ref must be WKT1"


def test_mesh_dis_no_gdal_attrs(structured_grid, modeltime):
    """GeoTransform and spatial_ref must NOT appear on the mesh (UGRID) projection variable.

    GDAL cannot interpret unstructured grids as rasters — these attributes would
    be misleading and are intentionally omitted from the mesh format.
    """
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "projection" in ds
    assert "GeoTransform" not in ds["projection"].attrs
    assert "spatial_ref" not in ds["projection"].attrs


def test_mesh_disv_no_gdal_attrs(vertex_grid, modeltime):
    """GeoTransform and spatial_ref must NOT appear on the DISV mesh projection variable."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "projection" in ds
    assert "GeoTransform" not in ds["projection"].attrs
    assert "spatial_ref" not in ds["projection"].attrs


# no-CRS variation
def test_structured_no_crs_no_projection(structured_grid_no_crs, modeltime):
    """No projection variable must be written when the grid has no CRS."""
    ds = structured_grid_no_crs.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED
    )
    assert "projection" not in ds, "projection variable must not be written without a CRS"


def test_structured_no_crs_no_grid_mapping(structured_grid_no_crs, modeltime):
    """x and y must not carry grid_mapping when no CRS is set."""
    ds = structured_grid_no_crs.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED
    )
    assert "grid_mapping" not in ds["x"].attrs
    assert "grid_mapping" not in ds["y"].attrs


def test_mesh_dis_no_crs_no_projection(structured_grid_no_crs, modeltime):
    """No projection variable must be written for layered-mesh DIS without a CRS."""
    ds = structured_grid_no_crs.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH
    )
    assert "projection" not in ds


def test_mesh_dis_no_crs_no_grid_mapping(structured_grid_no_crs, modeltime):
    """Mesh geometry arrays must not carry grid_mapping when no CRS is set."""
    ds = structured_grid_no_crs.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH
    )
    assert "grid_mapping" not in ds["mesh_node_x"].attrs
    assert "grid_mapping" not in ds["mesh_face_x"].attrs


def test_mesh_disv_no_crs_no_projection(vertex_grid_no_crs, modeltime):
    """No projection variable must be written for layered-mesh DISV without a CRS."""
    ds = vertex_grid_no_crs.to_xarray(modeltime=modeltime)
    assert "projection" not in ds


# UGRID topology variable full attrs
def test_mesh_dis_topology_full_attrs(structured_grid, modeltime):
    """Mesh topology variable must carry the full set of UGRID-1.0 required attributes."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    m = ds["mesh"]
    assert m.attrs.get("cf_role") == "mesh_topology"
    assert int(m.attrs.get("topology_dimension", -1)) == 2
    assert m.attrs.get("face_dimension") == "nmesh_face"
    assert "mesh_node_x" in m.attrs.get("node_coordinates", "")
    assert "mesh_node_y" in m.attrs.get("node_coordinates", "")
    assert "mesh_face_x" in m.attrs.get("face_coordinates", "")
    assert "mesh_face_y" in m.attrs.get("face_coordinates", "")
    assert m.attrs.get("face_node_connectivity") == "mesh_face_nodes"


def test_mesh_disv_topology_full_attrs(vertex_grid, modeltime):
    """Mesh topology variable must carry the full set of UGRID-1.0 attrs for DISV."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    m = ds["mesh"]
    assert m.attrs.get("cf_role") == "mesh_topology"
    assert int(m.attrs.get("topology_dimension", -1)) == 2
    assert m.attrs.get("face_dimension") == "nmesh_face"
    assert "mesh_node_x" in m.attrs.get("node_coordinates", "")
    assert "mesh_node_y" in m.attrs.get("node_coordinates", "")
    assert "mesh_face_x" in m.attrs.get("face_coordinates", "")
    assert "mesh_face_y" in m.attrs.get("face_coordinates", "")
    assert m.attrs.get("face_node_connectivity") == "mesh_face_nodes"


# UGRID geometry variable attrs
def test_mesh_dis_node_coord_attrs(structured_grid, modeltime):
    """mesh_node_x/y must carry standard_name, units, and grid_mapping."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    for var, sn in [
        ("mesh_node_x", "projection_x_coordinate"),
        ("mesh_node_y", "projection_y_coordinate"),
    ]:
        assert ds[var].attrs.get("standard_name") == sn, f"{var} standard_name wrong"
        assert ds[var].attrs.get("units") == "m", f"{var} units wrong"
        assert ds[var].attrs.get("grid_mapping") == "projection", f"{var} grid_mapping missing"


def test_mesh_dis_face_coord_attrs(structured_grid, modeltime):
    """mesh_face_x/y must carry standard_name, units, bounds, and grid_mapping."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert ds["mesh_face_x"].attrs.get("standard_name") == "projection_x_coordinate"
    assert ds["mesh_face_x"].attrs.get("units") == "m"
    assert ds["mesh_face_x"].attrs.get("bounds") == "mesh_face_xbnds"
    assert ds["mesh_face_x"].attrs.get("grid_mapping") == "projection"
    assert ds["mesh_face_y"].attrs.get("standard_name") == "projection_y_coordinate"
    assert ds["mesh_face_y"].attrs.get("units") == "m"
    assert ds["mesh_face_y"].attrs.get("bounds") == "mesh_face_ybnds"
    assert ds["mesh_face_y"].attrs.get("grid_mapping") == "projection"


def test_mesh_dis_face_bounds_fill_in_encoding(structured_grid, modeltime):
    """mesh_face_xbnds/ybnds _FillValue must be FILL_FLOAT64 in encoding (DIS path).

    These are padded float arrays where padding slots must use NF90_FILL_DOUBLE
    so CF validators and masking tools correctly identify them. xarray's default
    for float64 is NaN which is not a valid CF fill value.
    """
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "_FillValue" not in ds["mesh_face_xbnds"].attrs
    assert "_FillValue" not in ds["mesh_face_ybnds"].attrs
    assert ds["mesh_face_xbnds"].encoding.get("_FillValue") == FILL_FLOAT64
    assert ds["mesh_face_ybnds"].encoding.get("_FillValue") == FILL_FLOAT64


def test_mesh_disv_node_coord_attrs(vertex_grid, modeltime):
    """mesh_node_x/y must carry standard_name, units, and grid_mapping (DISV path)."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    for var, sn in [
        ("mesh_node_x", "projection_x_coordinate"),
        ("mesh_node_y", "projection_y_coordinate"),
    ]:
        assert ds[var].attrs.get("standard_name") == sn
        assert ds[var].attrs.get("units") == "m"
        assert ds[var].attrs.get("grid_mapping") == "projection"


def test_mesh_disv_face_coord_attrs(vertex_grid, modeltime):
    """mesh_face_x/y must carry standard_name, units, bounds, and grid_mapping (DISV path)."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert ds["mesh_face_x"].attrs.get("standard_name") == "projection_x_coordinate"
    assert ds["mesh_face_x"].attrs.get("bounds") == "mesh_face_xbnds"
    assert ds["mesh_face_x"].attrs.get("grid_mapping") == "projection"
    assert ds["mesh_face_y"].attrs.get("standard_name") == "projection_y_coordinate"
    assert ds["mesh_face_y"].attrs.get("bounds") == "mesh_face_ybnds"
    assert ds["mesh_face_y"].attrs.get("grid_mapping") == "projection"


def test_mesh_disv_face_bounds_fill_in_encoding(vertex_grid, modeltime):
    """mesh_face_xbnds/ybnds _FillValue must be FILL_FLOAT64 in encoding (DISV path)."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "_FillValue" not in ds["mesh_face_xbnds"].attrs
    assert "_FillValue" not in ds["mesh_face_ybnds"].attrs
    assert ds["mesh_face_xbnds"].encoding.get("_FillValue") == FILL_FLOAT64
    assert ds["mesh_face_ybnds"].encoding.get("_FillValue") == FILL_FLOAT64


def test_mesh_disv_face_bounds_padding_data_values(vertex_grid_mixed_poly, modeltime):
    """Padding slots in face bounds arrays must contain FILL_FLOAT64, not FILL_INT64.

    When cells have fewer vertices than max_face_nodes, _topology() pads the
    face_nodes array with FILL_INT64 and then must write FILL_FLOAT64 into the
    corresponding slots of the float x_bnds/y_bnds arrays.  Using FILL_INT64
    as the data value (-2147483647) is wrong for float arrays and would fail
    CF validators.
    """
    ds = vertex_grid_mixed_poly.to_xarray(modeltime=modeltime)
    x_bnds = ds["mesh_face_xbnds"].values
    y_bnds = ds["mesh_face_ybnds"].values
    fn = ds["mesh_face_nodes"].values
    mask = fn == FILL_INT64
    assert mask.any(), "fixture must produce at least one padding slot"
    assert (x_bnds[mask] == FILL_FLOAT64).all(), "x_bnds padding must be FILL_FLOAT64"
    assert (y_bnds[mask] == FILL_FLOAT64).all(), "y_bnds padding must be FILL_FLOAT64"
    assert not (x_bnds == FILL_INT64).any(), "x_bnds must not contain integer fill sentinel"
    assert not (y_bnds == FILL_INT64).any(), "y_bnds must not contain integer fill sentinel"


def test_mesh_geometry_fill_value_suppressed(structured_grid, modeltime):
    """mesh_node_x/y and mesh_face_x/y _FillValue must be suppressed — no missing geometry."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    for var in ("mesh_node_x", "mesh_node_y", "mesh_face_x", "mesh_face_y"):
        assert (
            ds[var].encoding.get("_FillValue") is None
        ), f"{var} _FillValue should be suppressed in encoding"


def test_mesh_face_nodes_attrs(structured_grid, modeltime):
    """mesh_face_nodes must carry cf_role, long_name, and 1-based start_index."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    fn = ds["mesh_face_nodes"]
    assert fn.attrs.get("cf_role") == "face_node_connectivity"
    assert int(fn.attrs.get("start_index", -1)) == 1, "face-node connectivity must be 1-based"
    assert fn.attrs.get("long_name"), "long_name must be non-empty"


# data variable fill values
def test_structured_float_param_fill_value(structured_grid):
    """Float GRIDDATA params (e.g. NPF K) must use FILL_FLOAT64 as _FillValue encoding."""
    ds = _structured_param_ds(structured_grid, name="k")
    assert ds["npf_k"].encoding.get("_FillValue") == FILL_FLOAT64


def test_structured_int_param_fill_value(structured_grid):
    """Integer GRIDDATA params (e.g. NPF icelltype) must use FILL_INT64 as _FillValue encoding."""
    ds = _structured_param_ds(structured_grid, name="icelltype")
    assert ds["npf_icelltype"].encoding.get("_FillValue") == FILL_INT64


def test_period_param_fill_value():
    """PERIOD block array params (e.g. WELG q) must use FILL_DNODATA (3e+30) as _FillValue.

    Cells without a well are marked with MF6's DNODATA sentinel, distinct from
    the CF fill value (FILL_FLOAT64) used for dense GRIDDATA arrays.
    """
    context = {
        "mesh": None,
        "modelname": "testmodel",
        "gridtype": "structured",
        "package_name": "welg_0",
        "package_type": "gwf-welg",
        "dims": [2, 2, 3, 3],
    }
    param = NetCDFParam.from_dict({"name": "q", "attrs": {}}, context=context)
    ds = param.to_xarray()
    assert ds["welg_0_q"].encoding.get("_FillValue") == FILL_DNODATA


def test_mesh_dis_float_param_fill_value(structured_grid):
    """Float GRIDDATA params in layered-mesh DIS format must use FILL_FLOAT64."""
    ds = _structured_param_ds(structured_grid, name="k", mesh="layered", layer=1)
    assert ds["npf_k_l1"].encoding.get("_FillValue") == FILL_FLOAT64


def test_mesh_dis_int_param_fill_value(structured_grid):
    """Integer GRIDDATA params in layered-mesh DIS format must use FILL_INT64."""
    ds = _structured_param_ds(structured_grid, name="icelltype", mesh="layered", layer=1)
    assert ds["npf_icelltype_l1"].encoding.get("_FillValue") == FILL_INT64


# modflow_input attribute format
def test_structured_param_modflow_input(structured_grid):
    """modflow_input must follow 'modelname/packagename/paramname' format (all lowercase)."""
    ds = _structured_param_ds(structured_grid, name="k")
    mi = ds["npf_k"].attrs.get("modflow_input", "")
    assert mi, "modflow_input attr missing on structured data variable"
    parts = mi.split("/")
    assert len(parts) == 3, f"modflow_input must have 3 slash-separated parts: {mi!r}"
    assert mi == mi.lower(), f"modflow_input must be lowercase: {mi!r}"
    assert parts[1] == "npf"
    assert parts[2] == "k"


def test_mesh_dis_param_modflow_input(structured_grid):
    """modflow_input must follow the same format for layered-mesh DIS face variables."""
    ds = _structured_param_ds(structured_grid, name="k", mesh="layered", layer=1)
    mi = ds["npf_k_l1"].attrs.get("modflow_input", "")
    assert mi, "modflow_input attr missing on mesh face data variable"
    parts = mi.split("/")
    assert len(parts) == 3, f"modflow_input must have 3 slash-separated parts: {mi!r}"
    assert mi == mi.lower(), f"modflow_input must be lowercase: {mi!r}"
    assert parts[1] == "npf"
    assert parts[2] == "k"
