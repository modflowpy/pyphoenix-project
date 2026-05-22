"""Tests for flopy4.mf6.utils.netcdf_postprocess."""

import numpy as np
import pytest
import xarray as xr

from flopy4.mf6.utils.netcdf_postprocess import postprocess_mesh_nc, postprocess_structured_nc

# WKT string matching what MF6 writes for EPSG:26911
_WKT = (
    'PROJCS["NAD83 / UTM zone 11N",'
    'GEOGCS["NAD83",'
    'DATUM["North_American_Datum_1983",'
    'SPHEROID["GRS 1980",6378137,298.257222101]],'
    'PRIMEM["Greenwich",0],'
    'UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],'
    'PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",-117],'
    'PARAMETER["scale_factor",0.9996],'
    'PARAMETER["false_easting",500000],'
    'PARAMETER["false_northing",0],'
    'UNIT["metre",1],'
    'AUTHORITY["EPSG","26911"]]'
)


def _write_minimal_mesh_nc(path):
    """Write a minimal mesh NC file as MF6 would — ``wkt`` only, no crs_wkt."""
    n = 4
    ds = xr.Dataset(
        {
            "projection": xr.Variable([], np.int32(1), attrs={"wkt": _WKT}),
            "head_l1": xr.Variable(
                ["time", "nmesh_face"],
                np.zeros((2, n), dtype=np.float64),
                attrs={
                    "mesh": "mesh",
                    "location": "face",
                    "coordinates": "mesh_face_x mesh_face_y",
                    "grid_mapping": "projection",
                },
            ),
        }
    )
    ds.to_netcdf(path)
    ds.close()


def test_postprocess_mesh_nc_adds_crs_wkt(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_mesh_nc(src)
    dst = tmp_path / "out_fixed.nc"
    result = postprocess_mesh_nc(src, out=dst)
    assert result == dst

    ds = xr.open_dataset(dst, mask_and_scale=False)
    p = ds["projection"]
    assert "wkt" in p.attrs
    assert "crs_wkt" in p.attrs
    assert p.attrs["crs_wkt"] == p.attrs["wkt"]
    assert "grid_mapping_name" in p.attrs
    assert p.attrs["grid_mapping_name"] == "transverse_mercator"
    ds.close()


def test_postprocess_mesh_nc_inplace(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_mesh_nc(src)
    result = postprocess_mesh_nc(src)
    assert result == src

    ds = xr.open_dataset(src, mask_and_scale=False)
    assert "crs_wkt" in ds["projection"].attrs
    ds.close()


def test_postprocess_mesh_nc_idempotent(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_mesh_nc(src)
    postprocess_mesh_nc(src)
    postprocess_mesh_nc(src)

    ds = xr.open_dataset(src, mask_and_scale=False)
    p = ds["projection"]
    assert "crs_wkt" in p.attrs
    assert "grid_mapping_name" in p.attrs
    ds.close()


def test_postprocess_mesh_nc_no_projection(tmp_path):
    """Files without a projection variable are returned unchanged."""
    src = tmp_path / "no_proj.nc"
    ds = xr.Dataset({"head": xr.Variable(["x"], np.zeros(3))})
    ds.to_netcdf(src)
    ds.close()

    result = postprocess_mesh_nc(src)
    ds2 = xr.open_dataset(result, mask_and_scale=False)
    assert "projection" not in ds2
    ds2.close()


def _write_minimal_structured_nc(path):
    """Write a minimal structured NC file as MF6 would — ``crs_wkt`` only."""
    nx, ny = 4, 3
    x = np.array([500.0, 1000.0, 1500.0, 2000.0])
    y = np.array([3000.0, 2000.0, 1000.0])
    x_bnds = np.array([[x[i] - 250, x[i] + 250] for i in range(nx)])
    # y_bnds[row] = [bottom, top] — same convention as grid.py _structured_dataset
    y_bnds = np.array([[y[i] - 500, y[i] + 500] for i in range(ny)])
    ds = xr.Dataset(
        {
            "projection": xr.Variable([], np.int32(1), attrs={"crs_wkt": _WKT}),
            "x_bnds": xr.Variable(["x", "bnd"], x_bnds),
            "y_bnds": xr.Variable(["y", "bnd"], y_bnds),
            "head": xr.Variable(
                ["time", "z", "y", "x"],
                np.zeros((2, 1, ny, nx), dtype=np.float64),
                attrs={
                    "grid_mapping": "projection",
                    "coordinates": "x y",
                    "_FillValue": 1e30,
                },
            ),
        },
        coords={
            "x": xr.Variable(["x"], x, attrs={"standard_name": "projection_x_coordinate"}),
            "y": xr.Variable(["y"], y, attrs={"standard_name": "projection_y_coordinate"}),
        },
    )
    ds.to_netcdf(path)
    ds.close()


def test_postprocess_structured_nc_adds_attrs(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_structured_nc(src)
    dst = tmp_path / "out_fixed.nc"
    result = postprocess_structured_nc(src, out=dst)
    assert result == dst

    ds = xr.open_dataset(dst, mask_and_scale=False)
    p = ds["projection"]
    assert "crs_wkt" in p.attrs
    assert "wkt" in p.attrs
    assert p.attrs["wkt"] == p.attrs["crs_wkt"]
    assert "grid_mapping_name" in p.attrs
    assert p.attrs["grid_mapping_name"] == "transverse_mercator"
    assert "GeoTransform" in p.attrs
    assert "spatial_ref" in p.attrs
    ds.close()


def test_postprocess_structured_nc_geotransform_values(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_structured_nc(src)
    postprocess_structured_nc(src)

    ds = xr.open_dataset(src, mask_and_scale=False)
    gt = [float(v) for v in ds["projection"].attrs["GeoTransform"].split()]
    # x_left  = x_bnds[0,0] = 250,  x_right = x_bnds[-1,1] = 2250
    # y_top   = y_bnds[0,1] = 3500, y_bot   = y_bnds[-1,0] = 500
    assert gt[0] == pytest.approx(250.0)  # x origin (left edge)
    assert gt[1] == pytest.approx(500.0)  # dx = (2250-250)/4
    assert gt[3] == pytest.approx(3500.0)  # y origin (top edge)
    assert gt[5] == pytest.approx(-1000.0)  # dy = (500-3500)/3
    ds.close()


def test_postprocess_structured_nc_idempotent(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_structured_nc(src)
    postprocess_structured_nc(src)
    postprocess_structured_nc(src)

    ds = xr.open_dataset(src, mask_and_scale=False)
    assert "wkt" in ds["projection"].attrs
    assert "GeoTransform" in ds["projection"].attrs
    ds.close()


def test_postprocess_structured_nc_no_projection(tmp_path):
    src = tmp_path / "no_proj.nc"
    ds = xr.Dataset({"head": xr.Variable(["x"], np.zeros(3))})
    ds.to_netcdf(src)
    ds.close()

    result = postprocess_structured_nc(src)
    ds2 = xr.open_dataset(result, mask_and_scale=False)
    assert "projection" not in ds2
    ds2.close()
