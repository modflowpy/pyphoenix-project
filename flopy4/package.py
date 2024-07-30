from abc import ABCMeta
from io import StringIO
from itertools import groupby
from pprint import pformat
from typing import Any, Dict, Optional

from flopy4.block import MFBlock, MFBlockMeta, MFBlocks
from flopy4.param import MFParam, MFParams
from flopy4.utils import strip


def get_block(pkg_name, block_name, params):
    """
    Dynamically subclass `MFBlock`. The class' name is composed from
    the given package and block name. The class will have attributes
    according to the given parameter specification; parameter values
    are not yet initialized.
    """
    cls = MFBlockMeta(
        f"{pkg_name.title()}{block_name.title()}Block",
        (MFBlock,),
        params.copy(),
    )
    return cls(name=block_name, params=params)


class MFPackageMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFPackage":
            return super().__new__(cls, clsname, bases, attrs)

        # detect package name
        pkg_name = clsname.replace("Package", "")

        # add class attributes for the package parameter specification.
        # dynamically set each parameter's name and docstring.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attrs[attr_name] = attr
                params[attr_name] = attr

        # add class attributes for the package block specification.
        # subclass `MFBlock` dynamically with class name and params
        # as given in the block parameter specification.
        blocks = dict()
        for block_name, block_params in groupby(
            params.values(), lambda p: p.block
        ):
            block = get_block(
                pkg_name=pkg_name,
                block_name=block_name,
                params={param.name: param for param in block_params},
            )
            attrs[block_name] = block
            blocks[block_name] = block

        attrs["params"] = MFParams(params)
        attrs["blocks"] = MFBlocks(blocks)

        return super().__new__(cls, clsname, bases, attrs)


class MFPackageMappingMeta(MFPackageMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFPackage(MFBlocks, metaclass=MFPackageMappingMeta):
    """
    MF6 component package. Maps block names to blocks.


    Notes
    -----
    Subclasses are generated from Jinja2 templates to
    match packages as specified by definition files.


    TODO: reimplement with `ChainMap`?
    """

    def __init__(
        self,
        name: Optional[str] = None,
        blocks: Optional[Dict[str, Dict]] = None,
    ):
        self.name = name
        super().__init__(blocks=blocks)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        # shortcut to block value for instance attribute.
        # the class attribute is the block specification.
        if name in self_type.blocks:
            return self[name].value

        # shortcut to parameter value for instance attribute.
        # the class attribute is the parameter specification,
        # and dictionary access on the instance returns the
        # full `MFParam` instance.
        if name in self_type.params:
            return self._get_param_values()[name]

        # add .blocks attribute as an alias for .value, this
        # overrides the class attribute with the block spec.
        # also add a .params attribute, which is a flat dict
        # of all block parameter values.
        if name == "blocks":
            return self.value
        elif name == "params":
            return self._get_param_values()

        return super().__getattribute__(name)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __eq__(self, other):
        if not isinstance(other, MFPackage):
            raise TypeError(f"Expected MFPackage, got {type(other)}")
        return super().__eq__(other)

    def _get_params(self) -> Dict[str, MFParam]:
        """Get a flattened dictionary of member parameters."""
        return {
            param_name: param
            for block in self.values()
            for param_name, param in block.items()
        }

    def _get_param_values(self) -> Dict[str, Any]:
        """Get a flattened dictionary of parameter values."""
        return {
            param_name: param.value
            for param_name, param in self._get_params().items()
        }

    @property
    def value(self):
        """
        Get a dictionary of package block values. This is a
        nested mapping of block names to blocks, where each
        block is a mapping of parameter names to parameter
        values.
        """
        return MFBlocks.value.fget(self)

    @value.setter
    def value(self, value):
        """
        Set package block values from a nested dictionary,
        where each block value is a mapping of parameter
        names to parameter values.
        """

        if value is None or not any(value):
            return

        # coerce the block mapping to the spec and set defaults
        blocks = type(self).coerce(value.copy(), set_default=True)
        MFBlocks.value.fset(self, blocks)

    @classmethod
    def coerce(
        cls, blocks: Dict[str, MFBlock], set_default: bool = False
    ) -> Dict[str, MFBlock]:
        """
        Check that the dictionary contains only known blocks,
        raising an error if any unknown blocks are provided.

        Sets default values for any missing member parameters
        and ensures provided parameter types are as expected.
        """

        known = dict()
        for block_name, block_spec in cls.blocks.copy().items():
            block = blocks.pop(block_name, block_spec)
            block = type(block).coerce(block, set_default=set_default)
            known[block_name] = block

        # raise an error if we have any unrecognized blocks.
        # `MFPackage` strictly disallows unrecognized blocks.
        # for an arbitrary block collection, use `MFBlocks`.
        if any(blocks):
            raise ValueError(f"Unrecognized blocks:\n{pformat(blocks)}")

        return known

    @classmethod
    def load(cls, f, **kwargs):
        """Load the package from file."""
        blocks = dict()
        members = cls.blocks

        while True:
            pos = f.tell()
            line = f.readline()
            if line == "":
                break
            if line == "\n":
                continue
            line = strip(line).lower()
            words = line.split()
            key = words[0]
            if key == "begin":
                name = words[1]
                block = members.get(name, None)
                if block is None:
                    continue
                f.seek(pos)
                blocks[name] = type(block).load(f, **kwargs)

        return cls(blocks=blocks)

    def write(self, f, **kwargs):
        """Write the package to file."""
        super().write(f, **kwargs)
