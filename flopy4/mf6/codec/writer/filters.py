import re
from collections.abc import Hashable, Mapping, Sequence
from io import StringIO
from pathlib import PurePath
from typing import Literal

import numpy as np
import xarray as xr
from numpy.typing import NDArray

from flopy4.mf6._types import Scalar
from flopy4.mf6.write_context import ArrayFormat, FloatPrecision

_NUMBER_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")

ArrayHow = Literal[
    "constant",
    "internal",
    "external",
    "layered constant",
    "layered internal",
    "layered mixed",
    "netcdf",
]


def block_begin(block_name: str) -> str:
    """A block's BEGIN line after the keyword: its name, then its index
    (PERIOD 1) or header record (CONTINUOUS FILEOUT <file>), whose case is
    kept."""
    name, _, header = block_name.partition(" ")
    return f"{name.upper()} {header}".rstrip()


def block_end(block_name: str) -> str:
    """A block's END line after the keyword: its name, and its index if any,
    but not a header record."""
    name, _, header = block_name.partition(" ")
    if header and len(header.split()) == 1 and _NUMBER_RE.fullmatch(header):
        return f"{name.upper()} {header}"
    return name.upper()


def array_how(
    value: xr.DataArray, netcdf: bool = False, array_format: "ArrayFormat | None" = None
) -> ArrayHow:
    """
    Determine how an array should be represented in MF6 input: the
    record(s) to write it with, per the attrs `annotate_arrays` and
    `write_external_arrays` mark it with, and `array_format`, the
    context's.

    Unless its `ArrayIO.format` (or else `array_format`) is "internal",
    an array whose values are all equal is CONSTANT; unless it's marked
    `layered`, a layered array whose layers each are is LAYERED CONSTANT.
    A dask-backed array skips the constant checks (they'd compute it) and
    is INTERNAL, LAYERED for a layered one: the writer streams it
    chunk-by-chunk via array2chunks without full materialization.
    """
    # arrays of fields MF6 reads from NetCDF are marked by egress
    if netcdf and value.attrs.get("netcdf", False):
        return "netcdf"
    # arrays written to files of their own are marked by
    # `write_external_arrays`
    if "open_close" in value.attrs:
        return "external"
    layered = "nlay" in value.dims
    if "layer_open_close" in value.attrs and layered:
        return "layered mixed"
    dask = hasattr(value.data, "blocks")
    internal = (value.attrs.get("format") or array_format) == "internal"
    as_layers = value.attrs.get("layered") if layered else False
    if as_layers:
        return "layered internal" if dask else "layered mixed"
    if dask:
        return "layered internal" if as_layers is None else "internal"
    if not internal and value.max() == value.min():
        return "constant"
    if as_layers is False:
        if value.ndim > 3:
            raise ValueError(f"Arrays with ndim > 3 are not supported, got ndim={value.ndim}")
        return "internal"
    if not internal and all(
        value.isel(nlay=k).max() == value.isel(nlay=k).min() for k in range(value.shape[0])
    ):
        return "layered constant"
    return "layered internal"


def iprn_option(value: xr.DataArray, layer: int | None = None) -> str:
    """An INTERNAL control record's `` IPRN <n>`` option for `value`, or
    for one of its layers, from the `iprn`/`layer_iprn` attrs
    `annotate_arrays` sets; empty if none is set."""
    iprn = value.attrs.get("layer_iprn", {}).get(layer) if layer is not None else None
    if iprn is None:
        iprn = value.attrs.get("iprn")
    return "" if iprn is None else f" IPRN {iprn}"


def binary_option(value: xr.DataArray, layer: int | None = None) -> str:
    """An OPEN/CLOSE control record's `` (BINARY)`` option for `value`, or
    for one of its layers, if `write_external_arrays` wrote its file
    binary; else empty."""
    if layer is None:
        binary = value.attrs.get("open_close_binary", False)
    else:
        binary = value.attrs.get("layer_open_close_binary", {}).get(layer, False)
    return " (BINARY)" if binary else ""


def layer_is_constant(
    value: xr.DataArray, layer: int, array_format: "ArrayFormat | None" = None
) -> bool:
    """Whether to write a layer of layered `value` CONSTANT: if all its
    values are equal, unless its `ArrayIO.format` (else the whole
    array's, else `array_format`, the context's) is "internal"."""
    fmt = value.attrs.get("layer_format", {}).get(layer) or value.attrs.get("format")
    if (fmt or array_format) == "internal":
        return False
    return is_constant(value.isel(nlay=layer))


def is_constant(value: xr.DataArray) -> bool:
    """Whether every value of `value` is the same. False for a dask array,
    which would have to be computed to tell."""
    if hasattr(value.data, "blocks"):
        return False
    return bool(value.max() == value.min())


def format_float(value: float, precision: "FloatPrecision | None" = None) -> str:
    """
    Format a float for MF6 input.

    Parameters
    ----------
    value : float
        Value to format
    precision : int or "lossless", optional
        Number of decimal places, in scientific notation. If "lossless" or
        None (the default), use the shortest string that reads back as the
        same value.
    """
    if precision is None or precision == "lossless":
        return repr(float(value))
    return f"{value:.{precision}e}"


def array2const(value: xr.DataArray, precision: "FloatPrecision | None" = None) -> Scalar:
    """
    Convert array to constant scalar value.

    Parameters
    ----------
    value : xr.DataArray
        Array to convert
    precision : int or "lossless", optional
        Number of decimal places for float output. If "lossless" or None
        (the default), floats are written losslessly.
    """
    if np.issubdtype(value.dtype, np.integer):
        return value.max().item()
    if np.issubdtype(value.dtype, np.floating):
        return format_float(value.max().item(), precision)
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
    elif value.ndim == 3:
        # regular 3D array, a chunk per layer
        for layer in value.values:
            yield np.squeeze(layer)
    else:
        # regular array, single chunk
        yield np.squeeze(value.values)


def array2string(value: NDArray, precision: "FloatPrecision | None" = None) -> str:
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
    precision : int or "lossless", optional
        Number of decimal places for float output. If "lossless" or None
        (the default), floats are written losslessly.
    """
    buffer = StringIO()
    value = np.asarray(value)
    if value.ndim > 2:
        raise ValueError(f"Only 1D and 2D arrays are supported, got ndim={value.ndim}")
    # a single value (squeezed by array2chunks) is a 1d array of one
    value = np.atleast_1d(value)
    if value.ndim == 1:
        # add an axis to 1d arrays so np.savetxt writes elements on 1 line
        value = value[None]

    if np.issubdtype(value.dtype, np.floating):
        if precision is None or precision == "lossless":
            return "\n".join(" ".join(map(repr, row)) for row in value.tolist())
        format = f"%.{precision}e"
    elif np.issubdtype(value.dtype, np.integer):
        format = "%d"
    else:
        format = "%s"

    np.savetxt(buffer, value, fmt=format, delimiter=" ")
    return buffer.getvalue().strip()


_BARE_WORD = re.compile(r"[a-zA-Z0-9().\/:;<=>?@_~+\[\\-][a-zA-Z0-9'().\/:;<=>?@_~+\[\\-]*")


def quote_if_needed(value: Scalar) -> str:
    """Format a scalar as one MF6 token: paths as POSIX, strings quoted
    if they wouldn't read back as a single word. Prefers single quotes,
    falls back to double if the value has a single quote."""
    if isinstance(value, PurePath):
        value = value.as_posix()
    if isinstance(value, str) and value == "":
        # `''` reads back as nothing, or an error, in most places
        raise ValueError("MF6 can't use an empty string as a value")
    if not isinstance(value, str) or _BARE_WORD.fullmatch(value):
        return str(value)
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    raise ValueError(f"MF6 can't represent a value with both quote types: {value!r}")


def data2lines(value: Sequence, inset: str = " ") -> str:
    """
    Pre-format list data rows to a single newline-joined string.

    Replaces per-row Jinja2 template iteration (which incurs sandbox
    getattr overhead for every cell) with a single Python string join.
    Functionally equivalent to the list macro's ``{% for row %}{{ record(row) }}``
    loop but ~10x faster for large packages.
    """
    return "\n".join(inset + " ".join(quote_if_needed(x) for x in row) for row in value)
