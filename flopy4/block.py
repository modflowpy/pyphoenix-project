from abc import ABCMeta
from collections import UserDict
from dataclasses import asdict
from typing import Any

from flopy4.array import MFArray
from flopy4.parameter import MFParameter, MFParameters
from flopy4.utils import strip


class MFBlockMeta(type):
    def __new__(cls, clsname, bases, attrs):
        new = super().__new__(cls, clsname, bases, attrs)
        if clsname == "MFBlock":
            return new

        # add parameter specification as class attribute
        new.params = MFParameters(
            {
                k: v
                for k, v in attrs.items()
                if issubclass(type(v), MFParameter)
            }
        )
        return new


class MFBlockMappingMeta(MFBlockMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFBlock(MFParameters, metaclass=MFBlockMappingMeta):
    """
    MF6 input block. Maps parameter names to parameters.

    Notes
    -----
    This class is dynamically subclassed by `MFPackage`
    to match each block within a package parameter set.

    Supports dictionary and attribute access. The class
    attributes specify the block's parameters. Instance
    attributes contain both the specification and value.

    The block's name and index are discovered upon load.
    """

    def __init__(self, name=None, index=None, params=None):
        self.name = name
        self.index = index
        super().__init__(params)
        for key, param in self.items():
            setattr(self, key, param)

    def __getattribute__(self, name: str) -> Any:
        # shortcut to parameter value for instance attribute.
        # the class attribute is the full parameter instance.
        attr = super().__getattribute__(name)
        return attr.value if isinstance(attr, MFParameter) else attr

    @property
    def params(self) -> MFParameters:
        """Block parameters."""
        return self.data

    @classmethod
    def load(cls, f, **kwargs):
        name = None
        index = None
        found = False
        params = dict()
        members = cls.params

        while True:
            pos = f.tell()
            line = strip(f.readline()).lower()
            words = line.split()
            key = words[0]
            if key == "begin":
                found = True
                name = words[1]
                if len(words) > 2 and str.isdigit(words[2]):
                    index = words[2]
            elif key == "end":
                break
            elif found:
                param = members.get(key)
                if param is not None:
                    f.seek(pos)
                    spec = asdict(param.with_name(key).with_block(name))
                    kwargs = {**kwargs, **spec}
                    if type(param) is MFArray:
                        # TODO: inject from model somehow?
                        # and remove special handling here
                        kwargs["cwd"] = ""
                    params[key] = type(param).load(f, **kwargs)

        return cls(name, index, params)

    def write(self, f):
        index = self.index if self.index is not None else ""
        begin = f"BEGIN {self.name.upper()} {index}\n"
        end = f"END {self.name.upper()}\n"

        f.write(begin)
        for param in self.values():
            param.write(f)
        f.write(end)


class MFBlocks(UserDict):
    """Mapping of block names to blocks."""

    def __init__(self, blocks=None):
        super().__init__(blocks)
