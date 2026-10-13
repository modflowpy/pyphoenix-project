"""
Wrap `attrs` specification utilities for MF6.
These include field decorators and introspection functions.
"""

import builtins
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, Union, Unpack, get_args, get_origin

import attrs
import numpy as np
from attrs import NOTHING, Attribute

from flopy4.mf6._types import (
    ARRAY_EQ,
    FloatArrayLike,
    IntArrayLike,
    TimeArraySeriesRef,
    to_ts_value,
    to_ts_values,
)
from flopy4.mf6.item import to_union_arm
from flopy4.spec import fields_dict as flopy_fields_dict

FieldType = Literal["keyword", "integer", "double", "string", "list", "record"]

# As in the DFN schema. An index is 1-based in the file, 0-based in memory;
# a "signed" one's sign carries a meaning of its own (SFR's ic). A cellid
# is in the grid of the component's own model, or of an exchange's first or
# second ("1", "2").
Index = bool | Literal["signed"]
Cellid = bool | Literal["1", "2"]
FileDirection = Literal[None, "in", "out"]


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


def _check_dim(instance, attribute, value):
    """An `on_setattr` hook raising if a dimension assigned to a package
    disagrees with the rows of a list it counts."""
    check = getattr(instance, "_check_dim_rows", None)
    if value is not None and check is not None:
        check(attribute.name, value)
    return value


# Field functions, one per DFN field type (modflow_devtools.dfns.schema), each
# taking that type's attributes. A field with a ``block`` is a component's;
# one without is a field of a list item or record. Each records its type, and
# its attributes that are set, in the field's metadata.


class FieldKwargs(TypedDict, total=False):
    """Arguments every field function takes: `attrs.field`'s, and the DFN's
    for any field."""

    default: Any
    validator: Any
    converter: Any
    repr: bool
    eq: Any
    init: bool
    metadata: dict
    on_setattr: Any
    alias: str | None
    block: str | None
    longname: str | None
    optional: bool
    netcdf: bool
    tagged: bool


def _pipe(*hooks):
    """`on_setattr` hooks run in turn, skipping any None."""
    return attrs.setters.pipe(*(h for h in hooks if h is not None))


def _field(type_: str, kwargs: FieldKwargs, **attributes) -> Any:
    """An `attrs.field` of DFN type ``type_``, its ``attributes`` (and the
    common ones in ``kwargs``) in its metadata where set."""
    metadata = dict(kwargs.get("metadata") or {})
    metadata["type"] = type_
    for key in ("block", "longname", "optional", "netcdf", "tagged"):
        if kwargs.get(key):
            metadata[key] = kwargs[key]  # type: ignore[literal-required]
    metadata.update({k: v for k, v in attributes.items() if v not in (None, False, ())})
    on_setattr = kwargs.get("on_setattr")
    if kwargs.get("block") == "dimensions":
        # check the dimension against the rows it counts when it is reassigned
        on_setattr = _pipe(attrs.setters.convert, attrs.setters.validate, _check_dim, on_setattr)
    return attrs.field(
        default=kwargs.get("default", NOTHING),
        validator=kwargs.get("validator"),
        converter=kwargs.get("converter"),
        repr=kwargs.get("repr", True),
        eq=kwargs.get("eq", True),
        init=kwargs.get("init", True),
        on_setattr=on_setattr,
        metadata=metadata,
        alias=kwargs.get("alias"),
    )


def _ts_converter(kwargs: FieldKwargs, converter) -> None:
    """A time series field of an item or record takes a series' name for a
    value (see `to_ts_value`). A component's names a time-array series and
    takes no converter."""
    if kwargs.get("block") is None:
        kwargs.setdefault("converter", converter)


def keyword(**kwargs: Unpack[FieldKwargs]) -> Any:
    """A keyword: a flag, present or not."""
    kwargs["tagged"] = True
    return _field("keyword", kwargs)


def string(
    *,
    time_series: bool = False,
    pk: bool = False,
    fk: str | None = None,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """A string. A time series one may name a time series instead."""
    if time_series:
        _ts_converter(kwargs, to_ts_value)
    return _field("string", kwargs, time_series=time_series, pk=pk, fk=fk)


def integer(
    *,
    index: Index = False,
    pk: bool = False,
    fk: str | None = None,
    time_series: bool = False,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """An integer. An ``index`` is 1-based in the file, 0-based in memory."""
    if time_series:
        _ts_converter(kwargs, to_ts_value)
    return _field("integer", kwargs, index=index, pk=pk, fk=fk, time_series=time_series)


def double(*, time_series: bool = False, **kwargs: Unpack[FieldKwargs]) -> Any:
    """A double. A time series one may name a time series instead."""
    if time_series:
        _ts_converter(kwargs, to_ts_value)
    return _field("double", kwargs, time_series=time_series)


def array(
    *,
    shape: tuple[str, ...] = (),
    layered: bool = False,
    index: Index = False,
    fk: str | None = None,
    cellid: Cellid = False,
    time_series: bool = False,
    fill_forward: bool = False,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """An array, of the dimensions ``shape`` names: a component's grid array
    (``("nlay", "nrow", "ncol")``), or an item's values (``("auxiliary",)``;
    unsized, ``()``, the rest of the row). A ``cellid``'s shape starts with
    ``ncelldim``, one cellid's components: ``("ncelldim",)`` is one cellid,
    ``("ncelldim", "numalphaj")`` several.

    Compares with `array_eq`, as numpy's elementwise ``==`` isn't a valid
    ``__eq__`` result. An item's array counted by another of its fields
    keeps that field in step when reassigned.
    """
    shape = tuple(shape)
    counts = shape[1:] if cellid else shape
    kwargs.setdefault("eq", ARRAY_EQ)
    if time_series:
        _ts_converter(kwargs, to_ts_values)
    if index == "signed":
        kwargs.setdefault("converter", to_signed_indexes)
    if kwargs.get("block") is None and len(counts) == 1:
        # keep a field counting the array in step when it is reassigned
        kwargs["on_setattr"] = _pipe(
            attrs.setters.convert, _recount(counts[0]), kwargs.get("on_setattr")
        )
    return _field(
        "array",
        kwargs,
        shape=shape,
        layered=layered,
        index=index,
        fk=fk,
        cellid=cellid,
        time_series=time_series,
        fill_forward=fill_forward,
    )


def list_(
    *,
    shape: tuple[str, ...] = (),
    fill_forward: bool = False,
    write_if_empty: bool = False,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """A list of items. Its ``shape``, if any, is the dimension counting its
    rows, exact (``("nper",)``) or a bound (``("<=maxbound",)``). A
    ``fill_forward`` list is given per period, each period's rows carrying
    on until the next's. A ``write_if_empty`` one's block is written even
    with no rows."""
    if len(shape) > 1:
        raise ValueError(f"a list has at most one dimension, got {shape!r}")
    dim = shape[0] if shape else None
    return _field("list", kwargs, dim=dim, fill_forward=fill_forward, write_if_empty=write_if_empty)


def union(*kinds: str, **kwargs: Unpack[FieldKwargs]) -> Any:
    """A value of any of several types. Given ``kinds``, it's one value of
    any of them, told apart when read (OBS's id: ``"cellid"``, ``"index"`` or
    ``"string"``; LAK's bedleak: ``"keyword"`` or ``"double"``). Without,
    its arms are the classes and words its annotation names (OC's
    ocsetting), and it builds its arm from the values given for it (see
    `item.to_union_arm`)."""
    if not kinds:
        kwargs.setdefault(
            "converter", attrs.Converter(to_union_arm, takes_self=True, takes_field=True)
        )
    return _field("union", kwargs, union=kinds)


def record(**kwargs: Unpack[FieldKwargs]) -> Any:
    """A record: several values on a line, held as a `Record`."""
    return _field("record", kwargs)


def file(
    *,
    direction: FileDirection = None,
    keyword: str | None = None,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """A file path, read (``direction="in"``) or written (``"out"``). A
    file record's ``keyword`` leads it: ``TS6 FILEIN <file>``."""
    return _field(
        "file", kwargs, direction=direction, _keyword=keyword.lower() if keyword else None
    )


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
    cellid: bool | Literal["1", "2"] = False,
    tagged: bool = False,
    array: bool = False,
    signed: bool = False,
    union: tuple[str, ...] | None = None,
    arms: bool = False,
):
    """Define a field: always a plain ``attrs.field()``.

    A field with a ``shape`` holds an array, so unless ``eq`` is given it
    compares with `array_eq` (numpy's elementwise ``==`` isn't a valid
    ``__eq__`` result). An ``array`` column of a table row (`Item`) is a
    tuple, compared as such; its ``shape`` is the dimension sizing it. A
    row's union of words and arm classes (``arms``) builds its arm from
    the values given for it (see `item.to_union_arm`).
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
        if block is None:
            # a table row's column: a name is a time series reference
            # (a package's period array names a time-array series instead)
            converter = converter or (to_ts_values if array else to_ts_value)
    if index:
        metadata["index"] = True
    if pk:
        metadata["pk"] = True
    if fk:
        metadata["fk"] = fk
    if cellid:
        metadata["cellid"] = cellid
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
    if block == "dimensions":
        # check the dimension against the rows it counts when it is reassigned
        hooks = [attrs.setters.convert, attrs.setters.validate, _check_dim]
        if on_setattr is not None:
            hooks.append(on_setattr)
        on_setattr = attrs.setters.pipe(*hooks)
    if union:
        metadata["union"] = union
    if signed:
        metadata["signed"] = True
        converter = converter or to_signed_indexes
    if arms:
        converter = converter or attrs.Converter(to_union_arm, takes_self=True, takes_field=True)
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
    the value. Lists are converted element-wise, and a single value given
    to a list field is wrapped in one."""
    from flopy4.attrs_xarray import child_field_candidates

    if (spec := child_field_candidates(field)) is None:
        return value
    kind, candidates = spec
    if kind == "list":
        if value is None:
            return value
        if not isinstance(value, (list, tuple)):
            return [_coerce_one(value, candidates)]
        items = [_coerce_one(v, candidates) for v in value]
        return value if all(a is b for a, b in zip(items, value)) else items
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
            if set(args) - {TimeArraySeriesRef} in ({IntArrayLike}, {FloatArrayLike}):
                # an array, or a time-array series giving it
                return to_field_type(next(a for a in args if a is not TimeArraySeriesRef))
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
    elif k.split()[0] == "period":
        return 4
    else:
        return 3
