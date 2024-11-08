"""Enumerates supported input variable types."""

from os import PathLike
from typing import (
    Iterable,
    Tuple,
    Union,
)

from numpy.typing import ArrayLike

Scalar = Union[bool, int, float, str]
"""A scalar input variable."""


Path = PathLike
"""A file path input variable."""


Array = ArrayLike
"""An array input variable."""


Record = Tuple[Union[Scalar, "Record"], ...]
"""A record input variable."""


Table = Iterable["Record"]
"""A table input variable."""


Variable = Union[Scalar, Array, Table, Record]
"""An input variable."""
