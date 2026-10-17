"""The ``mf6`` accessor on xarray arrays and datasets, registered when
``flopy4.mf6`` is imported. Its methods load the grid utilities on first
use, since they import flopy and xugrid."""

import xarray as xr


class _MF6Accessor:
    def __init__(self, obj):
        self._obj = obj

    def sel_world(self, x, y, **kwargs):
        """Select by world coordinates: ``da.mf6.sel_world(x, y)`` is
        ``sel_world(da, x, y)`` (see ``flopy4.mf6.utils.grid``). On a
        rotated structured grid, x/y are local, so this converts to them
        through the ``projection`` coordinate; otherwise it's just ``sel``.
        ``kwargs`` go to ``sel``, e.g. ``method="nearest"``. For
        point-wise selection, pass x and y as DataArrays sharing a dim."""
        from flopy4.mf6.utils.grid import sel_world

        return sel_world(self._obj, x, y, **kwargs)


@xr.register_dataarray_accessor("mf6")
class MF6DataArrayAccessor(_MF6Accessor):
    pass


@xr.register_dataset_accessor("mf6")
class MF6DatasetAccessor(_MF6Accessor):
    pass
