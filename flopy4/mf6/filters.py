from collections.abc import Iterable, Mapping
from inspect import isclass
import types
from typing import Union, get_args, get_origin
import numpy as np
import xarray as xr
from jinja2 import pass_context

from attrs import Attribute
from xattree import Xattribute


@pass_context
def value(ctx, field: Xattribute):
    """Return the kind of the field."""
    # TODO
    pass


def dask_expand(data: xr.DataArray):
    for block in data.data.to_delayed():
        block_data = block.compute()
        yield block_data


def nparray2string(data: np.ndarray):
    return np.array2string(data, separator=" ")[1:-1]  # remove brackets
