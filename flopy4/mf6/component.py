from abc import ABC
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, ClassVar, Optional

from attrs import fields
from modflow_devtools.dfn import Dfn, Field
from packaging.version import Version
from xattree import asdict as xattree_asdict
from xattree import xattree

from flopy4.mf6.constants import MF6
from flopy4.mf6.spec import field, fields_dict, to_field
from flopy4.mf6.utils.grid import update_maxbound
from flopy4.mf6.write_context import WriteContext
from flopy4.uio import IO, Loader, Writer

COMPONENTS = {}
"""MF6 component registry."""


# kw_only=True necessary so we can define optional fields here
# and required fields in subclasses. attrs complains otherwise
@xattree(kw_only=True)
class Component(ABC, MutableMapping):
    """
    Base class for MF6 components.

    Notes
    -----
    All subclasses of `Component` must be decorated with `xattree`.
    """

    _load = IO(Loader)  # type: ignore
    _write = IO(Writer)  # type: ignore

    dfn: ClassVar[Dfn]
    """The component's definition (i.e. specification)."""

    filename: str | None = field(default=None)
    """The name of the component's input file."""

    write_context: Optional[WriteContext] = field(default=None, repr=False)
    """Configuration context for writing input files."""

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

        Automatically handles common post-init tasks like computing maxbound
        for components with period block arrays.
        """
        self._update_maxbound_if_needed()

    def _update_maxbound_if_needed(self):
        """
        Update maxbound if this component has period block arrays.

        This method checks if the component has any period block arrays defined
        and calls update_maxbound if needed. This generalizes the pattern that
        was previously repeated in multiple component classes.
        """
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
        COMPONENTS[cls.__name__.lower()] = cls
        cls.dfn = cls.get_dfn()

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
    def get_dfn(cls) -> Dfn:
        """Get the component's definition (i.e. specification)."""
        fields = {field_name: to_field(field) for field_name, field in fields_dict(cls).items()}
        blocks: dict[str, dict[str, Field]] = {}
        for field_name, field_ in fields.items():
            if (block := field_.block) is not None:
                blocks.setdefault(block, {})[field_name] = field_
            else:
                blocks[field_name] = field_

        return Dfn(
            schema_version=Version("2"),
            name=cls.__name__.lower(),
            advanced=getattr(cls, "advanced_package", False),
            multi=getattr(cls, "multi_package", False),
            ref=getattr(cls, "sub_package", None),
            blocks=blocks,
        )

    def load(self, format: str = MF6) -> None:
        """Load the component and any children."""
        # TODO: setting filename is a temp hack to get the parent's
        # name as this component's filename stem, if it has one. an
        # actual solution is to auto-set the filename when children
        # are attached to parents.
        self.filename = self.filename or self.default_filename()
        self._load(format=format)
        for child in self.children.values():  # type: ignore
            child.load(format=format)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        """
        Write the component and any children.

        Parameters
        ----------
        format : str, optional
            Output format. Default is MF6.
        context : WriteContext, optional
            Configuration context for writing. If provided, overrides
            the component's write_context. If neither is provided,
            uses the current context from the context manager stack,
            or default settings.
        """
        # TODO: setting filename is a temp hack to get the parent's
        # name as this component's filename stem, if it has one. an
        # actual solution is to auto-set the filename when children
        # are attached to parents.
        self.filename = self.filename or self.default_filename()

        # Determine active context: provided > attached > current > default
        active_context = context or self.write_context or WriteContext.current()

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
        spec = self.dfn.fields

        if strict:
            data.pop("filename")
            data.pop("workspace", None)  # might be a Context

        if blocks:
            blocks_ = {}  # type: ignore
            for field_name in spec.keys():
                field_value = data[field_name]
                block_name = spec[field_name].block
                if strict and block_name is None:
                    continue
                if block_name not in blocks_:
                    blocks_[block_name] = {}
                blocks_[block_name][field_name] = field_value
            return blocks_
        else:
            return {
                field_name: data[field_name]
                for field_name in spec.keys()
                if spec[field_name].block or not strict
            }

    def to_xarray(self):
        return self.data.dataset  # type: ignore
