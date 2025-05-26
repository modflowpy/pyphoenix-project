import numpy as np
import xarray as xr
from attrs import Attribute
from jinja2 import pass_context
from numpy.typing import NDArray


def fieldkind(field: Attribute) -> str:
    """
    Get a field's `xattree` kind. Kind is either:

    - 'child' for child fields
    - 'array' for array fields
    - 'coord' for coordinate array fields
    - 'dim' for integer fields describing a dimension's size
    - 'attr' for all other fields
    """
    if (meta := field.metadata) is None:
        raise TypeError(f"Field {field.name} has no metadata")
    if (xatmeta := meta.get("xattree", None)) is None:
        raise TypeError(f"Field {field.name} has no xattree metadata")
    if "kind" not in xatmeta:
        raise TypeError(f"Field {field.name} has no kind")
    return xatmeta.get("kind", "attr")


@pass_context
def fieldvalue(ctx, field: Attribute):
    """Get a field's value from the data tree via the template context."""
    return ctx["data"][field.name]


def arraydelayed(value: xr.DataArray):
    """Yield chunks (lines) from a Dask array."""
    # TODO: Determine a good chunk size,
    # because if the underlying array is only numpy, it will stay one block.
    for chunk in value.chunk():
        yield chunk.compute()


def array2string(value: NDArray) -> str:
    """Convert an array to a string."""
    return np.array2string(value, separator=" ")[1:-1]  # remove brackets
