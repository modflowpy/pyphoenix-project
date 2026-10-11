from typing import Any

import numpy as np
from pyproj import CRS

# CF-standard numeric grid_mapping parameters shared across all three
# supported projected grid_mapping_name values.
_SHARED_CF_PARAMS = (
    "longitude_of_central_meridian",
    "latitude_of_projection_origin",
    "false_easting",
    "false_northing",
    "semi_major_axis",
    "inverse_flattening",
)


def cf_grid_mapping_params(crs: CRS) -> tuple[dict[str, Any], str | None]:
    """
    Return CF-standard numeric grid_mapping parameters for *crs*, in
    addition to wkt/crs_wkt: some netCDF readers -- notably ArcGIS's
    classic netCDF connector -- position a projected grid using these
    individual attributes rather than parsing wkt/crs_wkt text, and
    default every parameter to 0 if absent.

    Covers transverse_mercator, lambert_conformal_conic (2SP only -- CF
    has no scale_factor attribute for this method, so a 1SP CRS cannot
    be exactly represented), and albers_conical_equal_area. Always
    derive these from the original, unwrapped CRS: pyproj.CRS.to_cf()
    does not "see through" a wrapped DerivedProjectedCRS.

    Parameters
    ----------
    crs : pyproj.CRS
        The (unwrapped) CRS to extract parameters from.

    Returns
    -------
    tuple[dict, str | None]
        The parameters (empty if the grid_mapping_name is unsupported or
        unrecognized), and a warning message if the grid_mapping_name is
        recognized but unsupported (currently: 1SP lambert_conformal_conic
        variants), else None.
    """
    cf = crs.to_cf()
    gmn = cf.get("grid_mapping_name")

    if gmn == "transverse_mercator":
        keys = ("scale_factor_at_central_meridian", *_SHARED_CF_PARAMS)
    elif gmn in ("lambert_conformal_conic", "albers_conical_equal_area"):
        method = crs.coordinate_operation.method_name if crs.coordinate_operation else ""
        if "1SP" in method:
            return {}, (
                "1SP lambert_conformal_conic variants are not supported for "
                "CF grid_mapping parameter extraction (CF has no "
                "scale_factor attribute for this method); some netCDF "
                "readers may not correctly position this grid."
            )
        keys = ("standard_parallel", *_SHARED_CF_PARAMS)
    else:
        return {}, None

    params: dict[str, Any] = {}
    for k in keys:
        if k in cf:
            params[k] = np.asarray(cf[k]) if k == "standard_parallel" else cf[k]
    return params, None


def wrap_rotated_crs(
    crs: CRS,
    xorigin: float,
    yorigin: float,
    angrot: float,
) -> CRS | None:
    """
    Wrap a projected CRS in a derived CRS encoding MF6 grid rotation.

    Builds a DerivedProjectedCRS over *crs* with an EPSG:9624 (affine
    parametric transformation) deriving conversion parameterized from
    xorigin/yorigin/angrot (degrees), matching MF6's DisNCStructured.f90
    CRS_WKT rotation-wrapping exactly. Per ISO 19111, a deriving
    conversion is directed base->derived, so the parameters encode the
    world->local (inverse) rotation; a CRS-aware consumer applies the
    inverse to resolve true position from local coordinates.

    Parameters
    ----------
    crs : pyproj.CRS
        The base CRS to wrap. Must be a projected CRS.
    xorigin, yorigin : float
        Grid origin in *crs*.
    angrot : float
        Grid rotation angle in degrees.

    Returns
    -------
    pyproj.CRS | None
        The wrapped CRS, or None if *crs* is not a projected CRS.
    """
    if not crs.is_projected:
        return None

    ang = np.radians(angrot)
    a0 = -(xorigin * np.cos(ang) + yorigin * np.sin(ang))
    a1 = np.cos(ang)
    a2 = np.sin(ang)
    b0 = xorigin * np.sin(ang) - yorigin * np.cos(ang)
    b1 = -np.sin(ang)
    b2 = np.cos(ang)

    derived = {
        "type": "DerivedProjectedCRS",
        "name": "MODFLOW 6 rotated grid CRS",
        "base_crs": crs.to_json_dict(),
        "conversion": {
            "name": "MODFLOW 6 grid rotation",
            "method": {
                "name": "Affine parametric transformation",
                "id": {"authority": "EPSG", "code": 9624},
            },
            "parameters": [
                {"name": "A0", "value": a0, "unit": "metre"},
                {"name": "A1", "value": a1, "unit": "unity"},
                {"name": "A2", "value": a2, "unit": "unity"},
                {"name": "B0", "value": b0, "unit": "metre"},
                {"name": "B1", "value": b1, "unit": "unity"},
                {"name": "B2", "value": b2, "unit": "unity"},
            ],
        },
        "coordinate_system": {
            "subtype": "Cartesian",
            "axis": [
                {
                    "name": "Easting",
                    "abbreviation": "X",
                    "direction": "east",
                    "unit": "metre",
                },
                {
                    "name": "Northing",
                    "abbreviation": "Y",
                    "direction": "north",
                    "unit": "metre",
                },
            ],
        },
    }
    return CRS.from_json_dict(derived)
