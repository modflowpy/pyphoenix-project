from abc import ABC
from collections.abc import MutableMapping

from attrs import Attribute
from modflow_devtools.dfn import Dfn, Var
from xattree import xattree

from flopy4.mf6.spec import fields_dict
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
        # add class to the component registry
        COMPONENTS[cls.__name__.lower()] = cls

    def __attrs_post_init__(self):
        self._dfn = self._get_dfn()

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

    @property
    def dfn(self) -> Dfn:
        """Return the component's definition."""
        return self._dfn

    def _get_dfn(self) -> Dfn:
        def _to_dfn_spec(attribute: Attribute) -> Var:
            return Var(
                name=attribute.name,
                type=attribute.type,
                shape=attribute.metadata.get("dims", None),
                block=attribute.metadata.get("block", None),
                default=attribute.default,
                children={k: _to_dfn_spec(v) for k, v in fields_dict(attribute.type)}  # type: ignore
                if attribute.metadata.get("kind", None) == "child"  # type: ignore
                else None,  # type: ignore
            )

        fields = {k: _to_dfn_spec(v) for k, v in fields_dict(self.__class__).items()}
        blocks: dict[str, dict[str, Var]] = {}
        for k, v in fields.items():
            if (block := v.get("block", None)) is not None:
                blocks.setdefault(block, {})[k] = v
            else:
                blocks[k] = v
        return Dfn(
            name=self.name,  # type: ignore
            advanced=getattr(self, "advanced_package", False),
            multi=getattr(self, "multi_package", False),
            ref=getattr(self, "sub_package", None),
            sln=getattr(self, "solution_package", None),
            **blocks,
        )

    def load(self) -> None:
        self._load(format=format)
        for child in self.children.values():  # type: ignore
            child.load()

    def write(self) -> None:
        self._write(format=format)
        for child in self.children.values():  # type: ignore
            child.write()
