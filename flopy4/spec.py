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
