"""
Wrap `attrs` specification utilities.
"""

from attrs import Attribute
from attrs import fields_dict as attrs_fields_dict


def fields_dict(cls) -> dict[str, Attribute]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is an `attrs.Attribute`.
    """
    return dict(attrs_fields_dict(cls))


def array_shape(f: Attribute) -> tuple[str, ...]:
    """An array field's shape, the dimensions counting its values; ``()``
    for any other field."""
    return tuple(f.metadata.get("shape") or ()) if f.metadata.get("type") == "array" else ()


def list_dim(f: Attribute) -> str | None:
    """The dimension counting a list field's rows, exact (``"nper"``) or a
    bound (``"<=maxbound"``); None for any other field, or a list with no
    dimension."""
    if f.metadata.get("type") != "list":
        return None
    shape = f.metadata.get("shape") or ()
    return shape[0] if shape else None
