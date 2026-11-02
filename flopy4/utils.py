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
    """An int if the string is one, else a float (see `fortran_float`)."""
    if "." in value or "e" in value or "E" in value:
        return fortran_float(value)
    try:
        return int(value)
    except ValueError:
        return fortran_float(value)


# A whole token that's a number, allowing Fortran `D` exponents (`1D-5`).
NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eEdD][+-]?\d+)?")


def number_or_text(value: Any) -> Any:
    """A token as a number if it reads as one, else as it is: for a value
    whose type allows either (a time series name or a number)."""
    if isinstance(value, str) and NUMBER.fullmatch(value):
        return parse_number(value)
    return value


def from_text(value: Any, t: Any) -> Any:
    """A token read from a file, converted to the type ``t``: the reader
    keeps tokens as text, since only the schema can tell ``1.50`` the
    number from ``1.50`` the name. Anything but text passes through.
    A union tries a ``Literal`` arm's words (in any case), then a number
    if an arm is numeric and the token reads as that arm's kind (an int
    arm alone takes only integers), else keeps the text.
    A type it doesn't know gets a number if the token reads as one."""
    if not isinstance(value, str):
        return value
    if isinstance(t, str):
        t = {"int": int, "float": float, "str": str, "bool": bool, "Path": Path}.get(t, t)
    origin = typing.get_origin(t)
    if origin is typing.Literal:
        return value.upper() if value.upper() in typing.get_args(t) else value
    if is_union(t):
        args = [a for a in typing.get_args(t) if a is not type(None)]
        if len(args) == 1:
            return from_text(value, args[0])
        words = {
            w for a in args if typing.get_origin(a) is typing.Literal for w in typing.get_args(a)
        }
        if value.upper() in words:
            return value.upper()
        numeric = [a for a in args if a in (int, float)]
        if numeric and NUMBER.fullmatch(value):
            if float in numeric:
                return parse_number(value) if int in numeric else fortran_float(value)
            if value.lstrip("+-").isdigit():
                return int(value)
        return value
    if t is int:
        try:
            return int(value)
        except ValueError:
            return int(fortran_float(value))
    if t is float:
        return fortran_float(value)
    if t is bool:
        return True
    if t is str:
        return value
    if t is Path:
        return Path(value)
    if t is Any or t is typing.Any or t is None:
        return number_or_text(value)
    return value


# A real with a signed exponent but no letter, e.g. ``1.0+1`` (= 10.0).
_BARE_EXPONENT = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+))([+-]\d+)")
# ``D`` exponents as ``E``, for `str.translate`.
D_EXPONENT = str.maketrans("dD", "ee")


def fortran_float(value: str) -> float:
    """A real as Fortran reads one: also with a ``D`` exponent, or a
    signed exponent with no letter (``1.0+1`` = 10.0)."""
    try:
        return float(value)
    except ValueError:
        pass
    if m := _BARE_EXPONENT.fullmatch(value):
        return float(f"{m[1]}e{m[2]}")
    try:
        return float(value.translate(D_EXPONENT))
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
