from pathlib import Path
from typing import Any, Optional


def to_path(value: Any) -> Optional[Path]:
    """
    Convert a value to a Path if it has a value, otherwise return None.
    """
    return Path(value) if value else None
