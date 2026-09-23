"""Tests for the generic attrs<->xarray conversion layer
(flopy4/attrs_xarray.py, flopy4/protocols.py, flopy4/mixins.py).

Uses synthetic attrs classes to validate the conversion functions in
isolation, plus one round-trip against a real leaf MF6 package (Dis) to
confirm it also works unmodified on an actual generated class.
"""

from typing import Optional

import numpy as np
import xarray as xr
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

from flopy4.attrs_xarray import (
    attrs_to_dataset,
    attrs_to_datatree,
    dataset_to_attrs,
    datatree_to_attrs,
)
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.spec import field as mf6_field
from flopy4.mixins import DatasetConvertibleMixin, DataTreeConvertibleMixin
from flopy4.protocols import DatasetConvertible, DataTreeConvertible

_CFG = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


@dataclass(config=_CFG)
class Leaf(DatasetConvertibleMixin):
    """A leaf class with only scalar/array fields, no children."""

    name: str = "leaf"
    value: float = 1.0
    # Deliberately not named "dims"/"parent"/"_parent" -- flopy4.attrs_xarray
    # always excludes those (see its module docstring); no real DFN field
    # uses them either.
    values: Optional[np.ndarray] = mf6_field(default=None, shape=("nlay",))


@dataclass(config=_CFG)
class OnlyChild(DatasetConvertibleMixin):
    label: str = "child"


@dataclass(config=_CFG)
class ListChild(DatasetConvertibleMixin):
    idx: int = 0


@dataclass(config=_CFG)
class DictChild(DatasetConvertibleMixin):
    key: str = "k"


@dataclass(config=_CFG)
class Node(DataTreeConvertibleMixin):
    """An internal-node class with all three child-field kinds."""

    title: str = "node"
    only: Optional[OnlyChild] = None
    items: list[ListChild] = Field(default_factory=list)
    mapping: dict[str, DictChild] = Field(default_factory=dict)


def test_leaf_scalar_and_array_round_trip():
    leaf = Leaf(name="a", value=2.5, values=np.array([1.0, 2.0, 3.0]))
    ds = attrs_to_dataset(leaf)
    assert isinstance(ds, xr.Dataset)
    assert ds.attrs["name"] == "a"
    assert ds.attrs["value"] == 2.5
    assert list(ds["values"].dims) == ["nlay"]
    np.testing.assert_array_equal(ds["values"].values, [1.0, 2.0, 3.0])

    rebuilt = dataset_to_attrs(Leaf, ds)
    assert rebuilt.name == "a"
    assert rebuilt.value == 2.5
    np.testing.assert_array_equal(rebuilt.values, [1.0, 2.0, 3.0])


def test_leaf_mixin_to_xarray_and_from_dataset():
    leaf = Leaf(name="b", value=3.0)
    ds = leaf.to_xarray()
    assert isinstance(leaf, DatasetConvertible)
    rebuilt = Leaf.from_dataset(ds)
    assert rebuilt.name == "b"
    assert rebuilt.value == 3.0


def test_node_single_child_round_trip():
    node = Node(title="root", only=OnlyChild(label="x"))
    tree = attrs_to_datatree(node)
    assert isinstance(tree, xr.DataTree)
    assert "only" in tree.children
    assert tree.dataset.attrs["title"] == "root"

    rebuilt = datatree_to_attrs(Node, tree)
    assert rebuilt.title == "root"
    assert isinstance(rebuilt.only, OnlyChild)
    assert rebuilt.only.label == "x"


def test_node_list_children_round_trip():
    node = Node(items=[ListChild(idx=0), ListChild(idx=1), ListChild(idx=2)])
    tree = attrs_to_datatree(node)
    assert "items0" in tree.children
    assert "items1" in tree.children
    assert "items2" in tree.children

    rebuilt = datatree_to_attrs(Node, tree)
    assert [c.idx for c in rebuilt.items] == [0, 1, 2]


def test_node_dict_children_not_reconstructed():
    """Documented limitation: dict-kind children round-trip into the tree
    (by their real dict key) but can't be recovered back into the dict
    field from the tree alone -- see flopy4/attrs_xarray.py's module docstring.
    """
    node = Node(mapping={"foo": DictChild(key="foo"), "bar": DictChild(key="bar")})
    tree = attrs_to_datatree(node)
    assert "foo" in tree.children
    assert "bar" in tree.children

    rebuilt = datatree_to_attrs(Node, tree)
    assert rebuilt.mapping == {}


def test_node_mixin_to_xarray_and_from_datatree():
    node = Node(title="root2", only=OnlyChild(label="y"))
    tree = node.to_xarray()
    assert isinstance(node, DataTreeConvertible)
    rebuilt = Node.from_datatree(tree)
    assert rebuilt.title == "root2"
    assert rebuilt.only.label == "y"


def test_empty_node_has_no_children():
    node = Node()
    tree = attrs_to_datatree(node)
    assert dict(tree.children) == {}


def test_dis_leaf_round_trip_real_mf6_class():
    """Dis has no attrs-typed children when ncf is unset, so it's a real
    (not synthetic) example of a DatasetConvertible-shaped leaf class."""
    dis = Dis(nlay=2, nrow=3, ncol=4)
    ds = attrs_to_dataset(dis)
    assert ds.attrs["nlay"] == 2
    assert ds.attrs["nrow"] == 3
    assert ds.attrs["ncol"] == 4
    assert dict(ds["delr"].sizes) == {"ncol": 4}
    assert dict(ds["botm"].sizes) == {"nodes": 24}

    rebuilt = dataset_to_attrs(Dis, ds)
    assert rebuilt.nlay == 2
    assert rebuilt.nrow == 3
    assert rebuilt.ncol == 4
    np.testing.assert_array_equal(rebuilt.delr, dis.delr)
    np.testing.assert_array_equal(rebuilt.botm, dis.botm)
