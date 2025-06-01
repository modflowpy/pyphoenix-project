from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any

import numpy as np
import xarray as xr
from jinja2 import pass_context
from modflow_devtools.dfn import Dfn, Field
from numpy.typing import NDArray

from flopy4.mf6.spec import block_sort_key


def blocks(dfn: Dfn) -> dict:
    """
    Get blocks from an MF6 input definition. Anything not an
    explicitly defined key in the `Dfn` typed dict is a block.
    """
    return dict(
        sorted(
            {k: v for k, v in dfn.items() if k not in Dfn.__annotations__}.items(),
            key=block_sort_key,
        )
    )


def field_type(field: Field) -> str:
    """
    Get a field's type as defined by the MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types
    """
    return field["type"]


@pass_context
def field_value(ctx, field: Field):
    """Get a field's value via the template context."""
    return getattr(ctx["data"], field["name"])


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
        yield chunk.compute()


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
    format = (
        "%d"
        if np.issubdtype(value.dtype, np.integer)
        else "%f"
        if np.issubdtype(value.dtype, np.floating)
        else "%s"
    )
    np.savetxt(buffer, value, fmt=format, delimiter=" ")
    return buffer.getvalue().strip()


def is_list(value: Any) -> bool:
    return isinstance(value, list)
