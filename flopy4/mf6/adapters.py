import re
from typing import Optional
from warnings import warn

import numpy as np
from flopy.datbase import DataInterface, DataListInterface, DataType
from flopy.discretization import StructuredGrid
from flopy.discretization.grid import Grid
from flopy.discretization.modeltime import ModelTime
from flopy.export.utils import model_export, package_export
from flopy.mbase import ModelInterface
from flopy.pakbase import PackageInterface
from flopy.plot.plotutil import PlotUtilities
from xattree import Xattribute, get_xatspec

from flopy4.mf6.model import Model
from flopy4.mf6.package import Package


class Flopy3Model(ModelInterface):
    def __init__(
        self,
        model: Model,
        modelgrid: Optional[Grid] = None,
        modeltime: Optional[ModelTime] = None,
        ims: Optional[Package] = None,
        crs: Optional[int] = None,
    ):
        self._model = model
        self._grid = modelgrid
        self._time = modeltime
        self._ims = ims
        self._plist = list()
        self.type = "Model"
        self.name = model.name  # type: ignore

        if self._model is None:
            raise Exception("Model Interface needs a model")

        lenuni = "unknown"
        xoff = 0.0
        yoff = 0.0
        angrot = 0.0

        if self._grid is None:
            if hasattr(model, "dis"):
                if model.dis.length_units:
                    lenuni = model.dis.length_units.data
                if model.dis.xorigin:
                    xoff = model.dis.xorigin.data
                if model.dis.yorigin:
                    yoff = model.dis.yorigin.data
                if model.dis.angrot:
                    yoff = model.dis.angrot.data

                self._grid = StructuredGrid(
                    delc=model.dis.delc.data,
                    delr=model.dis.delr.data,
                    top=model.dis.top.data,
                    botm=model.dis.botm.data,
                    idomain=model.dis.idomain.data,
                    lenuni=lenuni,
                    crs=crs,
                    prjfile=None,
                    xoff=xoff,
                    yoff=yoff,
                    angrot=angrot,
                    nlay=model.dis.nlay,
                    nrow=model.dis.nrow,
                    ncol=model.dis.ncol,
                    laycbd=None,
                )

        if hasattr(model, "children"):
            for c in model.children:
                p_fp3 = Flopy3Package(
                    package=model.children[c],
                    model=self,
                    modeltime=modeltime,
                )
                self._plist.append(p_fp3)

    @property
    def modeltime(self):
        return self._time

    @property
    def modelgrid(self):
        return self._grid

    @property
    def packagelist(self):
        return self._plist

    @property
    def namefile(self):
        return ""

    @property
    def model_ws(self):
        return ""

    @property
    def exe_name(self):
        return ""

    @property
    def version(self):
        return ""

    @property
    def solver_tols(self):
        """
        Solver inner hclose and rclose values.
        """
        if self._ims is not None:
            return self._ims.inner_hclose, self._ims.inner_rclose

        return None

    @property
    def laytyp(self):
        """
        Layering type.
        """
        if "npf" in self._model.data:
            return self._model.data["npf"].icelltype

        return None

    @property
    def hdry(self):
        """
        Dry cell value.
        """
        return -1e30

    @property
    def hnoflo(self):
        """
        No-flow cell value.
        """
        return 1e30

    @property
    def verbose(self):
        return True

    @property
    def laycbd(self):
        """
        Quasi-3D confining bed. Not supported in MODFLOW 6.
        """
        return None

    def get_package_list(self, ftype=None):
        """
        Get a list of all the package names.
        """
        return [p.name for p in self._plist]

    def get_package(self, name=None):
        for p in self._plist:
            if p.name == name.upper():
                return p
        return None

    def plot(self, packages: Optional[list] = None, **kwargs):
        return PlotUtilities._plot_model_helper(self, SelPackList=packages, **kwargs)

    def export(self, f, **kwargs):
        return model_export(f, self, **kwargs)


class Flopy3Package(PackageInterface):
    def __init__(
        self,
        package: Package,
        model: Optional[Flopy3Model] = None,
        modelgrid: Optional[Grid] = None,
        modeltime: Optional[ModelTime] = None,
    ):
        self._model = model
        if hasattr(package, "data"):
            self._data = package.data
        else:
            raise Exception("Input package has no data")
        self._spec = get_xatspec(type(package)).flat
        if modelgrid:
            self._grid = modelgrid
        elif model:
            self._grid = model.modelgrid
        else:
            raise Exception("Input package needs grid")
        self._time = modeltime
        self._dlist = list()

        for a in self._data.attrs:
            if a == "host":
                continue
            if (
                self._data.attrs[a] is not None
                and a in self._spec
                and self._spec[a].type is not None
            ):
                d_fp3 = Flopy3Data(
                    data=self._data.attrs[a],
                    spec=self._spec[a],
                    name=a,
                    modelname=self.parent,
                    modelgrid=self._grid,
                    modeltime=modeltime,
                )
                self.__dict__[f"{a}"] = d_fp3
                self._dlist.append(d_fp3)

        for v in self._data.data_vars:
            if (
                self._data.data_vars[v] is not None
                and v in self._spec
                and self._spec[v].type is not None
            ):
                d_fp3 = Flopy3Data(
                    data=self._data.data_vars[v],
                    spec=self._spec[v],
                    name=v,
                    modelname=self.parent,
                    modelgrid=self._grid,
                    modeltime=modeltime,
                )
                self.__dict__[f"{v}"] = d_fp3
                self._dlist.append(d_fp3)

    @property
    def name(self):
        # or upper() or title()
        return self._data.name

    @name.setter
    def name(self, name):
        """Package name"""
        assert False, "Unsupported function to set the package name"

    @property
    def parent(self):
        return self._model

    @parent.setter
    def parent(self, parent):
        """Parent package"""
        assert False, "Unsupported function to set the parent"

    @property
    def package_type(self):
        return re.sub(r"\d+$", "", self._data.name).upper()

    @property
    def data_list(self):
        return self._dlist

    @property
    def plottable(self):
        return True

    @property
    def has_stress_period_data(self):
        # TODO oc returns true? is stress package?
        return "nper" in self._data.dims

    def check(self, f=None, verbose=True, level=1, checktype=None):
        """
        Check package data for common errors.
        """
        return None

    def plot(self, **kwargs):
        return PlotUtilities._plot_package_helper(self, **kwargs)

    def export(self, f, **kwargs):
        return package_export(f, self, **kwargs)


class Flopy3Data(DataInterface):
    def __init__(
        self,
        data,
        spec: Xattribute,
        name: Optional[str] = None,
        modelname: Optional[str] = None,
        modelgrid: Optional[Grid] = None,
        modeltime: Optional[ModelTime] = None,
    ):
        assert data is not None
        assert spec is not None
        assert spec.type is not None
        assert hasattr(spec.type, "__name__")
        self._name = name
        self._modelname = modelname
        self._grid = modelgrid
        self._time = modeltime
        self._data = data
        self._spec = spec

    # class DataType(Enum):
    #    array2d = 1 #  e.g. nrow, ncol
    #    array3d = 2 #  e.g. nlay, nrow, ncol
    #    transient2d = 3  # nper, nodes (grid)
    #    transient3d = 4  # nper, nrow, ncol (layer)
    #    list = 5
    #    transientlist = 6
    #    scalar = 7
    #    transientscalar = 8
    # TODO: how to handle transient data, list input
    @property
    def data_type(self):
        match self._spec.type.__name__:
            case "bool" | "float" | "integer":
                return DataType.scalar
            case "ndarray":
                if "nper" in self._data.dims:
                    if self._data.ndim == 2:
                        if "nnodes" in self._data.dims:
                            return DataType.transient2d  # nodes?
                    if self._data.ndim == 3:
                        return DataType.transient3d  # ncpl?
                    if self._data.ndim == 4:
                        return DataType.transient2d  # nodes?
                else:
                    if self._data.ndim == 1:
                        if "nnodes" in self._data.dims:
                            return DataType.array3d
                    if self._data.ndim == 2:
                        return DataType.array2d
                    if self._data.ndim == 3:
                        return DataType.array3d
            # TODO: boundname, auxvar arrays of strings?
            case _:
                warn(f"UNMATCHED data_type {self._name}: {self._spec.type.__name__}", UserWarning)

    @property
    def dtype(self):
        if self._spec.type.__name__ == "ndarray":
            if self._data.data.dtype == np.dtype("float64"):
                return np.float64
            elif self._data.data.dtype == np.dtype("int64"):
                return np.int64
            elif self._data.data.dtype == np.dtype("int32"):
                return np.int32
        return self._spec.type.__name__

    @property
    def array(self):
        if self._spec.type.__name__ == "ndarray":
            if "nnodes" in self._data.dims:
                if "nper" in self._data.dims:
                    shape = (
                        self._time.nper,
                        self._grid.nnodes,
                    )
                else:
                    shape = (
                        self._grid.nlay,
                        self._grid.nrow,
                        self._grid.ncol,
                    )

                return self._data.data.reshape(shape)
            else:
                return self._data.data
        return None

    @property
    def name(self):
        return self._name

    @property
    def model(self):
        return self._modelname

    @property
    def plottable(self):
        if self.data_type == DataType.scalar:
            return False
        return True


class Flopy3ListData(DataListInterface):
    @property
    def package(self):
        pass

    @property
    def to_array(self, kper=0, mask=False):
        pass

    @property
    def masked_4D_arrays_itr(self):
        pass
