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
from flopy4.mf6.converter.ingress.dim_context import DimContext
from flopy4.mf6.dimensions import DimensionResolver


def structure_keyword(value, field) -> str | None:
    return field.name if value else None


def _resolve_dimensions(
    self_, field, *, dims: dict | None = None
) -> tuple[list[str], list[int], dict]:
    """
    Get expected dimensions, shape, and resolved dimension values.

    Parameters
    ----------
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default
    dims : dict, optional
        Explicit dimension sizes to use. If provided, takes precedence over
        dims from parent or self_.__dict__.

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

    inherited_dims = {}
    if self_.parent and isinstance(self_.parent, DimensionResolver):
        inherited_dims = self_.parent.resolve_dims()

    explicit_dims = self_.__dict__.get("dims", {})
    dim_dict = inherited_dims | explicit_dims

    # Check object attributes directly for dimension values
    for dim_name in field.dims:
        if hasattr(self_, dim_name):
            dim_value = getattr(self_, dim_name)
            if isinstance(dim_value, int):
                dim_dict[dim_name] = dim_value

    # Phase 3: Try new dimension resolution protocol for missing dimensions
    # This searches self_'s children for DimensionProvider instances and delegates to parent
    if hasattr(self_, "resolve_dims"):
        for dim_name in field.dims:
            if dim_name not in dim_dict:  # Only resolve if not already found
                try:
                    result = self_.resolve_dims(dim_name)
                    if dim_name in result:
                        dim_dict[dim_name] = result[dim_name]
                except Exception:
                    pass  # Silently fall through to other resolution methods

    # Check structuring context (for dimension values extracted from parsed data
    # before attrs __init__ assigns them to self_)
    context_dims = DimContext.current()
    if context_dims:
        dim_dict.update(context_dims)

    # Override with explicitly provided dims (highest priority)
    if dims is not None:
        dim_dict.update(dims)

    # Compute derived dimensions if possible
    # nodes = nlay * nrow * ncol (structured grid)
    if "nodes" not in dim_dict and "nlay" in dim_dict and "nrow" in dim_dict and "ncol" in dim_dict:
        dim_dict["nodes"] = dim_dict["nlay"] * dim_dict["nrow"] * dim_dict["ncol"]
    # nodes2d = nrow * ncol (2D structured grid)
    if "nodes2d" not in dim_dict and "nrow" in dim_dict and "ncol" in dim_dict:
        dim_dict["nodes2d"] = dim_dict["nrow"] * dim_dict["ncol"]

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
    # Get expected shape
    expected_shape = tuple(dim_dict.get(d, d) for d in expected_dims)

    # Check if value has structured dimensions
    has_structured_3d = "nlay" in dim_dict and "nrow" in dim_dict and "ncol" in dim_dict
    has_structured_2d = "nrow" in dim_dict and "ncol" in dim_dict

    # Handle 'nodes' dimension (full 3D grid)
    if "nodes" in expected_dims and has_structured_3d:
        nlay = dim_dict["nlay"]
        nrow = dim_dict["nrow"]
        ncol = dim_dict["ncol"]
        nodes = dim_dict.get("nodes", nlay * nrow * ncol)

        # Case 1: (nlay, nrow, ncol) → (nodes,)
        if value_shape == (nlay, nrow, ncol) and expected_shape == (nodes,):
            return True, (nodes,)

        # Case 2: (nper, nlay, nrow, ncol) → (nper, nodes)
        if "nper" in expected_dims:
            nper = dim_dict["nper"]
            if value_shape == (nper, nlay, nrow, ncol) and expected_shape == (nper, nodes):
                return True, (nper, nodes)

    # Handle 'ncpl' dimension (cells per layer, 2D per-layer arrays)
    if "ncpl" in expected_dims and has_structured_2d:
        nrow = dim_dict["nrow"]
        ncol = dim_dict["ncol"]
        ncpl = dim_dict.get("ncpl", nrow * ncol)

        # Case 3: (nrow, ncol) → (ncpl,)
        if value_shape == (nrow, ncol) and expected_shape == (ncpl,):
            return True, (ncpl,)

        # Case 4: (nper, nrow, ncol) → (nper, ncpl)
        if "nper" in expected_dims:
            nper = dim_dict["nper"]
            if value_shape == (nper, nrow, ncol) and expected_shape == (nper, ncpl):
                return True, (nper, ncpl)

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

            # Check for broadcasting case (e.g., LAYERED: (nlay,) → (nlay, nrow, ncol))
            # If value has fewer dimensions but first N match, broadcast across remaining dims
            if len(value.dims) < len(expected_dims):
                # Check if leading dimensions match
                if all(
                    value.dims[i] == expected_dims[i]
                    or (
                        value.dims[i] in ("layer", "period")
                        and expected_dims[i] in ("nlay", "nper")
                    )
                    for i in range(len(value.dims))
                ):
                    # Leading dims match - broadcast across remaining dims
                    # Reshape to add singleton dimensions, then broadcast
                    # E.g., (2,) → (2, 1, 1) → (2, 10, 15)
                    reshape_dims = list(value.shape) + [1] * (len(expected_dims) - len(value.dims))
                    reshaped = value.values.reshape(reshape_dims)
                    broadcasted = np.broadcast_to(reshaped, expected_shape)
                    return broadcasted

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

            # Check for broadcasting case (fewer dimensions, leading dims match)
            if len(value.shape) < len(expected_shape):
                # Check if leading dimensions match
                if all(value.shape[i] == expected_shape[i] for i in range(len(value.shape))):
                    # Leading dims match - broadcast across remaining dims
                    # Reshape to add singleton dimensions, then broadcast
                    reshape_dims = list(value.shape) + [1] * (
                        len(expected_shape) - len(value.shape)
                    )
                    reshaped = value.reshape(reshape_dims)
                    broadcasted = np.broadcast_to(reshaped, expected_shape)
                    return broadcasted

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


def _convert_dataset_to_dict(
    ds: xr.Dataset | None,
    field_name: str,
    dim_dict: dict,
) -> dict[int, dict]:
    """
    Convert xr.Dataset (stress period data) to dict format.

    Dataset structure from transformer:
    - data_vars: Field values (e.g., field_0, q, head)
    - coords: kper (temporal), layer/row/col or node (spatial)

    Convert to dict format:
    {kper: {cellid: value, ...}, ...}

    Parameters
    ----------
    ds : xr.Dataset
        Input Dataset with stress period data
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
    if not isinstance(ds, xr.Dataset):
        return {}

    result: dict[int, dict] = {}

    # Get dimension info
    if "record" not in ds.dims:
        raise ValueError(f"Expected 'record' dimension in Dataset, got: {list(ds.dims.keys())}")

    # Get kper values
    kper_coord = ds.coords.get("kper")
    kper_vals = (
        kper_coord.values if kper_coord is not None else np.zeros(ds.dims["record"], dtype=int)
    )

    # Determine spatial coordinate format
    has_structured = all(coord in ds.coords for coord in ["layer", "row", "col"])
    has_node = "node" in ds.coords

    if not has_structured and not has_node:
        raise ValueError("Dataset must have either (layer, row, col) or (node,) coordinates")

    # Find the data variable - prefer field_name, otherwise use first data_var
    data_var_name: str | None = None
    if field_name in ds.data_vars:
        data_var_name = field_name
    elif len(ds.data_vars) > 0:
        # Use first data variable (e.g., field_0 from transformer)
        data_var_name = str(list(ds.data_vars.keys())[0])
    else:
        raise ValueError("No data variables found in Dataset")

    # Build records grouped by stress period
    for i in range(len(kper_vals)):
        kper = int(kper_vals[i])
        if kper not in result:
            result[kper] = {}

        # Extract cellid based on coordinate format
        if has_structured:
            cellid = (
                int(ds.coords["layer"].values[i]),
                int(ds.coords["row"].values[i]),
                int(ds.coords["col"].values[i]),
            )
        else:
            cellid = (int(ds.coords["node"].values[i]),)  # type: ignore

        # Extract field value
        value = ds[data_var_name].values[i]
        result[kper][cellid] = value

    return result


def _extract_external_path(data: xr.DataArray) -> tuple[str | None, xr.DataArray]:
    """
    Extract external file path from DataArray attrs if present.

    Transformer outputs external arrays as DataArray with:
    - data: np.nan (placeholder)
    - attrs: control_* metadata, plus external_path

    Parameters
    ----------
    data : xr.DataArray
        DataArray potentially containing external file path

    Returns
    -------
    path : str | None
        Path to external file, or None if not an external array
    data : xr.DataArray
        DataArray with external_path removed from attrs if it was present
    """
    if isinstance(data, xr.DataArray) and "external_path" in data.attrs:
        attrs = dict(data.attrs)
        path = attrs.pop("external_path")
        # Return updated DataArray without external_path in attrs
        data_updated = xr.DataArray(
            data=data.values, dims=data.dims, coords=data.coords, attrs=attrs
        )
        return str(path), data_updated
    return None, data


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
    value,
    self_,
    field,
    *,
    return_xarray: bool = False,
    sparse_threshold: int | None = None,
    dims: dict | None = None,
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
    dims : dict | None
        Explicit dimension sizes (e.g., {'nper': 10, 'nodes': 100}).
        If provided, takes precedence over dims from parent or self_.

    Returns
    -------
    xr.DataArray | np.ndarray | sparse.COO
        Structured array with proper shape and metadata
    """
    # Resolve dimensions
    dims_names, shape, dim_dict = _resolve_dimensions(self_, field, dims=dims)
    threshold = sparse_threshold if sparse_threshold is not None else SPARSE_THRESHOLD

    # Handle different input types
    if isinstance(value, pd.DataFrame):
        # Parse DataFrame format (from stress_period_data property)
        # Convert to dict format for processing
        value = _parse_dataframe(value, field.name, dim_dict)
        # Continue processing as dict below

    if isinstance(value, xr.Dataset):
        # Parse Dataset format (from transformer stress_period_data)
        # Convert to dict format for processing
        value = _convert_dataset_to_dict(value, field.name, dim_dict)
        # Continue processing as dict below

    if isinstance(value, dict):
        # Parse dict format with fill-forward logic
        parsed_dict = _parse_dict_format(value, dims_names, tuple(shape), dim_dict, field, self_)

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
                        if "nper" in dims_names:
                            coords_dict[(key, nn)] = value_data
                        else:
                            coords_dict[(nn,)] = value_data
                elif isinstance(val, dict):
                    # Nested dict: {cellid: value}
                    for cellid, v in val.items():
                        nn = get_nn(cellid, **dim_dict)
                        if "nper" in dims_names:
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
                if "nper" in dims_names:
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
                            if "nper" in dims_names:
                                result[kper, nn] = value_data
                            else:
                                result[nn] = value_data
                    elif isinstance(val, dict):
                        # Nested dict: {cellid: value}
                        for cellid, v in val.items():
                            nn = get_nn(cellid, **dim_dict)
                            if "nper" in dims_names:
                                result[kper, nn] = v
                            else:
                                result[nn] = v
                    elif isinstance(val, np.ndarray):
                        # Array value
                        if "nper" in dims_names:
                            result[kper] = val
                        else:
                            result = val
                    elif isinstance(val, xr.DataArray):
                        # xarray value
                        if "nper" in dims_names:
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
        result = _parse_list_format(value, dims_names, tuple(shape), field)

    elif isinstance(value, (xr.DataArray, np.ndarray)):
        # Check if this is an external array with path in attrs
        external_path = None
        if isinstance(value, xr.DataArray):
            external_path, value = _extract_external_path(value)
            if external_path:
                # TODO: Store path for lazy loading
                # For now, continue with placeholder (np.nan) or handle as needed
                # In the future, this should trigger lazy loading of the external file
                pass

        # Handle scalar DataArrays - broadcast to expected shape
        # (Common for CONSTANT control values like "CONSTANT 500.0")
        if isinstance(value, xr.DataArray) and len(value.dims) == 0:
            # Scalar DataArray - extract value and broadcast
            scalar_value = value.item()
            result = np.full(shape, scalar_value, dtype=field.dtype)
        elif isinstance(value, np.ndarray) and value.ndim == 0:
            # Scalar numpy array - extract value and broadcast
            scalar_value = value.item()
            result = np.full(shape, scalar_value, dtype=field.dtype)
        else:
            # Duck array - validate and reshape if needed
            result = _validate_duck_array(value, dims_names, tuple(shape), dim_dict)

        # Handle time fill-forward
        if "nper" in dims_names and "nper" in dim_dict:
            result = _fill_forward_time(result, dims_names, dim_dict["nper"])

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
        for dim in dims:  # type: ignore
            if dim in dim_dict:
                xr_coords[dim] = np.arange(dim_dict[dim])

        result = _to_xarray(result, dims, xr_coords)  # type: ignore

    return result
