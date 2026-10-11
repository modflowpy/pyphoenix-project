"""Tests for flopy4.mf6.utils.netcdf_postprocess."""

import subprocess
import sys

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
    assert p.attrs["crs_wkt"].startswith("PROJCRS["), "crs_wkt must be WKT2"
    assert p.attrs["wkt"].startswith("PROJCS["), "wkt must be WKT1"
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
    assert p.attrs["crs_wkt"].startswith("PROJCRS["), "crs_wkt must be WKT2"
    assert p.attrs["wkt"].startswith("PROJCS["), "wkt must be WKT1"
    assert "grid_mapping_name" in p.attrs
    assert p.attrs["grid_mapping_name"] == "transverse_mercator"
    assert "GeoTransform" not in p.attrs
    assert "spatial_ref" not in p.attrs
    assert p.attrs["longitude_of_central_meridian"] == pytest.approx(-117.0)
    assert p.attrs["latitude_of_projection_origin"] == pytest.approx(0.0)
    assert p.attrs["scale_factor_at_central_meridian"] == pytest.approx(0.9996)
    assert p.attrs["false_easting"] == pytest.approx(500_000.0)
    assert p.attrs["false_northing"] == pytest.approx(0.0)
    assert p.attrs["semi_major_axis"] == pytest.approx(6378137.0)
    assert p.attrs["inverse_flattening"] == pytest.approx(298.257222101)
    ds.close()


def test_postprocess_structured_nc_idempotent(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_structured_nc(src)
    postprocess_structured_nc(src)
    postprocess_structured_nc(src)

    ds = xr.open_dataset(src, mask_and_scale=False)
    assert "wkt" in ds["projection"].attrs
    assert ds["projection"].attrs["false_easting"] == pytest.approx(500_000.0)
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


def test_postprocess_structured_nc_no_bnds(tmp_path):
    """CF numeric grid_mapping parameters only need crs_wkt -- they are
    added whether or not x_bnds/y_bnds are present."""
    x = np.array([100.0, 200.0, 300.0])
    y = np.array([600.0, 500.0, 400.0])
    src = tmp_path / "no_bnds.nc"
    ds = xr.Dataset(
        {"projection": xr.Variable([], np.int32(1), attrs={"crs_wkt": _WKT})},
        coords={
            "x": xr.Variable(["x"], x),
            "y": xr.Variable(["y"], y),
        },
    )
    ds.to_netcdf(src)
    ds.close()

    postprocess_structured_nc(src)
    ds2 = xr.open_dataset(src, mask_and_scale=False)
    assert ds2["projection"].attrs["grid_mapping_name"] == "transverse_mercator"
    assert ds2["projection"].attrs["false_easting"] == pytest.approx(500_000.0)
    ds2.close()


def test_postprocess_structured_nc_already_wrapped_rotated(tmp_path):
    """A rotated grid's crs_wkt may already be a wrapped DerivedProjectedCRS
    (current-release MF6 output) -- postprocessing it must be a safe no-op,
    not crash. WKT1 has no derived-CRS syntax, so wkt must come from the
    unwrapped base CRS, not from converting the wrapped CRS directly."""
    pyproj = pytest.importorskip("pyproj")
    from flopy4.mf6.utils.crs import wrap_rotated_crs

    base = pyproj.CRS.from_epsg(26918)
    wrapped = wrap_rotated_crs(base, 500000.0, 4500000.0, 15.0)
    wrapped_wkt = wrapped.to_wkt(pyproj.enums.WktVersion.WKT2_2019)
    assert wrapped_wkt.startswith("DERIVEDPROJCRS[")

    src = tmp_path / "rotated.nc"
    ds = xr.Dataset(
        {"projection": xr.Variable([], np.int32(1), attrs={"crs_wkt": wrapped_wkt})},
        coords={
            "x": xr.Variable(["x"], np.array([50.0, 150.0, 250.0])),
            "y": xr.Variable(["y"], np.array([100.0, 0.0])),
        },
    )
    ds.to_netcdf(src)
    ds.close()

    postprocess_structured_nc(src)
    ds2 = xr.open_dataset(src, mask_and_scale=False)
    p = ds2["projection"]
    assert p.attrs["crs_wkt"].startswith("DERIVEDPROJCRS["), "wrap must be preserved"
    assert p.attrs["wkt"].startswith("PROJCS["), "wkt must be the unwrapped base CRS"
    assert p.attrs["grid_mapping_name"] == "transverse_mercator"
    assert p.attrs["false_easting"] == pytest.approx(500_000.0)
    ds2.close()


def _run_ncfix(*args):
    """Invoke ncfix via the module entry point so it works before pip install."""
    return subprocess.run(
        [sys.executable, "-m", "flopy4.mf6.utils.netcdf_postprocess", *args],
        capture_output=True,
        text=True,
    )


def test_ncfix_cli_structured(tmp_path):
    src = tmp_path / "structured.nc"
    _write_minimal_structured_nc(src)
    dst = tmp_path / "fixed.nc"
    result = _run_ncfix(str(src), "-o", str(dst), "--mode", "structured")
    assert result.returncode == 0, result.stderr

    ds = xr.open_dataset(dst, mask_and_scale=False)
    assert "GeoTransform" not in ds["projection"].attrs
    assert "crs_wkt" in ds["projection"].attrs
    assert ds["projection"].attrs["false_easting"] == 500_000.0
    ds.close()


def test_ncfix_cli_mesh_explicit_mode(tmp_path):
    src = tmp_path / "out.nc"
    _write_minimal_mesh_nc(src)
    result = _run_ncfix(str(src), "--mode", "mesh", "--verbose")
    assert result.returncode == 0, result.stderr
    assert "wrote:" in result.stdout

    ds = xr.open_dataset(src, mask_and_scale=False)
    assert "crs_wkt" in ds["projection"].attrs
    ds.close()


def test_ncfix_cli_auto_detect_structured(tmp_path):
    """Auto-detect falls back to structured when no UGRID markers are present."""
    src = tmp_path / "out.nc"
    _write_minimal_structured_nc(src)
    result = _run_ncfix(str(src), "--verbose")
    assert result.returncode == 0, result.stderr
    assert "wrote:" in result.stdout

    ds = xr.open_dataset(src, mask_and_scale=False)
    assert "GeoTransform" not in ds["projection"].attrs
    assert ds["projection"].attrs["false_easting"] == 500_000.0
    ds.close()
