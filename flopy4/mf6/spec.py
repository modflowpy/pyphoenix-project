"""
Wrap `xattree` and `attrs` specification utilities for MF6.
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
from modflow_devtools.dfn.schema import Field, FieldType

from flopy4.mf6._types import FloatArrayLike, IntArrayLike
from flopy4.spec import array as flopy_array
from flopy4.spec import coord as flopy_coord
from flopy4.spec import dim as flopy_dim
from flopy4.spec import field as flopy_field
from flopy4.spec import fields_dict as flopy_fields_dict


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
    always_emit: bool = False,
    auto_from: str | None = None,
    fill_forward: bool = False,
    reader: str | None = None,
    oc_action: str | None = None,
    oc_rtype: str | None = None,
    time_series: bool = False,
    index: bool = False,
    pk: bool = False,
    fk: str | None = None,
    cellid: bool = False,
    tagged: bool = False,
    prefix: tuple[str, ...] | None = None,
):
    """Define a codegen-v2 field: always a plain ``attrs.field()``.

    Codegen-v2 packages (``Package`` subclasses, hand-written or generated)
    are plain attrs classes, not ``@xattree``-decorated. Use
    ``xattree_field()`` instead for fields on real ``@xattree`` component
    classes (``Model``, ``Simulation``, ``Gwf``, ...) — routing one of
    *those* through plain ``attrs.field()``, or a codegen-v2 field through
    ``xattree_field()``, would be wrong either way: ``_get_xatspec()``
    recomputes from ``attrs.fields(cls)`` for whatever class is asked about,
    so a stray xattree marker on a non-decorated class's field would be
    treated as real xattree state and moved in/out of a DataTree that
    doesn't otherwise track it, corrupting ``Package``'s plain
    ``__dict__``-based field storage.
    """
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
    if always_emit:
        metadata["always_emit"] = True
    if auto_from:
        metadata["auto_from"] = auto_from
    if fill_forward:
        metadata["fill_forward"] = True
    if reader:
        metadata["reader"] = reader
    if oc_action:
        metadata["oc_action"] = oc_action
    if oc_rtype:
        metadata["oc_rtype"] = oc_rtype
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


def xattree_field(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    longname: str | None = None,
):
    """Define a field on a real ``@xattree``-decorated component class.

    See ``field()`` for why this is a separate function rather than a shared
    one that infers which case applies.
    """
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
    return flopy_field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
        on_setattr=on_setattr,
        metadata=metadata,
    )


FileInOut = Literal[None, "filein", "fileout"]


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
    inout: FileInOut | None = None,
    longname: str | None = None,
    optional: bool = False,
    prefix: tuple[str, ...] | None = None,
):
    """Define a codegen-v2 path field: always a plain ``attrs.field()``.

    ``prefix``: fixed token(s) a row-level path column emits before its own
    FILEIN/FILEOUT+filename (e.g. LAK tables' ``TAB6``, SSM fileinput's
    ``SPC6``) -- read by Item.to_tokens()/from_tokens() the same way any
    other row column's prefix= is (see flopy4.mf6.item.Item). Package-level
    path fields (options-block file records) don't need this -- there's no
    preceding row context, just the field's own inout=.

    See ``field()`` — use ``xattree_path()`` instead for fields on real
    ``@xattree`` component classes.
    """
    metadata = metadata or {}
    if prefix:
        metadata["prefix"] = tuple(prefix)
    if block:
        metadata["block"] = block
    if inout:
        metadata["inout"] = inout
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


def xattree_path(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    inout: FileInOut | None = None,
    longname: str | None = None,
):
    """Define a path field on a real ``@xattree``-decorated component class.

    See ``field()`` for why this is a separate function rather than a shared
    one that infers which case applies.
    """
    if block or inout or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if inout:
            metadata["inout"] = inout
        if longname:
            metadata["longname"] = longname
    return flopy_field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
        on_setattr=on_setattr,
        metadata=metadata,
    )


def dim(
    scope=None,
    coord: bool | str = True,
    default=NOTHING,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    block: str | None = None,
    longname: str | None = None,
):
    """Define a dimension field."""
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
    return flopy_dim(
        scope=scope,
        coord=coord,
        default=default,
        repr=repr,
        eq=eq,
        init=init,
        metadata=metadata,
    )


def coord(
    scope=None,
    default=NOTHING,
    repr=True,
    eq=True,
    metadata=None,
    block: str | None = None,
    longname: str | None = None,
):
    """Define a coordinate field."""
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
    return flopy_coord(
        scope=scope,
        default=default,
        repr=repr,
        eq=eq,
        metadata=metadata,
    )


def array(
    dtype: np.dtype | str | type | None = None,
    dims=None,
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=None,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    netcdf: bool | None = None,
    longname: str | None = None,
    prefix: tuple[str, ...] | None = None,
    row_keyword: bool | str = False,
    cellid: bool = False,
):
    """Define an array field."""
    if block or netcdf or longname or prefix or row_keyword or cellid:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if netcdf:
            metadata["netcdf"] = netcdf
        if longname:
            metadata["longname"] = longname
        if prefix:
            metadata["prefix"] = tuple(prefix)
        if row_keyword:
            metadata["row_keyword"] = row_keyword
        if cellid:
            metadata["cellid"] = True
    return flopy_array(
        dtype=dtype,
        dims=dims,
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        on_setattr=on_setattr,
        metadata=metadata,
    )


def embedded_keystring(
    keyword: str,
    feature_dim: str,
    dtype: np.dtype | str | type | None = None,
    default=None,
    block: str | None = None,
    longname: str | None = None,
    converter=None,
):
    """Define a 2D period field for embedded keystring output (e.g. LAK, MAW).

    Values indexed by (nper, feature_dim) emit rows:
        ``feature_num KEYWORD value``
    one row per non-fill entry.  Fill is FILL_DNODATA for numeric fields
    and None for object fields.
    """
    metadata: dict = {
        "embedded_keystring": True,
        "keyword": keyword,
    }
    if block:
        metadata["block"] = block
    if longname:
        metadata["longname"] = longname
    return flopy_array(
        dtype=dtype if dtype is not None else np.float64,
        dims=("nper", feature_dim),
        default=default,
        converter=converter,
        metadata=metadata,
    )


def keystring(
    default=None,
    block: str | None = None,
    dims: tuple = ("nper",),
    longname: str | None = None,
    converter=None,
):
    """Define a period output-control keystring field.

    Values are strings representing a valid ocsetting alternative,
    e.g. 'ALL', 'LAST', 'STEPS 1 3', 'FREQUENCY 2'.  The 'keystring'
    metadata key distinguishes these from plain string arrays so the
    egress writer can route them through the correct serialiser.
    """
    metadata: dict = {"keystring": True}
    if block:
        metadata["block"] = block
    if longname:
        metadata["longname"] = longname
    return flopy_array(
        dtype=np.dtypes.StringDType(),
        dims=dims,
        default=default,
        converter=converter,
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
                    case _:
                        return "record"
            return "list"
        # TODO handle arrays
        case _:
            return "record"


def get_field_type(attribute: Attribute) -> FieldType:
    """
    Get a `xattree` field's type as defined by the MODFLOW 6 input
    definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types

    The type of the field is determined from `xattree` metadata.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    match xatmeta["kind"]:
        case "child":
            return "list"  # Child components become tabular bindings
        case "array":
            return "array"
        case "coord":
            return "array"
        case "dim":
            return "integer"
        case "attr":
            if (t := attribute.type) is None:
                raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no type.")
            return to_field_type(t)
    raise ValueError(f"Could not map {attribute.name} to a valid MF6 type.")


def to_field(attribute: Attribute) -> Field:
    """
    Convert a `xattree` field specification to a field as defined by the
    MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    return Field(
        name=attribute.name,
        type=get_field_type(attribute),
        shape=xatmeta.get("dims", None),
        block=attribute.metadata.get("block", None),
        default=attribute.default,
        netcdf=attribute.metadata.get("netcdf", None),
        children={k: to_field(v) for k, v in fields_dict(attribute.type)}  # type: ignore
        if attribute.metadata.get("kind", None) == "child"  # type: ignore
        else None,  # type: ignore
    )


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
