"""The ``grid`` accessor on xarray arrays and datasets, registered when
``flopy4.mf6`` is imported. Its methods load the grid utilities on first
use, since they import flopy and xugrid."""

import xarray as xr


class _GridAccessor:
    def __init__(self, obj):
        self._obj = obj

    def sel(self, indexers=None, method=None, tolerance=None, drop=False, **indexers_kwargs):
        """Select as ``sel`` does, but also by elevation ``z``:
        ``da.grid.sel(x=..., y=..., z=...)`` is ``sel(da, ...)`` (see
        ``flopy4.mf6.utils.grid``). z picks the cell containing it in each
        vertical column left by the other indexers, raising ``KeyError``
        where there's none. x/y are in the grid's own frame; for world
        coordinates, use ``sel_world``."""
        from flopy4.mf6.utils.grid import sel

        return sel(
            self._obj, indexers, method=method, tolerance=tolerance, drop=drop, **indexers_kwargs
        )

    def sel_world(self, x, y, z=None, **kwargs):
        """Select by world coordinates: ``da.grid.sel_world(x, y)`` is
        ``sel_world(da, x, y)`` (see ``flopy4.mf6.utils.grid``). On a
        rotated structured grid, x/y are local, so this converts to them
        through the ``projection`` coordinate; otherwise it's just ``sel``.
        ``kwargs`` go to ``sel``, e.g. ``method="nearest"``. For
        point-wise selection, pass x and y (and z) as DataArrays sharing a
        dim. With ``z``, the cell containing that elevation is selected
        from the vertical column."""
        from flopy4.mf6.utils.grid import sel_world

        return sel_world(self._obj, x, y, z, **kwargs)

    def sel_z(self, z, **kwargs):
        """Select the cell containing elevation ``z`` in each vertical
        column: ``sel_z(da, z)`` (see ``flopy4.mf6.utils.vertical``). On
        a whole grid, a horizontal slice at that elevation, NaN where
        there's no cell."""
        from flopy4.mf6.utils.vertical import sel_z

        return sel_z(self._obj, z, **kwargs)

    def mask_z(self, zmin=None, zmax=None, **kwargs):
        """Which cells are in the elevation range ``zmin``–``zmax``:
        ``mask_z(da, zmin, zmax)`` (see ``flopy4.mf6.utils.vertical``),
        for ``da.where(mask)``."""
        from flopy4.mf6.utils.vertical import mask_z

        return mask_z(self._obj, zmin, zmax, **kwargs)


@xr.register_dataarray_accessor("grid")
class GridDataArrayAccessor(_GridAccessor):
    pass


@xr.register_dataset_accessor("grid")
class GridDatasetAccessor(_GridAccessor):
    pass
