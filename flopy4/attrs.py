from pathlib import Path
from typing import (
    Dict,
    Iterable,
    List,
    Optional,
    TypeVar,
    Union,
)

from attrs import NOTHING, Attribute, define, field, fields
from numpy.typing import ArrayLike
from pandas import DataFrame

# Core input data model. This enumerates the
# types FloPy accepts in input data contexts.

Scalar = Union[bool, int, float, str, Path]
Record = Dict[str, Union[Scalar, List[Scalar]]]
List = List[Union[Scalar, Record]]
Array = ArrayLike
Table = DataFrame
Param = Union[Scalar, Record, List, Array, Table]


# Wrap `attrs.field()` for input parameters.


def param(
    longname: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    optional: bool = False,
    default=NOTHING,
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
    itself or another nested context of parameters.
    """
    return {field.name: field for field in fields(cls)}


# Wrap `attrs.define()` for input contexts.


T = TypeVar("T")


def context(
    maybe_cls: Optional[type[T]] = None,
    *,
    frozen: bool = False,
    multi: bool = False,
):
    """
    Wrap `attrs.define()` for more opinionated input contexts.

    Notes
    -----
    Contexts are parameter containers and can be nested to an
    arbitrary depth.
    """

    def add_index(fields):
        return [
            Attribute.from_counting_attr(name="index", ca=field(), type=int),
            *fields,
        ]

    def wrap(cls):
        transformer = (lambda _, fields: add_index(fields)) if multi else None
        return define(
            cls,
            field_transformer=transformer,
            frozen=frozen,
            weakref_slot=True,
        )

    if maybe_cls is None:
        return wrap

    return wrap(maybe_cls)


def record(maybe_cls: Optional[type[T]] = None, *, frozen: bool = True):
    """
    Wrap `attrs.define()` for immutable records (tuples of parameters).

    Notes
    -----

    Records are frozen by default.

    A variadic record ends with a list. A `variadic` flag is attached
    to record classes via introspection at import time.
    """

    def add_variadic(cls, fields):
        last = fields[-1]
        variadic = False
        try:
            variadic = issubclass(last.type, Iterable)
        except:
            variadic = (
                hasattr(last.type, "__origin__")
                and last.type.__origin__ is list
            )
        setattr(cls, "variadic", variadic)
        return fields

    def wrap(cls):
        return define(
            cls,
            auto_attribs=True,
            field_transformer=add_variadic,
            frozen=frozen,
            weakref_slot=True,
        )

    if maybe_cls is None:
        return wrap

    return wrap(maybe_cls)
