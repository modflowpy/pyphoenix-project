# # Demo attrs/XArray object model

# Demonstrate a tentative `attrs`- and `xarray`-based object model,
# where `attrs` is used to define classes and `xarray` is used as
# the underlying data store.


from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional, get_origin

import numpy as np
from attr import Attribute, Factory, define, field, fields_dict
from numpy.typing import ArrayLike, NDArray
from xarray import Dataset, DataTree


def _to_path(value: Any) -> Optional[Path]:
    return Path(value) if value else None


def _parse_dim_names(shape: str) -> tuple[str, ...]:
    return tuple(
        [
            dim.strip()
            for dim in shape.strip()
            .replace("(", "")
            .replace(")", "")
            .split(",")
            if any(dim)
        ]
    )


def _try_resolve_dim(data: Optional[DataTree], name: str) -> int | str:
    name = name.strip()
    if data is None:
        return name
    value = data.get(name, None)
    if value is not None:
        return value.item()
    root = data.root
    paths = [
        "tdis",
        "dis",
        "gwf/dis",
    ]
    for path in paths:
        try:
            key = f"{path}/{name}"
            return root[key].item()
        except:
            try:
                return root[path].dims[name]
            except:
                pass
    return name


def _try_resolve_shape(data: DataTree, attr: Attribute) -> tuple[int | str]:
    shape = attr.metadata.get("shape", None)
    if shape is None:
        raise ValueError(f"Array {attr.name} missing shape metadata")
    shape = [_try_resolve_dim(data, dim) for dim in _parse_dim_names(shape)]
    return shape


def _reshape_array(value: ArrayLike, shape: tuple[int]) -> Optional[NDArray]:
    value = np.array(value)
    if value.shape == ():
        return np.full(shape, value.item())
    elif value.shape != shape:
        raise ValueError(
            f"Shape mismatch, got {value.shape}, expected {shape}"
        )
    return value


def _resolve_array(
    self, attr: Attribute, value: Optional[ArrayLike]
) -> Optional[NDArray]:
    if value is None:
        return None
    shape = _try_resolve_shape(self.data, attr)
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        raise ValueError(
            f"Class '{type(self).__name__}' "
            f"failed to resolve dims: {', '.join(unresolved)}"
        )
    return _reshape_array(value, shape)


def _bind_tree(self, parent):
    parent.data = parent.data.assign({self.data.name: self.data})
    self.data = parent.data[self.data.name]
    grandparent = getattr(parent, "parent", None)
    if grandparent is not None:
        _bind_tree(parent, grandparent)


def _init_tree(self, parent=None, **kwargs):
    cls = type(self)
    cls_name = cls.__name__.lower()
    spec = fields_dict(cls)
    data = Dataset()
    dims = set()

    # add arrays
    for name, attr in spec.items():
        value = kwargs.get(name, attr.default)
        shape = attr.metadata.get("shape", None)
        if shape is not None:
            dim_names = _parse_dim_names(shape)
            shape = [
                _try_resolve_dim(parent.data.root if parent else None, dim)
                for dim in dim_names
            ]
            shape = tuple(
                [
                    (dim if isinstance(dim, int) else kwargs.get(dim, dim))
                    for dim in shape
                ]
            )
            unresolved = [dim for dim in shape if not isinstance(dim, int)]
            if any(unresolved):
                raise ValueError(
                    f"Class '{cls_name}' "
                    f"failed to resolve dims: {', '.join(unresolved)}"
                )
            dims.update(dim_names)
            value = _reshape_array(value, shape)
            if value.shape == ():
                raise ValueError(
                    f"Failed to resolve array '{name}', "
                    f"make sure these dimensions exist: "
                    f"{','.join(dims)}"
                )
            data[name] = (dim_names, value)

    # add scalars
    for name, value in spec.items():
        if name in data or name in dims:
            continue
        value = kwargs.get(name, attr.default)
        data[name] = value

    self.data = DataTree(data, name=cls_name)
    if parent is not None:
        self.parent = parent
        _bind_tree(self, parent)


def _setattr(self, attr: Attribute, value: Any):
    cls = type(self)
    spec = fields_dict(cls)
    if attr.name not in spec:
        raise AttributeError(f"{cls.__name__} has no attribute {attr.name}")
    if value is None:
        return
    self.data[attr.name] = (
        (
            _parse_dim_names(attr.metadata["shape"]),
            _resolve_array(self, attr, value),
        )
        if get_origin(attr.type) in [list, np.ndarray]
        else value
    )
    # TODO run validation?


def component(cls):
    spec = fields_dict(cls)

    def _get(self, name):
        if name in spec:
            value = self.data.get(name, None)
            if value is not None:
                return value
            value = self.data.dims.get(name, None)
            if value is not None:
                return value
        return super(cls, self).__getattribute__(name)

    cls.__getattribute__ = _get
    return cls


class Package(ABC):
    data: DataTree = None


class Model(ABC):
    data: DataTree = None


class Sim(ABC):
    data: DataTree = None


# @component could in theory wrap the @define decorator
@component
@define(init=False, slots=False, on_setattr=_setattr)
class Dis(Package):
    length_units: str = field(
        # store block as metadata then dynamically
        # discover and expose blocks as properties.
        default=None,
        metadata={"block": "options"},
        # OR, blocks could be attrs classes too...
        # that will be necessary if variable names
        # at the top level are not unique, but they
        # currently are (if we like that constraint
        # we should document it and enforce it when
        # DFNs are loaded?)
    )
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    nlay: int = field(default=1, metadata={"block": "dimensions"})
    ncol: int = field(default=2, metadata={"block": "dimensions"})
    nrow: int = field(default=2, metadata={"block": "dimensions"})
    delr: NDArray[np.floating] = field(
        # we use a converter both to resolve an array shape
        # and check it, handling both conversion/validation
        converter=_resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol,)"},
    )
    delc: NDArray[np.floating] = field(
        converter=_resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nrow,)"},
    )
    top: NDArray[np.floating] = field(
        converter=_resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow)"},
    )
    botm: NDArray[np.floating] = field(
        converter=_resolve_array,
        default=0.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    idomain: Optional[NDArray[np.integer]] = field(
        converter=_resolve_array,
        default=1,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    nodes: Optional[int] = field(default=None)

    def __init__(
        self=None,
        model=None,
        length_units=None,
        nogrb=False,
        xorigin=None,
        yorigin=None,
        angrot=None,
        export_array_netcdf=False,
        nlay=1,
        ncol=2,
        nrow=2,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=0.0,
        idomain=1,
    ):
        _init_tree(
            self,
            parent=model,
            length_units=length_units,
            nogrb=nogrb,
            xorigin=xorigin,
            yorigin=yorigin,
            angrot=angrot,
            export_array_netcdf=export_array_netcdf,
            nlay=nlay,
            ncol=ncol,
            nrow=nrow,
            nodes=ncol * nrow * nlay,
            delr=delr,
            delc=delc,
            top=top,
            botm=botm,
            idomain=idomain,
        )


@component
@define(init=False, slots=False, on_setattr=_setattr)
class Ic(Package):
    strt: NDArray[np.floating] = field(
        converter=_resolve_array,
        default=1.0,
        metadata={"block": "packagedata", "shape": "(nodes)"},
    )
    export_array_ascii: bool = field(
        default=False, metadata={"block": "options"}
    )
    export_array_netcdf: bool = field(
        default=False,
        metadata={"block": "options"},
    )

    def __init__(
        self,
        model=None,
        strt=1.0,
        export_array_ascii=False,
        export_array_netcdf=False,
    ):
        _init_tree(
            self,
            parent=model,
            strt=strt,
            export_array_ascii=export_array_ascii,
            export_array_netcdf=export_array_netcdf,
        )


@component
@define(init=False, slots=False, on_setattr=_setattr)
class Oc(Package):
    @define(slots=False)
    class Format:
        columns: int = field(default=10)
        width: int = field(default=11)
        digits: int = field(default=4)
        format: Literal["exponential", "fixed", "general", "scientific"] = (
            field(default="general")
        )

    @define(slots=False)
    class Steps:
        first: Optional[Literal["first"]] = field(default="first")
        last: Optional[Literal["last"]] = field(default=None)
        all: Optional[Literal["all"]] = field(default=None)
        frequency: Optional[int] = field(default=None)
        steps: Optional[list[int]] = field(default=None)

    budget_file: Optional[Path] = field(
        converter=_to_path,
        default=None,
        metadata={"block": "options"},
    )
    budget_csv_file: Optional[Path] = field(
        converter=_to_path,
        default=None,
        metadata={"block": "options"},
    )
    head_file: Optional[Path] = field(
        converter=_to_path,
        default=None,
        metadata={"block": "options"},
    )
    printhead: Optional[Format] = field(
        default=None, init=False, metadata={"block": "options"}
    )
    perioddata: list[Steps] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper,)"},
    )

    def __init__(
        self,
        model=None,
        budget_file=None,
        budget_csv_file=None,
        head_file=None,
        printhead=None,
        perioddata=None,
    ):
        _init_tree(
            self,
            parent=model,
            budget_file=budget_file,
            budget_csv_file=budget_csv_file,
            head_file=head_file,
            printhead=printhead,
            perioddata=perioddata,
        )


@component
@define(init=False, slots=False, on_setattr=_setattr)
class Npf(Package):
    # no options, just arrays for now
    icelltype: NDArray[np.integer] = field(
        converter=_resolve_array,
        default=0,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k: NDArray[np.floating] = field(
        converter=_resolve_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k22: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    k33: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle1: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle2: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    angle3: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )
    wetdry: Optional[NDArray[np.floating]] = field(
        converter=_resolve_array,
        default=None,
        metadata={"block": "griddata", "shape": "(nodes)"},
    )

    def __init__(
        self,
        model=None,
        icelltype=0,
        k=1.0,
        k22=None,
        k33=None,
        angle1=None,
        angle2=None,
        angle3=None,
        wetdry=None,
    ):
        _init_tree(
            self,
            parent=model,
            icelltype=icelltype,
            k=k,
            k22=k22,
            k33=k33,
            angle1=angle1,
            angle2=angle2,
            angle3=angle3,
            wetdry=wetdry,
        )


@component
@define(init=False, slots=False)
class Gwf(Model):
    def __init__(
        self,
        sim=None,
    ):
        _init_tree(self, parent=sim)


@component
@define(init=False, slots=False, on_setattr=_setattr)
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = field(default=1.0)
        nstp: int = field(default=1)
        tsmult: float = field(default=1.0)

    nper: int = field(default=1, metadata={"block": "dimensions"})
    perioddata: list[PeriodData] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper)"},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )

    def __init__(
        self,
        sim=None,
        nper=1,
        perioddata=None,
        time_units=None,
        start_date_time=None,
    ):
        _init_tree(
            self,
            parent=sim,
            nper=nper,
            perioddata=perioddata,
            time_units=time_units,
            start_date_time=start_date_time,
        )


@component
@define(slots=False)
class Simulation(Sim):
    def __init__(self):
        _init_tree(self)


# Create a simulation.

sim = Simulation()
tdis = Tdis(sim=sim, nper=1, perioddata=[Tdis.PeriodData()])
gwf = Gwf(sim=sim)
dis = Dis(model=gwf)
ic = Ic(model=gwf, strt=1.0)
oc = Oc(model=gwf, perioddata=[Oc.Steps()])
npf = Npf(model=gwf, icelltype=0, k=1.0)

# View the data tree.
sim.data
