from collections.abc import Mapping
from itertools import chain
from pathlib import Path
from typing import Annotated, Any, Optional, get_origin

import attrs
import numpy as np
from attr import Attribute, fields_dict
from beartype.claw import beartype_this_package
from beartype.vale import Is, IsAttr, IsInstance
from flopy.discretization.grid import Grid
from flopy.discretization.modeltime import ModelTime
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
    strict: bool = False,
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
    if value is None:
        if strict:
            raise ValueError(
                f"Component class '{type(self).__name__}' array "
                f"variable '{attr.name}' could not be resolved "
            )
        return None
    dims = attr.metadata.get("dims", None)
    if not dims:
        if strict:
            raise ValueError(
                f"Component class '{type(self).__name__}' array "
                f"variable '{attr.name}' needs 'dims' metadata"
            )
        return None
    shape = [find(tree or DataTree(), key=dim, default=dim) for dim in dims]
    shape = tuple(
        [
            (dim if isinstance(dim, int) else kwargs.pop(dim, dim))
            for dim in shape
        ]
    )
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        if strict:
            raise ValueError(
                f"Component class '{type(self).__name__}' array "
                f"variable '{attr.name}' failed dim resolution: "
                f"{', '.join(unresolved)}"
            )
        return None
    return reshape_array(value, shape)


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
    name = self.data.name
    spec = fields_dict(cls)

    # bind parent
    if parent:
        # try binding first by name
        parent_spec = fields_dict(type(parent))
        parent_var = parent_spec.get(name, None)
        if parent_var:
            assert parent_var.metadata.get("bind", False)
            setattr(parent, name, self)
        # TODO bind multipackages by type
        # parent_bindings = {
        #     n: v
        #     for n, v in parent_spec.items()
        #     if v.metadata.get("bind", False)
        # }
        # print(parent_bindings)
        if name in parent.data:
            parent.data.update({name: self.data})
        else:
            parent.data = parent.data.assign({name: self.data})
        self.data = parent.data[self.data.name]

        # bind grandparent
        grandparent = getattr(parent, "parent", None)
        if grandparent is not None:
            bind_tree(parent, parent=grandparent)

        self.parent = parent

    # bind children
    self.children = children
    for n, c in (children or {}).items():
        v = spec.get(n, None)
        if v and v.metadata.get("bind", False):
            self.data.update({n: c.data})
            setattr(self, n, c)
        bind_tree(c, parent=self)


def init_tree(
    self: _IsAttrs,
    name: Optional[str] = None,
    parent: Optional[_HasTree] = None,
    children: Optional[Mapping[str, _HasTree]] = None,
    **kwargs,
):
    """
    Initialize a data tree for a component class instance.

    Notes
    -----
    This method must run after the default `__init__()`.

    The tree is built from the class' `attrs` fields, i.e.
    spirited from the instance's `__dict__` into the tree,
    which is attached to the instance as `self.data`. The
    `__dict__` is empty after this method runs, and field
    access is proxied to the tree.

    The class cannot use slots for this to work.
    """

    cls = type(self)
    spec = fields_dict(cls)
    dimensions = set()
    array_vars = {}
    scalar_vars = {}
    array_vals = {}
    scalar_vals = {}
    components = {}
    children = children or {}

    for var in spec.values():
        bind = var.metadata.get("bind", False)
        if bind:
            components[var.name] = var
            continue
        dims = var.metadata.get("dims", None)
        if dims is None:
            scalar_vars[var.name] = var
            continue
        dimensions.update(dims)
        array_vars[var.name] = var

    def _yield_scalars(spec, vals):
        for var in spec.values():
            val = vals.pop(var.name, var.default)
            yield (var.name, val)

    scalar_vals = dict(
        list(_yield_scalars(spec=scalar_vars, vals=self.__dict__))
    )

    def _yield_arrays(spec, vals):
        for var in spec.values():
            dims = var.metadata["dims"]
            val = resolve_array(
                self,
                var,
                value=vals.pop(var.name, var.default),
                tree=parent.data.root if parent else None,
                **{**scalar_vals, **kwargs},
            )
            if val is not None:
                yield (var.name, (dims, val))

    array_vals = dict(list(_yield_arrays(spec=array_vars, vals=self.__dict__)))

    self.data = DataTree(
        Dataset(
            array_vals,
            attrs={
                n: v for n, v in scalar_vals.items() if n not in dimensions
            },
        ),
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

    if name == "data":
        raise AttributeError

    cls = type(self)
    spec = fields_dict(cls)
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
        value = (shape, value)
    bind = attr.metadata.get("bind", False)
    if bind:
        self.data = self.data.assign({attr.name: value.data})
        return value
    self.data.update({attr.name: value})


def component(maybe_cls: Optional[type[_IsAttrs]] = None) -> type[_Component]:
    """
    Attach a data tree to an `attrs` class instance, and use
    the data tree for attribute storage: intercept gets/sets
    such that the class continues to act like normal `attrs`
    classes, but attributes are proxied into the data tree.

    Notes
    -----
    For this to work, the `attrs` class cannot use slots.
    """

    def wrap(cls):
        init_self = cls.__init__
        spec = fields_dict(cls)

        def init(self, *args, **kwargs):
            name = kwargs.pop("name", None)
            children = kwargs.pop("children", None)
            parent = args[0] if args and any(args) else None

            # resolve dims from grid and time discretizations
            # get dims from spec
            dim_kwargs = {}
            dims_used = set(
                chain(*[var.metadata.get("dims", []) for var in spec.values()])
            )
            grid: Grid = kwargs.pop("grid", None)
            time: ModelTime = kwargs.pop("time", None)
            if grid:
                grid_dims = ["nlay", "nrow", "ncol", "nnodes"]
                for dim in grid_dims:
                    if dim in dims_used:
                        dim_kwargs[dim] = getattr(grid, dim)
            if time:
                time_dims = ["nper", "ntstp"]
                for dim in time_dims:
                    if dim in dims_used:
                        dim_kwargs[dim] = getattr(time, dim)

            # run the original __init__, then set up the tree
            init_self(self, **kwargs)
            init_tree(
                self, name=name, parent=parent, children=children, **dim_kwargs
            )

            # override attribute access
            cls.__getattr__ = getattribute

        cls.__init__ = init
        return cls

    if maybe_cls is None:
        return wrap

    return wrap(maybe_cls)
