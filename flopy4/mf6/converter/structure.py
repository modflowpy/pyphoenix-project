from typing import Any

import numpy as np
import pandas as pd
import sparse
import xarray as xr
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA


def structure_keyword(value, field) -> str | None:
    return field.name if value else None


def _resolve_dimensions(self_, field) -> tuple[list[str], list[int], dict]:
    """
    Get expected dimensions, shape, and resolved dimension values.

    Parameters
    ----------
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default

    Returns
    -------
    dims : list[str]
        Dimension names (e.g., ['nper', 'nodes'])
    shape : list[int]
        Resolved shape (e.g., [10, 1000])
    dim_dict : dict
        Dimension values (e.g., {'nper': 10, 'nodes': 1000})
    """
    spec = get_xatspec(type(self_)).flat
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # Resolve dims from model context
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = dict(self_.parent.data.dims) if self_.parent else {}
    dim_dict = inherited_dims | explicit_dims

    # Check object attributes directly for dimension values
    # These override inherited dims (important during initialization when dims are passed as kwargs)
    for dim_name in field.dims:
        if hasattr(self_, dim_name):
            dim_value = getattr(self_, dim_name)
            if isinstance(dim_value, int):
                # Override any inherited value with the object's attribute value
                dim_dict[dim_name] = dim_value

    # Build shape by resolving dimension values
    shape = [dim_dict.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    return list(field.dims), shape, dim_dict


def _detect_grid_reshape(
    value_shape: tuple, expected_dims: list[str], dim_dict: dict
) -> tuple[bool, tuple | None]:
    """
    Check if structured↔flat conversion needed.

    Parameters
    ----------
    value_shape : tuple
        Shape of input array
    expected_dims : list[str]
        Expected dimension names
    dim_dict : dict
        Resolved dimension values

    Returns
    -------
    needs_reshape : bool
        True if reshape required
    target_shape : tuple | None
        Target shape for reshape, or None
    """
    # Check if we expect flat 'nodes' dimension
    if "nodes" not in expected_dims:
        return False, None

    # Get expected shape
    expected_shape = tuple(dim_dict.get(d, d) for d in expected_dims)

    # Check if value has structured dimensions
    has_structured = "nlay" in dim_dict and "nrow" in dim_dict and "ncol" in dim_dict

    if not has_structured:
        return False, None

    nlay = dim_dict["nlay"]
    nrow = dim_dict["nrow"]
    ncol = dim_dict["ncol"]
    nodes = dim_dict.get("nodes", nlay * nrow * ncol)

    # Check for structured→flat conversion
    # Case 1: (nlay, nrow, ncol) → (nodes,)
    if value_shape == (nlay, nrow, ncol) and expected_shape == (nodes,):
        return True, (nodes,)

    # Case 2: (nper, nlay, nrow, ncol) → (nper, nodes)
    if "nper" in expected_dims:
        nper = dim_dict["nper"]
        if value_shape == (nper, nlay, nrow, ncol) and expected_shape == (nper, nodes):
            return True, (nper, nodes)

    return False, None


def _reshape_grid(
    data: np.ndarray | xr.DataArray,
    target_shape: tuple,
    source_dims: list[str] | None = None,
    target_dims: list[str] | None = None,
) -> np.ndarray | xr.DataArray:
    """
    Perform structured↔flat grid conversion.

    Parameters
    ----------
    data : np.ndarray | xr.DataArray
        Input array to reshape
    target_shape : tuple
        Target shape after reshape
    source_dims : list[str] | None
        Source dimension names (for xarray)
    target_dims : list[str] | None
        Target dimension names (for xarray)

    Returns
    -------
    np.ndarray | xr.DataArray
        Reshaped array, preserving xarray metadata if applicable
    """
    if isinstance(data, xr.DataArray):
        # Reshape xarray and update dims
        reshaped_data = data.values.reshape(target_shape)
        if target_dims:
            return xr.DataArray(reshaped_data, dims=target_dims, attrs=data.attrs)
        return xr.DataArray(reshaped_data, attrs=data.attrs)
    else:
        # Simple numpy reshape
        return data.reshape(target_shape)


def _validate_duck_array(
    value: xr.DataArray | np.ndarray,
    expected_dims: list[str],
    expected_shape: tuple,
    dim_dict: dict,
) -> xr.DataArray | np.ndarray:
    """
    Validate and optionally reshape duck arrays.

    Parameters
    ----------
    value : xr.DataArray | np.ndarray
        Input array to validate
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    dim_dict : dict
        Resolved dimension values

    Returns
    -------
    xr.DataArray | np.ndarray
        Validated and possibly reshaped array
    """
    if isinstance(value, xr.DataArray):
        # Check dimension names
        if set(value.dims) != set(expected_dims):
            # Check for structured→flat conversion
            needs_reshape, target_shape = _detect_grid_reshape(value.shape, expected_dims, dim_dict)
            if needs_reshape:
                assert (
                    target_shape is not None
                )  # target_shape is always set when needs_reshape is True
                return _reshape_grid(
                    value, target_shape, [str(d) for d in value.dims], expected_dims
                )
            raise ValueError(f"Dimension mismatch: {value.dims} vs {expected_dims}")
        return value

    elif isinstance(value, np.ndarray):
        # Check shape
        if value.shape != expected_shape:
            # Try structured→flat reshape
            needs_reshape, target_shape = _detect_grid_reshape(value.shape, expected_dims, dim_dict)
            if needs_reshape:
                assert (
                    target_shape is not None
                )  # target_shape is always set when needs_reshape is True
                return _reshape_grid(value, target_shape)
            raise ValueError(f"Shape mismatch: {value.shape} vs {expected_shape}")
        return value


def _fill_forward_time(
    data: np.ndarray | xr.DataArray, dims: list[str], nper: int
) -> np.ndarray | xr.DataArray:
    """
    Add nper dimension if missing (broadcast to all periods).

    Parameters
    ----------
    data : np.ndarray | xr.DataArray
        Input array
    dims : list[str]
        Expected dimension names
    nper : int
        Number of stress periods

    Returns
    -------
    np.ndarray | xr.DataArray
        Array with nper dimension added if needed
    """
    if "nper" not in dims:
        return data

    if isinstance(data, xr.DataArray):
        if "nper" not in data.dims:
            # Broadcast to add nper dimension
            data_broadcast = np.broadcast_to(data.values, (nper, *data.shape))
            return xr.DataArray(data_broadcast, dims=["nper"] + list(data.dims), attrs=data.attrs)
        return data

    elif isinstance(data, np.ndarray):
        # Check if nper is in expected dims but not in data shape
        if len(data.shape) < len(dims):
            # Broadcast to add nper dimension
            data_broadcast = np.broadcast_to(data, (nper, *data.shape))
            return data_broadcast
        return data


def _parse_list_format(
    value: list, expected_dims: list[str], expected_shape: tuple, field
) -> np.ndarray:
    """
    Parse nested list formats to numpy array.

    Parameters
    ----------
    value : list
        Input list (possibly nested)
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    field : object
        Field specification

    Returns
    -------
    np.ndarray
        Parsed numpy array
    """
    # Convert to numpy array
    arr = np.array(value, dtype=field.dtype if hasattr(field, "dtype") else None)

    # Validate shape (convert both to tuples for comparison)
    expected_shape_tuple = tuple(expected_shape)
    if arr.shape != expected_shape_tuple:
        raise ValueError(f"List shape {arr.shape} doesn't match expected {expected_shape_tuple}")

    return arr


def _to_xarray(
    data: np.ndarray | sparse.COO,
    dims: list[str],
    coords: dict | None = None,
    attrs: dict | None = None,
) -> xr.DataArray:
    """
    Wrap array in xarray DataArray with metadata.

    Parameters
    ----------
    data : np.ndarray | sparse.COO
        Underlying array data
    dims : list[str]
        Dimension names
    coords : dict | None
        Coordinate arrays for each dimension
    attrs : dict | None
        Metadata attributes

    Returns
    -------
    xr.DataArray
        DataArray with proper metadata
    """
    return xr.DataArray(data=data, dims=dims, coords=coords or {}, attrs=attrs or {})


def _parse_dataframe(
    df: pd.DataFrame,
    field_name: str,
    dim_dict: dict,
) -> dict[int, dict]:
    """
    Parse pandas DataFrame to dict format compatible with stress period data.

    Expected DataFrame format (from stress_period_data property):
    - 'kper' column: stress period index
    - Spatial columns: either ('layer', 'row', 'col') or ('node',)
    - Field value column: named after the field (e.g., 'head', 'elev')

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with stress period data
    field_name : str
        Name of the field to extract values for
    dim_dict : dict
        Resolved dimension values (for coordinate conversion)

    Returns
    -------
    dict[int, dict]
        Dict mapping stress periods to cellid: value dicts
        Format: {kper: {cellid: value, ...}, ...}
    """
    if field_name not in df.columns:
        raise ValueError(
            f"Field '{field_name}' not found in DataFrame columns: {df.columns.tolist()}"
        )

    result: dict[int, dict] = {}

    # Determine coordinate format
    has_structured = all(col in df.columns for col in ["layer", "row", "col"])
    has_node = "node" in df.columns

    if not has_structured and not has_node:
        raise ValueError("DataFrame must have either (layer, row, col) or (node,) columns")

    # Group by stress period
    for kper in df["kper"].unique():
        period_data = df[df["kper"] == kper]
        cellid_dict = {}

        for _, row in period_data.iterrows():
            # Extract cellid based on coordinate format
            if has_structured:
                cellid = (int(row["layer"]), int(row["row"]), int(row["col"]))
            else:
                cellid = (int(row["node"]),)  # type: ignore

            # Extract field value
            value = row[field_name]
            cellid_dict[cellid] = value

        result[int(kper)] = cellid_dict

    return result


def _parse_dict_format(
    value: dict, expected_dims: list[str], expected_shape: tuple, dim_dict: dict, field, self_
) -> dict[int, Any]:
    """
    Parse dict format with fill-forward logic and mixed value types.

    Supports:
    - Stress period dicts: {0: data1, 5: data2} (fills forward)
    - Layer dicts: {0: data1, 1: data2}
    - Mixed value types: xarray, numpy, list, scalar
    - Metadata dicts: {0: {'data': ..., 'factor': 1.0}}
    - External file: {'filename': '...', 'data': [...]}

    Parameters
    ----------
    value : dict
        Input dictionary
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    dim_dict : dict
        Resolved dimension values
    field : object
        Field specification
    self_ : object
        Parent object for context

    Returns
    -------
    dict[int, Any]
        Parsed dict with integer keys and normalized values
    """
    # Check for external file format
    if "filename" in value:
        # External file format - for now, just extract data if present
        # TODO: implement actual file reading
        if "data" in value:
            return {0: value["data"]}
        return {0: value}

    parsed: dict[int, Any] = {}

    for key, val in value.items():
        # Handle special '*' key (means period/layer 0, don't fill forward)
        if key == "*":
            key = 0

        # Skip non-integer keys
        if not isinstance(key, int):
            continue

        # Handle metadata dict format: {0: {'data': ..., 'factor': 1.0}}
        if isinstance(val, dict) and "data" in val:
            # Extract data and metadata
            val = val["data"]
            # TODO: preserve metadata (factor, iprn, etc.) for later use

        # Process value based on type
        if isinstance(val, (xr.DataArray, np.ndarray)):
            # Duck array - validate and reshape if needed
            # For dict values, we need to handle them without the outer dimension
            # since the dict key provides that dimension
            if "nper" in expected_dims or "nlay" in expected_dims:
                # Remove the outer dimension from expected for validation
                inner_dims = expected_dims[1:] if expected_dims else expected_dims
                inner_shape = expected_shape[1:] if expected_shape else expected_shape
            else:
                inner_dims = expected_dims
                inner_shape = expected_shape

            parsed[key] = val

        elif isinstance(val, list):
            # List format
            if "nper" in expected_dims or "nlay" in expected_dims:
                inner_shape = expected_shape[1:] if expected_shape else expected_shape
            else:
                inner_shape = expected_shape

            # Check if it's a list of lists (structured data)
            if val and isinstance(val[0], (list, tuple)):
                # Structured boundary condition data
                parsed[key] = val
            else:
                # Simple list - convert to array
                parsed[key] = np.array(val)

        elif isinstance(val, (int, float)):
            # Scalar value
            parsed[key] = val

        else:
            # Unknown type, store as-is
            parsed[key] = val

    return parsed


def structure_array(
    value, self_, field, *, return_xarray: bool = False, sparse_threshold: int | None = None
) -> xr.DataArray | NDArray | sparse.COO:
    """
    Convert various array representations to structured arrays.

    Supports:
    - Dict-based sparse formats (stress periods, layers) with fill-forward
    - List-based formats (nested lists)
    - Duck arrays (xarray, numpy) with validation/reshaping
    - Scalars (broadcast to full shape)
    - External file metadata dicts
    - Mixed value types within dicts

    Parameters
    ----------
    value : dict | list | xr.DataArray | np.ndarray | float | int
        Input data in any supported format
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default
    return_xarray : bool, default False
        If True, return xr.DataArray; otherwise return raw array (for backward compatibility)
    sparse_threshold : int | None
        Override default sparse threshold for COO vs dense

    Returns
    -------
    xr.DataArray | np.ndarray | sparse.COO
        Structured array with proper shape and metadata
    """
    # Resolve dimensions
    dims, shape, dim_dict = _resolve_dimensions(self_, field)
    threshold = sparse_threshold if sparse_threshold is not None else SPARSE_THRESHOLD

    # Handle different input types
    if isinstance(value, pd.DataFrame):
        # Parse DataFrame format (from stress_period_data property)
        # Convert to dict format for processing
        value = _parse_dataframe(value, field.name, dim_dict)
        # Continue processing as dict below

    if isinstance(value, dict):
        # Parse dict format with fill-forward logic
        parsed_dict = _parse_dict_format(value, dims, tuple(shape), dim_dict, field, self_)

        # Build array using sparse or dense approach
        if np.prod(shape) > threshold:
            # Sparse approach
            coords_dict: dict[tuple[Any, ...], Any] = {}

            for key, val in parsed_dict.items():
                if isinstance(val, (int, float, str)):
                    # Scalar value (number or string) - set for entire period/layer
                    if "nper" in dim_dict:
                        coords_dict[(key,)] = val
                    else:
                        # Fill entire spatial extent with scalar
                        if len(shape) == 1:
                            coords_dict[(key,)] = val
                        else:
                            # For now, store scalar - will be expanded later
                            coords_dict[(key,)] = val
                elif isinstance(val, list) and val and isinstance(val[0], (list, tuple)):
                    # Structured boundary condition data: [[cellid, ...], ...]
                    for row in val:
                        cellid = (
                            row[0] if isinstance(row[0], tuple) else tuple(row[: len(shape) - 1])
                        )
                        value_data = row[-1]
                        nn = get_nn(cellid, **dim_dict)
                        if "nper" in dims:
                            coords_dict[(key, nn)] = value_data
                        else:
                            coords_dict[(nn,)] = value_data
                elif isinstance(val, dict):
                    # Nested dict: {cellid: value}
                    for cellid, v in val.items():
                        nn = get_nn(cellid, **dim_dict)
                        if "nper" in dims:
                            coords_dict[(key, nn)] = v
                        else:
                            coords_dict[(nn,)] = v
                else:
                    # Other types (including custom objects) - store as scalar for this period/layer
                    if "nper" in dim_dict or "nlay" in dim_dict:
                        coords_dict[(key,)] = val
                    else:
                        if len(shape) == 1:
                            coords_dict[(key,)] = val
                        else:
                            coords_dict[(key,)] = val

            # Convert to sparse COO
            if coords_dict:
                coords = np.array(list(map(list, zip(*coords_dict.keys()))))
                result = sparse.COO(
                    coords,
                    list(coords_dict.values()),
                    shape=shape,
                    fill_value=field.default or FILL_DNODATA,
                )
            else:
                # Empty dict - return empty sparse array
                result = sparse.COO(
                    np.empty((len(shape), 0), dtype=int),
                    [],
                    shape=shape,
                    fill_value=field.default or FILL_DNODATA,
                )
        else:
            # Dense approach
            result = np.full(shape, FILL_DNODATA, dtype=field.dtype)

            # Fill in values with fill-forward logic
            sorted_keys = sorted(parsed_dict.keys())
            for idx, key in enumerate(sorted_keys):
                val = parsed_dict[key]

                # Determine fill range (current key to next key or end)
                if "nper" in dims:
                    next_key = (
                        sorted_keys[idx + 1]
                        if idx + 1 < len(sorted_keys)
                        else dim_dict.get("nper", key + 1)
                    )
                    kper_range = range(key, next_key)
                else:
                    kper_range = range(key, key + 1)

                for kper in kper_range:
                    if isinstance(val, (int, float, str)):
                        # Scalar value (number or string)
                        if len(shape) == 1:
                            result[kper] = val
                        else:
                            result[kper] = np.full(shape[1:], val, dtype=field.dtype)
                    elif isinstance(val, list) and val and isinstance(val[0], (list, tuple)):
                        # Structured boundary condition data
                        for row in val:
                            cellid = (
                                row[0]
                                if isinstance(row[0], tuple)
                                else tuple(row[: len(shape) - 1])
                            )
                            value_data = row[-1]
                            nn = get_nn(cellid, **dim_dict)
                            if "nper" in dims:
                                result[kper, nn] = value_data
                            else:
                                result[nn] = value_data
                    elif isinstance(val, dict):
                        # Nested dict: {cellid: value}
                        for cellid, v in val.items():
                            nn = get_nn(cellid, **dim_dict)
                            if "nper" in dims:
                                result[kper, nn] = v
                            else:
                                result[nn] = v
                    elif isinstance(val, np.ndarray):
                        # Array value
                        if "nper" in dims:
                            result[kper] = val
                        else:
                            result = val
                    elif isinstance(val, xr.DataArray):
                        # xarray value
                        if "nper" in dims:
                            result[kper] = val.values
                        else:
                            result = val.values
                    else:
                        # Other types (including custom objects) - store as-is
                        if len(shape) == 1:
                            result[kper] = val
                        else:
                            # For multi-dimensional arrays with object dtype, store the object
                            result[kper] = val

            # Apply fill value replacement (skip for object dtypes)
            if field.dtype != np.object_:
                result[result == FILL_DNODATA] = field.default or FILL_DNODATA

    elif isinstance(value, list):
        # List format
        result = _parse_list_format(value, dims, tuple(shape), field)

    elif isinstance(value, (xr.DataArray, np.ndarray)):
        # Duck array - validate and reshape if needed
        result = _validate_duck_array(value, dims, tuple(shape), dim_dict)

        # Handle time fill-forward
        if "nper" in dims and "nper" in dim_dict:
            result = _fill_forward_time(result, dims, dim_dict["nper"])

    elif isinstance(value, (int, float)):
        # Scalar - broadcast to full shape
        result = np.full(shape, value, dtype=field.dtype)

    else:
        # Unknown type - return as-is for backward compatibility
        return value

    # Wrap in xarray if requested
    if return_xarray and not isinstance(result, xr.DataArray):
        # Build coordinates
        xr_coords: dict[str, Any] = {}
        for dim in dims:
            if dim in dim_dict:
                xr_coords[dim] = np.arange(dim_dict[dim])

        result = _to_xarray(result, dims, xr_coords)

    return result
