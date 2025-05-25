"""
Wrap `xattree` and `attrs` specification utilities.
These include field decorators and introspection functions.
"""

from attrs import NOTHING, Attribute
from xattree import array as xattree_array
from xattree import coord as xattree_coord
from xattree import dim as xattree_dim
from xattree import field as xattree_field
from xattree import fields_dict as xattree_fields_dict


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


def fields(cls) -> list[Attribute]:
    """Return an ordered list of fields for a component class."""
    return list(fields_dict(cls).values())


def fields_dict(cls) -> dict[str, Attribute]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is an `attrs.Attribute`.
    """
    fields = xattree_fields_dict(cls)
    return {k: v for k, v in fields.items()}
