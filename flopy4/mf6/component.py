from abc import ABC
from collections.abc import MutableMapping
from pathlib import Path

from modflow_devtools.dfn import Dfn, Field
from xattree import xattree

from flopy4.mf6.spec import field, fields_dict, to_dfn_field
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

    We use the `children` attribute provided by `xattree`. We know
    children are also `Component`s, but mypy does not. TODO: fix??
    Then we can remove the `# type: ignore` comments.
    """

    _load = IO(Loader)  # type: ignore
    _write = IO(Writer)  # type: ignore

    filename: str = field(default=None)

    @property
    def path(self) -> Path:
        return Path.cwd() / self.filename

    def _default_filename(self) -> str:
        name = self.name  # type: ignore
        cls_name = self.__class__.__name__.lower()
        return f"{name}.{cls_name}"

    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls
        cls.dfn = cls.get_dfn()

    def __attrs_post_init__(self):
        if not self.filename:
            self.filename = self._default_filename()

    def __getitem__(self, key):
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
        """Generate the component's MODFLOW 6 definition."""
        fields = {field_name: to_dfn_field(field) for field_name, field in fields_dict(cls).items()}
        blocks: dict[str, dict[str, Field]] = {}
        for field_name, field_ in fields.items():
            if (block := field_.get("block", None)) is not None:
                blocks.setdefault(block, {})[field_name] = field_
            else:
                blocks[field_name] = field_

        return Dfn(
            name=cls.__name__.lower(),
            advanced=getattr(cls, "advanced_package", False),
            multi=getattr(cls, "multi_package", False),
            ref=getattr(cls, "sub_package", None),
            sln=getattr(cls, "solution_package", None),
            **blocks,
        )

    def load(self, format: str) -> None:
        self._load(format=format)
        for child in self.children.values():  # type: ignore
            child.load(format)

    def write(self, format: str) -> None:
        self._write(format=format)
        for child in self.children.values():  # type: ignore
            child.write(format)
