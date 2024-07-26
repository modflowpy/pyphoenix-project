from abc import ABCMeta
from collections import UserDict
from dataclasses import asdict
from io import StringIO
from pprint import pformat
from typing import Any

from flopy4.array import MFArray
from flopy4.compound import MFKeystring, MFRecord
from flopy4.param import MFParam, MFParams
from flopy4.utils import find_upper, strip


def get_keystrings(members, name):
    return [
        m for m in members.values() if isinstance(m, MFKeystring) and name in m
    ]


def get_param(members, name, block):
    param = next(iter(get_keystrings(members, name)), None)
    if param is None:
        param = members.get(name)
        if param is None:
            raise ValueError(f"Invalid parameter: {name.upper()}")
        param.name = name
    param.block = block
    return param


class MFBlockMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFBlock":
            return super().__new__(cls, clsname, bases, attrs)

        # detect block name
        block_name = (
            clsname[list(find_upper(clsname))[1] :]
            .replace("Block", "")
            .lower()
        )

        # add parameter specification as class attribute.
        # dynamically set the parameters' name and block.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attr.block = block_name
                attrs[attr_name] = attr
                params[attr_name] = attr
        attrs["params"] = MFParams(params)

        return super().__new__(cls, clsname, bases, attrs)


class MFBlockMappingMeta(MFBlockMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFBlock(MFParams, metaclass=MFBlockMappingMeta):
    """
    MF6 input block. Maps parameter names to parameters.

    Notes
    -----
    This class is dynamically subclassed by `MFPackage`
    to match each block within a package parameter set.

    Supports dictionary and attribute access. The class
    attributes specify the block's parameters. Instance
    attributes expose the parameter value.

    The block's name and index are discovered upon load.
    """

    def __init__(self, name=None, index=None, params=None):
        self.name = name
        self.index = index
        super().__init__(params)

    def __getattribute__(self, name: str) -> Any:
        if name == "data":
            return super().__getattribute__(name)

        if name == "params":
            return MFParams({k: v.value for k, v in self.data.items()})

        param = self.data.get(name)
        return (
            param.value
            if param is not None
            else super().__getattribute__(name)
        )

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    @classmethod
    def load(cls, f, **kwargs):
        """Load the block from file."""
        name = None
        index = None
        found = False
        params = dict()
        members = cls.params

        while True:
            pos = f.tell()
            line = f.readline()
            if line == "":
                raise ValueError("Early EOF, aborting")
            if line == "\n":
                continue
            words = strip(line).lower().split()
            key = words[0]
            if key == "begin":
                found = True
                name = words[1]
                if len(words) > 2 and str.isdigit(words[2]):
                    index = int(words[2])
            elif key == "end":
                break
            elif found:
                param = get_param(members, key, name)
                if param is not None:
                    f.seek(pos)
                    spec = asdict(param)
                    kwrgs = {**kwargs, **spec}
                    ptype = type(param)
                    if ptype is MFArray:
                        # TODO: inject from model somehow?
                        # and remove special handling here
                        kwrgs["cwd"] = ""
                    if ptype is MFRecord:
                        kwrgs["params"] = param.data.copy()
                    if ptype is MFKeystring:
                        kwrgs["params"] = param.data.copy()
                    params[param.name] = ptype.load(f, **kwrgs)

        return cls(name, index, params)

    def write(self, f):
        """Write the block to file."""
        index = self.index if self.index is not None else ""
        begin = f"BEGIN {self.name.upper()} {index}\n"
        end = f"END {self.name.upper()}\n"

        f.write(begin)
        super().write(f)
        f.write(end)


class MFBlocks(UserDict):
    """Mapping of block names to blocks."""

    def __init__(self, blocks=None):
        super().__init__(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def __repr__(self):
        return pformat(self.data)

    def write(self, f):
        """Write the blocks to file."""
        for block in self.data.values():
            block.write(f)
