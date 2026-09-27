"""
Mixins implementing the `DatasetConvertible`/`DataTreeConvertible`
protocols (`flopy4/protocols.py`) on top of the generic dataclass<->xarray
conversion functions (`flopy4/dataclass_xarray.py`).
"""

import xarray as xr

from flopy4.dataclass_xarray import (
    dataclass_to_dataset,
    dataclass_to_datatree,
    dataset_to_dataclass,
    datatree_to_dataclass,
)


class DatasetConvertibleMixin:
    """Mixin for leaf dataclasses with no dataclass-typed child fields."""

    def to_xarray(self) -> xr.Dataset:
        return dataclass_to_dataset(self)

    @classmethod
    def from_dataset(cls, dataset: xr.Dataset):
        return dataset_to_dataclass(cls, dataset)


class DataTreeConvertibleMixin:
    """Mixin for internal-node dataclasses with one or more
    dataclass-typed child fields."""

    def to_xarray(self) -> xr.DataTree:
        return dataclass_to_datatree(self)

    @classmethod
    def from_datatree(cls, tree: xr.DataTree):
        return datatree_to_dataclass(cls, tree)
