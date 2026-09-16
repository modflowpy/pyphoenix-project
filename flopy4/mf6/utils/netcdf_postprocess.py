"""Post-processing utilities to bring MF6 output NC files into CF/CRS parity
with flopy4 input NC files.

MF6 6.8.0+ already writes ``crs_wkt``/``grid_mapping_name`` (mesh) and
``wkt``/``crs_wkt``/``grid_mapping``/``grid_mapping_name`` (structured) --
this module is then a no-op bridge for those.  Two things it still does:

- **Legacy pre-6.8.0 files**: backfill missing ``wkt``/``crs_wkt``/
  ``grid_mapping_name``, and fix ``crs_wkt`` holding WKT1 instead of WKT2
  (a real bug present through 6.7.0, fixed in 6.8.0).
- **Structured output, any current release**: add ``GeoTransform`` and
  ``spatial_ref`` for GDAL-based tools (QGIS) -- not yet in any MF6
  release.  ArcGIS Pro reads ``crs_wkt`` directly and doesn't need this.

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

import argparse
from pathlib import Path
from typing import Union

import xarray as xr


def _apply_mesh_crs_attrs(ds: xr.Dataset) -> xr.Dataset:
    """Add ``crs_wkt`` and ``grid_mapping_name`` to the ``projection`` variable.

    No-op on MF6 6.8.0+, which already writes both. Bridges legacy
    pre-6.8.0 files that only have ``wkt``.
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

    # wkt on mesh output is WKT1; crs_wkt must be WKT2 per CF-1.13
    ds["projection"].attrs.setdefault("crs_wkt", crs.to_wkt(WktVersion.WKT2_2019))
    gmn = cf.get("grid_mapping_name")
    if gmn:
        ds["projection"].attrs.setdefault("grid_mapping_name", gmn)

    return ds


def _apply_structured_crs_attrs(ds: xr.Dataset) -> xr.Dataset:
    """Add ``wkt``/``grid_mapping_name`` (legacy bridge), fix ``crs_wkt``
    (legacy bug), and add ``GeoTransform``/``spatial_ref`` (still needed --
    not yet in any released MF6) to the ``projection`` variable.
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

    # Pre-6.8.0 MF6 wrote WKT1 to crs_wkt (bug, fixed in 6.8.0); overwrite
    # unconditionally -- idempotent on already-correct 6.8.0+ files.
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
    """Post-process an MF6 UGRID/mesh output NC file for CF-1.13 compliance.

    Backfills ``crs_wkt`` and ``grid_mapping_name`` on the ``projection``
    variable for legacy pre-6.8.0 files; a no-op on 6.8.0+.

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
    """Post-process an MF6 CF-structured output NC file for CF-1.13/GDAL compliance.

    Backfills ``wkt``/``grid_mapping_name`` (legacy pre-6.8.0 bridge, no-op on
    6.8.0+) and adds ``GeoTransform``/``spatial_ref`` (still needed on any
    current release) for QGIS/GDAL placement.  ArcGIS Pro reads ``crs_wkt``
    directly and doesn't need this.

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


def _detect_mode(path: Path) -> str:
    with xr.open_dataset(path, mask_and_scale=False) as ds:
        conventions = ds.attrs.get("Conventions", "")
        has_ugrid = "UGRID" in conventions or "mesh_face_nodes" in ds
    return "mesh" if has_ugrid else "structured"


def main():
    parser = argparse.ArgumentParser(
        prog="ncfix",
        description=(
            "Post-process an MF6 output NetCDF file to add missing CF-1.13 / GDAL "
            "attributes to the projection variable."
        ),
    )
    parser.add_argument("path", type=Path, help="MF6 output .nc file to fix")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output path (default: overwrite input file in-place)",
    )
    parser.add_argument(
        "--mode",
        choices=["structured", "mesh", "auto"],
        default="auto",
        help="Grid type to assume (default: auto-detect from file contents)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        mode = _detect_mode(args.path)
        if args.verbose:
            print(f"detected mode: {mode}")

    if mode == "mesh":
        out = postprocess_mesh_nc(args.path, out=args.out)
    else:
        out = postprocess_structured_nc(args.path, out=args.out)

    if args.verbose:
        print(f"wrote: {out}")


if __name__ == "__main__":
    main()
