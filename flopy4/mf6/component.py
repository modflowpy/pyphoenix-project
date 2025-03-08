from abc import ABC

COMPONENTS = {}
"""MF6 component registry."""


class Component(ABC):
    @classmethod
    def __attrs_init_subclass__(cls):
        COMPONENTS[cls.__name__.lower()] = cls
