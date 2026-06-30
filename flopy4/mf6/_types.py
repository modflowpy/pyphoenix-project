"""Shared type definitions for flopy4.mf6 packages."""

from pathlib import Path
from typing import TypeAlias, Union

from numpy.typing import NDArray

try:
    import dask.array as da

    ArrayLike: TypeAlias = Union[NDArray, da.Array]
    """NDArray or dask Array — used for griddata and READARRAY period fields."""
except ImportError:
    ArrayLike: TypeAlias = NDArray  # type: ignore[misc, no-redef]


def _optional_path(v):
    """Converter for Optional[Path] attrs fields.

    Accepts None, str, or Path; returns None or Path.
    """
    if v is None:
        return None
    return Path(v) if not isinstance(v, Path) else v
