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
import xugrid as xu
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
    """UGRID topology must be present as an xu.Ugrid2d grid on the returned UgridDataset."""
    uds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert isinstance(uds, xu.UgridDataset), "expected UgridDataset for layered-mesh format"
    assert len(uds.grids) == 1, "expected exactly one UGRID grid"
    assert isinstance(uds.grids[0], xu.Ugrid2d)
    assert uds.grids[0].name == "mesh", "mesh topology variable missing"
    assert uds.grids[0].to_dataset()["mesh"].attrs.get("cf_role") == "mesh_topology"


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
    """UGRID topology must be present as an xu.Ugrid2d grid on the returned UgridDataset."""
    uds = vertex_grid.to_xarray(modeltime=modeltime)
    assert isinstance(uds, xu.UgridDataset), "expected UgridDataset for vertex grid"
    assert len(uds.grids) == 1, "expected exactly one UGRID grid"
    assert isinstance(uds.grids[0], xu.Ugrid2d)
    assert uds.grids[0].name == "mesh"
    assert uds.grids[0].to_dataset()["mesh"].attrs.get("cf_role") == "mesh_topology"


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


def test_mesh_dis_face_bounds(structured_grid, modeltime):
    """mesh_face_xbnds/ybnds must be present with shape (nfaces, 4) for a structured grid."""
    uds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    nfaces = structured_grid.nrow * structured_grid.ncol
    for var in ("mesh_face_xbnds", "mesh_face_ybnds"):
        assert var in uds, f"{var} missing from layered-mesh DIS dataset"
        assert uds[var].shape == (nfaces, 4), f"{var} shape mismatch: {uds[var].shape}"


def test_mesh_disv_face_bounds(vertex_grid, modeltime):
    """mesh_face_xbnds/ybnds must be present with shape (ncpl, max_nodes) for a vertex grid."""
    uds = vertex_grid.to_xarray(modeltime=modeltime)
    for var in ("mesh_face_xbnds", "mesh_face_ybnds"):
        assert var in uds, f"{var} missing from layered-mesh DISV dataset"
        assert uds[var].shape[0] == vertex_grid.ncpl, f"{var} face dimension mismatch"


def test_mesh_dis_face_nodes_fill_in_encoding(structured_grid, modeltime):
    """The UGRID fill value passed to xu.Ugrid2d must match FILL_INT64 (DIS path)."""
    from flopy4.mf6.constants import FILL_INT64

    uds = structured_grid.to_xarray(modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH)
    assert uds.grids[0].fill_value == FILL_INT64


def test_mesh_disv_face_nodes_fill_in_encoding(vertex_grid, modeltime):
    """The UGRID fill value passed to xu.Ugrid2d must match FILL_INT64 (DISV path)."""
    from flopy4.mf6.constants import FILL_INT64

    uds = vertex_grid.to_xarray(modeltime=modeltime)
    assert uds.grids[0].fill_value == FILL_INT64


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
    assert coords_attr == "" or all(c not in coords_attr for c in ["y", "x"]), (
        f"structured data var should not carry redundant coordinates attr: {coords_attr!r}"
    )


def _write_mesh_netcdf(grid_uds, param_ds, path):
    """Write a UGRID dataset to disk using MF6's UGRID dimension naming."""
    grid = grid_uds.grids[0]
    topo = grid.assign_face_coords(grid.to_dataset())
    _dim_rename = {
        k: v
        for k, v in {
            "mesh_nFaces": "nmesh_face",
            "mesh_nNodes": "nmesh_node",
            "mesh_nMax_face_nodes": "max_nmesh_face_nodes",
        }.items()
        if k in topo.dims
    }
    if _dim_rename:
        topo = topo.rename(_dim_rename)
        for attr in ("face_dimension", "node_dimension", "max_face_nodes_dimension"):
            if topo["mesh"].attrs.get(attr) in _dim_rename:
                topo["mesh"].attrs[attr] = _dim_rename[topo["mesh"].attrs[attr]]
    topo.merge(xr.merge([grid_uds.obj, param_ds])).to_netcdf(path)


def test_mesh_topology_in_netcdf(structured_grid, modeltime, tmp_path):
    """UGRID topology variables must be present in the written file with MF6 dimension names."""
    grid_uds = structured_grid.to_xarray(
        modeltime=modeltime, netcdf_format=NetCDFFormat.LAYERED_MESH
    )
    path = tmp_path / "mesh_topology.nc"
    _write_mesh_netcdf(grid_uds, xr.Dataset(), path)

    nc4 = pytest.importorskip("netCDF4")
    root = nc4.Dataset(path)
    try:
        variables = list(root.variables.keys())
        dims = list(root.dimensions.keys())
        assert "mesh" in variables, f"mesh topology variable missing; got {variables}"
        assert "mesh_face_nodes" in variables, "mesh_face_nodes missing"
        assert "mesh_node_x" in variables, "mesh_node_x missing"
        assert "mesh_node_y" in variables, "mesh_node_y missing"
        assert "mesh_face_x" in variables, "mesh_face_x missing"
        assert "mesh_face_y" in variables, "mesh_face_y missing"
        assert "projection" in variables, "projection (CRS) variable missing"
        assert "nmesh_face" in dims, f"nmesh_face dimension missing; got {dims}"
        assert "nmesh_node" in dims, f"nmesh_node dimension missing; got {dims}"
        mesh_attrs = {a: root["mesh"].getncattr(a) for a in root["mesh"].ncattrs()}
        assert mesh_attrs.get("cf_role") == "mesh_topology"
        assert mesh_attrs.get("face_dimension") == "nmesh_face"
    finally:
        root.close()


def test_mesh_data_var_coordinates_survives_roundtrip(structured_grid, modeltime, tmp_path):
    """coordinates = 'mesh_face_x mesh_face_y' on mesh face vars must survive round-trip.

    Verified via raw netCDF4 because xarray strips the coordinates attr when reopening.
    """
    grid_uds = structured_grid.to_xarray(
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
    path = tmp_path / "mesh_roundtrip.nc"
    _write_mesh_netcdf(grid_uds, param.to_xarray(), path)
    attrs = _raw_var_attrs(path, "npf_k_l1")
    coords_attr = attrs.get("coordinates", "")
    assert "mesh_face_x" in coords_attr and "mesh_face_y" in coords_attr, (
        f"coordinates attr missing or wrong on raw disk: {coords_attr!r}"
    )


def test_mesh_data_var_cf_attrs_survive_roundtrip(structured_grid, modeltime, tmp_path):
    """mesh, location, and grid_mapping attrs on face data vars must survive round-trip."""
    grid_uds = structured_grid.to_xarray(
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
    path = tmp_path / "mesh_cf_attrs_roundtrip.nc"
    _write_mesh_netcdf(grid_uds, param.to_xarray(), path)
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
