"""
Wrap `xattree` and `attrs` specification utilities for MF6.
These include field decorators and introspection functions.
"""

import builtins
import types
from typing import Union, get_args, get_origin

import numpy as np
from attrs import NOTHING, Attribute
from modflow_devtools.dfn import Dfn, Field, FieldType, Reader

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
    block: str | None = None,
):
    """Define a field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = "urword"
    return flopy_field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
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
        metadata["reader"] = "urword"
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
        metadata["reader"] = "readarray"
    return flopy_coord(
        scope=scope,
        default=default,
        repr=repr,
        eq=eq,
        metadata=metadata,
    )


def array(
    cls=None,
    dims=None,
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=None,
    metadata=None,
    block: str | None = None,
    reader: Reader = "readarray",
):
    """Define an array field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = reader
    return flopy_array(
        cls=cls,
        dims=dims,
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        metadata=metadata,
    )


Block = dict[str, Attribute]


def block_sort_key(item: tuple[str, dict]) -> int:
    k, _ = item
    if k == "options":
        return 0
    elif k == "dimensions":
        return 1
    elif k == "griddata":
        return 2
    elif k == "packagedata":
        return 3
    elif "period" in k:
        # some packages have block "period", some have "perioddata"
        return 4
    else:
        return 5


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


def get_dfn_field_type(attribute: Attribute) -> FieldType:
    """
    Get a `xattree` field's type as defined by the MODFLOW 6 input
    definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types

    The type of the field is determined from `xattree` metadata.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    kind = xatmeta["kind"]
    match kind:
        case "child":
            raise ValueError(f"Top-level field should not be a child: {attribute.name}")
        case "array":
            return "recarray"
        case "coord":
            return "recarray"
        case "dim":
            return "integer"
        case "attr":
            match attribute.type:
                case builtins.str | np.str_:
                    return "string"
                case builtins.bool | np.bool:
                    return "keyword"
                case builtins.int | np.integer:
                    return "integer"
                case builtins.float | np.floating:
                    return "double precision"

                case t if (
                    get_origin(t) in (Union, types.UnionType) and get_args(t)[-1] is types.NoneType
                ):
                    return "union"
                case _:
                    return "record"
    raise ValueError(f"Could not map {attribute.name} to a valid MF6 type.")


def to_dfn_field(attribute: Attribute) -> Field:
    """
    Convert a `xattree` field specification to a field as defined by the
    MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    return Field(
        name=attribute.name,
        type=get_dfn_field_type(attribute),
        shape=xatmeta.get("dims", None),
        block=attribute.metadata.get("block", None),
        default=attribute.default,
        children={k: to_dfn_field(v) for k, v in fields_dict(attribute.type)}  # type: ignore
        if attribute.metadata.get("kind", None) == "child"  # type: ignore
        else None,  # type: ignore
        reader=attribute.metadata.get("reader", "urword"),
    )


def get_blocks(dfn: Dfn) -> dict:
    """
    Get blocks from an MF6 input definition. Anything not an
    explicitly defined key in the `Dfn` typed dict is a block.
    """
    return dict(
        sorted(
            {k: v for k, v in dfn.items() if k not in Dfn.__annotations__}.items(),
            key=block_sort_key,
        )
    )
