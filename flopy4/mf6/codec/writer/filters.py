from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any

import numpy as np
import xarray as xr
from numpy.typing import NDArray

from flopy4.mf6.constants import FILL_DNODATA


def _is_keystring_format(dataset: xr.Dataset) -> bool:
    """Check if dataset should use keystring format based on metadata."""
    field_metadata = dataset.attrs.get("field_metadata", {})
    return any(meta.get("format") == "keystring" for meta in field_metadata.values())


def _is_tabular_time_format(dataset: xr.Dataset) -> bool:
    """True if a dataset has multiple columns and only one dimension 'nper'."""
    return len(dataset.data_vars) > 1 and all(
        "nper" in var.dims and len(var.dims) == 1 for var in dataset.data_vars.values()
    )


def is_dataset(value: Any) -> bool:
    return isinstance(value, xr.Dataset)


def field_format(value: Any) -> str:
    """
    Get a field's formatting type as defined by the MF6 definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types
    """
    if isinstance(value, bool):
        return "keyword"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double precision"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (dict, tuple)):
        return "record"
    if isinstance(value, xr.DataArray):
        if value.dtype == "object":
            return "list"
        return "array"
    if isinstance(value, (xr.Dataset, list)):
        if isinstance(value, xr.Dataset):
            if _is_keystring_format(value):
                return "keystring"
            if _is_tabular_time_format(value):
                return "list"
        return "list"
    return "keystring"


def has_time_dim(value: Any) -> bool:
    return isinstance(value, xr.DataArray) and "nper" in value.dims


def array_how(value: xr.DataArray) -> str:
    # TODO
    # - detect constant arrays?
    # - above certain size, use external?
    return "internal"


def array_chunks(value: xr.DataArray, chunks: Mapping[Hashable, int] | None = None):
    """
    Yield chunks from a dask-backed array of up to 3 dimensions.
    If it's not already chunked, split it into chunks of the
    specified sizes, given as a dictionary mapping dimension
    names to chunk sizes.

    If chunk sizes are not specified, chunk the array with at
    most 2 dimensions per chunk, where:

    - If the array is 3D, assume the first dimension is the
    vertical (i.e. layers) and the others horizontal (rows and
    columns, in that order), and yield a chunk per layer, such
    that an array with indices (k, i, j) becomes k chunks, each
    of shape (i, j).

    - If the array is 1D or 2D, yield it as a single chunk.

    If the array is not a dask array, yield it as a single chunk.
    """

    if hasattr(value.data, "blocks"):
        if value.chunks is None:
            if chunks is None:
                match value.ndim:
                    case 1:
                        # 1D array, single chunk
                        chunks = {value.dims[0]: value.shape[0]}
                    case 2:
                        # 2D array, single chunk
                        chunks = {value.dims[0]: value.shape[0], value.dims[1]: value.shape[1]}
                    case 3:
                        # 3D array, chunk for each layer
                        chunks = {
                            value.dims[0]: 1,
                            value.dims[1]: value.shape[1],
                            value.dims[2]: value.shape[2],
                        }
            value = value.chunk(chunks)
        for chunk in value.data.blocks:
            yield np.squeeze(chunk.compute())
    else:
        # regular array, single chunk
        yield np.squeeze(value.values)


def array2string(value: NDArray) -> str:
    """
    Convert an array to a string. The array can be 1D or 2D.
    If the array is 1D, it is converted to a 1-line string,
    with elements separated by whitespace. If the array is
    2D, each row becomes a line in the string.

    Used for writing array-based input to MF6 input files.
    """
    buffer = StringIO()
    value = np.asarray(value)
    if value.ndim > 2:
        raise ValueError("Only 1D and 2D arrays are supported.")
    if value.ndim == 1:
        # add an axis to 1d arrays so np.savetxt writes elements on 1 line
        value = value[None]
    value = np.atleast_1d(value)
    format = (
        "%d"
        if np.issubdtype(value.dtype, np.integer)
        else "%f"
        if np.issubdtype(value.dtype, np.floating)
        else "%s"
    )
    np.savetxt(buffer, value, fmt=format, delimiter=" ")
    return buffer.getvalue().strip()


def nonempty(arr: NDArray | xr.DataArray) -> NDArray:
    if isinstance(arr, xr.DataArray):
        arr = arr.values
    if arr.dtype == "object":
        mask = arr != None  # noqa: E711
    else:
        mask = ~np.ma.masked_invalid(arr).mask
        mask = mask & (arr != FILL_DNODATA)
    return mask


def data2list(value: list | xr.DataArray | xr.Dataset):
    """
    Yield record tuples from a list, `DataArray` or `Dataset`.

    Yields
    ------
    tuple
        Tuples of (*cellid, *values) or (*values) depending on spatial dimensions
    """

    if isinstance(value, list):
        for item in value:
            yield item
        return

    if isinstance(value, xr.Dataset):
        yield from dataset2list(value)
        return

    # handle scalar
    if value.ndim == 0:
        if not np.isnan(value.item()) and value.item() is not None:
            yield (value.item(),)
        return

    spatial_dims = [d for d in value.dims if d in ("nlay", "nrow", "ncol", "nodes")]
    has_spatial_dims = len(spatial_dims) > 0
    mask = nonempty(value)
    indices = np.where(mask)
    values = value.values[mask]
    for i, val in enumerate(values):
        if has_spatial_dims:
            cellid = tuple(idx[i] + 1 for idx in indices)
            result = cellid + (val,)
        else:
            result = (val,)
        yield result


def dataset2list(value: xr.Dataset):
    """
    Yield record tuples from an xarray Dataset. For regular/tabular list-based format.

    Yields
    ------
    tuple
        Tuples of (*cellid, *values) or (*values) depending on spatial dimensions
    """
    if value is None or not any(value.data_vars):
        return

    # handle scalar
    first_arr = next(iter(value.data_vars.values()))
    if first_arr.ndim == 0:
        field_vals = []
        for field_name in value.data_vars.keys():
            field_val = value[field_name]
            if hasattr(field_val, "item"):
                field_vals.append(field_val.item())
            else:
                field_vals.append(field_val)
        yield tuple(field_vals)
        return

    # build mask
    combined_mask: Any = None
    for field_name, arr in value.data_vars.items():
        mask = nonempty(arr)
        combined_mask = mask if combined_mask is None else combined_mask | mask
    if combined_mask is None or not np.any(combined_mask):
        return

    spatial_dims = [d for d in first_arr.dims if d in ("nlay", "nrow", "ncol", "nodes")]
    has_spatial_dims = len(spatial_dims) > 0
    indices = np.where(combined_mask)
    for i in range(len(indices[0])):
        field_vals = []
        for field_name in value.data_vars.keys():
            field_val = value[field_name][tuple(idx[i] for idx in indices)]
            if hasattr(field_val, "item"):
                field_vals.append(field_val.item())
            else:
                field_vals.append(field_val)
        if has_spatial_dims:
            cellid = tuple(idx[i] + 1 for idx in indices)
            yield cellid + tuple(field_vals)
        else:
            yield tuple(field_vals)


def data2keystring(value: dict | xr.Dataset):
    """
    Yield record tuples from a dict or dataset. For irregular list-based format, i.e. keystrings.

    Yields
    ------
    tuple
        Tuples of (field_name, value) for use with record macro
    """
    if isinstance(value, dict):
        if not value:
            return
        for field_name, field_val in value.items():
            yield (field_name.upper(), field_val)
    elif isinstance(value, xr.Dataset):
        if value is None or not any(value.data_vars):
            return

        for field_name in value.data_vars.keys():
            name = (
                field_name.replace("_", " ").upper()
                if np.issubdtype(value.data_vars[field_name].dtype, np.str_)
                else field_name.upper()
            )
            field_val = value[field_name]
            if hasattr(field_val, "item"):
                val = field_val.item()
            else:
                val = field_val
            yield (name, val)
