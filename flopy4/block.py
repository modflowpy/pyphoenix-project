from abc import ABCMeta
from collections import UserDict
from dataclasses import asdict
from io import StringIO
from pprint import pformat
from typing import Any, Dict, Optional

from flopy4.array import MFArray
from flopy4.compound import MFKeystring, MFRecord
from flopy4.param import MFParam, MFParams
from flopy4.utils import find_upper, strip


def get_keystrings(members, name):
    return [
        m for m in members.values() if isinstance(m, MFKeystring) and name in m
    ]


def get_param(members, block_name, param_name):
    param = next(iter(get_keystrings(members, param_name)), None)
    if param is None:
        param = members.get(param_name)
        if param is None:
            raise ValueError(f"Invalid parameter: {param_name.upper()}")
        param.name = param_name
    param.block = block_name
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

        # add class attributes for the block parameter specification.
        # dynamically set each parameter's name, block and docstring.
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
    Likewise the parameter values are populated on load.
    They can also be initialized by passing a dictionary
    of names/values to `params` when calling `__init__`.
    Only recognized parameters (i.e. parameters known to
    the block specification) are allowed.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        index: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.index = index
        super().__init__(params=params)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        # shortcut to parameter value for instance attribute.
        # the class attribute is the parameter specification.
        if name in self_type.params:
            return self.value[name]

        # add .params attribute as an alias for .value, this
        # overrides the class attribute with the param spec.
        if name == "params":
            return self.value

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    @property
    def value(self):
        """Get a dictionary of block parameter values."""
        return super().value

    @value.setter
    def value(self, value):
        """Set block parameter values from a dictionary."""

        if value is None or not any(value):
            return

        params = dict()
        values = value.copy()

        # check provided parameters. if any are missing, set them
        # to default values. assume if a param name matches, its
        # type/value are ok (param setters should validate them).
        for param_name, param in type(self).params.copy().items():
            value = values.pop(param_name, None)
            value = param.default_value if value is None else value
            param.value = value
            params[param_name] = param

        # raise an error if we have any unrecognized parameters.
        # `MFBlock` strictly disallows unrecognized params. for
        # an arbitrary collection of parameters, use `MFParams`.
        if any(values):
            raise ValueError(f"Unknown parameters:\n{pformat(values)}")

        # populate internal dict and set attributes
        super().__init__(params=params)

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
                param = get_param(members, name, key)
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

        return cls(name=name, index=index, params=params)

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
        for block in self.values():
            block.write(f)
