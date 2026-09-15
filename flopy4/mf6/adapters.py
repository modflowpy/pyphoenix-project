import re
import types
from typing import Optional, Union, get_args, get_origin
from warnings import warn

import attrs
import numpy as np
from flopy.datbase import DataInterface, DataListInterface, DataType
from flopy.discretization.grid import Grid
from flopy.discretization.modeltime import ModelTime
from flopy.export.utils import model_export, package_export
from flopy.mbase import ModelInterface
from flopy.pakbase import PackageInterface
from flopy.plot.plotutil import PlotUtilities

from flopy4.attrs_xarray import attrs_to_dataset
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package


def _to_numpy(val):
    """Extract numpy data from a value (handles xr.DataArray, ndarray, or scalar)."""
    if hasattr(val, "data") and hasattr(val, "dims"):
        return val.data  # xr.DataArray
    return np.asarray(val) if val is not None else val


# The only runtime types Flopy3Data's data_type/dtype/array properties
# know how to dispatch on.
_LEAF_TYPES = (bool, int, float, str, np.ndarray)


def _resolve_leaf_type(annotation) -> "type | None":
    """Unwrap `Optional[...]` and a parameterized generic (e.g.
    `NDArray[np.float64]`) down to the concrete runtime type
    `Flopy3Data` dispatches on (`bool`/`int`/`float`/`str`/`np.ndarray`).

    Returns `None` for anything else (a nested attrs/Component type,
    `Path`, `datetime`, `Record`, a bare `dict`/`list` period field, ...)
    -- those aren't representable as a single flopy3 `Data` leaf.
    """
    tp = annotation
    if tp is None:
        return None
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) != 1:
            return None
        tp = args[0]
        origin = get_origin(tp)
    resolved = origin if origin is not None else tp
    if isinstance(resolved, type) and issubclass(resolved, _LEAF_TYPES):
        return resolved
    return None


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
                    lenuni = _to_numpy(model.dis.length_units)
                if model.dis.xorigin:
                    xoff = _to_numpy(model.dis.xorigin)
                if model.dis.yorigin:
                    yoff = _to_numpy(model.dis.yorigin)
                if model.dis.angrot:
                    yoff = _to_numpy(model.dis.angrot)

                self._grid = model.dis.to_grid()
                self._grid.legacy = True

        if hasattr(model, "_children"):
            for package in model._children.values():
                if not isinstance(package, Package):
                    continue
                p_fp3 = Flopy3Package(
                    package=package,
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
        npf = getattr(self._model, "npf", None)
        if npf is not None:
            return npf.icelltype
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
        self._package = package
        self._dataset = attrs_to_dataset(package)
        if modelgrid:
            self._grid = modelgrid
        elif model:
            self._grid = model.modelgrid
        else:
            raise Exception("Input package needs grid")
        self._time = modeltime
        self._dlist = list()

        field_by_name = {f.name: f for f in attrs.fields(type(package))}

        for a, value in self._dataset.attrs.items():
            field = field_by_name.get(a)
            if field is None or value is None:
                continue
            leaf_type = _resolve_leaf_type(field.type)
            if leaf_type is None:
                continue
            d_fp3 = Flopy3Data(
                data=value,
                leaf_type=leaf_type,
                name=a,
                modelname=self.parent,
                modelgrid=self._grid,
                modeltime=modeltime,
            )
            self.__dict__[f"{a}"] = d_fp3
            self._dlist.append(d_fp3)

        for v, data_array in self._dataset.data_vars.items():
            field = field_by_name.get(v)
            if field is None:
                continue
            d_fp3 = Flopy3Data(
                data=data_array,
                leaf_type=np.ndarray,
                name=str(v),
                modelname=self.parent,
                modelgrid=self._grid,
                modeltime=modeltime,
            )
            self.__dict__[f"{v}"] = d_fp3
            self._dlist.append(d_fp3)

    @property
    def name(self):
        # or upper() or title()
        return self._package.name

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
        return re.sub(r"\d+$", "", self._package.name).upper()

    @property
    def data_list(self):
        return self._dlist

    @property
    def plottable(self):
        return True

    @property
    def has_stress_period_data(self):
        # Stress-period recarray packages (CHD, DRN, etc.)
        if getattr(self._package, "_stress_period_data", None) is not None:
            return True
        # Any other "period"-block field (covers OC's own
        # _stress_period_data too, redundantly with the check above -- kept
        # as a generic fallback for any period field shape).
        try:
            for f in attrs.fields(type(self._package)):
                if f.metadata.get("block") == "period":
                    attr_name = f.alias if (f.alias and f.name.startswith("_")) else f.name
                    if getattr(self._package, attr_name, None) is not None:
                        return True
        except attrs.exceptions.NotAnAttrsClassError:
            pass
        return "nper" in self._dataset.dims

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
        leaf_type: type,
        name: Optional[str] = None,
        modelname: Optional[str] = None,
        modelgrid: Optional[Grid] = None,
        modeltime: Optional[ModelTime] = None,
    ):
        assert data is not None
        assert leaf_type is not None
        assert hasattr(leaf_type, "__name__")
        self._name = name
        self._modelname = modelname
        self._grid = modelgrid
        self._time = modeltime
        self._data = data
        self._leaf_type = leaf_type

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
        match self._leaf_type.__name__:
            case "bool" | "float" | "integer" | "int" | "str":
                return DataType.scalar
            case "ndarray":
                if "nper" in self._data.dims:
                    if self._data.ndim == 2:
                        if "nodes" in self._data.dims:
                            return DataType.transient2d  # nodes?
                    if self._data.ndim == 3:
                        return DataType.transient3d  # ncpl?
                    if self._data.ndim == 4:
                        return DataType.transient2d  # nodes?
                else:
                    if self._data.ndim == 1:
                        if "nodes" in self._data.dims:
                            return DataType.array3d
                    if self._data.ndim == 2:
                        return DataType.array2d
                    if self._data.ndim == 3:
                        return DataType.array3d
            # TODO: boundname, auxvar arrays of strings?
            case _:
                warn(f"UNMATCHED data_type {self._name}: {self._leaf_type.__name__}", UserWarning)

    @property
    def dtype(self):
        if self._leaf_type.__name__ == "ndarray":
            if self._data.data.dtype == np.dtype("float64"):
                return np.float64
            elif self._data.data.dtype == np.dtype("int64"):
                return np.int64
            elif self._data.data.dtype == np.dtype("int32"):
                return np.int32
        return self._leaf_type.__name__

    @property
    def array(self):
        if self._leaf_type.__name__ == "ndarray":
            if "nodes" in self._data.dims:
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
