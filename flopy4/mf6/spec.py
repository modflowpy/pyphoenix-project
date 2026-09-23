"""
Wrap `attrs` specification utilities for MF6.
These include field decorators and introspection functions.
"""

import builtins
import types
from datetime import datetime
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import attrs
import numpy as np
from attrs import NOTHING, Attribute

from flopy4.mf6._types import FloatArrayLike, IntArrayLike
from flopy4.spec import fields_dict as flopy_fields_dict

FieldType = Literal["keyword", "integer", "double", "string", "list", "record"]


def field(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    alias: str | None = None,
    block: str | None = None,
    longname: str | None = None,
    shape: tuple[str, ...] | None = None,
    layered: bool | None = None,
    optional: bool = False,
    netcdf: bool | None = None,
    schema: str | None = None,
    write_if_empty: bool = False,
    auto_from: str | None = None,
    fill_forward: bool = False,
    time_series: bool = False,
    index: bool = False,
    pk: bool = False,
    fk: str | None = None,
    cellid: bool = False,
    tagged: bool = False,
    prefix: tuple[str, ...] | None = None,
    array: bool = False,
):
    """Define a field: always a plain ``attrs.field()``."""
    metadata = metadata or {}
    if block:
        metadata["block"] = block
    if longname:
        metadata["longname"] = longname
    if shape:
        metadata["shape"] = shape
    if layered is not None:
        # Explicit False must round-trip: some consumers (netcdf.py) default
        # a *missing* key to True, so omitting a deliberate False would flip it.
        metadata["layered"] = layered
    if optional:
        metadata["optional"] = True
    if netcdf:
        metadata["netcdf"] = True
    if schema:
        metadata["schema"] = schema
    if write_if_empty:
        metadata["write_if_empty"] = True
    if auto_from:
        metadata["auto_from"] = auto_from
    if fill_forward:
        metadata["fill_forward"] = True
    if time_series:
        metadata["time_series"] = True
    if index:
        metadata["index"] = True
    if pk:
        metadata["pk"] = True
    if fk:
        metadata["fk"] = fk
    if cellid:
        metadata["cellid"] = True
    if tagged:
        metadata["tagged"] = True
    if prefix:
        metadata["prefix"] = tuple(prefix)
    if array:
        metadata["array"] = True
    return attrs.field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
        on_setattr=on_setattr,
        metadata=metadata,
        alias=alias,
    )


FileDirection = Literal[None, "in", "out"]


def path(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    direction: FileDirection | None = None,
    longname: str | None = None,
    optional: bool = False,
    prefix: tuple[str, ...] | None = None,
):
    """Define a path field: always a plain ``attrs.field()``.

    ``prefix``: fixed token(s) a row-level path column emits before its own
    FILEIN/FILEOUT+filename (e.g. LAK tables' ``TAB6``, SSM fileinput's
    ``SPC6``) -- read by Item.to_tokens()/from_tokens() the same way any
    other row column's prefix= is (see flopy4.mf6.item.Item). Package-level
    path fields (options-block file records) don't need this -- there's no
    preceding row context, just the field's own direction=.
    """
    metadata = metadata or {}
    if prefix:
        metadata["prefix"] = tuple(prefix)
    if block:
        metadata["block"] = block
    if direction:
        metadata["direction"] = direction
    if longname:
        metadata["longname"] = longname
    if optional:
        metadata["optional"] = True
    return attrs.field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
        on_setattr=on_setattr,
        metadata=metadata,
    )


Block = dict[str, Attribute]


def blocks(cls) -> list[list[Attribute]]:
    """Return an ordered list of blocks for a component class."""
    return [list(v.values()) for v in blocks_dict(cls).values()]


def blocks_dict(cls) -> dict[str, Block]:
    """
    Return an ordered dictionary of blocks for a component class,
    whose keys are block names. Each block is a map from variable
    (field) name to `attrs.Attribute`.
    """
    fields = fields_dict(cls)
    blocks: dict[str, Block] = {}
    for k, v in fields.items():
        block = v.metadata["block"]
        if block not in blocks:
            blocks[block] = {}
        blocks[block][k] = v
    return dict(sorted(blocks.items(), key=block_sort_key))


def fields(cls) -> list[Attribute]:
    """Return an ordered list of fields for a component class."""
    return list(fields_dict(cls).values())


def fields_dict(cls) -> dict[str, Attribute]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is an `attrs.Attribute`.
    """
    fields = flopy_fields_dict(cls)
    return {k: v for k, v in fields.items() if "block" in v.metadata}


def _ndarray_field_type(t) -> FieldType | None:
    """Map a bare ``NDArray[dtype]`` annotation to its DFN field type, if possible.

    Hand-written DIS/DISV griddata fields (``delr``, ``top``, ``idomain``, ...)
    are typed with plain ``NDArray[np.int64]``/``NDArray[np.float64]`` rather
    than ``IntArrayLike``/``FloatArrayLike`` (those exist for fields that may
    also be dask-backed; DIS/DISV griddata never is). Returns ``None`` for
    anything that isn't a parameterized ``numpy.ndarray`` annotation.
    """
    if get_origin(t) is not np.ndarray:
        return None
    args = get_args(t)
    if len(args) < 2:
        return None
    dtype_args = get_args(args[1])
    if not dtype_args or not isinstance(dtype_args[0], type):
        return None
    scalar = dtype_args[0]
    if issubclass(scalar, np.bool_):
        return "keyword"
    if issubclass(scalar, np.integer):
        return "integer"
    if issubclass(scalar, np.floating):
        return "double"
    if issubclass(scalar, (np.str_, np.object_)):
        return "string"
    return None


def repeating_array_key_type(field_type) -> type | None:
    """For ``Optional[dict[K, IntArrayLike | FloatArrayLike]]``, return
    ``K`` -- the header type of a block that repeats (e.g. utl-tas's "time"
    block), whose own array field is keyed by header value. Returns
    ``None`` for anything else, including a plain array
    (``Optional[FloatArrayLike]``, e.g. RCHA's period-readarray fields) and
    an ``Optional[dict[int, list[ItemClass]]]`` period Item-list (see
    ``item.item_list_type``) -- structurally distinct shapes, detected from
    the annotation itself rather than a metadata flag, the same way
    ``item_list_type`` reads its own dict-wrapped shape.
    """
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None or get_origin(inner) is not dict:
        return None
    key, val = get_args(inner)
    return key if val in (IntArrayLike, FloatArrayLike) else None


def to_field_type(t: type) -> FieldType:
    if (result := _ndarray_field_type(t)) is not None:
        return result
    match t:
        case builtins.str | np.str_:
            return "string"
        case builtins.bool | np.bool:
            return "keyword"
        case builtins.int | np.integer:
            return "integer"  # type: ignore
        case builtins.float | np.floating:
            return "double"  # type: ignore
        case t if t is Path or t is datetime:
            return "string"
        case t if t is IntArrayLike:
            return "integer"
        case t if t is FloatArrayLike:
            return "double"
        case t if get_origin(t) is dict:
            # A time-array-series field (e.g. utl-tas.tas_array), typed
            # dict[float, IntArrayLike | FloatArrayLike] -- the dtype lives
            # in the dict's value type, not the field's own top-level type.
            return to_field_type(get_args(t)[-1])
        case t if get_origin(t) in (Union, types.UnionType):
            args = get_args(t)
            if args[-1] is types.NoneType:
                if (result := _ndarray_field_type(args[0])) is not None:
                    return result
                match args[0]:
                    case builtins.str | np.str_:
                        return "string"
                    case builtins.bool | np.bool:
                        return "keyword"
                    case builtins.int | np.integer:
                        return "integer"
                    case builtins.float | np.floating:
                        return "double"
                    case tt if tt is Path or tt is datetime:
                        return "string"
                    case tt if tt is IntArrayLike:
                        return "integer"
                    case tt if tt is FloatArrayLike:
                        return "double"
                    case tt if get_origin(tt) is dict:
                        return to_field_type(get_args(tt)[-1])
                    case _:
                        return "record"
            return "list"
        # TODO handle arrays
        case _:
            return "record"


def block_sort_key(item) -> int:
    # TODO: remove when no longer needed, block order should
    # be as appears in the definition
    k, _ = item
    if k == "options":
        return 0
    elif k == "dimensions":
        return 1
    elif k == "griddata":
        return 2
    elif "period" in k:
        return 4
    else:
        return 3
