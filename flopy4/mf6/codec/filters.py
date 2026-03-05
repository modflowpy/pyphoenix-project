"""Filters shared by both reader and writer."""

from typing import Any

import xarray as xr
from modflow_devtools.dfns.schema.field import Field
from modflow_devtools.dfns.schema.v2 import FieldType


def field_type(value: Any) -> FieldType:
    """Get a value's type according to the MF6 specification."""

    if isinstance(value, Field):
        return value.type
    if isinstance(value, bool):
        return "keyword"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (dict, tuple)):
        return "record"
    if isinstance(value, xr.DataArray):
        if value.dtype == "object":
            return "list"
        return "array"
    if isinstance(value, (list, xr.Dataset)):
        return "list"
    raise ValueError(f"Unsupported field type: {type(value)}")
