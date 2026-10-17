"""Checks against classes of modules flopy4 imports only when they're used
(flopy, xugrid), made without importing them."""

import sys
from typing import Any


def isinstance_of(value: Any, module: str, name: str) -> bool:
    """Whether ``value`` is an instance of the class ``name`` in ``module``.
    If the module hasn't been imported, nothing can be one, so this doesn't
    import it."""
    cls = getattr(sys.modules.get(module), name, None)
    return cls is not None and isinstance(value, cls)
