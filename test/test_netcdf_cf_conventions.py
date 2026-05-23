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
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.netcdf import NetCDFParam
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
    """Both crs_wkt and wkt must be present and equal on the projection variable."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.STRUCTURED)
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs, "crs_wkt missing from projection variable"
    assert "wkt" in proj.attrs, "wkt missing from projection variable"
    assert proj.attrs["crs_wkt"] == proj.attrs["wkt"], "crs_wkt and wkt must be identical"
    assert len(proj.attrs["crs_wkt"]) > 0, "crs_wkt must not be empty"
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
    """Both crs_wkt and wkt must be present and equal on the projection variable."""
    ds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert "projection" in ds
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs
    assert "wkt" in proj.attrs
    assert proj.attrs["crs_wkt"] == proj.attrs["wkt"]
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
    """Both crs_wkt and wkt must be present and equal on the projection variable."""
    ds = vertex_grid.to_xarray(modeltime=modeltime)
    assert "projection" in ds
    proj = ds["projection"]
    assert "crs_wkt" in proj.attrs
    assert "wkt" in proj.attrs
    assert proj.attrs["crs_wkt"] == proj.attrs["wkt"]
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
