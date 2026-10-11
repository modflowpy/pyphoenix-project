"""Post-processing utilities to bring MF6 output NC files into CF/CRS parity
with flopy4 input NC files.

MF6 6.8.0+ already writes ``crs_wkt``/``grid_mapping_name`` (mesh) and
``wkt``/``crs_wkt``/``grid_mapping``/``grid_mapping_name`` (structured) --
this module is then a no-op bridge for those.  Two things it still does:

- **Legacy pre-6.8.0 files**: backfill missing ``wkt``/``crs_wkt``/
  ``grid_mapping_name``, and fix ``crs_wkt`` holding WKT1 instead of WKT2
  (a real bug present through 6.7.0, fixed in 6.8.0).
- **Structured output, any release before CF grid_mapping numeric
  parameter support**: add the CF-standard numeric grid_mapping
  parameters (e.g. ``false_easting``, ``scale_factor_at_central_meridian``)
  that ArcGIS's classic netCDF connector reads directly, for
  ``transverse_mercator``, ``lambert_conformal_conic`` (2SP only), and
  ``albers_conical_equal_area``.

This module cannot backfill rotation-positioning for a rotated
(ANGROT != 0) structured grid on a legacy file: MF6 never writes
xorigin/yorigin/angrot as retrievable output attributes, and for a
rotated grid the file's own x/y coordinate values are grid-local with no
recoverable real-world position. Rotation-positioning is only available
from a release where MF6 wraps crs_wkt in a derived CRS at write time.

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
    (legacy bug), and add the CF-standard numeric grid_mapping parameters
    (for a release before MF6 wrote them) to the ``projection`` variable.
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

    from flopy4.mf6.utils.crs import cf_grid_mapping_params

    crs = ProjCRS.from_wkt(wkt)
    # If crs_wkt is already a wrapped DerivedProjectedCRS (a rotated grid
    # from a release that wraps it at write time), grid_mapping_name/CF
    # numeric parameters must come from its base CRS -- to_cf() does not
    # "see through" the wrapper. An ordinary ProjectedCRS also has a
    # source_crs (its underlying geographic CRS), so only unwrap when
    # crs itself is actually a DerivedProjectedCRS.
    base_crs = crs
    if crs.type_name == "Derived Projected CRS" and crs.source_crs is not None:
        base_crs = crs.source_crs
    cf = base_crs.to_cf()

    # Pre-6.8.0 MF6 wrote WKT1 to crs_wkt (bug, fixed in 6.8.0); overwrite
    # unconditionally -- idempotent on already-correct 6.8.0+ files.
    # wkt remains WKT1 for legacy-tool compatibility. Derived from
    # base_crs, not crs: WKT1 has no derived-CRS syntax, so converting an
    # already-wrapped DerivedProjectedCRS to WKT1 raises a CRSError.
    _wkt1 = base_crs.to_wkt(WktVersion.WKT1_GDAL)
    _wkt2 = crs.to_wkt(WktVersion.WKT2_2019)
    ds["projection"].attrs["crs_wkt"] = _wkt2
    ds["projection"].attrs.setdefault("wkt", _wkt1)
    gmn = cf.get("grid_mapping_name")
    if gmn:
        ds["projection"].attrs.setdefault("grid_mapping_name", gmn)

    params, warning = cf_grid_mapping_params(base_crs)
    if warning:
        import warnings

        warnings.warn(warning)
    for k, v in params.items():
        ds["projection"].attrs.setdefault(k, v)

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

    Backfills ``wkt``/``grid_mapping_name`` (legacy pre-6.8.0 bridge, no-op
    on 6.8.0+) and the CF-standard numeric grid_mapping parameters that
    ArcGIS's classic netCDF connector reads directly (for a release
    before MF6 wrote them). Does not backfill rotation-positioning for a
    rotated grid -- see the module docstring.

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
