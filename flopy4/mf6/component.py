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

    def __attrs_post_init__(self):
        self._where = type(self).__xattree__["where"]

    def __getitem__(self, key):
        data = getattr(self, self._where)
        return data.children[key]

    def __setitem__(self, key, value):
        data = getattr(self, self._where)
        if key in data.children:
            data.update({key: value})
        else:
            data = data.assign({key: value})
        setattr(self, self._where, data)

    def __delitem__(self, key):
        data = getattr(self, self._where)
        data = data.drop_nodes(key)
        setattr(self, self._where, data)

    def __iter__(self):
        data = getattr(self, self._where)
        return iter(data.children)

    def __len__(self):
        data = getattr(self, self._where)
        return len(data.children)
