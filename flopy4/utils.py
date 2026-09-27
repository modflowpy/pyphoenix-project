import types
import typing
from pathlib import Path
from typing import Any, Optional


def to_path(value: Any) -> Optional[Path]:
    """
    Try to convert a value to a Path if it's not None, otherwise return None.
    """
    return Path(value) if value else None


def parse_number(value: str) -> int | float:
    """Parse a string into int or float based on its content."""
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        else:
            return int(value)
    except ValueError:
        return float(value)


def is_union(obj):
    origin = typing.get_origin(obj)
    return origin is typing.Union or (hasattr(types, "UnionType") and origin is types.UnionType)


def unwrap_optional(tp):
    """T for Optional[T], else tp unchanged (a multi-arm Union included)."""
    if is_union(tp):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp
