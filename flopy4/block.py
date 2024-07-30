from abc import ABCMeta
from collections import OrderedDict, UserDict
from dataclasses import asdict
from io import StringIO
from pprint import pformat
from typing import Any, Dict, Optional

from flopy4.array import MFArray
from flopy4.compound import MFKeystring, MFRecord, get_keystrings
from flopy4.param import MFParam, MFParams
from flopy4.scalar import MFScalar
from flopy4.utils import find_upper, strip


def get_param(params, block_name, param_name):
    """
    Find the first parameter in the collection with
    the given name, set its block name, and return it.
    """
    param = next(get_keystrings(params, param_name), None)
    if param is None:
        param = params.get(param_name)
        if param is None:
            raise ValueError(f"Invalid parameter: {param_name}")
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

        # if a parameter mapping is provided, coerce it to the
        # spec and set default values
        if params is not None:
            params = type(self).coerce(params, set_default=True)

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

    def __eq__(self, other):
        return super().__eq__(other)

    @property
    def value(self):
        """Get a dictionary of block parameter values."""
        return MFParams.value.fget(self)

    @value.setter
    def value(self, value):
        """Set block parameter values from a dictionary."""

        if value is None or not any(value):
            return

        # coerce the parameter mapping to the spec and set defaults
        params = type(self).coerce(value.copy(), set_default=True)
        MFParams.value.fset(self, params)

    @classmethod
    def coerce(
        cls, params: Dict[str, Any], set_default: bool = False
    ) -> Dict[str, MFParam]:
        """
        Check that the dictionary contains only expected parameters,
        raising an error if any unrecognized parameters are provided.

        Dictionary values may be subclasses of `MFParam` or values
        provided directly. If the former, this function optionally
        sets default values for any missing member parameters.
        """

        known = dict()
        for param_name, param_spec in cls.params.copy().items():
            param = params.pop(param_name, param_spec)

            # make sure param is of expected type. set a
            # default value if enabled and none provided.
            spec_type = type(param_spec)
            real_type = type(param)
            if issubclass(real_type, MFParam):
                if param.value is None and set_default:
                    param.value = param_spec.default_value
            elif issubclass(spec_type, MFScalar) and real_type == spec_type.T:
                param = spec_type(value=param, **asdict(param_spec))
            else:
                raise TypeError(
                    f"Expected '{param_name}' as {spec_type}, got {real_type}"
                )

            known[param_name] = param

        # raise an error if we have any unknown parameters.
        # `MFBlock` strictly disallows unrecognized params,
        # for arbitrary parameter collections use `MFParams`.
        if any(params):
            raise ValueError(f"Unrecognized parameters:\n{pformat(params)}")

        return known

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
                if param is None:
                    continue
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
    """
    Mapping of block names to blocks. Acts like a
    dictionary, also supports named attribute access.
    """

    def __init__(self, blocks=None):
        MFBlocks.assert_blocks(blocks)
        super().__init__(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        if not isinstance(other, MFBlocks):
            raise TypeError(f"Expected MFBlocks, got {type(other)}")
        return OrderedDict(sorted(self.value)) == OrderedDict(
            sorted(other.value)
        )

    @staticmethod
    def assert_blocks(blocks):
        """
        Raise an error if any of the given items are
        not subclasses of `MFBlock`.
        """
        if not blocks:
            return
        elif isinstance(blocks, dict):
            blocks = blocks.values()
        not_blocks = [
            b
            for b in blocks
            if b is not None and not issubclass(type(b), MFBlock)
        ]
        if any(not_blocks):
            raise TypeError(f"Expected MFBlock subclasses, got {not_blocks}")

    @property
    def value(self) -> Dict[str, Dict[str, Any]]:
        """
        Get a dictionary of package block values. This is a
        nested mapping of block names to blocks, where each
        block is a mapping of parameter names to parameter
        values.
        """
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict[str, Dict[str, Any]]]):
        """Set block values from a nested dictionary."""

        if value is None or not any(value):
            return

        blocks = value.copy()
        MFBlocks.assert_blocks(blocks)
        self.update(blocks)
        for key, block in self.items():
            setattr(self, key, block)

    def write(self, f, **kwargs):
        """Write the blocks to file."""
        for block in self.values():
            block.write(f, **kwargs)
