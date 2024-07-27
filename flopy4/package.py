from abc import ABCMeta
from io import StringIO
from itertools import groupby
from typing import Any

from flopy4.block import MFBlock, MFBlockMeta, MFBlocks
from flopy4.param import MFParam, MFParams
from flopy4.utils import strip


def get_block(pkg_name, block_name, params):
    cls = MFBlockMeta(
        f"{pkg_name.title()}{block_name.title()}Block",
        (MFBlock,),
        params.copy(),
    )
    return cls(name=block_name)


class MFPackageMeta(type):
    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFPackage":
            return super().__new__(cls, clsname, bases, attrs)

        # detect package name
        pkg_name = clsname.replace("Package", "")

        # add parameter and block specification as class
        # attributes. subclass mfblock dynamically based
        # on each block parameter specification.
        params = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFParam):
                attr.__doc__ = attr.description
                attr.name = attr_name
                attrs[attr_name] = attr
                params[attr_name] = attr
        params = MFParams(params)
        blocks = MFBlocks(
            {
                block_name: get_block(
                    pkg_name=pkg_name,
                    block_name=block_name,
                    params={p.name: p for p in block},
                )
                for block_name, block in groupby(
                    params.values(), lambda p: p.block
                )
            }
        )

        attrs["params"] = params
        attrs["blocks"] = blocks
        for block_name, block in blocks.items():
            attrs[block_name] = block

        return super().__new__(cls, clsname, bases, attrs)


class MFPackageMappingMeta(MFPackageMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFPackage(MFBlocks, metaclass=MFPackageMappingMeta):
    """
    MF6 model or simulation component package.

    TODO: reimplement with `ChainMap`?
    """

    def __init__(self, blocks=None):
        super().__init__(blocks)

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        # shortcut to block value for instance attribute.
        # the class attribute is the block specification.
        if name in self_type.blocks:
            return self[name].value

        # shortcut to parameter value for instance attribute.
        # the class attribute is the parameter specification.
        if name in self_type.params:
            return self._param_values()[name]

        # define .blocks and .params attributes with values,
        # overriding the class attributes with specification
        if name == "blocks":
            return self.value
        if name == "params":
            return self._param_values()

        return super().__getattribute__(name)

    def _param_values(self):
        # todo cache
        return MFParams(
            {
                param_name: param.value
                for block in self.values()
                for param_name, param in block.items()
            }
        )

    @property
    def value(self):
        return MFBlocks({k: v.value for k, v in self.items()})

    @value.setter
    def value(self, value):
        # todo set from dict of blocks
        pass

    @classmethod
    def load(cls, f):
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
                block = members.get(name)
                if block is not None:
                    f.seek(pos)
                    blocks[name] = type(block).load(f)

        return cls(blocks)

    def write(self, f):
        """Write the package to file."""
        super().write(f)
