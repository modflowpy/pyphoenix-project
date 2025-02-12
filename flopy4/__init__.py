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

_IsAttrs = Annotated[object, Is[lambda obj: attrs.has(type(obj))]]
"""Runtime-applied type hint for `attrs` based class instances."""

_HasTree = Annotated[object, IsAttr["data", IsInstance[DataTree]]]
"""Runtime-applied type hint for objects with a `DataTree` in `.data`."""

_Component = Annotated[
    object,
    (
        Is[lambda obj: attrs.has(type(obj))]
        & IsAttr["data", IsInstance[DataTree]]
    ),
]
"""
An `attrs`-based class with a `DataTree` in `.data`.
The minimal contract for component class instances.
"""


def get(
    tree: DataTree, key: str, default: Optional[Scalar] = None
) -> Optional[Scalar]:
    """
    Get a value with the given `name` from the given `tree`
    node. Look first in its variables, then dims, then attrs.
    If not found, return a `default`. Search is not recursive.
    """

    value = tree.get(key, None)
    if value is not None:
        if value.shape == ():
            return value.item()
        return value
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
    within its own `Dataset`, then depth-first from the root downwards.
    A set of search paths can be provided to look in before continuing
    with the unguided DFS. If a match is not found, return a `default`.
    """

    def _find_recursive(tree, key):
        key = key.strip()
        # this node first
        value = get(tree, key, None)
        if value is not None:
            return value
        # bfs over children
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
    self: _IsAttrs,
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
            (dim if isinstance(dim, int) else kwargs.pop(dim, dim))
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


def bind_tree(
    self: _Component,
    parent: _Component = None,
    children: Optional[Mapping[str, _Component]] = None,
):
    """
    Bind a given component to a parent component, linking the
    two components and their data trees. If the parent is not
    the tree's root, rebind it to recursively up to the root.

    Also attach any child components to the given component's
    data tree, as well as to any non-`attrs` attributes whose
    name matches a child's name.

    TODO: this is massively duplicative, since each component
    has a subtree of its own, next to the one its parent owns
    and in which its tree appears. need to have a single tree
    at the root, then each component's data is a view into it.
    """

    cls = type(self)

    if parent:
        parent_spec = fields_dict(type(parent))
        if self.data.name in parent_spec:
            setattr(parent, self.data.name, self)

        # TODO
        # parent_bindings = {
        #     k: v
        #     for k, v in parent_spec.items()
        #     if v.metadata.get("bind", False)
        # }

        parent.data = parent.data.assign({self.data.name: self.data})
        self.data = parent.data[self.data.name]
        grandparent = getattr(parent, "parent", None)
        if grandparent is not None:
            bind_tree(parent, grandparent)
        self.parent = parent
    self.children = children
    spec = fields_dict(type(self))
    for n, c in (children or {}).items():
        if n in spec:
            setattr(self, n, c)


def init_tree(
    self: _IsAttrs,
    name: Optional[str] = None,
    parent: Optional[_HasTree] = None,
    children: Optional[Mapping[str, _HasTree]] = None,
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
    arrays = {}
    scalars = {}
    children = children or {}

    # set scalars and arrays. filter array dims out
    # so they're not attached as both vars and dims.
    # also filter out subcomponents, just want vars.
    for attr in spec.values():
        bind = attr.metadata.get("bind", False)
        if bind:
            continue
        dims_ = attr.metadata.get("dims", None)
        if dims_ is None:
            scalars[attr.name] = attr
            continue
        dims.update(dims_)
        arrays[attr.name] = attr
    scalars = {k: self.__dict__.pop(k, v.default) for k, v in scalars.items()}
    for attr in arrays.values():
        dims_ = attr.metadata["dims"]
        value = resolve_array(
            self,
            attr,
            value=self.__dict__.pop(attr.name, attr.default),
            tree=parent.data.root if parent else None,
            **scalars,
        )
        data[attr.name] = (dims_, value)
    for k, v in scalars.items():
        data.attrs[k] = v

    self.data = DataTree(
        data,
        name=name or cls.__name__.lower(),
        children={n: c.data for n, c in children.items()},
    )
    bind_tree(self, parent=parent, children=children)


def getattribute(self: Any, name: str) -> Any:
    """
    Proxy `attrs` attribute access, returning values from
    an `xarray.DataTree` in `self.data`.

    Notes
    -----
    Overrides `__getattribute__` in classes fulfilling the
    `_Component` contract. But don't annotate `self` as a
    `_Component` because beartype use `__getattribute__`
    to evaluate the type hint, creating recursion.
    """
    cls = type(self)
    spec = fields_dict(cls)
    if name == "data":
        raise AttributeError
    tree = self.data
    var = spec.get(name, None)
    if var:
        value = get(tree, name, None)
        if value is not None:
            return value
    raise AttributeError


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
    if value is None or not hasattr(self, "data"):
        return value
    if get_origin(attr.type) in [list, np.ndarray]:
        shape = attr.metadata["dims"]
        value = resolve_array(self, attr, value)
        self.data[attr.name] = (shape, value)
    else:
        self.data[attr.name] = value
    # TODO run validation?


def component(cls: type[_IsAttrs]) -> type[_Component]:
    """
    Attach a data tree to an `attrs` class instance, and use
    the data tree for attribute storage: intercept gets/sets
    such that the class continues to act like normal `attrs`
    classes, but attributes are proxied into the data tree.

    Notes
    -----
    For this to work, the `attrs` class cannot use slots.
    """

    old_init = cls.__init__

    def _init(self, *args, **kwargs):
        name = kwargs.pop("name", None)
        parent = args[0] if args and any(args) else None
        children = kwargs.pop("children", None)
        old_init(self, **kwargs)
        init_tree(self, name=name, parent=parent, children=children)
        cls.__getattr__ = getattribute

    cls.__init__ = _init
    return cls
