from attrs import NOTHING, Attribute, fields_dict
from xattree import array as xattree_array
from xattree import coord as xattree_coord
from xattree import dim as xattree_dim
from xattree import field as xattree_field


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
    return xattree_field(
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
    return xattree_dim(
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
    return xattree_coord(
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
):
    """Define an array field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
    return xattree_array(
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
    fields = {k: v for k, v in fields.items() if "block" in v.metadata}
    blocks: dict[str, Block] = {}
    for k, v in fields.items():
        block = v.metadata["block"]
        if block not in blocks:
            blocks[block] = {}
        blocks[block][k] = v
    return blocks
