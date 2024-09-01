from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar, overload

from attrs import Attribute, define, field, fields
from numpy.typing import ArrayLike
from pandas import DataFrame

# Core input parameter model.

Scalar = bool | int | float | str | Path
Record = Dict[str, Scalar]
List = List[Scalar | Record]
Array = ArrayLike
Table = DataFrame
Param = Scalar | Record | List | Array | Table


# Wrap `attrs.field()` for parameters


def param(
    longname: Optional[str] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    optional: bool = True,
    default=None,
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
    Each parameter is returned as a `attrs.Attribute`.

    Notes
    -----
    Wraps `attrs.fields()`. A parameter can be a value
    itself or another nested context of parameters.
    """
    return {field.name: field for field in fields(cls)}


# Wrap `attrs.define()` for contexts.


T = TypeVar("T")


@overload
def context(*, frozen=False, multi=False) -> Callable[[type[T]], type[T]]: ...


@overload
def context(maybe_cls: type[T]) -> type[T]: ...


def add_index(cls, fields):
    return [
        Attribute.from_counting_attr(name="index", ca=field(), type=int),
        *fields,
    ]


def context(
    maybe_cls: type[T] | None = None,
    *,
    frozen: bool = False,
    multi: bool = False,
):
    """
    Wrap `attrs.define()` for more opinionated input contexts.
    """

    def wrap(cls):
        return define(
            cls,
            field_transformer=add_index if multi else None,
            frozen=frozen,
            weakref_slot=True,
        )

    if maybe_cls is None:
        return wrap

    return wrap(maybe_cls)
