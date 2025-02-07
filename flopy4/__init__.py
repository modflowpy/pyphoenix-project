from typing import Any, Optional, get_origin

import numpy as np
from attr import Attribute, fields_dict
from numpy.typing import ArrayLike, NDArray
from xarray import Dataset, DataTree


def _parse_dim_names(shape: str) -> tuple[str, ...]:
    return tuple(
        [
            dim.strip()
            for dim in shape.strip()
            .replace("(", "")
            .replace(")", "")
            .split(",")
            if any(dim)
        ]
    )


def _try_resolve_dim(data: Optional[DataTree], name: str) -> int | str:
    name = name.strip()
    if data is None:
        return name
    value = data.get(name, None)
    if value is not None:
        return value.item()
    root = data.root
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
                pass
    return name


def _try_resolve_shape(data: DataTree, attr: Attribute) -> tuple[int | str]:
    shape = attr.metadata.get("shape", None)
    if shape is None:
        raise ValueError(f"Array {attr.name} missing shape metadata")
    shape = [_try_resolve_dim(data, dim) for dim in _parse_dim_names(shape)]
    return shape


def _reshape_array(value: ArrayLike, shape: tuple[int]) -> Optional[NDArray]:
    value = np.array(value)
    if value.shape == ():
        return np.full(shape, value.item())
    elif value.shape != shape:
        raise ValueError(
            f"Shape mismatch, got {value.shape}, expected {shape}"
        )
    return value


def resolve_array(
    self, attr: Attribute, value: Optional[ArrayLike]
) -> Optional[NDArray]:
    """
    Resolve an array-like value to a numpy array with the correct shape.
    The shape is determined by the shape metadata of the attribute, and
    the dimensions are resolved by looking up the corresponding values
    in the data tree.
    """
    if value is None:
        return None
    shape = _try_resolve_shape(self.data, attr)
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        raise ValueError(
            f"Class '{type(self).__name__}' "
            f"failed to resolve dims: {', '.join(unresolved)}"
        )
    return _reshape_array(value, shape)


def _bind_tree(self, parent):
    parent.data = parent.data.assign({self.data.name: self.data})
    self.data = parent.data[self.data.name]
    grandparent = getattr(parent, "parent", None)
    if grandparent is not None:
        _bind_tree(parent, grandparent)


def init_tree(self, parent=None, **kwargs):
    """
    Initialize a data tree for a component instance.
    """
    cls = type(self)
    cls_name = cls.__name__.lower()
    spec = fields_dict(cls)
    data = Dataset()
    dims = set()

    # add arrays
    for name, attr in spec.items():
        value = kwargs.get(name, attr.default)
        shape = attr.metadata.get("shape", None)
        if shape is not None:
            dim_names = _parse_dim_names(shape)
            shape = [
                _try_resolve_dim(parent.data.root if parent else None, dim)
                for dim in dim_names
            ]
            shape = tuple(
                [
                    (dim if isinstance(dim, int) else kwargs.get(dim, dim))
                    for dim in shape
                ]
            )
            unresolved = [dim for dim in shape if not isinstance(dim, int)]
            if any(unresolved):
                raise ValueError(
                    f"Class '{cls_name}' "
                    f"failed to resolve dims: {', '.join(unresolved)}"
                )
            dims.update(dim_names)
            value = _reshape_array(value, shape)
            if value.shape == ():
                raise ValueError(
                    f"Failed to resolve array '{name}', "
                    f"make sure these dimensions exist: "
                    f"{','.join(dims)}"
                )
            data[name] = (dim_names, value)

    # add scalars
    for name, value in spec.items():
        if name in data or name in dims:
            continue
        value = kwargs.get(name, attr.default)
        data[name] = value

    self.data = DataTree(data, name=cls_name)
    if parent is not None:
        self.parent = parent
        _bind_tree(self, parent)


def getattribute(self, name: str) -> Any:
    """Override `__getattribute__` to proxy attribute access."""
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
    """Hook for setting attribute values."""
    cls = type(self)
    spec = fields_dict(cls)
    if attr.name not in spec:
        raise AttributeError(f"{cls.__name__} has no attribute {attr.name}")
    if value is None:
        return
    self.data[attr.name] = (
        (
            _parse_dim_names(attr.metadata["shape"]),
            resolve_array(self, attr, value),
        )
        if get_origin(attr.type) in [list, np.ndarray]
        else value
    )
    # TODO run validation?


def component(cls):
    """
    Decorator for component classes.

    This decorator adds a data tree to the class instance, on
    top of the existing attributes. The data tree is used to
    store both scalars and arrays. Attributes proxy the tree.
    """
    cls.__getattribute__ = getattribute
    return cls
