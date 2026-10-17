"""Grids, time, and readers of MF6's output. Each loads on first use, since
they import flopy and xugrid, which loading and writing input don't need."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flopy4.mf6.utils import grid, time
    from flopy4.mf6.utils.cbc_reader import open_cbc
    from flopy4.mf6.utils.heads_reader import open_hds
    from flopy4.mf6.utils.netcdf_postprocess import (
        postprocess_mesh_nc,
        postprocess_structured_nc,
    )

_LAZY = {
    "grid": ("flopy4.mf6.utils.grid", None),
    "time": ("flopy4.mf6.utils.time", None),
    "open_cbc": ("flopy4.mf6.utils.cbc_reader", "open_cbc"),
    "open_hds": ("flopy4.mf6.utils.heads_reader", "open_hds"),
    "postprocess_mesh_nc": ("flopy4.mf6.utils.netcdf_postprocess", "postprocess_mesh_nc"),
    "postprocess_structured_nc": (
        "flopy4.mf6.utils.netcdf_postprocess",
        "postprocess_structured_nc",
    ),
}

__all__ = [
    "open_hds",
    "open_cbc",
    "postprocess_mesh_nc",
    "postprocess_structured_nc",
    "grid",
    "time",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attr = _LAZY[name]
    value = import_module(module) if attr is None else getattr(import_module(module), attr)
    globals()[name] = value
    return value
