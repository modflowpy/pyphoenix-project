import types
from typing import Any, Optional, Union, get_args, get_origin
from warnings import warn

import attrs
import numpy as np
import xarray as xr
from flopy.datbase import DataInterface, DataListInterface, DataType
from flopy.discretization.grid import Grid
from flopy.discretization.modeltime import ModelTime
from flopy.export.utils import model_export, package_export
from flopy.mbase import ModelInterface
from flopy.pakbase import PackageInterface
from flopy.plot.plotutil import PlotUtilities

from flopy4.attrs_xarray import attrs_to_dataset
from flopy4.mf6.item import item_list_type
from flopy4.mf6.model import Model
from flopy4.mf6.package import _DTYPE_MAP, Package, period_shape
from flopy4.mf6.spec import to_field_type

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
        crs: Any = None,
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

        if self._grid is None:
            self._grid = _model_grid(model)
        # overrides the discretization's own (anything pyproj accepts)
        if crs is not None and self._grid is not None:
            self._grid.crs = crs

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
        # flopy3's plot_bc reads boundary cells by mf6's cellid convention
        return "mf6"

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
        return [p.name[0] for p in self._plist]

    def get_package(self, name=None):
        """
        A package by name, else by type (a list if several have it),
        ignoring case, as flopy3's MF6 models find them. Every package
        if no name is given; None if none matches.
        """
        if name is None:
            return self._plist[:]
        key = name.lower()
        for p in self._plist:
            if p.name[0].lower() == key:
                return p
        of_type = [p for p in self._plist if p.package_type.lower() == key]
        if not of_type:
            return None
        return of_type[0] if len(of_type) == 1 else of_type

    def to_geodataframe(self, gdf=None, kper=0, package_names=None, shorten_attr=False, **kwargs):
        """
        A GeoDataFrame of the grid's cells with each package's data, the
        period's for transient data, as flopy3's MF6 models build one
        (`model_export` to a shapefile). Packages may be chosen by name
        or type; HFB, whose barriers are between cells, is left out.
        """
        if gdf is None:
            if self._grid is None:
                raise AttributeError(
                    "model does not have a grid instance, please supply a geodataframe"
                )
            gdf = self._grid.to_geodataframe()
        if package_names is None:
            package_names = [p.name[0] for p in self._plist]
        for p in self._plist:
            if p.package_type == "HFB":
                continue
            if p.name[0] not in package_names and p.package_type not in package_names:
                continue
            gdf = p.to_geodataframe(gdf, kper=kper, full_grid=True, shorten_attr=shorten_attr)
        return gdf

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
            # a grid array holding one value is the full array
            leaf_type: type
            if (filled := _filled_array(package, field, value)) is not None:
                value, leaf_type = filled, np.ndarray
            elif (resolved := _resolve_leaf_type(field.type)) is not None:
                leaf_type = resolved
            else:
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

        if (spd := Flopy3ListData.from_package(self)) is not None:
            self.__dict__["stress_period_data"] = spd
            self._dlist.append(spd)

    @property
    def name(self):
        # a list, as flopy3's packages' (it reads name[0])
        return [self._package._name_or_class()]

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
        # from the class, not the name, which may be anything
        return type(self._package).__name__.upper()

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
        # Any other fill-forward (period) field (covers OC's own
        # _stress_period_data too, redundantly with the check above -- kept
        # as a generic fallback for any period field shape).
        try:
            for f in attrs.fields(type(self._package)):
                if f.metadata.get("fill_forward"):
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

    def to_geodataframe(self, gdf=None, kper=0, full_grid=True, shorten_attr=False, **kwargs):
        """
        A GeoDataFrame of the grid's cells with the package's arrays and
        the period's stress period data, as flopy3's MF6 packages build
        one (`package_export` to a shapefile). Data that doesn't fit the
        grid is left out. With ``full_grid`` false, cells with no data
        are dropped.
        """
        if gdf is None:
            gdf = self._grid.to_geodataframe()
        for d in self._dlist:
            gdf = d.to_geodataframe(gdf, kper=kper, full_grid=True, shorten_attr=shorten_attr)
        if not full_grid:
            # the grid's own columns (flopy3 counts "active" as data, so
            # drops nothing)
            cols = [c for c in gdf if c not in ("geometry", "node", "row", "col", "active")]
            gdf = gdf.dropna(subset=cols, how="all")
            gdf = gdf.dropna(axis="columns", how="all")
        return gdf

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

    # TODO: lists besides stress period data (packagedata, connectiondata,
    # ...), which flopy3's advanced-package plotting reads; see Flopy3ListData
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

    def to_geodataframe(self, gdf=None, kper=0, full_grid=True, shorten_attr=False, **kwargs):
        """
        Add the array to a GeoDataFrame of the grid's cells, as flopy3's
        MF6 arrays do: one column if it has a value per cell of a layer,
        one per layer if it has one per cell, the period's if transient.
        Scalars, and arrays of any other size (``delr``), are left out.
        """
        from flopy.export.shapefile_utils import shape_attr_name

        if self._grid is None:
            return gdf
        if gdf is None:
            gdf = self._grid.to_geodataframe()
        data = self.array
        if data is None or self.name is None:
            return gdf
        name = shape_attr_name(self.name) if shorten_attr else self.name
        if "nper" in self._data.dims:
            data = data[kper]
            name = f"{name}_{kper}"
        ncpl = self._grid.nnodes if self._grid.grid_type == "unstructured" else self._grid.ncpl
        data = np.asarray(data)
        if data.size == ncpl:
            gdf[name] = data.ravel()
        elif ncpl and data.size % ncpl == 0:
            for ix, arr in enumerate(data.reshape((-1, ncpl))):
                gdf[f"{name}_{ix}"] = arr
        if not full_grid and "active" in gdf:
            gdf = gdf[gdf["active"] > 0]
        return gdf


# flopy3 sums a column's values where cells repeat in a period, and
# averages the rest
_SUMMED_COLUMNS = frozenset({"cond", "flux"})


class Flopy3ListData(DataInterface, DataListInterface):
    """A package's stress period data as flopy3's transient list, so
    flopy3's plotting and export see boundary conditions.

    flopy3 reads it as `.array[kper]` (a recarray per period, or None
    for none: `plot_bc`), `to_array(kper, mask)` (a grid array per
    column) and `masked_4D_arrays_itr()` (NetCDF export). Periods fill
    forward as in MF6: one not given repeats the last one given, and one
    given empty has no entries. Columns are the period item's fields,
    with array fields (``aux``) spread one per value, named for the
    package's auxiliary variables where they are. A value given as a
    time series name is NaN. Columns that aren't numbers (cellids,
    boundnames) are objects, which flopy3 skips.

    Built by `from_package` for a package with stress period data.
    """

    def __init__(self, package: "Flopy3Package", nper: int):
        self._package = package
        self._nper = nper
        pkg = package._package
        item_cls = item_list_type(pkg._period_item_field().type)
        self._kpers = sorted(pkg.stress_period_data)
        self._dtype, flat = _flatten(pkg.to_dataframe(), item_cls, pkg)
        self._data = {}
        for kper in self._kpers:
            rows = flat[flat["kper"] == kper].drop(columns="kper") if len(flat) else flat
            self._data[kper] = _recarray(rows, self._dtype)

    @classmethod
    def from_package(cls, package: "Flopy3Package") -> "Flopy3ListData | None":
        """The package's stress period data, or None if it has none, or
        its rows are of more than one kind (a list of unions)."""
        pkg = package._package
        if not getattr(pkg, "stress_period_data", None):
            return None
        try:
            field = pkg._period_item_field()
        except (AttributeError, ValueError):
            return None
        if not isinstance(item_list_type(field.type), type):
            return None
        return cls(package, nper=_nper(package))

    @property
    def name(self):
        return "stress_period_data"

    @property
    def package(self):
        return self._package

    @property
    def model(self):
        return self._package.parent

    @property
    def data_type(self):
        return DataType.transientlist

    @property
    def dtype(self):
        return self._dtype

    @property
    def plottable(self):
        return True

    @property
    def data(self):
        """A recarray for each period given (empty for none)."""
        return dict(self._data)

    @property
    def array(self):
        """A recarray for every period, filled forward; None for a
        period with no entries."""
        return {
            kper: (recs if len(recs) else None)
            for kper in range(self._nper)
            for recs in [self._period(kper)]
        }

    def _period(self, kper: int) -> np.recarray:
        given = [k for k in self._kpers if k <= kper]
        if not given:
            return _recarray(None, self._dtype)
        return self._data[given[-1]]

    def to_array(self, kper=0, mask=False):
        """The period's numeric columns as grid arrays, by column name.

        Cells without an entry are 0, or NaN and masked with ``mask``.
        Returns None if the rows have no ``cellid``."""
        if "cellid" not in (self._dtype.names or ()):
            return None
        shape = self.model.modelgrid.shape
        recs = self._period(kper)
        cellids = [c for c in recs["cellid"] if c is not None]
        keep = np.array([c is not None for c in recs["cellid"]], dtype=bool)
        ndim = len(shape)
        idx = tuple(np.array(cellids, dtype=int).reshape(len(cellids), ndim).T)
        cnt = np.zeros(shape)
        np.add.at(cnt, idx, 1.0)
        arrays = {}
        for name in self._dtype.names:
            if self._dtype[name].kind == "O":
                continue
            arr = np.zeros(shape)
            np.add.at(arr, idx, recs[name][keep].astype(float))
            if name not in _SUMMED_COLUMNS:
                np.divide(arr, cnt, out=arr, where=cnt > 0)
            if mask:
                arr[cnt == 0] = np.nan
                arr = np.ma.masked_where(cnt == 0, arr)
            arrays[name] = arr
        return arrays

    @property
    def masked_4D_arrays(self):
        return dict(self.masked_4D_arrays_itr())

    def masked_4D_arrays_itr(self):
        """Each numeric column as an ``(nper, *grid shape)`` array, NaN
        where a period has no entry."""
        periods = [self.to_array(kper, mask=True) for kper in range(self._nper)]
        if not periods or periods[0] is None:
            return
        for name in periods[0]:
            yield name, np.stack([np.ma.filled(p[name], np.nan) for p in periods])

    def plot(
        self,
        key=None,
        names=None,
        kper=0,
        filename_base=None,
        file_extension=None,
        mflay=None,
        **kwargs,
    ):
        # as flopy3's mf6 lists: nothing to place without cells (OC)
        if "cellid" not in (self._dtype.names or ()):
            return None
        return PlotUtilities._plot_mflist_helper(
            self,
            key=key,
            names=names,
            kper=kper,
            filename_base=filename_base,
            file_extension=file_extension,
            mflay=mflay,
            **kwargs,
        )

    def to_geodataframe(self, gdf=None, kper=0, full_grid=True, shorten_attr=False, **kwargs):
        """Add the period's columns to a GeoDataFrame of the grid's cells,
        one per layer, as flopy3's mf6 lists do (`mflist_export` to a
        shapefile)."""
        from flopy.export.shapefile_utils import shape_attr_name

        modelgrid = self.model.modelgrid
        if modelgrid is None:
            return gdf
        if gdf is None:
            gdf = modelgrid.to_geodataframe()
        data = self.to_array(kper=kper, mask=True)
        if data is None:
            return gdf
        col_names = []
        for name, arr in data.items():
            name = (
                shape_attr_name(name, length=4)
                if shorten_attr
                else f"{self._package.name[0].lower()}_{name}"
            )
            if modelgrid.grid_type == "unstructured":
                gdf[name] = np.ma.filled(arr, np.nan).ravel()
                col_names.append(name)
                continue
            for lay in range(modelgrid.nlay):
                aname = f"{name}{lay}{kper}" if shorten_attr else f"{name}_{lay}_{kper}"
                gdf[aname] = np.ma.filled(arr[lay], np.nan).ravel()
                col_names.append(aname)
        if not full_grid:
            gdf = gdf.dropna(subset=col_names, how="all")
            gdf = gdf.dropna(axis="columns", how="all")
        return gdf


def _filled_array(package: Package, field: attrs.Attribute, value: Any) -> "xr.DataArray | None":
    """A grid array holding one value (a constant, or its default) filled
    to its shape, with dims named as the shape's; None for anything else,
    or if the shape's dimensions aren't known."""
    meta = field.metadata
    if meta.get("type") != "array" or meta.get("block") != "griddata":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        return None
    if (shape := period_shape(package, field)) is None:
        return None
    dtype = _DTYPE_MAP.get(to_field_type(field.type), np.float64) if field.type else np.float64
    return xr.DataArray(np.full(shape, value, dtype=dtype), dims=meta["shape"], name=field.name)


# where models keep their discretization, by kind of model
_DIS_FIELDS = ("dis", "dis2d", "disv2d", "disv1d")


def _model_grid(model: Model) -> "Grid | None":
    """The grid of the model's discretization package, which carries the
    origin, rotation, length units and crs; None if it has none."""
    for name in _DIS_FIELDS:
        if (dis := getattr(model, name, None)) is not None:
            grid = dis.to_grid()
            grid.legacy = True
            return grid
    return None


def _nper(package: "Flopy3Package") -> int:
    """The number of stress periods: from the model time, else the
    package's dimensions, else one past the last period given."""
    model = package.parent
    for time in (package._time, getattr(model, "modeltime", None)):
        if time is not None:
            return int(time.nper)
    pkg = package._package
    if nper := pkg.resolve_dims("nper").get("nper"):
        return int(nper)
    return max(pkg.stress_period_data) + 1


def _flatten(df, item_cls, pkg) -> "tuple[np.dtype, Any]":
    """Spread array columns one per value, and settle each column's
    dtype over every period: numeric if every value is, else objects.
    Cellids stay tuples (objects)."""
    import pandas as pd

    fields = {f.name: f for f in attrs.fields(item_cls)}
    out = pd.DataFrame({"kper": df["kper"]}) if len(df) else pd.DataFrame({"kper": []})
    dtypes: list[tuple[str, type]] = []
    for col in df.columns:
        if col == "kper":
            continue
        field = fields.get(col)
        kind = field.metadata.get("type") if field is not None else None
        values = df[col]
        if kind == "cellid":
            out[col] = values
            dtypes.append((col, object))
            continue
        if kind == "array" or values.map(lambda v: isinstance(v, (tuple, list))).any():
            width = max((len(v) for v in values if isinstance(v, (tuple, list))), default=0)
            names = _spread_names(col, width, field, pkg)
            for i, name in enumerate(names):
                spread = values.map(
                    lambda v, i=i: v[i] if isinstance(v, (tuple, list)) and i < len(v) else None
                )
                dtypes.append((name, _settle(out, name, spread, field)))
            continue
        dtypes.append((col, _settle(out, col, values, field)))
    return np.dtype(dtypes), out


def _spread_names(col, width, field, pkg) -> list[str]:
    """Names for an array column's values: the auxiliary variables'
    for an ``auxiliary``-shaped field, else the column's with an index."""
    shape = tuple(field.metadata.get("shape") or ()) if field is not None else ()
    aux = getattr(pkg, "auxiliary", None)
    if shape == ("auxiliary",) and aux is not None and len(aux) == width:
        return [str(a) for a in aux]
    return [f"{col}{i}" for i in range(width)]


def _settle(out, name, values, field) -> type:
    """Set `out[name]` to `values`, numeric if they all are, and return
    the column's dtype. A field that may hold time series names is float,
    NaN where one does. A string field is objects, even if its values are
    all missing or look like numbers."""
    import pandas as pd

    if field is not None and field.metadata.get("type") == "string":
        out[name] = values.astype(object)
        return object
    time_series = field is not None and field.metadata.get("time_series")
    try:
        numeric = pd.to_numeric(values, errors="coerce" if time_series else "raise")
    except (TypeError, ValueError):
        out[name] = values.astype(object)
        return object
    if numeric.dtype.kind not in "iuf":
        out[name] = values.astype(object)
        return object
    out[name] = numeric
    return numeric.dtype.type


def _recarray(rows, dtype: np.dtype) -> np.recarray:
    """A period's rows as a recarray of the list's dtype."""
    if rows is None or not len(rows):
        return np.recarray((0,), dtype=dtype)
    recs = np.recarray((len(rows),), dtype=dtype)
    for name in dtype.names or ():
        recs[name] = rows[name].to_numpy()
    return recs
