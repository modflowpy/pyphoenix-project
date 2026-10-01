"""Shared type definitions for flopy4.mf6 packages."""

from collections.abc import Callable, Iterable
from datetime import datetime
from os import PathLike
from pathlib import PurePath
from typing import Any, Protocol, TypeAlias, TypeVar

import numpy as np

_DT = TypeVar("_DT", bound=np.generic, covariant=True)

Scalar: TypeAlias = bool | int | np.integer | float | np.floating | str | PurePath | datetime
"""A single, non-array value -- covers every leaf DFN scalar type
(including numpy scalar dtypes) plus PurePath/datetime for path- and
time-typed fields. Usable directly in `isinstance()` checks (PEP 604
unions support this natively)."""


class _ArrayLike(Protocol[_DT]):
    """Structural stand-in for "ndarray or duck array of this dtype".

    Matches anything exposing `.dtype`/`.shape` like `numpy.ndarray` does —
    `dask.array.Array`, and other duck arrays (sparse, cupy, xarray-backed,
    ...) — without enumerating specific libraries or importing them here.
    Used for griddata and READARRAY period fields, which may be dask-backed
    (see `codec/writer/filters.py`'s `array2chunks`, which streams
    dask-backed arrays without materializing them).
    """

    @property
    def dtype(self) -> np.dtype[_DT]: ...
    @property
    def shape(self) -> tuple[int, ...]: ...


IntArrayLike: TypeAlias = _ArrayLike[np.int64]
FloatArrayLike: TypeAlias = _ArrayLike[np.float64]


def _wrap(v) -> list:
    """A single value (a str or path is one value, not an iterable) as a
    one-element list, else the values as a list."""
    if isinstance(v, (str, bytes, PathLike)) or not isinstance(v, Iterable):
        return [v]
    return list(v)


def to_list(convert: Callable) -> Callable[[Any], list]:
    """attrs converter to a list, each element through `convert`."""
    return lambda v: [convert(x) for x in _wrap(v)]


def to_array(dtype) -> Callable[[Any], np.ndarray]:
    """attrs converter to a 1D array of `dtype`."""
    return lambda v: np.asarray(_wrap(v), dtype=dtype)
