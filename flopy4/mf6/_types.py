"""Shared type definitions for flopy4.mf6 packages."""

from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar

import numpy as np

_DT = TypeVar("_DT", bound=np.generic, covariant=True)


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


def _optional_path(v):
    """Converter for Optional[Path] attrs fields.

    Accepts None, str, or Path; returns None or Path.
    """
    if v is None:
        return None
    return Path(v) if not isinstance(v, Path) else v
