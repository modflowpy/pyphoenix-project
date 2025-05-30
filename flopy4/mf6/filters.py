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


def array_delay(value: xr.DataArray, chunks=None):
    """
    Yield chunks from an array. Each chunk becomes a line in the file.
    If the array is not already chunked, it is chunked using the given
    chunk size. If no chunk size is provided, the entire array becomes
    a single chunk.
    """
    if value.chunks is None:
        chunk_shape = chunks or {dim: size for dim, size in zip(value.dims, value.shape)}
        value = value.chunk(chunk_shape)
    for chunk in value.data.blocks:
        yield chunk.compute()


def array2string(value: NDArray) -> str:
    """Convert an array to a string."""
    s = np.array2string(value, separator=" ")
    if value.shape != ():
        s = s[1:-1]  # remove brackets
    return s.replace("'", "").replace('"', "")  # remove quotes


def is_dict(value: Any) -> bool:
    """Check if the value is a dictionary."""
    return isinstance(value, dict)
