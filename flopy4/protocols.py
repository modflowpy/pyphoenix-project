"""
Runtime-checkable protocols for the explicit dataclass<->xarray conversion
layer (`flopy4/dataclass_xarray.py`, `flopy4/mixins.py`).
"""

from typing import Protocol, runtime_checkable

import xarray as xr


@runtime_checkable
class DatasetConvertible(Protocol):
    """A leaf object: convertible to/from a flat `xr.Dataset`.

    For dataclasses with no dataclass-typed child fields (e.g. a DFN leaf
    package with only scalar/array fields).
    """

    def to_xarray(self) -> xr.Dataset: ...

    @classmethod
    def from_dataset(cls, dataset: xr.Dataset) -> "DatasetConvertible": ...


@runtime_checkable
class DataTreeConvertible(Protocol):
    """An internal-node object: convertible to/from a hierarchical
    `xr.DataTree`.

    For dataclasses with one or more dataclass-typed child fields (single,
    list, or dict), whose own scalar/array fields form the tree's root
    dataset and whose children form named child nodes.
    """

    def to_xarray(self) -> xr.DataTree: ...

    @classmethod
    def from_datatree(cls, tree: xr.DataTree) -> "DataTreeConvertible": ...
