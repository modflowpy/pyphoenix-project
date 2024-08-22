from abc import ABCMeta
from typing import Any, Dict, Optional

from flopy4.block import MFBlock
from flopy4.package import MFPackage, MFPackages
from flopy4.utils import strip


class MFModelMeta(type):
    def __new__(cls, clsname, bases, attrs):
        packages = dict()
        for attr_name, attr in attrs.items():
            if issubclass(type(attr), MFPackage):
                # attr.__doc__ = attr.description
                attr.name = attr_name
                attrs[attr_name] = attr
                packages[attr_name] = attr

        attrs["packages"] = MFPackages(packages)

        return super().__new__(cls, clsname, bases, attrs)


class MFModelMappingMeta(MFModelMeta, ABCMeta):
    # http://www.phyast.pitt.edu/~micheles/python/metatype.html
    pass


class MFModel(MFPackages, metaclass=MFModelMappingMeta):
    """
    MF6 model.

    Notes
    -----
    Needs MFList input type and then support for
    reading blocks as in package implementation.

    """

    def __init__(
        self,
        name: Optional[str] = None,
        mempath: Optional[str] = None,
        packages: Optional[Dict[str, Dict]] = None,
    ):
        self.name = name
        self.mempath = mempath

        super().__init__(packages=packages)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        if name + "6" in self_type.packages:
            return self.value[name]

        if name == "packages":
            return self.value

        return super().__getattribute__(name)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, MFModel):
            raise TypeError(f"Expected MFPackage, got {type(other)}")
        return super().__eq__(other)

    @property
    def value(self):
        """ """
        return MFPackages.value.fget(self)

    @classmethod
    def load(cls, f, **kwargs):
        """Load the model name file."""
        blocks = dict()
        packages = dict()
        members = cls.packages
        nam_members = type(cls.packages.nam6).blocks

        mempath = kwargs.pop("mempath", None)
        mname = strip(mempath.split("/")[-1])

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
                block = nam_members.get(name, None)
                if block is None:
                    continue
                f.seek(pos)
                blocks[name] = type(block).load(f, **kwargs)

        MFModel.load_packages(members, blocks, packages, mempath, **kwargs)
        return cls(name=mname, mempath=mempath, packages=packages)

    @staticmethod
    def load_packages(
        members,
        blocks: Dict[str, MFBlock],
        packages: Dict[str, MFPackage],
        mempath,
        **kwargs,
    ):
        """Load model name file packages"""
        model_shape = None
        assert "packages" in blocks
        for param_name, param in blocks["packages"].items():
            if param_name != "packages":
                continue
            assert "ftype" in param.value
            assert "fname" in param.value
            assert "pname" in param.value
            for i in range(len(param.value["ftype"])):
                ftype = param.value["ftype"][i]
                fname = param.value["fname"][i]
                pname = param.value["pname"][i]
                package = members.get(ftype.lower(), None)
                with open(fname, "r") as f:
                    kwargs["model_shape"] = model_shape
                    kwargs["mempath"] = f"{mempath}/{pname}"
                    packages[pname] = type(package).load(f, **kwargs)
                    if ftype.lower() == "dis6":
                        nlay = packages[pname].params["nlay"]
                        nrow = packages[pname].params["nrow"]
                        ncol = packages[pname].params["ncol"]
                        model_shape = (nlay, nrow, ncol)
                    elif ftype.lower() == "disv6":
                        nlay = packages[pname].params["nlay"]
                        ncpl = packages[pname].params["ncpl"]
                        model_shape = (nlay, ncpl)
                    elif ftype.lower() == "disu6":
                        nodes = packages[pname].params["nodes"]
                        model_shape = nodes

    def write(self, f, **kwargs):
        """Write the list to file."""
        pass
