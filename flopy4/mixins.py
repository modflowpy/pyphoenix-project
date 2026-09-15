"""
Mixins implementing the `DatasetConvertible`/`DataTreeConvertible`
protocols (`flopy4/protocols.py`) on top of the generic attrs<->xarray
conversion functions (`flopy4/attrs_xarray.py`).
"""

import xarray as xr

from flopy4.attrs_xarray import (
    attrs_to_dataset,
    attrs_to_datatree,
    dataset_to_attrs,
    datatree_to_attrs,
)


class DatasetConvertibleMixin:
    """Mixin for leaf attrs classes with no attrs-typed child fields."""

    def to_xarray(self) -> xr.Dataset:
        return attrs_to_dataset(self)

    @classmethod
    def from_dataset(cls, dataset: xr.Dataset):
        return dataset_to_attrs(cls, dataset)


class DataTreeConvertibleMixin:
    """Mixin for internal-node attrs classes with one or more attrs-typed
    child fields."""

    def to_xarray(self) -> xr.DataTree:
        return attrs_to_datatree(self)

    @classmethod
    def from_datatree(cls, tree: xr.DataTree):
        return datatree_to_attrs(cls, tree)
