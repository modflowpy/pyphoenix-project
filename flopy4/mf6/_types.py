"""Shared type definitions for flopy4.mf6 packages."""

from collections.abc import Callable, Iterable
from datetime import datetime
from os import PathLike
from pathlib import Path, PurePath
from typing import Any, Protocol, TypeAlias, TypeVar

import attrs
import numpy as np
from numpy.typing import NDArray

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


@attrs.frozen
class TimeArraySeriesRef:
    """A period's array given by a time-array series, by its name, which
    MF6 interpolates in time: ``RECHARGE TIMEARRAYSERIES <name>``.

    This is the typed form. A plain name, ``recharge={0: "rchseries"}``, is
    also accepted at init and converted to this, but mypy rejects it: the
    conversion happens after init, not in a field converter.
    """

    name: str

    def __str__(self) -> str:
        return self.name


def _wrap(v) -> list:
    """A single value (a str or path is one value, not an iterable) as a
    one-element list, else the values as a list."""
    if isinstance(v, (str, bytes, PathLike)) or not isinstance(v, Iterable):
        return [v]
    return list(v)


def to_list(convert: Callable) -> Callable[[Any], list]:
    """attrs converter to a list, each element through `convert`."""
    return lambda v: [convert(x) for x in _wrap(v)]


def to_path_list(value: "str | PathLike | Iterable[str | PathLike] | None") -> list[Path] | None:
    """attrs converter to a list of paths, or None. A named function, not
    ``optional(to_list(Path))``, so mypy can read its argument type."""
    return None if value is None else [Path(x) for x in _wrap(value)]


def to_str_array(value: "str | Iterable[str] | None") -> NDArray[np.str_] | None:
    """attrs converter to a 1D string array (AUXILIARY's names), or None.
    A named function, not a converter factory, so mypy can read its
    argument type."""
    return None if value is None else np.asarray(_wrap(value), dtype=np.str_)


def _is_dask(x: Any) -> bool:
    return type(x).__module__.split(".")[0] == "dask"


def array_eq(a: Any, b: Any) -> bool:
    """Array-aware equality for component fields.

    - ``None`` equals only ``None``; dicts (e.g. time-array series) are
      compared key by key.
    - Shape and dtype must match, NaNs at the same position compare equal
      (float and complex dtypes only).
    - Dask arrays are never computed: they are equal only if shape, dtype,
      chunks and graph name match. A dask array never equals a numpy array.
    """
    if a is b:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, TimeArraySeriesRef) or isinstance(b, TimeArraySeriesRef):
        return a == b
    if isinstance(a, dict) or isinstance(b, dict):
        return (
            isinstance(a, dict)
            and isinstance(b, dict)
            and a.keys() == b.keys()
            and all(array_eq(a[k], b[k]) for k in a)
        )
    if _is_dask(a) or _is_dask(b):
        return (
            _is_dask(a)
            and _is_dask(b)
            and a.shape == b.shape
            and a.dtype == b.dtype
            and a.chunks == b.chunks
            and a.name == b.name
        )
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    return bool(np.array_equal(a, b, equal_nan=a.dtype.kind in "fc"))


ARRAY_EQ = attrs.cmp_using(eq=array_eq)
"""``eq=`` value for attrs fields holding arrays."""
