from abc import ABC
from collections.abc import MutableMapping

from xattree import xattree

COMPONENTS = {}
"""MF6 component registry."""


@xattree
class Component(ABC, MutableMapping):
    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls

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

    def write(self) -> None:
        # TODO: write with jinja to file
        for child in self.children.values():  # type: ignore
            child.write()
