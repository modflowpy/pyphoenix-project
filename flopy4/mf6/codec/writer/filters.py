from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any, Literal

import attrs
import numpy as np
import xarray as xr
from numpy.typing import NDArray
from xattree import Scalar

from flopy4.mf6.constants import FILL_DNODATA

ArrayHow = Literal[
    "constant", "internal", "external", "layered constant", "layered internal", "netcdf"
]


def array_how(value: xr.DataArray, netcdf: bool = False) -> ArrayHow:
    """
    Determine how an array should be represented in MF6 input.
    Options are "constant", "internal", or "external". If the
    array is dask-backed, skip the constant check (would trigger
    compute) and route to internal — the writer streams it
    chunk-by-chunk via array2chunks without full materialization.
    For numpy arrays there is no materialization cost to check if
    all values are the same, so return "constant" or "internal"
    as appropriate.
    """
    if netcdf:
        return "netcdf"
    if hasattr(value.data, "blocks"):
        # Dask-backed: stream as internal, never materialize to check constant.
        if "nlay" in value.dims:
            return "layered internal"
        return "internal"
    if value.max() == value.min():
        return "constant"
    if "nlay" in value.dims:
        layer_const = True
        for layer in range(value.shape[0]):
            val_layer = value.isel(nlay=layer)
            if val_layer.max() != val_layer.min():
                layer_const = False
                break
        if layer_const:
            return "layered constant"
        return "layered internal"
    if value.ndim <= 2:
        return "internal"
    raise ValueError(f"Arrays with ndim > 3 are not supported, got ndim={value.ndim}")


def array2const(value: xr.DataArray, precision: int = 8) -> Scalar:
    """
    Convert array to constant scalar value.

    Parameters
    ----------
    value : xr.DataArray
        Array to convert
    precision : int, optional
        Number of decimal places for float output. Default is 8.
    """
    if np.issubdtype(value.dtype, np.integer):
        return value.max().item()
    if np.issubdtype(value.dtype, np.floating):
        return f"{value.max().item():.{precision}e}"
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


def array2string(value: NDArray, precision: int = 9) -> str:
    """
    Convert an array to a string. The array can be 1D or 2D.
    If the array is 1D, it is converted to a 1-line string,
    with elements separated by whitespace. If the array is
    2D, each row becomes a line in the string.

    Used for writing array-based input to MF6 input files.

    Parameters
    ----------
    value : NDArray
        Array to convert
    precision : int, optional
        Number of decimal places for float output. Default is 9.
    """
    buffer = StringIO()
    value = np.asarray(value)
    if value.ndim > 2:
        raise ValueError(f"Only 1D and 2D arrays are supported, got ndim={value.ndim}")
    if value.ndim == 1:
        # add an axis to 1d arrays so np.savetxt writes elements on 1 line
        value = value[None]
    value = np.atleast_1d(value)

    if np.issubdtype(value.dtype, np.floating):
        format = f"%.{precision}e"
    elif np.issubdtype(value.dtype, np.integer):
        format = "%d"
    else:
        format = "%s"

    np.savetxt(buffer, value, fmt=format, delimiter=" ")
    return buffer.getvalue().strip()


def quote_if_needed(value: str) -> str:
    """
    Wrap a string in single quotes if it contains double-quotes.

    WKT CRS strings (e.g. PROJCS["NAD83 / UTM zone 11N",...]) always
    contain double-quotes and must be single-quoted for MF6 to parse them.
    MF6 keyword sequences like 'STEPS 1 5' or 'all' are left as-is even
    if they contain spaces, because they are not string literals.
    """
    if isinstance(value, str) and '"' in value:
        return f"'{value}'"
    return str(value)


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
    from flopy4.mf6.gwf.disv import Disv

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

    spatial_dims = [d for d in value.dims if d in ("nlay", "nrow", "ncol", "ncpl", "nodes")]
    has_spatial_dims = len(spatial_dims) > 0
    mask = nonempty(value)
    indices = np.where(mask)
    values = value.values[mask]
    for i, val in enumerate(values):
        if isinstance(val, Disv.Cell2dRecord):
            rec = (
                val.icell2d + 1,
                val.xc,
                val.yc,
                val.ncvert,
            ) + tuple(v + 1 for v in val.icvert)
        elif has_spatial_dims:
            cellid = tuple(idx[i] + 1 for idx in indices)
            rec = cellid + (val,)
        else:
            rec = (val,)
        yield rec


def data2lines(value: list | tuple | dict | xr.Dataset | xr.DataArray, inset: str = " ") -> str:
    """
    Pre-format list data rows to a single newline-joined string.

    Replaces per-row Jinja2 template iteration (which incurs sandbox
    getattr overhead for every cell) with a single Python string join.
    Functionally equivalent to the list macro's ``{% for row %}{{ record(row) }}``
    loop but ~10x faster for large packages.
    """
    return "\n".join(inset + " ".join(str(x) for x in row) for row in data2list(value))


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
                if not (name.startswith("save_") or name.startswith("print_")):  # type: ignore
                    # TODO: not working yet
                    if name == "perioddata":
                        val = value[name]
                        val = val.item() if val.shape == () else val
                        yield attrs.astuple(val, recurse=True)  # type: ignore
                    continue
                val = value[name]
                val = val.item() if val.shape == () else val
                yield (*name.split("_"), val)  # type: ignore

        else:
            row: list[Any] = []
            for name, da in value.data_vars.items():
                val = da.item() if da.shape == () else da
                if kw := da.attrs.get("row_keyword", False):
                    if val:
                        row.append(kw if isinstance(kw, str) else str(name).upper())
                else:
                    row.extend(da.attrs.get("prefix", ()))
                    row.append(val)
            yield tuple(row)
        return

    combined_mask: Any = None
    spatial_da = None  # a non-aux DataArray for deriving spatial dims/mask
    for name, first in value.data_vars.items():
        if "naux" in first.dims:
            # nonempty gives (spatial..., naux) bool array; collapse naux with any()
            mask = nonempty(first).any(axis=-1)
        else:
            mask = nonempty(first)
            spatial_da = first
        combined_mask = mask if combined_mask is None else (combined_mask | mask)
    if combined_mask is None or not np.any(combined_mask):
        return

    if spatial_da is None:
        spatial_da = first
    spatial_dims = [d for d in spatial_da.dims if d in ("nlay", "nrow", "ncol", "nodes")]
    has_spatial_dims = len(spatial_dims) > 0
    indices = np.where(combined_mask)
    n_active = len(indices[0])

    # Pre-extract all values from each data variable as numpy arrays so the
    # per-row loop uses O(1) numpy scalar access instead of per-cell xarray
    # label-based indexing (which has ~80µs overhead per call).
    extracted: dict[str, np.ndarray] = {
        str(name): da.values[tuple(indices)] for name, da in value.data_vars.items()
    }

    # Pre-compute 1-based cellids for all active cells.
    cellids: list[np.ndarray] = [idx + 1 for idx in indices] if has_spatial_dims else []

    for i in range(n_active):
        if is_oc:
            for name in value.data_vars.keys():
                raw = extracted[str(name)][i]
                val = raw.item() if hasattr(raw, "ndim") and raw.ndim == 0 else raw
                yield (*str(name).split("_"), val)  # type: ignore
        else:
            row2: list[Any] = []
            for name, da in value.data_vars.items():
                raw = extracted[str(name)][i]
                val = raw.item() if hasattr(raw, "ndim") and raw.ndim == 0 else raw
                if kw := da.attrs.get("row_keyword", False):
                    if val:
                        row2.append(kw if isinstance(kw, str) else str(name).upper())
                else:
                    row2.extend(da.attrs.get("prefix", ()))
                    if da.attrs.get("cellid"):
                        if isinstance(val, tuple):
                            row2.extend(c + 1 for c in val)
                        else:
                            row2.append(val + 1)
                    else:
                        if hasattr(val, "ndim") and val.ndim > 0:
                            row2.extend(float(v) for v in np.asarray(val).flat)
                        else:
                            row2.append(val)
            if has_spatial_dims:
                cellid = tuple(cid[i].item() for cid in cellids)
                yield cellid + tuple(row2)
            else:
                yield tuple(row2)
