from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any, Literal

import attrs
import numpy as np
import xarray as xr
from numpy.typing import NDArray
from xattree import Scalar

from flopy4.mf6.constants import FILL_DNODATA

ArrayHow = Literal["constant", "internal", "external"]


def array_how(value: xr.DataArray) -> ArrayHow:
    """
    Determine how an array should be represented in MF6 input.
    Options are "constant", "internal", or "external". If the
    array dask-backed, assumed it's big and return "external".
    Otherwise there is no materialization cost to check if all
    values are the same, so return "constant" or "internal" as
    appropriate.
    """
    if hasattr(value.data, "blocks"):
        return "external"
    if value.max() == value.min():
        return "constant"
    return "internal"


def array2const(value: xr.DataArray) -> Scalar:
    if np.issubdtype(value.dtype, np.integer):
        return value.max().item()
    if np.issubdtype(value.dtype, np.floating):
        return f"{value.max().item():.8f}"
    return value.ravel()[0]


def array2chunks(value: xr.DataArray, chunks: Mapping[Hashable, int] | None = None):
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


def nonempty(value: NDArray | xr.DataArray) -> NDArray:
    """
    Return a boolean mask of non-empty (non-nodata) values in an array.
    TODO: don't hardcode FILL_DNODATA, support different fill values
    """
    if isinstance(value, xr.DataArray):
        value = value.values
    if value.dtype == "object":
        mask = value != None  # noqa: E711
    else:
        mask = ~np.ma.masked_invalid(value).mask
        mask = mask & (value != FILL_DNODATA)
    return mask


def data2list(value: list | tuple | dict | xr.Dataset | xr.DataArray):
    """
    Yield records (tuples) from data in a `list`, `dict`, `DataArray` or `Dataset`.
    """

    if isinstance(value, (list, tuple)):
        for rec in value:
            yield rec
        return

    if isinstance(value, dict):
        for name, val in value.values():
            yield (name, val)
        return

    if isinstance(value, xr.Dataset):
        yield from dataset2list(value)
        return

    # otherwise we have a DataArray
    if value.ndim == 0:  # handle scalar
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
            rec = cellid + (val,)
        else:
            rec = (val,)
        yield rec


def dataset2list(value: xr.Dataset):
    """
    Yield records (tuples) from an `xarray.Dataset`.

    If the first data variable is a string type, assume all are
    string type. Then the dataset represents a keystring; yield
    tuples of (name, *value). Otherwise, yield tuples: (*value)
    if no spatial dimensions, or (*cellid, *value) when spatial
    dimensions are present.
    """
    if value is None or not any(value.data_vars):
        return

    # special case OC for now.
    # TODO remove after properly handling object dtype period data arrays
    is_oc = any(
        str(v.name).startswith("save_") or str(v.name).startswith("print_")
        for v in value.data_vars.values()
    )

    # handle scalar
    if (first := next(iter(value.data_vars.values()))).ndim == 0:
        if is_oc:
            for name in value.data_vars.keys():
                if not (name.startswith("save_") or name.startswith("print_")):
                    # TODO: not working yet
                    if name == "perioddata":
                        val = value[name]
                        val = val.item() if val.shape == () else val
                        yield attrs.astuple(val, recurse=True)
                    continue
                val = value[name]
                val = val.item() if val.shape == () else val
                yield (*name.split("_"), val)

        else:
            vals = []
            for name in value.data_vars.keys():
                val = value[name]
                val = val.item() if val.shape == () else val
                vals.append(val)
            yield tuple(vals)
        return

    combined_mask: Any = None
    for name, first in value.data_vars.items():
        mask = nonempty(first)
        combined_mask = mask if combined_mask is None else combined_mask | mask
    if combined_mask is None or not np.any(combined_mask):
        return

    spatial_dims = [d for d in first.dims if d in ("nlay", "nrow", "ncol", "nodes")]
    has_spatial_dims = len(spatial_dims) > 0
    indices = np.where(combined_mask)
    for i in range(len(indices[0])):
        if is_oc:
            for name in value.data_vars.keys():
                val = value[name][tuple(idx[i] for idx in indices)]
                val = val.item() if val.shape == () else val
                yield (*name.split("_"), val)
        else:
            vals = []
            for name in value.data_vars.keys():
                val = value[name][tuple(idx[i] for idx in indices)]
                val = val.item() if val.shape == () else val
                vals.append(val)
            if has_spatial_dims:
                cellid = tuple(idx[i] + 1 for idx in indices)
                yield cellid + tuple(vals)
            else:
                yield tuple(vals)
