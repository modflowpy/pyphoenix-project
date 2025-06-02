from abc import ABC
from collections.abc import MutableMapping

from modflow_devtools.dfn import Dfn, Field
from xattree import xattree

from flopy4.mf6.spec import fields_dict, to_dfn_field
from flopy4.uio import IO, Loader, Writer

COMPONENTS = {}
"""MF6 component registry."""


@xattree
class Component(ABC, MutableMapping):
    """
    Base class for MF6 components.

    Notes
    -----
    All subclasses of `Component` must be decorated with `xattree`.

    We use the `children` attribute provided by `xattree`. We know
    children are also `Component`s, but mypy does not. TODO: fix??
    """

    _load = IO(Loader)  # type: ignore
    _write = IO(Writer)  # type: ignore

    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls
        cls.dfn = cls.get_dfn()

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
        fields = {field_name: to_dfn_field(field) for field_name, field in fields_dict(cls).items()}
        blocks: dict[str, dict[str, Field]] = {}
        for field_name, field in fields.items():
            if (block := field.get("block", None)) is not None:
                blocks.setdefault(block, {})[field_name] = field
            else:
                blocks[field_name] = field

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
