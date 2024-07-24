from abc import ABCMeta
from collections import UserDict
from dataclasses import asdict
from io import StringIO
from typing import Any

from flopy4.array import MFArray
from flopy4.compound import MFKeystring, MFRecord
from flopy4.param import MFParam, MFParams
from flopy4.utils import find_upper, strip


def single_keystring(members):
    params = list(members.values())
    return len(params) == 1 and isinstance(params[0], MFKeystring)


def get_param(members, key):
    return (
        list(members.values())[0]
        if single_keystring(members)
        else members.get(key)
    )


class MFBlockMeta(type):
    def __new__(cls, clsname, bases, attrs):
        new = super().__new__(cls, clsname, bases, attrs)
        if clsname == "MFBlock":
            return new

        # detect block name
        block_name = (
            clsname[list(find_upper(clsname))[1] :]
            .replace("Block", "")
            .lower()
        )

        # add parameter specification class attributes
        params = {
            k: v.with_name(k).with_block(block_name)
            for k, v in attrs.items()
            if issubclass(type(v), MFParam)
        }
        if len([p for p in params if isinstance(p, MFKeystring)]) > 1:
            raise ValueError("Only one keystring allowed per block")
        for key, param in params.items():
            setattr(new, key, param)
        new.params = MFParams(params)

        return new


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
    attributes contain both the specification and value.

    The block's name and index are discovered upon load.
    """

    def __init__(self, name=None, index=None, params=None):
        self.name = name
        self.index = index
        super().__init__(params)

    def __getattribute__(self, name: str) -> Any:
        # shortcut to parameter value for instance attribute.
        # the class attribute is the full parameter instance.
        attr = super().__getattribute__(name)
        return attr.value if isinstance(attr, MFParam) else attr

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    @property
    def params(self) -> MFParams:
        """Block parameters."""
        return self.data

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
                param = get_param(members, key)
                if param is not None:
                    f.seek(pos)
                    spec = asdict(param.with_name(key).with_block(name))
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
                    params[key] = ptype.load(f, **kwrgs)

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
