"""Post-processing utilities to bring MF6 output NC files into CF/CRS parity
with flopy4 input NC files.

MF6 writes a ``projection`` variable but omits some attributes required for
full CF-1.11 compliance and GDAL-based tool support.

- **Mesh output**: missing ``crs_wkt`` and ``grid_mapping_name``.
- **Structured output**: missing ``wkt``, ``grid_mapping_name``, and the GDAL
  georeferencing attributes (``GeoTransform`` / ``spatial_ref``) needed for
  correct placement in QGIS and other GDAL-based tools.  ArcGIS Pro does not
  require these attributes — it reads ``crs_wkt`` directly from raw MF6 output.

Usage::

    from flopy4.mf6.utils.netcdf_postprocess import (
        postprocess_mesh_nc,
        postprocess_structured_nc,
    )
    postprocess_mesh_nc("ff-netcdf.nc")                    # mesh — in-place
    postprocess_structured_nc("ff-netcdf.nc")              # structured — in-place
    postprocess_structured_nc("ff-netcdf.nc", out="fixed.nc")  # new file
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import xarray as xr


def _apply_mesh_crs_attrs(ds: xr.Dataset) -> xr.Dataset:
    """Add ``crs_wkt`` and ``grid_mapping_name`` to the ``projection`` variable.

    MF6 mesh output already writes ``wkt``; this brings the variable into full
    CF-1.11 parity with flopy4 input files.
    """
    if "projection" not in ds:
        return ds

    wkt = ds["projection"].attrs.get("wkt")
    if wkt is None:
        return ds

    try:
        from pyproj import CRS as ProjCRS
    except ImportError:
        return ds

    from pyproj.enums import WktVersion

    crs = ProjCRS.from_wkt(wkt)
    cf = crs.to_cf()

    # wkt on mesh output is WKT1; crs_wkt must be WKT2 per CF-1.11
    ds["projection"].attrs.setdefault("crs_wkt", crs.to_wkt(WktVersion.WKT2_2019))
    gmn = cf.get("grid_mapping_name")
    if gmn:
        ds["projection"].attrs.setdefault("grid_mapping_name", gmn)

    return ds


def _apply_structured_crs_attrs(ds: xr.Dataset) -> xr.Dataset:
    """Add ``wkt``, ``grid_mapping_name``, ``GeoTransform``, and ``spatial_ref``
    to the ``projection`` variable of an MF6 structured output NC file.

    MF6 structured output already writes ``crs_wkt`` and ``grid_mapping`` on
    x/y/head; this adds the remaining attrs needed for GDAL-based tools.
    """
    if "projection" not in ds:
        return ds

    wkt = ds["projection"].attrs.get("crs_wkt")
    if wkt is None:
        return ds

    try:
        from pyproj import CRS as ProjCRS
    except ImportError:
        return ds

    from pyproj.enums import WktVersion

    crs = ProjCRS.from_wkt(wkt)
    cf = crs.to_cf()

    # MF6 structured output writes WKT1 to crs_wkt; overwrite with WKT2 per CF-1.11.
    # wkt and spatial_ref remain WKT1 for GDAL/legacy-tool compatibility.
    _wkt1 = crs.to_wkt(WktVersion.WKT1_GDAL)
    _wkt2 = crs.to_wkt(WktVersion.WKT2_2019)
    ds["projection"].attrs["crs_wkt"] = _wkt2
    ds["projection"].attrs.setdefault("wkt", _wkt1)
    gmn = cf.get("grid_mapping_name")
    if gmn:
        ds["projection"].attrs.setdefault("grid_mapping_name", gmn)

    # Derive GeoTransform from x_bnds/y_bnds if available, otherwise from
    # cell-centre spacing. GDAL reads GeoTransform from the grid_mapping
    # variable (not global attrs) to set the raster extent.
    if "x_bnds" in ds and "y_bnds" in ds:
        xb = ds["x_bnds"].values
        yb = ds["y_bnds"].values
        x_left = float(xb[0, 0])
        x_right = float(xb[-1, 1])
        y_top = float(yb[0, 1])  # y_bnds[row, 1] = top of row
        y_bot = float(yb[-1, 0])  # y_bnds[row, 0] = bottom of row
        ncol = ds.sizes.get("x", xb.shape[0])
        nrow = ds.sizes.get("y", yb.shape[0])
        dx_eff = (x_right - x_left) / ncol
        dy_eff = (y_bot - y_top) / nrow  # negative for north-up
    elif "x" in ds and "y" in ds:
        x = ds["x"].values
        y = ds["y"].values
        dx = float(x[1] - x[0]) if len(x) > 1 else 1.0
        dy = float(y[1] - y[0]) if len(y) > 1 else 1.0
        x_left = float(x[0]) - 0.5 * dx
        y_top = float(y[0]) - 0.5 * dy
        dx_eff = dx
        dy_eff = dy
    else:
        return ds

    gt = [x_left, dx_eff, 0.0, y_top, 0.0, dy_eff]
    ds["projection"].attrs.setdefault("GeoTransform", " ".join(str(v) for v in gt))
    ds["projection"].attrs.setdefault("spatial_ref", _wkt1)

    return ds


def postprocess_mesh_nc(
    path: Union[str, Path],
    out: Union[str, Path, None] = None,
) -> Path:
    """Post-process an MF6 UGRID/mesh output NC file for CF-1.11 compliance.

    Adds the missing ``crs_wkt`` and ``grid_mapping_name`` attributes to the
    ``projection`` variable so the file matches the conventions written by
    flopy4 for input files.

    Parameters
    ----------
    path:
        Path to the MF6 mesh output ``.nc`` file.
    out:
        Destination path.  Defaults to overwriting *path* in-place.

    Returns
    -------
    Path
        Path to the written file.
    """
    path = Path(path)
    out = Path(out) if out is not None else path

    with xr.open_dataset(path, mask_and_scale=False) as ds:
        ds = _apply_mesh_crs_attrs(ds)
        ds.load()

    encoding = {v: {"_FillValue": None} for v in ds.coords}
    ds.to_netcdf(out, encoding=encoding)
    ds.close()
    return out


def postprocess_structured_nc(
    path: Union[str, Path],
    out: Union[str, Path, None] = None,
) -> Path:
    """Post-process an MF6 CF-structured output NC file for full CF-1.11 and
    GDAL compliance.

    Adds the missing ``wkt``, ``grid_mapping_name``, ``GeoTransform``, and
    ``spatial_ref`` attributes to the ``projection`` variable so the file
    matches the conventions written by flopy4 for input files and is correctly
    placed by QGIS and other GDAL-based tools.  ArcGIS Pro reads ``crs_wkt``
    directly from raw MF6 output and does not require this post-processing.

    Parameters
    ----------
    path:
        Path to the MF6 structured output ``.nc`` file.
    out:
        Destination path.  Defaults to overwriting *path* in-place.

    Returns
    -------
    Path
        Path to the written file.
    """
    path = Path(path)
    out = Path(out) if out is not None else path

    with xr.open_dataset(path, mask_and_scale=False) as ds:
        ds = _apply_structured_crs_attrs(ds)
        ds.load()

    encoding = {v: {"_FillValue": None} for v in ds.coords}
    ds.to_netcdf(out, encoding=encoding)
    ds.close()
    return out
