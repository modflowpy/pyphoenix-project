"""Enumerates supported input variable types."""

from pathlib import Path
from typing import (
    Iterable,
    Tuple,
    Union,
)

from numpy.typing import ArrayLike

Scalar = Union[bool, int, float, str, Path]
"""A scalar input variable."""


Array = ArrayLike
"""An array input variable"""


Table = Iterable["Record"]
"""A table input variable."""


Record = Tuple[Union[Scalar, "Record"], ...]
"""A record input variable."""


Variable = Union[Scalar, Array, Table, Record]
"""An input variable."""
