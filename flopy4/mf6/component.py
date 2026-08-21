from abc import ABC
from collections.abc import MutableMapping
from os import PathLike
from pathlib import Path
from typing import Any, ClassVar, Optional

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

    dfn_name: ClassVar[str] = ""
    """The component's canonical DFN name (e.g. 'gwf-ic'), set by subclasses
    that are registered in FNAMES/FTYPES -- see the FNAMES docstring above."""

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
        # Only register classes that declare their own `dfn_name`.
        # Abstract bases (Package, Context, Model, Exchange, Solution,
        # DisBase, ...) have no `dfn_name` of their own and are silently
        # skipped.
        dfn_name = cls.__dict__.get("dfn_name")
        if dfn_name is not None:
            FNAMES[dfn_name] = cls

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
