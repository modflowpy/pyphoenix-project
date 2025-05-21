"""Wrap `xattree` and `attrs` specification utilities."""

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
):
    """Define a field."""
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
):
    """Define a dimension field."""
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
):
    """Define a coordinate field."""
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
):
    """Define an array field."""
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
