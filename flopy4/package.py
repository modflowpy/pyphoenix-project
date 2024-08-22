from abc import ABCMeta
from collections import OrderedDict, UserDict
from io import StringIO
from itertools import groupby
from keyword import kwlist
from pprint import pformat
from typing import Any, Dict, Optional
from warnings import warn

from flopy4.block import MFBlock, MFBlockMeta, MFBlocks, collect_params
from flopy4.param import MFParam, MFParams
from flopy4.utils import strip


def collect_blocks(
    params: Dict[str, MFParam],
    package_name: str,
) -> Dict[str, MFBlock]:
    """
    Collect the block specification for the given dictionary of
    parameters. Subclass `MFBlock` dynamically and set the name
    of the block subclass by concatenating the package name and
    the block name, with a trailing "Block".
    """

    blocks = dict()
    for block_name, block_params in groupby(
        params.values(), lambda p: p.block
    ):
        block = make_block(
            params={param.name: param for param in block_params},
            block_name=block_name,
            package_name=package_name,
        )
        blocks[block_name] = block
    return blocks


def make_block(
    params: Dict[str, MFParam],
    block_name: str,
    package_name: str,
) -> MFBlock:
    """
    Dynamically subclass `MFBlock` and return an instance of the new
    class. The class will have attributes according to the parameter
    specification provided, but parameter values are not initialized
    until they are loaded from an input file or set manually.
    """

    cls_name = f"{package_name.title()}{block_name.title()}Block"
    cls = MFBlockMeta(
        cls_name,
        (MFBlock,),
        params.copy(),
    )
    return cls(name=block_name, params=params)


class MFPackageMeta(type):
    """
    Modify the creation of `MFPackage` subclasses to search the package's
    class attributes, find any which are MF6 input parameters, set up those
    parameters' attributes, dynamically create a set of `MFBlock`s to match,
    and attach `.params` and `.blocks` attributes as the parameter and block
    specification, respectively.

    TODO: specify parameters via `attrs` with leading underscore, to
    avoid collisions with Python keywords. Then we only attach a non-
    underscored attribute if there is no collision. Parameters whose
    name collides with a reserved keyword are accessible only by way
    of the package's dictionary API.
    """

    def __new__(cls, clsname, bases, attrs):
        if clsname == "MFPackage":
            return super().__new__(cls, clsname, bases, attrs)

        # infer package name
        package_name = clsname.replace("Package", "")

        # collect parameters
        params = collect_params(attrs)
        attrs["params"] = MFParams(params)
        for name, param in params.items():
            if name in kwlist:
                warn(f"Parameter name is a reserved keyword: {name}")
            else:
                attrs[name] = param

        # collect blocks
        blocks = collect_blocks(params, package_name)
        attrs["blocks"] = MFBlocks(blocks)
        for name, block in blocks.items():
            if name in kwlist:
                warn(f"Block name is a reserved keyword: {name}")
            else:
                attrs[name] = block

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


    TODO: pull
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
        params = {}

        mempath = kwargs.pop("mempath", None)
        kwargs.pop("modeltype", None)

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
                kwargs["blk_params"] = params
                kwargs["mempath"] = f"{mempath}/{name}"
                blocks[name] = type(block).load(f, **kwargs)
                if name == "options" or name == "dimensions":
                    params[name] = blocks[name].params

        return cls(blocks=blocks)

    def write(self, f, **kwargs):
        """Write the package to file."""
        super().write(f, **kwargs)


class MFPackages(UserDict):
    """
    Mapping of package names to packages. Acts like a
    dictionary, also supports named attribute access.
    """

    def __init__(self, packages=None):
        MFPackages.assert_packages(packages)
        super().__init__(packages)
        for key, package in self.items():
            setattr(self, key, package)

    def __repr__(self):
        return pformat(self.data)

    def __eq__(self, other):
        if not isinstance(other, MFPackages):
            raise TypeError(f"Expected MFPackages, got {type(other)}")
        return OrderedDict(sorted(self.value)) == OrderedDict(
            sorted(other.value)
        )

    @staticmethod
    def assert_packages(packages):
        """
        Raise an error if any of the given items are
        not subclasses of `MFPackage`.
        """
        if not packages:
            return
        elif isinstance(packages, dict):
            packages = packages.values()
        not_packages = [
            p
            for p in packages
            if p is not None and not issubclass(type(p), MFPackage)
        ]
        if any(not_packages):
            raise TypeError(
                f"Expected MFPackage subclasses, got {not_packages}"
            )

    @property
    def value(self) -> Dict[str, Dict[str, Any]]:
        """
        Get a dictionary of package package values. This is a
        nested mapping of package names to packages.
        ....
        """
        return {k: v.value for k, v in self.items()}

    @value.setter
    def value(self, value: Optional[Dict[str, Dict[str, Any]]]):
        """Set package values from a nested dictionary."""

        if value is None or not any(value):
            return

        packages = value.copy()
        MFPackages.assert_packages(packages)
        self.update(packages)
        for key, package in self.items():
            setattr(self, key, package)
