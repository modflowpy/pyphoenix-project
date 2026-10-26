import re
import types
import typing
from pathlib import Path
from typing import Any, Optional


def to_path(value: Any) -> Optional[Path]:
    """
    Try to convert a value to a Path if it's not None, otherwise return None.
    """
    return Path(value) if value else None


def empty_if_none(value: Any) -> dict:
    """A dict for None, else the value as is."""
    return {} if value is None else value


def parse_number(value: str) -> int | float:
    """Parse a string into int or float based on its content."""
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        else:
            return int(value)
    except ValueError:
        return float(value)


# A real with a signed exponent but no letter, e.g. ``1.0+1`` (= 10.0).
_BARE_EXPONENT = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+))([+-]\d+)")
_D_EXPONENT = str.maketrans("dD", "ee")


def fortran_float(value: str) -> float:
    """A real as Fortran reads one (an ``F`` edit descriptor's input), as
    MF6 reads every real: also with a ``D`` exponent, or a signed exponent
    with no letter (``1.0+1`` = 10.0, as Fortran writes a three-digit
    exponent: ``0.1234+100``)."""
    try:
        return float(value)
    except ValueError:
        pass
    if m := _BARE_EXPONENT.fullmatch(value):
        return float(f"{m[1]}e{m[2]}")
    try:
        return float(value.translate(_D_EXPONENT))
    except ValueError:
        raise ValueError(f"could not convert string to float: {value!r}") from None


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
