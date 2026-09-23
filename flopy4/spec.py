"""
Generic pydantic-dataclass specification utilities.
"""

from typing import Any

from pydantic.dataclasses import is_pydantic_dataclass


def is_dataclass_instance(value: Any) -> bool:
    """True if `value` is an instance of a pydantic dataclass. Used
    wherever generic tree-walking code needs to tell a nested
    dataclass-typed value apart from a plain scalar/array leaf value."""
    return is_pydantic_dataclass(type(value))


def fields_dict(cls) -> dict[str, Any]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is a pydantic `FieldInfo`.
    """
    return dict(getattr(cls, "__pydantic_fields__", {}))
