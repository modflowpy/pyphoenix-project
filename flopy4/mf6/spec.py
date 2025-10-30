"""
Wrap `xattree` and `attrs` specification utilities for MF6.
These include field decorators and introspection functions.
"""

import builtins
import types
from datetime import datetime
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import numpy as np
from attrs import NOTHING, Attribute
from modflow_devtools.dfn.schema.block import block_sort_key
from modflow_devtools.dfn.schema.v2 import Field as FieldV2
from modflow_devtools.dfn.schema.v2 import FieldType

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
    block: str | None = None,
):
    """Define a field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
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
):
    """Define a path field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
    if inout:
        metadata = metadata or {}
        metadata["inout"] = inout
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
):
    """Define a dimension field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
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
):
    """Define a coordinate field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
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
):
    """Define an array field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
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


def to_field(attribute: Attribute) -> FieldV2:
    """
    Convert a `xattree` field specification to a field as defined by the
    MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    return FieldV2(
        name=attribute.name,
        type=get_field_type(attribute),
        shape=xatmeta.get("dims", None),
        block=attribute.metadata.get("block", None),
        default=attribute.default,
        children={k: to_field(v) for k, v in fields_dict(attribute.type)}  # type: ignore
        if attribute.metadata.get("kind", None) == "child"  # type: ignore
        else None,  # type: ignore
    )
