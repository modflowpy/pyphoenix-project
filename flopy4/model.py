from abc import ABCMeta
from typing import Any, Dict, Optional

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
        """Load the package from file."""
        packages = dict()
        members = cls.packages

        mempath = kwargs.pop("mempath", None)
        mname = strip(mempath.split("/")[-1])
        model_shape = None

        while True:
            # pos = f.tell()
            line = f.readline()
            if line == "":
                break
            if line == "\n":
                continue
            line = strip(line).lower()
            words = line.split()
            # TODO: Temporary code. Reimplement below to load
            #       dfn block specification with MFList support
            if words[0] == "begin" and words[1] == "packages":
                count = 0
                while True:
                    count += 1
                    line = f.readline()
                    line = strip(line).lower()
                    words = line.split()
                    if words[0] == "end":
                        break
                    elif len(words) > 1:
                        ptype = words[0]
                        fpth = words[1]
                        # TODO: pname should be type (remove trailing 6)
                        #       if base (not multi-instance see example
                        #       spec/ipkg/gwf_ic.v2.py)
                        if len(words) > 2:
                            pname = words[2]
                        else:
                            pname = f"{ptype}-{count}"
                    package = members.get(ptype, None)
                    with open(fpth, "r") as f_pkg:
                        kwargs["model_shape"] = model_shape
                        kwargs["mempath"] = f"{mempath}/{pname}"
                        packages[pname] = type(package).load(f_pkg, **kwargs)
                        if ptype == "dis6":
                            nlay = packages[pname].params["nlay"]
                            nrow = packages[pname].params["nrow"]
                            ncol = packages[pname].params["ncol"]
                            model_shape = (nlay, nrow, ncol)
                        elif ptype == "disv6":
                            nlay = packages[pname].params["nlay"]
                            ncpl = packages[pname].params["ncpl"]
                            model_shape = (nlay, ncpl)
                        elif ptype == "disu6":
                            nodes = packages[pname].params["nodes"]
                            model_shape = nodes

        return cls(name=mname, mempath=mempath, packages=packages)
