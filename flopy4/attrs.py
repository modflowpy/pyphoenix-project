from pathlib import Path
from typing import (
    Any,
    Optional,
    TypeVar,
    Union,
)

import attr
from attrs import NOTHING, asdict, define, field, fields
from cattrs import structure
from numpy.typing import ArrayLike
from pandas import DataFrame

# Enumerate the primitive types to support.
# This is just for reference, not meant to
# be definitive, exclusive, or exhaustive.

Scalar = Union[bool, int, float, str, Path]
"""A scalar input parameter."""


Array = ArrayLike
"""An array input parameter"""


Table = DataFrame
"""A table input parameter."""


Param = Union[Scalar, Array, Table]
"""An input parameter."""


# Wrap `attrs.field()` for input parameters.


def param(
    longname: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    optional: bool = False,
    default=NOTHING,
    alias=None,
    metadata=None,
    validator=None,
    converter=None,
):
    """
    Define a program input parameter. Wraps `attrs.field()`
    with a few extra metadata properties.
    """
    metadata = metadata or {}
    metadata["longname"] = longname
    metadata["description"] = description
    metadata["deprecated"] = deprecated
    metadata["optional"] = optional
    return field(
        default=default,
        validator=validator,
        repr=True,
        eq=True,
        order=False,
        hash=False,
        init=True,
        alias=alias,
        metadata=metadata,
        converter=converter,
    )


def params(cls):
    """
    Return a dictionary of the class' input parameters.
    Each parameter is returned as an `attrs.Attribute`.

    Notes
    -----
    Wraps `attrs.fields()`. A parameter can be a value
    itself or another nested context of parameters. We
    eschew the traditional `get_...()` naming in favor
    of `params()` in the spirit of `attrs.fields()`.
    """
    return {field.name: field for field in fields(cls)}


# Wrap `attrs.define()` for input contexts.


T = TypeVar("T")


def context(
    maybe_cls: Optional[type[T]] = None,
    *,
    auto_attribs: bool = True,
    frozen: bool = False,
):
    """
    Wrap `attrs.define()` for more opinionated input contexts.

    Notes
    -----
    Input contexts may be nested to an arbitrary depth.

    Contexts can be made immutable with `frozen=True`.
    """

    def from_dict(cls, d: dict):
        """Convert the dictionary to a context."""
        return structure(d, cls)

    def to_dict(self):
        """Convert the context to a dictionary."""
        return asdict(self, recurse=True)

    def wrap(cls):
        setattr(cls, "from_dict", classmethod(from_dict))
        setattr(cls, "to_dict", to_dict)
        return define(
            cls,
            auto_attribs=auto_attribs,
            frozen=frozen,
            slots=False,
            weakref_slot=True,
        )

    if maybe_cls is None:
        return wrap

    return wrap(maybe_cls)


# Utilities


def is_attrs(cls: type) -> bool:
    """Determines whether the given class is `attrs`-based."""

    return hasattr(cls, "__attrs_attrs__")


def is_frozen(cls: type) -> bool:
    """
    Determines whether the `attrs`-based class is frozen (i.e. immutable).

    Notes
    -----
    The class *must* be `attrs`-based, otherwise `TypeError` is raised.

    The way to check this may change in the future. See:
        - https://github.com/python-attrs/attrs/issues/853
        - https://github.com/python-attrs/attrs/issues/602
    """

    return cls.__setattr__ == attr._make._frozen_setattrs


def to_path(value: Any) -> Optional[Path]:
    """Try to convert the value to a `Path`."""
    if value is None:
        return None
    try:
        return Path(value).expanduser()
    except:
        raise ValueError(f"Can't convert value to Path: {value}")
