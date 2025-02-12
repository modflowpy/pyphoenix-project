from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Optional, get_origin

import attrs
import numpy as np
from attr import Attribute, fields_dict
from beartype.claw import beartype_this_package
from beartype.vale import Is, IsAttr, IsInstance
from numpy.typing import ArrayLike, NDArray
from xarray import Dataset, DataTree

from flopy4.utils import reshape_array

beartype_this_package()


Scalar = bool | int | float | str | Path
"""A scalar value."""

_HasAttrs = Annotated[object, Is[lambda obj: attrs.has(type(obj))]]
"""Runtime-applied type hint for `attrs` based class instances."""

_HasData = Annotated[object, IsAttr["data", IsInstance[DataTree]]]
"""Runtime-applied type hint for objects with a `DataTree` in `.data`."""

_Component = Annotated[
    object,
    (
        Is[lambda obj: attrs.has(type(obj))]
        & IsAttr["data", IsInstance[DataTree]]
    ),
]
"""
An `attrs`-based class with a `DataTree` in `.data.
The minimal contract for component class instances.
"""


def get(
    tree: DataTree, key: str, default: Optional[Scalar] = None
) -> Optional[Scalar]:
    """
    Get a value with the given `name` from the given `tree`.
    Look first in the tree's variables, then its dimensions,
    then in `attrs`. If not found, return `None`.

    This function searches this node only.
    """

    value = tree.get(key, None)
    if value is not None:
        return value.item()
    value = tree.dims.get(key, None)
    if value is not None:
        return value
    value = tree.attrs.get(key, None)
    if value is not None:
        return value
    return default


def find(
    tree: DataTree,
    key: str,
    default: Optional[Scalar] = None,
) -> Optional[Scalar]:
    """
    Search for a value with the given `key` in the given `tree`, first
    within itself, then from the root downwards in breadth-first order.

    A set of search paths can be provided to look in before continuing
    with the unguided BFS.

    If the value is not found, return the `default`.
    """

    def _find_recursive(tree, key):
        key = key.strip()

        # look in current node first
        value = get(tree, key, None)
        if value is not None:
            return value

        # look in children
        for node in tree.children.values():
            value = get(node, key, None)
            if value is not None:
                return value
            result = _find_recursive(node, key)
            if result is not None:
                return result
        return None

    return _find_recursive(tree.root, key) or default


def resolve_array(
    self: _HasAttrs,
    attr: Attribute,
    value: ArrayLike,
    tree: DataTree = None,
    **kwargs,
) -> Optional[NDArray]:
    """
    Resolve an array-like value to the given variable's expected shape.
    If the value is a collection, check if the shape matches. If scalar,
    broadcast it to the expected shape.

    The shape is expected as a tuple of dimension names under key "dims"
    in `attr.metadata`.

    Dimensions can be resolved from an optional `xarray.DataTree` or can
    be passed in as kwargs. If a dimension cannot be resolved or found,
    a `ValueError` is raised.
    """
    value = value or attr.default
    dims = attr.metadata.get("dims", None)
    if not dims:
        raise ValueError(
            f"Component class '{type(self).__name__}' array "
            f"variable '{attr.name}' needs 'dims' metadata"
        )
    shape = [find(tree or DataTree(), key=dim, default=dim) for dim in dims]
    shape = tuple(
        [
            (dim if isinstance(dim, int) else kwargs.get(dim, dim))
            for dim in shape
        ]
    )
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        raise ValueError(
            f"Component class '{type(self).__name__}' failed "
            f"to resolve dimensions: {', '.join(unresolved)}"
        )
    value = reshape_array(value, shape)
    if value.shape == ():
        raise ValueError(
            f"Failed to resolve array '{attr.name}', "
            f"are you sure these dimensions exist? "
            f"{','.join(dims)}"
        )
    return value


def bind_tree(self: _HasData, parent: _HasData):
    """
    Bind a child component to a parent, linking their trees.
    If the parent isn't the root, rebind it to recursively
    upwards to the root.

    TODO: this is massively duplicative, since each component
    has a subtree of its own, next to the one its parent owns
    and in which its tree appears. need to have a single tree
    at the root, then each component's data is a view into it.
    """
    parent.data = parent.data.assign({self.data.name: self.data})
    self.data = parent.data[self.data.name]
    grandparent = getattr(parent, "parent", None)
    if grandparent is not None:
        bind_tree(parent, grandparent)


def init_tree(
    self: _HasAttrs,
    name: Optional[str] = None,
    parent: Optional[_HasData] = None,
    children: Optional[Mapping[str, _HasData]] = None,
):
    """
    Initialize a data tree for a component class instance.
    The tree is built from the class' `attrs` fields, i.e.
    spirited from the instance's `__dict__` into the tree,
    which is attached to the instance as `self.data`. The
    class cannot use slots for this to work.

    Notes
    -----
    This method must run after the default `__init__()`.
    """
    cls = type(self)
    spec = fields_dict(cls)
    data = Dataset()
    dims = set()

    # set arrays, then scalars. filter array dims out
    # on the first pass thru, while we set up arrays,
    # so they're not attached as both vars and dims.
    for attr in spec.values():
        dims_ = attr.metadata.get("dims", None)
        if dims_ is None:
            continue
        dims.update(dims_)
        value = resolve_array(
            self,
            attr,
            value=self.__dict__.pop(attr.name),
            tree=parent.data.root if parent else None,
            **self.__dict__,
        )
        data[attr.name] = (dims_, value)
    for attr in spec.values():
        if attr.name in data or attr.name in dims:
            continue
        data[attr.name] = self.__dict__.pop(attr.name, attr.default)

    # create tree
    self.data = DataTree(
        data,
        name=name or cls.__name__.lower(),
        children={
            n: c.data for n, c in (children or {}).items() if c is not None
        },
    )

    # bind tree
    if parent is not None:
        self.parent = parent
        bind_tree(self, parent)


def getattribute(self: Any, name: str) -> Any:
    """
    Proxy `attrs` attribute access, returning values from
    an `xarray.DataTree` in `self.data`.

    Notes
    -----
    Overrides `__getattribute__` in classes fulfilling the
    `Component` contract. But we don't annotate `self` as a
    `Component` because beartype will use `__getattribute__`
    to resolve the type hint, which will create recursion.
    """
    cls = type(self)
    spec = fields_dict(cls)
    try:
        tree = self.data
    except:
        return super(cls, self).__getattribute__(name)
    if name in spec:
        value = get(tree, name, None)
        if value is not None:
            return value
    return super(cls, self).__getattribute__(name)


def setattribute(self: _Component, attr: Attribute, value: Any):
    """
    Intercept values sent to an `attrs` attribute, and
    set corresponding variables in an `xarray.DataTree`
    in `self.data`.

    Notes
    -----
    For the `on_setattr` hook in `_Component` classes.
    """
    cls = type(self)
    spec = fields_dict(cls)
    if attr.name not in spec:
        raise AttributeError(f"{cls.__name__} has no attribute {attr.name}")
    if value is None:
        return
    data = getattr(self, "data", None)
    if data is None:
        return value
    if get_origin(attr.type) in [list, np.ndarray]:
        shape = attr.metadata["dims"]
        value = resolve_array(self, attr, value)
        self.data[attr.name] = (shape, value)
    else:
        self.data[attr.name] = value
    # TODO run validation?


def component(cls: type[_HasAttrs]) -> type[_Component]:
    """
    Attach a data tree to an `attrs` class instance, and use
    the data tree for attribute storage: intercept gets/sets
    such that the class continues to act like normal `attrs`
    classes, but attributes are proxied into the data tree.

    Notes
    -----
    For this to work, the `attrs` class may not use slots.
    """

    old_init = cls.__init__

    def init(self, *args, **kwargs):
        name = kwargs.pop("name", None)
        parent = args[0] if args and any(args) else None
        children = kwargs.pop("children", None)
        old_init(self, **kwargs)
        init_tree(self, name=name, parent=parent, children=children)

    cls.__getattribute__ = getattribute
    cls.__init__ = init
    return cls
