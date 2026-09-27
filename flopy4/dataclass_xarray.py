"""
Generic conversion between `pydantic.dataclasses.dataclass`-decorated
classes and `xarray` `Dataset`/`DataTree` objects.

Reads only two things per field: its own instance value (via `getattr`)
and, for array values, the field's own `shape` metadata (a tuple of
dimension-name strings -- the same convention `flopy4.mf6.spec.field()`/
`array()` already tag leaf DFN packages with).

Child detection (which fields hold nested dataclass instances, as opposed
to plain scalar/array leaf values) is done by inspecting instance *values*
with `is_dataclass_instance()` when building a tree (mirrors the field-walk
+ `isinstance` pattern `flopy4.dimensions` already established), and by
inspecting field *type annotations* when reconstructing one from a tree
(a bare `DataTree` node carries no back-pointer to the field it came
from, so reconstruction has no values to inspect yet).

InitVars (e.g. `Component.dims`) aren't stored, so they're skipped.

Known limitation: a field literally named `parent` or `_parent`
is always excluded (see `_RESERVED_FIELD_NAMES` for why each one is
there). No real DFN field uses any of these names today; if one ever
did, it would need a different name or a second, explicit exclusion
mechanism here.

Known limitation: a "dict"-kind child field (e.g. `Simulation.models`)
can't be reconstructed from a plain `DataTree` alone -- the dict's real
keys are caller-given names with no recoverable relationship to the
field name, unlike "list"-kind's positional `f"{field_name}{index}"`
convention. Namefile binding rows carry this information separately;
reconstruction should use that rather than guessing here. Likewise, a
"list"-kind field whose element type is itself a `Union` of dataclasses
(e.g. `list[Union[Chd, Chdg]]`) isn't resolved to a concrete arm.
"""

import types
from typing import Any, Union, get_args, get_origin

import numpy as np
import xarray as xr
from pydantic.dataclasses import is_pydantic_dataclass

from flopy4.spec import field_meta, is_dataclass_instance, pydantic_fields

# Field names to always skip, regardless of what they hold. `parent` and `_parent`
# (Output.parent, Component._parent -- see their own docstrings) are
# back-reference fields whose runtime values would otherwise look
# structurally like real leaf/child data and cause infinite recursion
# (parent -> child -> same parent) if walked, so they're excluded by
# name rather than by (unreliable) type-checking.
_RESERVED_FIELD_NAMES = frozenset({"parent", "_parent"})


def _leaf_fields_and_children(
    obj,
) -> "tuple[dict[str, tuple], dict[str, Any], dict[str, dict | list]]":
    """Split `obj`'s pydantic fields by instance value into:
    - leaf fields: ``{name: (FieldInfo, value)}``
    - single-child fields: ``{name: child_obj}``
    - collection-child fields: ``{name: {key: child_obj}}`` or ``{name: [child_obj, ...]}``
    """
    leaves: "dict[str, tuple]" = {}
    single_children: "dict[str, Any]" = {}
    collection_children: "dict[str, dict | list]" = {}
    for name, finfo in pydantic_fields(type(obj)).items():
        if name in _RESERVED_FIELD_NAMES or finfo.init_var:
            continue
        # A private field (leading underscore) exposed under an alias --
        # e.g. Context._workspace/alias="workspace" -- is keyed by that
        # alias here, not its real (private) name, matching the public API
        # the field is actually meant to be read/written through (same
        # convention structure.py/unstructure.py already use).
        exposed = finfo.alias if (finfo.alias and name.startswith("_")) else name
        value = getattr(obj, name, None)
        if value is None:
            continue
        if is_dataclass_instance(value):
            single_children[exposed] = value
        elif (
            isinstance(value, dict)
            and value
            and all(is_dataclass_instance(v) for v in value.values())
        ):
            collection_children[exposed] = value
        elif (
            isinstance(value, (list, tuple))
            and value
            and all(is_dataclass_instance(v) for v in value)
        ):
            collection_children[exposed] = list(value)
        else:
            leaves[exposed] = (finfo, value)
    return leaves, single_children, collection_children


def _array_dims(finfo: Any, name: str, ndim: int) -> tuple:
    meta = field_meta(finfo)
    shape_meta = meta.get("shape") if isinstance(meta, dict) else None
    if shape_meta and len(shape_meta) == ndim:
        return tuple(shape_meta)
    return tuple(f"{name}_dim{i}" for i in range(ndim))


def dataclass_to_dataset(obj) -> xr.Dataset:
    """Flatten `obj`'s own scalar/array fields into a flat `xr.Dataset`.

    Dataclass-typed child fields are skipped here -- see
    `dataclass_to_datatree()` for those. A `numpy.ndarray`-valued field becomes
    a data variable, with dims named from its `shape` metadata when
    present (falling back to generic per-axis names otherwise); everything
    else becomes a dataset-level attr.
    """
    leaves, _, _ = _leaf_fields_and_children(obj)
    data_vars = {}
    ds_attrs = {}
    for name, (finfo, value) in leaves.items():
        meta = field_meta(finfo)
        has_shape = isinstance(meta, dict) and meta.get("shape")
        if isinstance(value, xr.DataArray):
            data_vars[name] = value
        elif isinstance(value, np.ndarray):
            data_vars[name] = xr.DataArray(value, dims=_array_dims(finfo, name, value.ndim))
        elif has_shape and isinstance(value, (list, tuple)):
            # A shape-tagged field whose value hasn't (yet) been coerced to
            # a real ndarray -- e.g. assigned directly post-construction,
            # bypassing whatever coercion __post_init__ normally does. The
            # field's own metadata says it's array-shaped regardless of the
            # value's current runtime type, so honor that rather than
            # silently dropping it to a dataset-level attr.
            arr = np.asarray(value)
            data_vars[name] = xr.DataArray(arr, dims=_array_dims(finfo, name, arr.ndim))
        else:
            ds_attrs[name] = value
    return xr.Dataset(data_vars, attrs=ds_attrs)


def _init_field_names(cls: type) -> set:
    # init=False fields (e.g. Dis's derived nodes/ncpl/nvert) have no
    # __init__ parameter -- they're recomputed by __post_init__, not
    # round-tripped through the constructor. Exposed under each field's
    # alias when it has one and is itself private (leading underscore),
    # matching _leaf_fields_and_children's own exposed-name convention --
    # a dataset produced from Context.workspace (backed by the private
    # _workspace/alias="workspace" field) is keyed "workspace", so lookups
    # here must match that key, not the private real name.
    return {
        (f.alias if (f.alias and name.startswith("_")) else name)
        for name, f in pydantic_fields(cls).items()
        if f.init is not False
    }


def _leaf_kwargs_from_dataset(cls: type, dataset: xr.Dataset) -> dict:
    field_names = _init_field_names(cls)
    kwargs: dict = {}
    for name, da in dataset.data_vars.items():
        if name in field_names:
            kwargs[name] = da.values
    for name, value in dataset.attrs.items():
        if name in field_names:
            kwargs[name] = value
    return kwargs


def dataset_to_dataclass(cls: type, dataset: xr.Dataset):
    """Construct a `cls` instance from an `xr.Dataset` shaped like
    `dataclass_to_dataset()`'s output: data variables and dataset-level attrs
    are matched to `cls`'s fields by name and passed as constructor
    kwargs. Unmatched dataset keys are ignored; fields with no matching
    key fall back to `cls`'s own default.
    """
    return cls(**_leaf_kwargs_from_dataset(cls, dataset))


def dataclass_to_datatree(obj, _ancestors: frozenset = frozenset()) -> xr.DataTree:
    """Recursively convert `obj` into an `xr.DataTree`.

    `obj`'s own leaf fields become the root dataset (`dataclass_to_dataset()`).
    Each dataclass-typed child field becomes a named child node
    (recursively converted the same way); a dict- or list-of-children
    field expands to one child node per entry, named by its dict key or
    ``f"{field_name}{index}"`` respectively.

    A back-reference field pointing back up the tree (e.g. `Component`'s
    own `_parent` attribute) is detected by object identity against
    the current recursion's ancestor chain and skipped rather than
    followed -- otherwise a parent/child pair recurses infinitely. A
    non-ancestor object appearing more than once in the graph is not
    affected; only actual cycles are.
    """
    _, single_children, collection_children = _leaf_fields_and_children(obj)
    ancestors = _ancestors | {id(obj)}
    children: "dict[str, xr.DataTree]" = {}
    for name, child in single_children.items():
        if id(child) in ancestors:
            continue
        children[name] = dataclass_to_datatree(child, ancestors)
    for field_name, collection in collection_children.items():
        items = collection.items() if isinstance(collection, dict) else enumerate(collection)
        for key, child in items:
            if id(child) in ancestors:
                continue
            node_name = str(key) if isinstance(collection, dict) else f"{field_name}{key}"
            children[node_name] = dataclass_to_datatree(child, ancestors)
    return xr.DataTree(dataset=dataclass_to_dataset(obj), children=children)


def _unwrap_optional(tp):
    if get_origin(tp) in (Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _child_field_spec(finfo: Any) -> "tuple[str, type] | None":
    """If `finfo`'s declared type holds dataclass-typed child/children,
    return ``(kind, element_type)`` where `kind` is ``"one"``, ``"list"``,
    or ``"dict"``. Returns `None` for plain scalar/array fields, an
    unresolvable annotation, or a collection whose element type isn't a
    plain dataclass (e.g. a `Union` of arms -- see module docstring).
    """
    tp = finfo.annotation
    if tp is None:
        return None
    tp = _unwrap_optional(tp)
    origin = get_origin(tp)
    if origin is None:
        return ("one", tp) if isinstance(tp, type) and _is_pydantic_type(tp) else None
    args = get_args(tp)
    if origin in (list, tuple) and len(args) >= 1 and _is_pydantic_type(args[0]):
        return ("list", args[0])
    if origin is dict and len(args) == 2 and _is_pydantic_type(args[1]):
        return ("dict", args[1])
    return None


def _is_pydantic_type(tp: Any) -> bool:
    return isinstance(tp, type) and is_pydantic_dataclass(tp)


def child_field_candidates(finfo: Any) -> "tuple[str, tuple[type, ...]] | None":
    """Like `_child_field_spec`, but resolves *every* concrete
    dataclass-decorated candidate class for the field, including each arm
    of a `Union` of dataclasses in the collection-element (or bare "only")
    position -- e.g. `list[Union[Chd, Chdg]]`, needed to disambiguate an
    MF6 base/grid-array package pair sharing one namefile ftype (see
    `converter/binding.py`'s `component_ftype()`). Returns `None` under
    the same conditions as `_child_field_spec`: an unresolvable
    annotation, or a type/collection-element that resolves to no
    dataclass-decorated candidate at all.

    Kind is `"only"`, `"list"`, or `"dict"`, matching the child-collection
    vocabulary used throughout `flopy4/mf6/converter/`.
    """
    tp = finfo.annotation
    if tp is None:
        return None
    tp = _unwrap_optional(tp)
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        # Optional[Union[A, B]] -- _unwrap_optional only collapses a
        # single non-None arm, so a genuine multi-arm Union survives here.
        candidates = tuple(a for a in get_args(tp) if a is not type(None) and _is_pydantic_type(a))
        return ("only", candidates) if candidates else None
    if origin is None:
        return ("only", (tp,)) if _is_pydantic_type(tp) else None
    args = get_args(tp)
    if origin in (list, tuple) and len(args) >= 1:
        elem = args[0]
        if get_origin(elem) in (Union, types.UnionType):
            candidates = tuple(a for a in get_args(elem) if _is_pydantic_type(a))
            return ("list", candidates) if candidates else None
        return ("list", (elem,)) if _is_pydantic_type(elem) else None
    if origin is dict and len(args) == 2 and _is_pydantic_type(args[1]):
        return ("dict", (args[1],))
    return None


def datatree_to_dataclass(cls: type, tree: xr.DataTree):
    """Construct a `cls` instance from an `xr.DataTree` produced by
    `dataclass_to_datatree()`.

    The root dataset supplies `cls`'s own scalar/array field kwargs (see
    `dataset_to_dataclass()`). Each dataclass-typed child field is matched to
    child node(s) by name and recursively reconstructed against the
    field's own declared element type. See the module docstring for the
    "dict"-kind and `Union`-element limitations.
    """
    kwargs = _leaf_kwargs_from_dataset(cls, tree.dataset)
    for name, finfo in pydantic_fields(cls).items():
        if finfo.init is False:
            continue
        spec = _child_field_spec(finfo)
        if spec is None:
            continue
        kind, elem_type = spec
        if kind == "one":
            if name in tree.children:
                kwargs[name] = datatree_to_dataclass(elem_type, tree.children[name])
        elif kind == "list":
            items = []
            i = 0
            while f"{name}{i}" in tree.children:
                items.append(datatree_to_dataclass(elem_type, tree.children[f"{name}{i}"]))
                i += 1
            if items:
                kwargs[name] = items
        # "dict"-kind: not reconstructable from node name alone -- see
        # module docstring. Left unset; a caller with namefile binding
        # rows can fill it in separately.
    return cls(**kwargs)
