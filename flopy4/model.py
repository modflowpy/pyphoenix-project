from abc import ABCMeta
from pathlib import Path
from typing import Any, Dict, Optional

from flopy4.block import MFBlock
from flopy4.ispec.gwf_nam import GwfNam
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
        mtype: Optional[str] = None,
        packages: Optional[Dict[str, MFPackage]] = None,
        nam: Optional[MFPackage] = None,
    ):
        self.name = name
        self.mempath = mempath
        self.mtype = mtype
        self._p = packages

        super().__init__(packages=packages)

    def __getattribute__(self, name: str) -> Any:
        self_type = type(self)

        if name + "6" in self_type.packages:
            return self.value[name]
            # return self.packages[name]

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
        packages = dict()
        members = cls.packages

        mempath = kwargs.pop("mempath", None)
        mtype = kwargs.pop("mtype", None)
        mname = strip(mempath.split("/")[-1])
        kwargs["mempath"] = f"{mempath}"
        kwargs["name"] = f"{mname}.nam"
        kwargs["mname"] = mname
        kwargs["ftype"] = "nam6"

        packages["nam6"] = GwfNam.load(f, **kwargs)

        MFModel.load_packages(members, packages["nam6"], packages, **kwargs)
        return cls(name=mname, mempath=mempath, mtype=mtype, packages=packages)

    @staticmethod
    def load_packages(
        members,
        blocks: Dict[str, MFBlock],
        packages: Dict[str, MFPackage],
        mempath,
        **kwargs,
    ):
        """Load model name file packages"""
        if "ftype" not in blocks.params["packages"]:
            # packages block was empty
            return
        kwargs.pop("mname", None)
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
                    kwargs["ftype"] = ftype.lower()
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

    def write(self, basepath, **kwargs):
        """Write the model to files."""
        path = Path(basepath)
        for p in self._p:
            if self._p[p].name.endswith(".nam"):
                with open(path / self._p[p].name, "w") as f:
                    self._p[p].write(f)
            else:
                with open(path / self._p[p].name, "w") as f:
                    self._p[p].write(f)
