from pathlib import Path
from typing import Any, Optional

import numpy as np
from numpy.typing import ArrayLike, NDArray


def to_path(value: Any) -> Optional[Path]:
    """
    Convert a value to a Path if it has a value, otherwise return None.
    """
    return Path(value) if value else None


def reshape_array(value: ArrayLike, shape: tuple[int]) -> Optional[NDArray]:
    """
    If the `ArrayLike` is iterable, make sure it's the given shape.
    If it's a scalar, broadcast it to the given shape.
    """
    value = np.array(value)
    if value.shape == ():
        return np.full(shape, value.item())
    if value.shape != shape:
        raise ValueError(
            f"Shape mismatch, got {value.shape}, expected {shape}"
        )
    return value
