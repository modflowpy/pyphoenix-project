from typing import Any

import numpy as np
import xarray as xr
from jinja2 import pass_context
from modflow_devtools.dfn import Dfn, Field
from numpy.typing import NDArray


def blocks(dfn: Dfn) -> dict:
    return {k: v for k, v in dfn.items() if k not in Dfn.__annotations__}


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


def array_delay(value: xr.DataArray):
    """Yield chunks (lines) from a Dask array."""
    # TODO: Determine a good chunk size,
    # because if the underlying array is only numpy, it will stay one block.
    for chunk in value.chunk():
        yield chunk.compute()


def array2string(value: NDArray) -> str:
    """Convert an array to a string."""
    return np.array2string(value, separator=" ")[1:-1]  # remove brackets


def is_dict(value: Any) -> bool:
    """Check if the value is a dictionary."""
    return isinstance(value, dict)
