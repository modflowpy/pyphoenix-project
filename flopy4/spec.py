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


def is_array(f: Attribute) -> bool:
    """Whether a field is an array (its DFN type, which the field functions
    in `flopy4.mf6.spec` record in its metadata)."""
    return f.metadata.get("type") == "array"


def reference_names(value):
    """A reference field's value as names, in the field's own shape (a
    list, or one value); names given as strings, and None, stay."""
    if isinstance(value, list):
        return [reference_names(v) for v in value]
    return value if value is None or isinstance(value, str) else value.name


def referenced(value) -> list:
    """The components a reference field's value refers to (not names)."""
    values = value if isinstance(value, list) else [value]
    return [v for v in values if v is not None and not isinstance(v, str)]


def is_reference(f: Attribute) -> bool:
    """Whether a field refers to components it doesn't own (e.g. the models
    a solution solves). Such a field isn't a child field: walkers that
    follow children skip it, and its components keep their own parents."""
    return bool(f.metadata.get("reference"))
