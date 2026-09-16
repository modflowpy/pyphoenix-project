from abc import ABC
from collections.abc import MutableMapping
from os import PathLike
from pathlib import Path
from typing import Any, ClassVar, Optional

import attrs
from attrs import fields

from flopy4.dimensions import DimensionResolverMixin
from flopy4.mf6.constants import MF6
from flopy4.mf6.spec import field, fields_dict
from flopy4.mf6.write_context import WriteContext
from flopy4.uio import IO, Loader, Writer

FNAMES: "dict[str, type[Component]]" = {}
"""MF6 component name (e.g. 'gwf-dis') -> component class."""

FTYPES: "dict[str, type[Component]]" = {}
"""MF6 component ftype (e.g. 'gwf-dis6') -> component class."""


def _prefix(dfn_name: str) -> "str | None":
    prefix, sep, _ = dfn_name.partition("-")
    return prefix if sep else None


def _qualify(name: str, prefix: "str | None") -> str:
    return f"{prefix}-{name}" if prefix is not None else name


def get_fnames() -> "dict[str, type[Component]]":
    """Get a map of MF6 component name (e.g. 'gwf-dis') to component class."""
    return FNAMES


def get_ftypes() -> "dict[str, type[Component]]":
    """Get a map of MF6 component ftype (e.g. 'gwf-dis6') to component class."""
    if not FTYPES:
        from collections import defaultdict

        from flopy4.mf6.converter.binding import component_ftype

        by_token: "dict[str, list[type[Component]]]" = defaultdict(list)
        for cls in set(FNAMES.values()):
            by_token[component_ftype(cls).lower()].append(cls)

        for token, classes in by_token.items():
            if len(classes) == 1:
                FTYPES[token] = classes[0]
            else:
                for cls in classes:
                    FTYPES[_qualify(token, _prefix(cls.dfn_name))] = cls
    return FTYPES


def get_ftype(token: str, prefix: "str | None" = None) -> "type[Component] | None":
    """Look up a single ftype token (e.g. 'dis6') in get_ftypes()."""
    ftypes = get_ftypes()
    token = token.lower()
    if prefix is not None and (cls := ftypes.get(f"{prefix}-{token}")) is not None:
        return cls
    return ftypes.get(token)


def _is_default_child_name(child: "Component") -> bool:
    """Whether `child`'s current `.name` is still at its class-name
    default (see `Component.name`'s own field docstring), i.e. no
    explicit name was ever given."""
    return child.name == type(child).__name__.lower()  # type: ignore[attr-defined]


def _resolve_child_name(used: "set[str]", kind: str, field_name: str, child: "Component") -> str:
    """Resolve the name `child` should be attached under (stored as its
    own `.name`), given the set of names already claimed by any of the
    parent's other children (`used`).

    An explicitly-given name sticks as-is, raising on a collision. An
    unnamed "only"-kind child gets the field's own name; an unnamed
    "list"-kind child gets `f"{field_name}{i}"`, grouped by field, not
    the child's own concrete class -- including for a base/grid-array
    field pair like
    `chd: list[Union[Chd, Chdg]]` sharing one sequence, since both arms
    share one real MF6 namefile ftype (see `converter/binding.py`'s
    `component_ftype()`). "dict"-kind isn't handled here -- its name is
    the mapping key itself, resolved by the caller.
    """
    if kind not in ("only", "list"):
        raise TypeError(f"Bad child collection kind '{kind}'")
    if not _is_default_child_name(child):
        if child.name in used:  # type: ignore[attr-defined]
            raise ValueError(
                f"Child name '{child.name}' collides with an existing child "  # type: ignore[attr-defined]
                "on the same parent."
            )
        return child.name  # type: ignore[attr-defined]
    if kind == "only":
        return field_name
    i = 0
    while f"{field_name}{i}" in used:
        i += 1
    return f"{field_name}{i}"


def _find_child_field(parent_cls: type, child_cls: type) -> "tuple[Any, str] | None":
    """Find the single field on `parent_cls` that accepts `child_cls` as a
    child, by type annotation (`child_field_candidates()`).

    Returns `(field, kind)`, or `None` if no field matches. Raises
    `TypeError` if more than one field matches (ambiguous).
    """
    from flopy4.attrs_xarray import child_field_candidates

    matches = []
    for f in fields(parent_cls):  # type: ignore[arg-type]
        spec = child_field_candidates(f)
        if spec is None:
            continue
        kind, candidates = spec
        if any(issubclass(child_cls, c) for c in candidates):
            matches.append((f, kind))
    if not matches:
        return None
    if len(matches) > 1:
        names = ", ".join(f.name for f, _ in matches)
        raise TypeError(
            f"Class '{parent_cls.__name__}' has multiple fields of type "
            f"'{child_cls.__name__}' ({names}); can't bind."
        )
    return matches[0]


# kw_only=True necessary so we can define optional fields here
# and required fields in subclasses. attrs complains otherwise
@attrs.define(kw_only=True, slots=False)
class Component(DimensionResolverMixin, ABC, MutableMapping):
    """
    Base class for MF6 components.

    Notes
    -----
    Component inherits from DimensionRegistryMixin to provide dimension
    resolution capabilities to all MF6 components.
    """

    dfn_name: ClassVar[str] = ""
    """The component's canonical DFN name (e.g. 'gwf-ic'), set by subclasses
    that are registered in FNAMES/FTYPES -- see the FNAMES docstring above."""

    _load = IO(Loader)  # type: ignore
    _write = IO(Writer)  # type: ignore

    filename: str | None = field(default=None)
    """The name of the component's input file."""

    name: str = field(
        default=attrs.Factory(lambda self: type(self).__name__.lower(), takes_self=True)
    )
    """The component's own identity/tag name. Computed per-instance from
    the *actual* runtime class (`takes_self=True`), not whichever class in
    the hierarchy happens to declare this field -- so a `Package` leaf
    (e.g. `Ic`, never separately subclassed for this field) still gets
    "ic", not "package". Overridden explicitly by `_resolve_child_name()`/
    `_attach_to_parent_field()` when a component is attached as a named
    child; otherwise this default stands."""

    _parent: Any = field(default=None, repr=False, eq=False)
    """Parent back-reference -- source of truth for "who is this
    component's parent", top-down (`Gwf(dis=Dis(...))`) and bottom-up
    (`Dis(parent=gwf)`) alike. Leading underscore triggers attrs' private-
    attribute convention, so the constructor keyword stays `parent=` even
    though the field is `_parent`. Typed `Any` so `child_field_candidates()`
    (type-annotation based) doesn't mistake it for a real child field.

    Populated by `_set_child_parents()` (top-down) and
    `_attach_to_parent_field()` (bottom-up), and kept current by
    `parent`'s setter below. Excluded by name from `to_dict()`'s
    `attrs.asdict()` recursion (alongside the unrelated `Output.parent`)
    since a live `.parent` would otherwise be a reference cycle.
    """

    dims: dict = field(default=attrs.Factory(dict), repr=False, eq=False)
    """Accepts `dims=` at construction (e.g. `Ic(dims={"nodes": 900})`)
    for API-compatibility with existing call sites. Read directly via
    `self.__dict__.get("dims")` by `Package.__attrs_post_init__` for
    griddata broadcasting -- not resolved/consumed by anything at the
    `Component` level itself."""

    @property
    def parent(self) -> "Component | None":
        """This component's parent, if attached (`None` otherwise).

        Just `self._parent` -- this property exists so `.parent` reads
        *and* writes (see the setter below) work under one name, instead
        of a write-only `parent=` constructor kwarg and a separately-named
        `._parent` for reads.
        """
        return self._parent

    @parent.setter
    def parent(self, value: "Component | None") -> None:
        """Attach this component to a new parent, or detach it if `value`
        is `None`.

        If already attached elsewhere, detaches from the old parent's
        field first (`del old[self.name]`), then attaches to the new one
        via `_attach_to_parent_field()` -- the same logic construction-time
        bottom-up attach (`Ic(parent=gwf)`) uses, including its naming
        rule: an explicitly-set `.name` is kept as long as it doesn't
        collide with a sibling already on the new parent, otherwise a
        fresh default name is resolved there.
        """
        if value is not None and not isinstance(value, Component):
            raise TypeError(f"parent must be a Component or None, got {type(value).__name__}")
        old = self._parent
        if old is value:
            return
        if old is not None:
            del old[self.name]  # type: ignore[attr-defined]
        self._parent = None
        if value is not None:
            self._parent = value
            self._attach_to_parent_field(value)

    @property
    def _children(self) -> "dict[str, Component]":
        """Unified view of every attached child, keyed by each child's own
        `.name`, independent of which field on this component holds it.

        Computed fresh on each access rather than cached: component counts
        are small, so there's no need for the complexity of cache
        invalidation.

        Re-runs `_set_child_parents()` first (idempotent) so every reader
        sees correctly-named children even if a list/dict field was
        reassigned via plain attribute set (`gwf.wel = [...]`) rather than
        construction or `__setitem__` -- the one case that otherwise skips
        naming, leaving siblings collided on the shared class-name default
        (which becomes the MF6 PNAME on write, e.g. `Binding.from_component()`
        -- some MF6 builds tolerate the resulting duplicate registration,
        others don't). Centralized here, rather than in each consumer
        (`write()`, `NetCDFModel.from_model()`, ...), so nothing can read a
        stale name depending on call order.

        Detects child fields via `flopy4.attrs_xarray.child_field_candidates()`.
        """
        from flopy4.attrs_xarray import child_field_candidates

        self._set_child_parents()

        result: "dict[str, Component]" = {}
        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            kind, _ = spec
            if kind == "only":
                if isinstance(value, Component):
                    result[value.name] = value
            elif kind == "list":
                for child in value:
                    if isinstance(child, Component):
                        result[child.name] = child
            elif kind == "dict":
                for child in value.values():
                    if isinstance(child, Component):
                        result[child.name] = child
        return result

    def _set_child_parents(self) -> None:
        """Stamp `_parent` on every already-populated Component-typed
        field (single, list, or dict); see `_parent`'s own docstring
        above. Also resolves and stamps each child's `.name` --
        `_resolve_child_name()`'s top-down counterpart to
        `_attach_to_parent_field()`'s bottom-up one.

        Detects child fields via `child_field_candidates()` (type-
        annotation based).
        """
        from flopy4.attrs_xarray import child_field_candidates

        used: "set[str]" = set()
        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            kind, _ = spec

            if kind == "only":
                if isinstance(value, Component):
                    value.__dict__["_parent"] = self
                    value.name = _resolve_child_name(used, kind, f.name, value)  # type: ignore[attr-defined]
                    used.add(value.name)  # type: ignore[attr-defined]
            elif kind == "list":
                for child in value:
                    if isinstance(child, Component):
                        child.__dict__["_parent"] = self
                        child.name = _resolve_child_name(used, kind, f.name, child)  # type: ignore[attr-defined]
                        used.add(child.name)  # type: ignore[attr-defined]
            elif kind == "dict":
                for key, child in value.items():
                    if isinstance(child, Component):
                        child.__dict__["_parent"] = self
                        if key in used:
                            raise ValueError(
                                f"Child name '{key}' collides with an "
                                "existing child on the same parent."
                            )
                        child.name = key  # type: ignore[attr-defined]
                        used.add(child.name)  # type: ignore[attr-defined]

    @property
    def path(self) -> Path:
        """The path to the component's input file."""
        self.filename = self.filename or self.default_filename()
        return Path.cwd() / self.filename

    def default_filename(self) -> str:
        """
        Generate a default filename for the component.
        By default, this is the component's name then
        the class name in lowercase, separated by dot.

        Override this method in subclasses to provide
        a custom default filename.
        """
        name = self.name  # type: ignore
        cls_name = self.__class__.__name__.lower()
        return f"{name}.{cls_name}"

    def __attrs_post_init__(self):
        """
        Post-initialization hook for all components. Chains to parent
        class post-init hooks (including DimensionRegistryMixin).

        Also runs the two `_parent`-tracking hooks (see `_parent`'s
        docstring): stamps `_parent` on this component's own already-
        populated children (top-down construction), and -- if this
        component's own `_parent` was given directly as `parent=`, i.e.
        bottom-up construction -- attaches `self` into the matching field
        on it and resolves its `.name` -- see `_attach_to_parent_field()`'s
        docstring.
        """
        # Chain to parent classes (including DimensionRegistryMixin)
        if hasattr(super(), "__attrs_post_init__"):
            super().__attrs_post_init__()  # type: ignore[misc]
        if self._parent is not None:
            self._attach_to_parent_field(self._parent)
        self._set_child_parents()

    def _attach_to_parent_field(self, parent: "Component") -> None:
        """Bottom-up counterpart to `_set_child_parents()`: when this
        component was constructed with `parent=` directly (e.g.
        `Ic(parent=gwf)`), or assigned via `self.parent = parent` (see the
        `parent` property's setter), find the matching field on `parent`
        and write `self` into it, resolving `.name` the same way
        `_set_child_parents` does for top-down construction.

        Doesn't touch `self._parent` itself -- callers (post-init, and the
        `parent` setter) are responsible for that; this only handles the
        parent-side field attachment and naming.
        """
        match = _find_child_field(type(parent), type(self))
        if match is None:
            return
        target_field, kind = match
        used = {c.name for c in parent._children.values()}  # type: ignore[attr-defined]
        if kind == "only":
            self.name = _resolve_child_name(used, kind, target_field.name, self)  # type: ignore[attr-defined]
            setattr(parent, target_field.name, self)
        elif kind == "list":
            self.name = _resolve_child_name(used, kind, target_field.name, self)  # type: ignore[attr-defined]
            getattr(parent, target_field.name).append(self)
        elif kind == "dict":
            # No positional auto-key to fall back on for an unnamed child,
            # unlike "only"/"list" -- see `_set_child_parents`'s "dict"
            # branch: the child's own `.name` (explicit, or its
            # class-name default) is the key.
            key = self.name  # type: ignore[attr-defined]
            if key in used:
                raise ValueError(
                    f"Child name '{key}' collides with an existing child on the same parent."
                )
            getattr(parent, target_field.name)[key] = self

    @classmethod
    def __attrs_init_subclass__(cls):
        # Only register classes that declare their own `dfn_name`.
        # Abstract bases (Package, Context, Model, Exchange, Solution,
        # DisBase, ...) have no `dfn_name` of their own and are silently
        # skipped.
        dfn_name = cls.__dict__.get("dfn_name")
        if dfn_name is not None:
            FNAMES[dfn_name] = cls

    def __getitem__(self, key):
        return self._children[key]

    def __setitem__(self, key, value):
        """Attach `value` under `key`.

        If `key` names an already-attached child, replace it in place, in
        whatever field/slot currently holds it (matching that child's
        own kind). Otherwise, find the single field on this class that
        accepts `type(value)` (`_find_child_field`) and attach it there
        fresh. Either way, `value.name` is set to `key` and its `_parent`
        stamped -- mirrors `_set_child_parents`/`_attach_to_parent_field`,
        just triggered by assignment instead of construction/attachment.
        """
        if not isinstance(value, Component):
            raise TypeError(f"Expected a Component, got {type(value).__name__}")

        from flopy4.attrs_xarray import child_field_candidates

        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                continue
            kind, _ = spec
            current = getattr(self, f.name, None)
            if kind == "only":
                if isinstance(current, Component) and current.name == key:  # type: ignore[attr-defined]
                    value.name = key  # type: ignore[attr-defined]
                    value.__dict__["_parent"] = self
                    setattr(self, f.name, value)
                    return
            elif kind == "list":
                for i, child in enumerate(current or []):
                    if isinstance(child, Component) and child.name == key:  # type: ignore[attr-defined]
                        value.name = key  # type: ignore[attr-defined]
                        value.__dict__["_parent"] = self
                        current[i] = value
                        return
            elif kind == "dict":
                if current and key in current:
                    value.name = key  # type: ignore[attr-defined]
                    value.__dict__["_parent"] = self
                    current[key] = value
                    return

        match = _find_child_field(type(self), type(value))
        if match is None:
            raise TypeError(f"No field on {type(self).__name__} accepts a {type(value).__name__}")
        target_field, kind = match
        value.__dict__["_parent"] = self
        value.name = key  # type: ignore[attr-defined]
        if kind == "only":
            setattr(self, target_field.name, value)
        elif kind == "list":
            getattr(self, target_field.name).append(value)
        elif kind == "dict":
            getattr(self, target_field.name)[key] = value

    def __delitem__(self, key):
        """Detach the child named `key`, from whatever field/slot
        currently holds it."""
        from flopy4.attrs_xarray import child_field_candidates

        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                continue
            kind, _ = spec
            value = getattr(self, f.name, None)
            if kind == "only":
                if isinstance(value, Component) and value.name == key:  # type: ignore[attr-defined]
                    setattr(self, f.name, None)
                    return
            elif kind == "list":
                for i, child in enumerate(value or []):
                    if isinstance(child, Component) and child.name == key:  # type: ignore[attr-defined]
                        del value[i]
                        return
            elif kind == "dict":
                if value and key in value:
                    del value[key]
                    return
        raise KeyError(key)

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)

    @classmethod
    def load(
        cls, path: str | PathLike, format: str = MF6, name: "str | None" = None
    ) -> "Component":
        """Load a component from a file.

        `name`, if given, overrides the default auto-assigned name (e.g.
        a namefile binding row's pname, threaded down by a parent's
        `_resolve_bindings` call when loading this component as a child).
        """
        return cls._load(path, format=format, name=name)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        """
        Write the component and any children.

        Parameters
        ----------
        format : str, optional
            Output format. Default is MF6.
        context : WriteContext, optional
            Configuration context for writing. If not provided,
            uses the current context from the context manager stack,
            or default settings.
        """
        # TODO: setting filename is a temp hack to get the parent's
        # name as this component's filename stem, if it has one. an
        # actual solution is to auto-set the filename when children
        # are attached to parents.
        self.filename = self.filename or self.default_filename()

        # Determine active context: provided > current > default
        active_context = context or WriteContext.current()

        self._write(format=format, context=active_context)
        for child in self._children.values():
            child.write(format=format, context=context)

    def to_dict(self, blocks: bool = False, strict: bool = False) -> dict[str, Any]:
        """
        Convert the component to a dictionary representation.

        Parameters
        ----------
        blocks : bool, optional
            If True, return a nested dict keyed by block name
            with values as dicts of fields. Default is False.
        strict : bool, optional
            If True, include only fields in the DFN specification.

        Returns
        -------
        dict[str, Any]
            Dictionary containing component data, either
            in terms of fields (flat) or blocks (nested).
        """
        # Exclude any field literally named "parent" or "_parent" at every
        # recursion level, not just this component's own: e.g.
        # Gwf.Output.parent is a genuine back-reference to the owning Gwf,
        # unrelated to Component._parent, but recursing into it the same
        # way would infinitely loop (output -> parent -> output -> ...).
        data = attrs.asdict(
            self, recurse=True, filter=lambda attr, value: attr.name not in ("parent", "_parent")
        )
        spec = fields_dict(self.__class__)

        if strict:
            data.pop("filename")
            data.pop("workspace", None)  # might be a Context

        if blocks:
            blocks_ = {}  # type: ignore
            for field_name, field_attr in spec.items():
                field_value = data[field_name]
                block_name = field_attr.metadata.get("block")
                if strict and block_name is None:
                    continue
                if block_name not in blocks_:
                    blocks_[block_name] = {}
                blocks_[block_name][field_name] = field_value
            return blocks_
        else:
            return {
                field_name: data[field_name]
                for field_name, field_attr in spec.items()
                if field_attr.metadata.get("block") or not strict
            }

    def to_xarray(self):
        """Flat xr.Dataset of this component's own scalar/array fields,
        merged with any child packages that have griddata fields.

        Built directly from live attribute values via flopy4.attrs_xarray's
        attrs_to_dataset.
        """
        import xarray as _xr

        from flopy4.attrs_xarray import attrs_to_dataset

        base = attrs_to_dataset(self)
        extra = list(self._collect_child_griddata_datasets().values())
        if not extra:
            return base
        try:
            merged = _xr.merge([base] + extra, join="outer")
            merged.attrs.update(base.attrs)
            return merged
        except Exception:
            return base

    def _collect_child_griddata_datasets(self) -> dict:
        """Walk children and return {name: xr.Dataset} for v2 packages with griddata."""
        result: dict = {}
        try:
            for name, child in self._children.items():
                try:
                    _fields = attrs.fields(type(child))
                except attrs.exceptions.NotAnAttrsClassError:
                    continue
                if not any(f.metadata.get("block") == "griddata" for f in _fields):
                    continue
                try:
                    ds = child.to_xarray()
                    if ds is not None and hasattr(ds, "data_vars") and ds.data_vars:
                        result[name] = ds
                except Exception:
                    pass
        except Exception:
            pass
        return result
