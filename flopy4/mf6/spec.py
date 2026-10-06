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

from flopy4.mf6._types import ARRAY_EQ, FloatArrayLike, IntArrayLike
from flopy4.spec import fields_dict as flopy_fields_dict

FieldType = Literal["keyword", "integer", "double", "string", "list", "record"]


def _recount(count: str):
    """An `on_setattr` hook setting the count column `count` to the length
    of the array being assigned."""

    def hook(instance, attribute, value):
        from flopy4.mf6.item import Item  # circular at import time

        if (
            value is not None
            and isinstance(instance, Item)
            and count in attrs.fields_dict(type(instance))
        ):
            object.__setattr__(instance, count, len(value))
        return value

    return hook


def field(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=None,
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
    dim: str | None = None,
    fill_forward: bool = False,
    time_series: bool = False,
    index: bool = False,
    pk: bool = False,
    fk: str | None = None,
    cellid: bool = False,
    tagged: bool = False,
    array: bool = False,
    signed: bool = False,
):
    """Define a field: always a plain ``attrs.field()``.

    A field with a ``shape`` holds an array, so unless ``eq`` is given it
    compares with `array_eq` (numpy's elementwise ``==`` isn't a valid
    ``__eq__`` result). An ``array`` column of a table row (`Item`) is a
    tuple, compared as such; its ``shape`` is the dimension sizing it.
    """
    if eq is None:
        eq = ARRAY_EQ if shape and not array else True
    metadata = metadata or {}
    if block:
        metadata["block"] = block
    if longname:
        metadata["longname"] = longname
    if shape:
        metadata["shape"] = shape
    if layered is not None:
        metadata["layered"] = layered
    if optional:
        metadata["optional"] = True
    if netcdf:
        metadata["netcdf"] = True
    if schema:
        metadata["schema"] = schema
    if write_if_empty:
        metadata["write_if_empty"] = True
    if dim:
        metadata["dim"] = dim
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
    if array:
        metadata["array"] = True
    if shape and array:
        # keep a column counting the array in step when it is reassigned
        hooks = [attrs.setters.convert, _recount(shape[0])]
        if on_setattr is not None:
            hooks.append(on_setattr)
        on_setattr = attrs.setters.pipe(*hooks)
    if signed:
        metadata["signed"] = True
        converter = converter or to_signed_indexes
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


def to_signed_indexes(values):
    """Signed indexes (SFR's ic) as (0-based index, sign) pairs. Each value
    is such a pair, or an int as in the file: a 1-based index carrying its
    sign (-3 -> (2, -1)). There's no 0-based signed int: 0 has no negative."""
    if values is None:
        return None
    pairs = []
    for v in values:
        if isinstance(v, (tuple, list)):
            i, sign = v
            if sign not in (1, -1):
                raise ValueError(f"sign must be 1 or -1, got {sign!r}")
            pairs.append((int(i), int(sign)))
        elif (n := int(v)) == 0:
            raise ValueError("a signed index as in the file is 1-based, got 0")
        else:
            pairs.append((abs(n) - 1, -1 if n < 0 else 1))
    return tuple(pairs)


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
    keyword: str | None = None,
):
    metadata = metadata or {}
    if keyword:
        metadata["_keyword"] = keyword.lower()
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


def _coerce_one(value, candidates: tuple[type, ...]):
    if value is None or isinstance(value, candidates):
        return value
    for cls in candidates:
        if (coerce := getattr(cls, "coerce", None)) is not None and (
            coerced := coerce(value)
        ) is not None:
            return coerced
    names = " or ".join(c.__name__ for c in candidates)
    raise TypeError(f"Expected {names} (or a value one accepts), got {type(value).__name__}")


def coerce_child(value, field: Attribute):
    """Convert a child field's value with its candidate classes' `coerce`
    classmethods, which return an instance or `None` if they don't accept
    the value. Lists and dicts are converted element-wise."""
    from flopy4.attrs_xarray import child_field_candidates

    if (spec := child_field_candidates(field)) is None:
        return value
    kind, candidates = spec
    if kind == "list" and isinstance(value, (list, tuple)):
        items = [_coerce_one(v, candidates) for v in value]
        return value if all(a is b for a, b in zip(items, value)) else items
    if kind == "dict" and isinstance(value, dict):
        coerced = {k: _coerce_one(v, candidates) for k, v in value.items()}
        return value if all(coerced[k] is v for k, v in value.items()) else coerced
    return _coerce_one(value, candidates)


def child(
    block: str | None = None,
    default=None,
    converter=None,
    keyword: str | None = None,
    direction: FileDirection | None = None,
):
    """A child component field: the component itself, standing in for the
    DFN field that names its file. A child named by a file record
    (``NCF6 FILEIN <file>``) has the record's keyword and direction."""
    metadata: dict = {"child": True}
    if block:
        metadata["block"] = block
    if keyword:
        metadata["_keyword"] = keyword.lower()
    if direction:
        metadata["direction"] = direction
    return attrs.field(
        default=default,
        converter=converter or attrs.Converter(coerce_child, takes_field=True),
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


def repeating_array_key_type(field_type) -> type | None:
    """For ``Optional[dict[K, IntArrayLike | FloatArrayLike]]``, return
    ``K`` -- the header type of a block that repeats (e.g. utl-tas's "time"
    block), whose own array field is keyed by header value. Returns
    ``None`` for anything else, including a plain array and an
    ``Optional[dict[int, list[ItemClass]]]`` period Item-list (see
    ``item.item_list_type``) -- structurally distinct shapes, detected from
    the annotation itself rather than a metadata flag, the same way
    ``item_list_type`` reads its own dict-wrapped shape. Period array
    fields (RCHA's recharge) have this shape too, keyed by period; callers
    tell them apart by their ``fill_forward`` metadata.
    """
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None or get_origin(inner) is not dict:
        return None
    key, val = get_args(inner)
    return key if val in (IntArrayLike, FloatArrayLike) else None


def to_field_type(t: type) -> FieldType:
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
            # e.g. a time-array-series field
            return to_field_type(get_args(t)[-1])
        case t if get_origin(t) in (Union, types.UnionType):
            args = get_args(t)
            if args[-1] is types.NoneType:
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
