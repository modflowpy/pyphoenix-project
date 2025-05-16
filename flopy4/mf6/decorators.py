from attrs import NOTHING
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
    """Create a field."""
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
    """Create a dimension field."""
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
    """Create a coordinate field."""
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
    """Create an array field."""
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
