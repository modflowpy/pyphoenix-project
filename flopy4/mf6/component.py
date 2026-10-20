import copy
from abc import ABC
from collections.abc import MutableMapping
from functools import lru_cache
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional

import attrs
from attrs import fields

from flopy4.dimensions import DimensionResolverMixin
from flopy4.mf6.constants import MF6
from flopy4.mf6.external import in_write_session, write_session
from flopy4.mf6.spec import fields_dict
from flopy4.mf6.write_context import WriteContext
from flopy4.spec import is_reference, reference_names, referenced, resolve
from flopy4.uio import IO, Loader, Writer
from flopy4.utils import empty_if_none

if TYPE_CHECKING:
    from flopy4.mf6.load_context import LoadContext

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
    from flopy4.mf6 import _import_components

    _import_components()
    return FNAMES


def get_ftypes() -> "dict[str, type[Component]]":
    """Get a map of MF6 component ftype (e.g. 'gwf-dis6') to component class."""
    if not FTYPES:
        from flopy4.mf6 import _import_components

        _import_components()
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


def _resolve_child_name(used: "set[str]", kind: str, child: "Component") -> str:
    """Resolve the name `child` should be attached under (stored as its
    own `.name`), given the set of names already claimed by any of the
    parent's other children (`used`).

    A name already set (given, or assigned on an earlier attach) is kept
    as is, raising if a sibling has it. An unnamed "only"-kind child takes
    its class name ("dis" for `Dis`, "disv" for `Disv`). An unnamed
    "list"-kind child takes its class name plus the first free index from
    0 ("wel0", "rcha0", "gwf0"). A stored name never changes, so deleting
    a sibling doesn't renumber the rest.
    """
    if kind not in ("only", "list"):
        raise TypeError(f"Bad child collection kind '{kind}'")
    if child.name is not None:  # type: ignore[attr-defined]
        if child.name in used:  # type: ignore[attr-defined]
            raise ValueError(
                f"Child name '{child.name}' collides with an existing child "  # type: ignore[attr-defined]
                "on the same parent."
            )
        return child.name  # type: ignore[attr-defined]
    name = type(child).__name__.lower()
    if kind == "only":
        return name
    i = 0
    while f"{name}{i}" in used:
        i += 1
    return f"{name}{i}"


def _check_filenames(top: "Component") -> None:
    """Raise if two components in the tree under `top` have one file,
    which writing would overwrite. Compares paths case-insensitively, as
    macOS's and Windows' filesystems do."""
    seen: "dict[str, Component]" = {}
    stack = [top]
    while stack:
        c = stack.pop()
        key = c.path.as_posix().casefold()
        if (other := seen.get(key)) is not None and other is not c:
            raise ValueError(
                f"{c.filename} is the file for both {type(other).__name__} "
                f"'{other.name}' and {type(c).__name__} '{c.name}'; "
                "give one a different filename"
            )
        seen[key] = c
        stack.extend(reversed(list(c._children.values())))


@lru_cache(maxsize=None)
def _child_fields(cls: type) -> "tuple[tuple[str, bool], ...]":
    """The fields of ``cls`` that may hold a child, as (name, whether it's
    a child column): a child column (LAK's laktab), or a record or union
    arm that may hold one (SFR's CrossSection). Cached, so rows needn't
    each be walked field by field."""
    from flopy4.mf6.item import _field_type_str, _union_field_arms
    from flopy4.mf6.record import _nested_class, record_type

    if not attrs.has(cls):
        return ()
    found = []
    for f in fields(cls):
        if f.metadata.get("child"):
            found.append((f.name, True))
            continue
        if (t := _field_type_str(f)) is None:
            nested = [c] if (c := record_type(f.type)) else []
        elif (arms := _union_field_arms(cls, f)) is not None:
            nested = list(arms[1])
        else:
            nested = [c] if (c := _nested_class(cls, t)) else []
        if any(_may_hold_children(c) for c in nested):
            found.append((f.name, False))
    return tuple(found)


def _may_hold_children(cls: type) -> bool:
    """Whether a row of ``cls`` may hold a child (see `_child_fields`)."""
    return bool(_child_fields(cls))  # type: ignore[arg-type]  # lru_cache wants Hashable


def _row_children(row: Any) -> "list[Component]":
    """The children in a list's row (LAK's ``ifno TAB6 FILEIN <file>``),
    including in its union arm (SFR's ``CROSS_SECTION TAB6 FILEIN``)."""
    if isinstance(row, Component):
        return []
    children = []
    for name, child in _child_fields(type(row)):  # type: ignore[arg-type]  # lru_cache wants Hashable
        value = getattr(row, name)
        if child:
            children += [value] if isinstance(value, Component) else []
        elif attrs.has(type(value)):
            children += _row_children(value)
    return children


def _may_hold_any(rows: Any) -> bool:
    """Whether a list's rows may be or hold a child, by their classes,
    so a list of plain rows (DISV's 100k cell2d) isn't walked by row."""
    from flopy4.mf6.item_table import ItemTable

    if isinstance(rows, ItemTable):
        return _may_hold_children(rows.item_cls)  # type: ignore[arg-type]  # lru_cache wants Hashable
    return any(
        issubclass(t, Component) or _may_hold_children(t)  # type: ignore[arg-type]  # lru_cache wants Hashable
        for t in set(map(type, rows))
    )


def _period_row_children(value: Any) -> "list[Component]":
    """The children in a period block's rows, by period (SFR's
    ``CROSS_SECTION TAB6 FILEIN <file>``)."""
    if not isinstance(value, dict):
        return []
    rows = (
        row
        for period in value.values()
        if isinstance(period, list) and _may_hold_any(period)
        for row in period
    )
    return [c for row in rows for c in _row_children(row)]


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

    _filename: Optional[Path] = attrs.field(
        default=None, alias="filename", converter=attrs.converters.optional(Path)
    )
    """The filename set, if any (see `filename`). `None` means the
    default."""

    name: Optional[str] = attrs.field(default=None)
    """The component's name among its parent's children. `None` until
    given or attached: attaching gives an unnamed component one (see
    `_resolve_child_name()`), which is then kept like a given name. To
    rename, assign it; a clash with a sibling raises on the parent's next
    access to its children."""

    _parent: Any = attrs.field(default=None, repr=False, eq=False)
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

    write_context: Optional[WriteContext] = attrs.field(default=None, repr=False, eq=False)
    """How to write this component: whole-write settings, and settings
    for its own arrays, by field (see `WriteContext`). Loading sets it to
    reproduce how the file wrote its arrays; set it to None to drop that.
    Ranks below a `write()` argument and an active `with WriteContext(...)`
    block, above the ancestors' (whose `arrays` don't apply here: they key
    the ancestor's own fields). Not written to file, and left out of
    `to_dict()`."""

    dims: dict = attrs.field(
        default=attrs.Factory(dict),
        converter=empty_if_none,
        repr=False,
        eq=False,
    )
    """Dimensions given explicitly (e.g. `Ic(dims={"nodes": 900})`, or
    those given to `Package.load`), for a component not attached to a
    tree that provides them. `resolve_dims()` falls back to these, and
    `Package.__attrs_post_init__` sizes griddata from them. `None` is
    accepted and converted to an empty dict."""

    @property
    def filename(self) -> Path:
        """The component's input file, relative to the workspace: the one
        set (given, or loaded from the name file), else `default_filename()`,
        worked out fresh on each read, so a default follows a rename. Set it
        to a path (a `str` is converted), or to `None` to go back to the
        default. Written to name files with POSIX separators."""
        return self._filename or Path(self.default_filename())

    @filename.setter
    def filename(self, value: "str | PathLike | None") -> None:
        self._filename = None if value is None else Path(value)

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
        rule: a name already set is kept, and raises if a sibling on the
        new parent has it; an unnamed component gets an automatic name.
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

        Re-runs `_set_child_parents()` first (idempotent): child fields
        attach what's assigned or added to them (see `_attach_field()`),
        but the children in a list's rows (LAK's, SFR's tables) are
        attached only here, when a row is changed in place.

        Detects child fields via `flopy4.attrs_xarray.child_field_candidates()`.
        """
        from flopy4.attrs_xarray import child_field_candidates

        self._set_child_parents()

        result: "dict[str, Component]" = {}
        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                for c in _period_row_children(getattr(self, f.name, None)):
                    result[c.name] = c  # type: ignore[attr-defined,index]
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            kind, _ = spec
            if kind == "only":
                if isinstance(value, Component):
                    result[value.name] = value  # type: ignore[index]
            elif kind == "list" and _may_hold_any(value):
                for child in value:
                    if isinstance(child, Component):
                        result[child.name] = child  # type: ignore[index]
                    for c in _row_children(child):
                        result[c.name] = c  # type: ignore[index]
        return result

    def _set_child_parents(self) -> None:
        """Stamp `_parent` on every already-populated Component-typed
        field (single or list); see `_parent`'s own docstring
        above. Also resolves and stamps each child's `.name` --
        `_resolve_child_name()`'s top-down counterpart to
        `_attach_to_parent_field()`'s bottom-up one.

        Detects child fields via `child_field_candidates()` (type-
        annotation based).
        """
        from flopy4.attrs_xarray import child_field_candidates

        # gather first, so automatic names avoid every name already set,
        # wherever its child comes in the field order
        found: "list[tuple[str, Component]]" = []
        # rows may share a child (one table file named in several places)
        stamped: "set[int]" = set()

        def add(kind: str, c: "Component") -> None:
            if id(c) not in stamped:
                stamped.add(id(c))
                c.__dict__["_parent"] = self
                found.append((kind, c))

        for f in fields(type(self)):
            spec = child_field_candidates(f)
            if spec is None:
                for c in _period_row_children(getattr(self, f.name, None)):
                    add("list", c)
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            kind, _ = spec
            if kind == "only":
                if isinstance(value, Component):
                    add(kind, value)
            elif kind == "list" and _may_hold_any(value):
                for child in value:
                    for c in [child] if isinstance(child, Component) else _row_children(child):
                        add(kind, c)

        used: "set[str]" = set()
        for kind, c in found:
            if c.name is not None:  # type: ignore[attr-defined]
                used.add(_resolve_child_name(used, kind, c))
        for kind, c in found:
            if c.name is None:  # type: ignore[attr-defined]
                c.name = _resolve_child_name(used, kind, c)  # type: ignore[attr-defined]
                used.add(c.name)  # type: ignore[attr-defined]

    @property
    def path(self) -> Path:
        """The path to the component's input file: in the workspace of the
        model or simulation it belongs to, or the cwd if none."""
        return self.root / self.filename

    @property
    def root(self) -> Path:
        """The directory the component's paths are relative to: the
        workspace of the model or simulation it belongs to (for a
        simulation's components, the simulation directory). If none, the
        directory of its file, if that's given as an absolute path, else
        the cwd."""
        node = self._parent
        while node is not None and not hasattr(node, "workspace"):
            node = node._parent
        if node is not None:
            return node.workspace
        if self._filename is not None and self._filename.is_absolute():
            return self._filename.parent
        return Path.cwd()

    def _name_or_class(self) -> str:
        """The component's name, or its class name, lowercase, if it has
        none yet (it's detached)."""
        return self.name or type(self).__name__.lower()

    def default_filename(self) -> str:
        """
        Generate a default filename for the component.
        By default, this is the component's name then
        the class name in lowercase, separated by dot.

        Override this method in subclasses to provide
        a custom default filename.
        """
        cls_name = self.__class__.__name__.lower()
        return f"{self._name_or_class()}.{cls_name}"

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
        if self._parent is None:
            self._parent = self._references_parent()
        if self._parent is not None:
            self._attach_to_parent_field(self._parent)
        self._set_child_parents()

    def _attach_field(self, name: str, value: Any) -> Any:
        """Set the child field `name` to `value`, attaching and naming its
        children as construction does (`gwf.wel = [...]`, `dis.ncf = ncf`).
        A name clash raises, leaving the field as it was. Called by the
        field's `on_setattr` hook, which returns `value` for attrs to set
        again."""
        old = self.__dict__.get(name)
        object.__setattr__(self, name, value)
        try:
            self._set_child_parents()
        except Exception:
            object.__setattr__(self, name, old)
            raise
        return value

    def _references_parent(self) -> "Component | None":
        """The parent the components this one refers to share (e.g. the
        simulation a solution's or an exchange's models are in), which a
        component given no parent joins. None if they have none; an error
        if they have different ones."""
        parents = {}
        refs = []
        for f in self._reference_fields():
            for c in referenced(getattr(self, f.name)):
                refs.append(c)
                p = c.__dict__.get("_parent")
                if hasattr(p, "models"):
                    parents[id(p)] = p
        if len(parents) > 1:
            names = [c.name for c in refs]
            raise ValueError(
                f"{self.name}: {names} belong to different simulations"  # type: ignore[attr-defined]
            )
        return next(iter(parents.values()), None)

    def _reference_fields(self) -> list:
        """This component's reference fields (see `flopy4.spec.reference`)."""
        return [f for f in fields(type(self)) if is_reference(f)]

    def _resolved(self, name: str) -> Any:
        """Reference field `name`'s value with names resolved among the
        parent's (the simulation's) models. As given if there's no parent
        to look in."""
        value = getattr(self, name)
        models = getattr(self._parent, "models", None)
        return value if models is None else resolve(value, models)

    def _resolve_references(self) -> None:
        """Resolve the names in this component's children's reference
        fields to the models they name, where it has them."""
        for child in self._children.values():
            for f in child._reference_fields():
                setattr(child, f.name, child._resolved(f.name))

    def _reference_errors(self) -> list[str]:
        """What's wrong with this component's references: a required one
        missing, one not among the simulation's models, or one its field's
        check finds a problem with (see `flopy4.spec.reference`)."""
        errors = []
        models = getattr(self._parent, "models", [])
        for f in self._reference_fields():
            value = self._resolved(f.name)
            if value is None and f.metadata["required"]:
                errors.append(f"{self.name} has no {f.name}")  # type: ignore[attr-defined]
            check = f.metadata["check"]
            for v in value if isinstance(value, list) else [value]:
                if v is None:
                    continue
                if isinstance(v, str) or not any(m is v for m in models):
                    errors.append(
                        f"{self.name} refers to model {reference_names(v)!r} in {f.name}, "  # type: ignore[attr-defined]
                        "which isn't in the simulation"
                    )
                elif check is not None and (problem := check(self, v)):
                    errors.append(f"{self.name} {problem}")  # type: ignore[attr-defined]
        return errors

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
        used = set(parent._children)
        self.name = _resolve_child_name(used, kind, self)  # type: ignore[attr-defined]
        if kind == "only":
            setattr(parent, target_field.name, self)
        elif kind == "list":
            getattr(parent, target_field.name).append(self)

    @classmethod
    def __attrs_init_subclass__(cls):
        # Only register classes that declare their own `dfn_name`.
        # Abstract bases (Package, Context, Model, Exchange, Solution, ...)
        # have no `dfn_name` of their own and are silently skipped.
        dfn_name = cls.__dict__.get("dfn_name")
        if dfn_name is not None:
            FNAMES[dfn_name] = cls

    def __getitem__(self, key):
        return self._children[key]

    def __copy__(self):
        """A shallow copy, sharing everything, its parent too. (Without
        this, `copy.copy` would go through `__getstate__`/`__setstate__`
        and take the original's children for its own.)"""
        new = type(self).__new__(type(self))
        new.__dict__.update(self.__dict__)
        return new

    def __getstate__(self):
        """Pickle what this component owns, as `__deepcopy__` copies it:
        not its parent, so it unpickles detached unless its parent was
        pickled too, and its reference fields by name, so a solution
        doesn't take its models along. A simulation resolves its
        solutions' names again when it's unpickled."""
        state = dict(self.__dict__)
        state["_parent"] = None
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if is_reference(f) and f.name in state:
                state[f.name] = reference_names(state[f.name])
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._set_child_parents()

    def __deepcopy__(self, memo):
        """Copy what this component owns (its children and values), not
        what it only refers to. Its parent becomes its copy if that's
        copied in the same operation, as when copying a whole simulation;
        otherwise it's dropped, so a lone copy comes out detached. Its
        reference fields (e.g. a solution's models) are copied by name, as
        they're pickled, and resolved by the copied parent among its own
        copies (see `_resolve_references`): a copied simulation's solutions
        and exchanges hold its copied models, a lone copy their names.
        """
        cls = type(self)
        new = cls.__new__(cls)
        memo[id(self)] = new
        references = {f.name for f in self._reference_fields()}
        for key, value in self.__dict__.items():
            if key == "_parent":
                value = memo.get(id(value))
            elif key in references:
                value = reference_names(value)
            else:
                value = copy.deepcopy(value, memo)
            new.__dict__[key] = value
        new._resolve_references()
        return new

    def __setitem__(self, key, value):
        """Attach `value` under `key`.

        `value` must be unnamed (it takes `key`) or already named `key`;
        any other name raises, rather than renaming it silently. If `key`
        names an already-attached child, replace it in place, in whatever
        field/slot currently holds it (matching that child's own kind).
        Otherwise, find the single field on this class that accepts
        `type(value)` (`_find_child_field`) and attach it there fresh.
        Either way, `value`'s `_parent` is stamped -- mirrors
        `_set_child_parents`/`_attach_to_parent_field`, just triggered by
        assignment instead of construction/attachment.
        """
        if not isinstance(value, Component):
            raise TypeError(f"Expected a Component, got {type(value).__name__}")
        if value.name is not None and value.name != key:  # type: ignore[attr-defined]
            raise ValueError(
                f"Can't attach a {type(value).__name__} named '{value.name}' "  # type: ignore[attr-defined]
                f"under '{key}'; rename it first, or use '{value.name}' as the key."  # type: ignore[attr-defined]
            )

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
        raise KeyError(key)

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)

    @classmethod
    def load(
        cls,
        path: str | PathLike,
        format: str = MF6,
        name: "str | None" = None,
        *,
        context: "LoadContext | None" = None,
    ) -> "Component":
        """Load a component from a file.

        `name`, if given, overrides the default auto-assigned name (e.g.
        a namefile binding row's pname, threaded down by a parent's
        `_resolve_bindings` call when loading this component as a child).
        `context` says where the file sits in the simulation (see
        `LoadContext`). By default, relative paths in it resolve against
        its own directory; to load a model on its own, give the
        simulation directory as the context's workspace.
        """
        return cls._load(path, format=format, name=name, context=context)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        """
        Write the component and any children.

        Parameters
        ----------
        format : str, optional
            Output format. Default is MF6.
        context : WriteContext, optional
            Configuration context for writing. Its settings beat those of
            an active context manager, then this component's and its
            ancestors' `write_context`; see `WriteContext.resolve`. Each
            child resolves its own, from the same argument.
        """
        # ancestors' contexts give whole-write settings only: their arrays
        # key the ancestor's own fields, not this component's
        ancestors = []
        node = self._parent
        while node is not None:
            if node.write_context is not None:
                ancestors.append(attrs.evolve(node.write_context, arrays={}))
            node = node._parent
        active_context = WriteContext.resolve(
            context, WriteContext.current(), self.write_context, *ancestors
        )

        # before writing this component's own file: getting the children
        # stamps their parents and names, which a name file's rows (and
        # the children's default filenames) are made from
        children = self._children
        if not in_write_session():
            _check_filenames(self)
        with write_session():
            self._write(format=format, context=active_context)
            for child in children.values():
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
        # recursion level, not just this component's own: a back-reference
        # to the owner would loop forever (child -> parent -> child -> ...).
        data = attrs.asdict(
            self,
            recurse=True,
            filter=lambda attr, value: attr.name not in ("parent", "_parent", "write_context"),
        )
        spec = fields_dict(self.__class__)

        if strict:
            data.pop("_filename")
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
