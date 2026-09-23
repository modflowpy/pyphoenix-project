"""Shared type definitions for flopy4.mf6 packages."""

from datetime import datetime
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, runtime_checkable

import numpy as np

_DT = TypeVar("_DT", bound=np.generic, covariant=True)

Scalar: TypeAlias = bool | int | np.integer | float | np.floating | str | Path | datetime
"""A single, non-array value -- covers every leaf DFN scalar type
(including numpy scalar dtypes) plus Path/datetime for path- and
time-typed fields. Usable directly in `isinstance()` checks (PEP 604
unions support this natively)."""


@runtime_checkable
class _ArrayLike(Protocol[_DT]):
    """Structural stand-in for "ndarray or duck array of this dtype".

    Matches anything exposing `.dtype`/`.shape` like `numpy.ndarray` does —
    `dask.array.Array`, and other duck arrays (sparse, cupy, xarray-backed,
    ...) — without enumerating specific libraries or importing them here.
    Used for griddata and READARRAY period fields, which may be dask-backed
    (see `codec/writer/filters.py`'s `array2chunks`, which streams
    dask-backed arrays without materializing them).

    `@runtime_checkable` is required for pydantic (not needed under attrs,
    which never validated this annotation at all): under
    `arbitrary_types_allowed=True`, pydantic builds an `isinstance()`-based
    validator for any type it doesn't otherwise understand, which requires
    the protocol to support `isinstance()` at all -- confirmed empirically
    that schema-building itself fails with a `SchemaError` (not even a
    runtime `ValidationError`) without this decorator, even though the
    generic type parameter (`_DT`) is itself ignored by the resulting
    isinstance check either way, same as plain Python `Protocol` semantics.
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
