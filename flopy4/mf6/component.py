from abc import ABC
from collections.abc import MutableMapping
from os import PathLike
from pathlib import Path
from typing import Any, Optional

from attrs import fields
from xattree import asdict as xattree_asdict
from xattree import xattree

from flopy4.dimensions import DimensionResolverMixin
from flopy4.mf6.constants import MF6
from flopy4.mf6.spec import fields_dict
from flopy4.mf6.spec import xattree_field as field
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.mf6.write_context import WriteContext
from flopy4.uio import IO, Loader, Writer

COMPONENTS: dict[str, type] = {}
"""MF6 component name -> component type, keyed by fully-qualified name
(e.g. 'gwf-ic') for classes with a model prefix, or by the plain
lowercased class name for classes without one ('simulation', 'gwf', ...).
Use `lookup_component()` rather than indexing this directly unless the
fully-qualified key is already known."""

FTYPES: dict[str, type] = {}
"""MF6 file-type (lowercased, e.g. 'gwf-dis6') -> component class, keyed
the same way as `COMPONENTS` but by ftype token instead of class name.
Use `lookup_ftype()` rather than indexing this directly unless the
fully-qualified key is already known."""


def _model_prefix(cls: type) -> "str | None":
    parts = cls.__module__.split(".")
    if len(parts) >= 4 and parts[0] == "flopy4" and parts[1] == "mf6":
        return parts[2]
    return None


def _qualify(name: str, prefix: "str | None") -> str:
    return f"{prefix}-{name}" if prefix is not None else name


def _lookup(registry: "dict[str, type]", name: str, prefix: "str | None") -> "type | None":
    """Resolve `name` against a fully-qualified-keyed registry.

    Tries, in order: `prefix` qualifying `name` (a caller that knows its
    scope, e.g. `_resolve_bindings` resolving within a known model);
    `name` itself, in case it's already fully qualified (the brief
    `<model>-<component>` form DFN files use) or unprefixed to begin with
    (`Simulation`, `Tdis`, `Model` leaves, ...); and finally a best-effort
    scan for a single registered key ending in `-{name}` -- genuinely
    unambiguous single-component names resolve this way, but names shared
    by more than one model (e.g. 'ic') return `None` rather than an
    arbitrary pick, since the registry alone can't disambiguate them.
    """
    if prefix is not None and (cls := registry.get(_qualify(name, prefix))) is not None:
        return cls
    if (cls := registry.get(name)) is not None:
        return cls
    suffix = f"-{name}"
    matches = {cls for key, cls in registry.items() if key.endswith(suffix)}
    return matches.pop() if len(matches) == 1 else None


def lookup_component(name: str, prefix: "str | None" = None) -> "type | None":
    """Look up a registered component class by name (see `_lookup`)."""
    return _lookup(COMPONENTS, name.lower(), prefix)


def lookup_ftype(token: str, prefix: "str | None" = None) -> "type | None":
    """Look up a registered component class by ftype token (see `_lookup`)."""
    return _lookup(get_ftypes(), token.lower(), prefix)


def get_ftypes() -> "dict[str, type]":
    """Build and return the ftypes registry, keyed like `COMPONENTS` but
    by ftype token (e.g. 'gwf-dis6') instead of class name.

    Some tokens aren't globally unique -- every model type has its own
    'DIS6'/'IC6'/'OC6'/... via a shared abstract base (e.g. `Dis` under
    `gwf`/`gwt`/`gwe`/`prt` all subclass the same `gwf.disbase.DisBase`),
    so type-based disambiguation alone can't tell a GWF `Dis` from a GWT
    one -- that's what the model-qualified key is for.
    """
    if not FTYPES:
        from flopy4.mf6.converter.binding import component_ftype

        for cls in set(COMPONENTS.values()):
            if ABC in cls.__bases__:
                continue
            token = component_ftype(cls).lower()
            FTYPES[_qualify(token, _model_prefix(cls))] = cls
    return FTYPES


# kw_only=True necessary so we can define optional fields here
# and required fields in subclasses. attrs complains otherwise
@xattree(kw_only=True)
class Component(DimensionResolverMixin, ABC, MutableMapping):
    """
    Base class for MF6 components.

    Notes
    -----
    All subclasses of `Component` must be decorated with `xattree`.
    Component inherits from DimensionRegistryMixin to provide dimension
    resolution capabilities to all MF6 components.
    """

    _load = IO(Loader)  # type: ignore
    _write = IO(Writer)  # type: ignore

    filename: str | None = field(default=None)
    """The name of the component's input file."""

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
        Post-initialization hook for all components.

        Automatically handles common post-init tasks like updating maxbound
        for packages with period block arrays. Chains to parent class
        post-init hooks (including DimensionRegistryMixin).
        """
        # Chain to parent classes (including DimensionRegistryMixin)
        if hasattr(super(), "__attrs_post_init__"):
            super().__attrs_post_init__()  # type: ignore[misc]
        self._update_maxbound_if_needed()

    def _update_maxbound_if_needed(self):
        """
        Update maxbound if this component has period block arrays.

        This method checks if the component has any period block arrays defined
        and calls update_maxbound if needed. Packages with maxbound fields
        (like CHD, DRN, etc.) will have it automatically computed at
        initialization and updated when period arrays change.
        """
        # Package leaves compute maxbound in Package.__attrs_post_init__ via
        # _init_row_lists; skip the xattree metadata scan for them.
        from flopy4.mf6.package import Package

        if isinstance(self, Package):
            return

        # Check if component has a maxbound field and period block arrays
        component_fields = fields(self.__class__)
        has_maxbound = any(f.name == "maxbound" for f in component_fields)
        has_period_arrays = any(
            f.metadata
            and f.metadata.get("block") == "period"
            and f.metadata.get("xattree", {}).get("dims")
            for f in component_fields
        )

        if has_maxbound and has_period_arrays:
            update_maxbound(self, None, None)

    @classmethod
    def __attrs_init_subclass__(cls):
        # Keyed by fully-qualified name (e.g. "gwf-ic") for classes in a
        # model subpackage (flopy4.mf6.<model>.<pkg>), or by the plain
        # class name otherwise -- see `lookup_component()` for resolving
        # a bare name like "ic" when the model scope isn't known upfront.
        COMPONENTS[_qualify(cls.__name__.lower(), _model_prefix(cls))] = cls

    def __getitem__(self, key):
        # We use `children` from `xattree` to implement MutableMapping.
        # children are also `Component`s, but mypy doesn't know this..
        # TODO fix, then we can remove the `# type: ignore` comments.
        return self.children[key]  # type: ignore

    def __setitem__(self, key, value):
        self.children[key] = value  # type: ignore

    def __delitem__(self, key):
        del self.children[key]  # type: ignore

    def __iter__(self):
        return iter(self.children)  # type: ignore

    def __len__(self):
        return len(self.children)  # type: ignore

    @classmethod
    def load(
        cls, path: str | PathLike, format: str = MF6, name: "str | None" = None
    ) -> "Component":
        """Load a component from a file.

        `name`, if given, overrides xattree's default auto-assigned name
        (e.g. a namefile binding row's pname, threaded down by a parent's
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
        for child in self.children.values():  # type: ignore
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
        data = xattree_asdict(self)
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
        """Flat xr.Dataset merging this component's DataTree dataset with any
        codegen v2 child packages that have griddata fields.
        """
        import xarray as _xr

        base = self.data.dataset  # type: ignore
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
        import attrs as _attrs

        result: dict = {}
        try:
            for name, child in (getattr(self, "children", None) or {}).items():
                try:
                    _fields = _attrs.fields(type(child))
                except _attrs.exceptions.NotAnAttrsClassError:
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
