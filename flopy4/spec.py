"""
Generic pydantic-dataclass specification utilities.
"""

from typing import Any

from pydantic.dataclasses import is_pydantic_dataclass
from pydantic.fields import FieldInfo


def is_dataclass_instance(value: Any) -> bool:
    """True if `value` is an instance of a pydantic dataclass. Used
    wherever generic tree-walking code needs to tell a nested
    dataclass-typed value apart from a plain scalar/array leaf value."""
    return is_pydantic_dataclass(type(value))


def pydantic_fields(cls: type) -> dict[str, FieldInfo]:
    """A pydantic dataclass's fields, by name.

    Use this rather than `cls.__pydantic_fields__` directly: pydantic sets
    that attribute at runtime but doesn't declare it on the decorated
    class's type, so mypy only sees it after `is_pydantic_dataclass()`
    narrows `cls`.
    """
    if not is_pydantic_dataclass(cls):
        raise TypeError(f"{cls!r} is not a pydantic dataclass")
    return cls.__pydantic_fields__


def field_meta(finfo: FieldInfo) -> dict[str, Any]:
    """A field's flopy4 metadata (`block`, `shape`, ...), or `{}`.

    Stored in `json_schema_extra`, which pydantic types as a JSON dict or
    a callable; flopy4 only ever stores a dict there.
    """
    extra = finfo.json_schema_extra
    return extra if isinstance(extra, dict) else {}


def fields_dict(cls) -> dict[str, Any]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is a pydantic `FieldInfo`.
    Empty for anything that isn't a pydantic dataclass.
    """
    return dict(pydantic_fields(cls)) if is_pydantic_dataclass(cls) else {}
