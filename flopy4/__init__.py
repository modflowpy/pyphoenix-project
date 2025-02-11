from pathlib import Path
from typing import Any, Optional, get_origin

import numpy as np
from attr import Attribute, fields_dict
from beartype.claw import beartype_this_package
from numpy.typing import ArrayLike, NDArray
from xarray import Dataset, DataTree

from flopy4.utils import reshape_array

beartype_this_package()


Scalar = bool | int | float | str | Path


def resolve(
    tree: Optional[DataTree], name: str, default=None
) -> Optional[Scalar]:
    name = name.strip()
    if tree is None:
        return default
    value = tree.get(name, None)
    if value is not None:
        return value.item()
    root = tree.root
    paths = [
        "tdis",
        "dis",
        "gwf/dis",
    ]
    for path in paths:
        try:
            key = f"{path}/{name}"
            return root[key].item()
        except:
            try:
                return root[path].dims[name]
            except:
                try:
                    return root[path].attrs[name]
                except:
                    pass
    return default


def resolve_array(
    self: Any,
    attr: Attribute,
    value: Optional[ArrayLike] = None,
    tree: DataTree = None,
    **kwargs,
) -> Optional[NDArray]:
    """
    Resolve an array-like value to the given variable's expected shape.
    If the value is a collection, check if the shape matches. If scalar,
    broadcast it to the expected shape.
    """
    if value is None:
        value = attr.default
    shape = attr.metadata.get("shape", None)
    if shape is None:
        raise ValueError(f"Array variable {attr.name} missing shape metadata")
    dim_names = shape
    shape = [resolve(tree, name=dim, default=dim) for dim in shape]
    shape = tuple(
        [
            (dim if isinstance(dim, int) else kwargs.get(dim, dim))
            for dim in shape
        ]
    )
    missing = [dim for dim in shape if not isinstance(dim, int)]
    if any(missing):
        raise ValueError(
            f"Class '{type(self).__name__}' "
            f"failed to resolve dims: {', '.join(missing)}"
        )
    value = reshape_array(value, shape)
    if value.shape == ():
        raise ValueError(
            f"Failed to resolve array '{attr.name}', "
            f"are you sure these dimensions exist? "
            f"{','.join(dim_names)}"
        )
    return value


def bind_tree(self: Any, parent: Any):
    """
    Bind a child component to a parent component, linking their data trees.
    """
    parent.data = parent.data.assign({self.data.name: self.data})
    self.data = parent.data[self.data.name]
    grandparent = getattr(parent, "parent", None)
    if grandparent is not None:
        bind_tree(parent, grandparent)


def init_tree(self, parent=None, children=None, **kwargs):
    """
    Initialize a data tree for a component.

    TODO: no need to pass kwargs in explicitly? just run
    the attrs-generated initializer method then move the
    contents of `__dict__` into the xarray store here...
    """
    cls = type(self)
    cls_name = cls.__name__.lower()
    spec = fields_dict(cls)
    data = Dataset()
    dims = set()

    # set arrays, then scalars. filter array dims out
    # on the first pass thru, while we set up arrays,
    # so they're not duplicated as both vars and dims.
    for name, attr in spec.items():
        shape = attr.metadata.get("shape", None)
        if shape is None:
            continue
        dims.update(shape)
        value = resolve_array(
            self,
            attr,
            value=None,
            tree=parent.data.root if parent else None,
            **kwargs,
        )
        data[name] = (shape, value)
    for name, value in spec.items():
        if name in data or name in dims:
            continue
        value = kwargs.get(name, attr.default)
        data[name] = value

    # create this node
    self.data = DataTree(
        data,
        name=cls_name,
        children={n: c for n, c in (children or {}).items() if c is not None},
    )

    # bind to parent tree
    if parent is not None:
        self.parent = parent
        bind_tree(self, parent)


def getattribute(self, name: str) -> Any:
    """
    Proxy `attrs` attribute access, returning values from
    an `xarray.DataTree` in `self.data`. Meant to override
    an `attrs`-based class' `__getattribute__` method.
    """
    cls = type(self)
    spec = fields_dict(cls)
    if name in spec:
        value = self.data.get(name, None)
        if value is not None:
            return value
        value = self.data.dims.get(name, None)
        if value is not None:
            return value
        value = self.data.attrs.get(name, None)
        if value is not None:
            return value
    return super(cls, self).__getattribute__(name)


def setattribute(self, attr: Attribute, value: Any):
    """
    Intercept values sent to an `attrs` attribute, and
    set corresponding variables in an `xarray.DataTree`
    in `self.data`. Meant to be called by `on_setattr`.
    """
    cls = type(self)
    spec = fields_dict(cls)
    if attr.name not in spec:
        raise AttributeError(f"{cls.__name__} has no attribute {attr.name}")
    if value is None:
        return
    if get_origin(attr.type) in [list, np.ndarray]:
        shape = attr.metadata["shape"]
        value = resolve_array(self, attr, value)
        self.data[attr.name] = (shape, value)
    else:
        self.data[attr.name] = value

    # TODO run validation?


def component(cls):
    """
    Attach a data tree to an `attrs` class instance, and use
    the data tree for attribute storage: intercept gets/sets
    such that the class continues to act like normal `attrs`
    classes, but attributes are proxied into the data tree.

    TODO: wrap `__init__` and call `init_tree` here, instead
    of making decorated classes do it, and just shift fields
    from `__dict__` into the data tree, deleting them after.

    The `attrs` class must have `slots=False` for it to work!
    """

    cls.__getattribute__ = getattribute
    return cls
