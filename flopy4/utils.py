from pathlib import Path
from typing import Any, Optional


def find_upper(s: str):
    """Return uppercase characters in a string."""
    for i in range(len(s)):
        if s[i].isupper():
            yield i


def flatten(l: Any):
    """Flatten lists or tuples."""
    if isinstance(l, list | tuple):
        for x in l:
            yield from flatten(x)
    else:
        yield l


def to_path(value: Any) -> Optional[Path]:
    """
    Convert a value to a Path if it has a value,
    otherwise return None.
    """
    return Path(value) if value else None
