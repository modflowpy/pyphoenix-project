from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray

from flopy4.mf6.constants import FILL_DNODATA


def is_list_block(block: dict) -> bool:
    """
    Check if a block is a list block, which is a block that
    contains only one recarray field using list input.
    """
    meaningful_fields = {k: v for k, v in block.items() if v is not None}
    if len(meaningful_fields) == 0:
        return False

    # TODO: how to not hard-code these?
    stress_fields = {
        "head",
        "q",
        "elev",
        "cond",
        "rate",
        "flux",
        "concentration",
        "stage",
        "bhead",
        "aux",
        "boundname",
    }
    for field_name in meaningful_fields.keys():
        if field_name.lower() not in stress_fields:
            return False
    return True


def dict_blocks(data: dict) -> dict:
    """
    Get dictionary blocks: blocks which can contain
    one or more fields, as opposed to a list block, which
    may only contain one recarray field, using list input.
    """
    return {
        name: block
        for name, block in data.items()
        if block is not None and not is_list_block(block)
    }


def list_blocks(data: dict) -> dict:
    """Get list blocks, which contain only one recarray field."""
    return {
        name: block for name, block in data.items() if block is not None and is_list_block(block)
    }


def field_type(value: Any) -> str:
    """
    Get a field's type as defined by the MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types
    """
    if isinstance(value, bool):
        return "keyword"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (dict, tuple)):
        return "record"
    if isinstance(value, (list, np.ndarray, xr.DataArray)):
        return "recarray"
    return "keystring"


def array_how(value: xr.DataArray) -> str:
    return "internal"


def array_chunks(value: xr.DataArray, chunks: Mapping[Hashable, int] | None = None):
    """
    Yield chunks from an array of up to 3 dimensions. If the
    array is not already chunked, split it into chunks of the
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
    """

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


def array2string(value: NDArray) -> str:
    """
    Convert an array to a string. The array can be 1D or 2D.
    If the array is 1D, it is converted to a 1-line string,
    with elements separated by whitespace. If the array is
    2D, each row becomes a line in the string.
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


def array2list(value: xr.DataArray, include_zeros: bool = False):
    """
    Generator that yields sparse (indices, value, *aux) tuples from a `DataArray`.
    Iterates only over meaningful values (excludes zeros, NaN, and `FILL_DNODATA`).

    Parameters
    ----------
    value : xr.DataArray
        The input array to iterate over sparsely
    include_zeros : bool, optional
        If True, include zero values in iteration. Default False.

    Yields
    ------
    tuple
        Tuples of (layer, row, col, value) with 1-based indexing for MF6
    """
    from flopy4.mf6.constants import FILL_DNODATA

    if not include_zeros:
        mask = (value != 0) & (value != FILL_DNODATA) & ~np.isnan(value)
    else:
        mask = (value != FILL_DNODATA) & ~np.isnan(value)

    indices = np.where(mask)
    values = value.values[mask]
    for i, val in enumerate(values):
        idx_1based = tuple(idx[i] + 1 for idx in indices)
        yield idx_1based + (val,)


def keystring2list(value: xr.DataArray):
    """
    Generator for object arrays containing structured data (keystrings).
    Yields structured records for non-null entries.

    Parameters
    ----------
    value : xr.DataArray
        Array with object dtype containing structured data

    Yields
    ------
    tuple
        Tuples of (layer, row, col, *structured_values) with 1-based indexing
    """
    coord_arrays = np.meshgrid(*[np.arange(s) for s in value.shape], indexing="ij")
    flat_values = value.values.flat
    flat_coords = zip(*[arr.flat for arr in coord_arrays])
    for coords, val in zip(flat_coords, flat_values):
        if val is not None and not pd.isna(val):
            coords_1based = tuple(c + 1 for c in coords)
            if hasattr(val, "_asdict"):  # Named tuple
                yield coords_1based + tuple(val._asdict().values())
            elif isinstance(val, dict):
                yield coords_1based + tuple(val.values())
            else:
                yield coords_1based + (val,)


def keystring2list_multifield(field_arrays: dict, period_idx: int):
    """
    Combines multiple fields (e.g., elev, cond) for a given stress period

    Parameters
    ----------
    field_arrays : dict
        Dictionary of field_name -> xarray.DataArray
    period_idx : int
        Time period index (0-based)

    Yields
    ------
    tuple
        Tuples of (layer, row, col, field1_value, field2_value, ...)
        with 1-based indexing
    """
    if not field_arrays:
        return

    # determine spatial structure from first array
    first_field = next(iter(field_arrays.values()))
    if not isinstance(first_field, (np.ndarray, xr.DataArray)):
        return

    # get period slice
    period_slices = {}
    for field_name, field_array in field_arrays.items():
        if isinstance(field_array, xr.DataArray):
            period_data = field_array.isel(nper=period_idx)
            period_slices[field_name] = period_data.values
        elif isinstance(field_array, np.ndarray):
            period_slices[field_name] = field_array[period_idx]

    # Find all locations where at least one field has meaningful data
    combined_mask = None
    for field_name, period_data in period_slices.items():
        meaningful_mask = (
            (period_data != 0) & (period_data != FILL_DNODATA) & ~np.isnan(period_data)
        )
        if combined_mask is None:
            combined_mask = meaningful_mask
        else:
            combined_mask = combined_mask | meaningful_mask

    if combined_mask is None or not np.any(combined_mask):
        return

    indices = np.where(combined_mask)
    for i in range(len(indices[0])):
        idx_1based = tuple(idx[i] + 1 for idx in indices)
        field_values = []
        for field_name in field_arrays.keys():
            period_data = period_slices[field_name]
            val = period_data[tuple(idx[i] for idx in indices)]
            field_values.append(val)

        yield idx_1based + tuple(field_values)
