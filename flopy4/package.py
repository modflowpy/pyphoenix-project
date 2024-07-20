from abc import ABCMeta
from collections import UserDict
from itertools import groupby
from typing import Any

from flopy4.block import MFBlock, MFBlockMeta, MFBlocks
from flopy4.parameter import MFParameter, MFParameters
from flopy4.utils import strip


def get_block(clsname, params):
    return MFBlockMeta(clsname, (MFBlock,), params)(params=params)


class MFPackageMeta(type):
    def __new__(cls, clsname, bases, attrs):
        new = super().__new__(cls, clsname, bases, attrs)
        if clsname == "MFPackage":
            return new

        # add parameter and block specification as class
        # attributes. subclass mfblock dynamically based
        # on each block parameter specification.
        pkg_name = clsname.replace("Package", "")
        params = MFParameters(
            {
                k: v.with_name(k)
                for k, v in attrs.items()
                if issubclass(type(v), MFParameter)
            }
        )
        new.params = params
        new.blocks = MFBlocks(
            {
                block_name: get_block(
                    clsname=f"{pkg_name.title()}{block_name.title()}Block",
                    params={p.name: p for p in block},
                )
                for block_name, block in groupby(
                    params.values(), lambda p: p.block
                )
            }
        )
        return new


class MFPackageMappingMeta(MFPackageMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFPackage(UserDict, metaclass=MFPackageMappingMeta):
    """
    MF6 model or simulation component package.


    TODO: reimplement with `ChainMap`?
    """

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if name == "data":
            return value

        # shortcut to parameter value for instance attribute.
        # the class attribute is the full parameter instance.
        params = {
            param_name: param
            for block in self.data.values()
            for param_name, param in block.items()
        }
        param = params.get(name)
        return params[name].value if param is not None else value

    @property
    def params(self) -> MFParameters:
        """Package parameters."""
        return MFParameters(
            {
                name: param
                for block in self.data
                for name, param in block.items()
            }
        )

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

        pkg = cls()
        pkg.update(blocks)
        return pkg

    def write(self, f):
        """Write the package to file."""
        for block in self.data.values():
            block.write(f)
