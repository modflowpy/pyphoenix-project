import types
from typing import Union, get_args, get_origin

import numpy as np
import xarray as xr
import xattree
from jinja2 import pass_context
from numpy.typing import NDArray
from xattree import Xattribute


def fieldkind(field: Xattribute) -> str:
    """Get the kind of a field."""
    if isinstance(field, (xattree.Array, xattree.Coord)):
        return "array"
    if isinstance(field, xattree.Dim):
        return "scalar"
    if isinstance(field, xattree.Child):
        raise TypeError(f"Child field {field.name} unsupported in this context")
    type_ = field.type
    if type_ is None:
        raise TypeError(f"Field {field.name} has no type")
    if issubclass(type_, xattree.Scalar):
        return "scalar"
    args = get_args(type_)
    origin = get_origin(type_)
    if origin in (Union, types.UnionType):
        if args[-1] is types.NoneType:  # Optional
            type_ = args[0]
            assert type_ is not None
        else:
            return "union"
    if issubclass(type_, xattree.Scalar):
        return "scalar"
    if issubclass(type_, xattree.Attr):
        return "record"
    raise TypeError(f"Unsupported field type {type_} for field {field.name}")


@pass_context
def fieldvalue(ctx, field: Xattribute):
    return ctx["data"][field.name]


def arraydelayed(value: xr.DataArray):
    for block in value.data.to_delayed():
        block_data = block.compute()
        yield block_data


def array2string(value: NDArray) -> str:
    return np.array2string(value, separator=" ")[1:-1]  # remove brackets
