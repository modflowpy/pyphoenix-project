# # Attrs demo

# This example demonstrates a tentative `attrs`-based object model which
# which uses `xarray` to provide a `DataTree` view.

from datetime import datetime
from itertools import repeat
from os import PathLike
from pathlib import Path
from typing import Iterable, Literal, Optional, get_origin
from warnings import warn

import numpy as np
from attr import Factory, define, field, fields_dict
from numpy.typing import ArrayLike, NDArray
from xarray import Dataset, DataTree


def _parse_dim_names(s: str) -> tuple[str]:
    return tuple(
        [
            ss.strip()
            for ss in s.strip().replace("(", "").replace(")", "").split(",")
            if any(ss)
        ]
    )


def _try_resolve_dim(self, name) -> int | str:
    name = name.strip()
    value = getattr(self, name, None)
    if value:
        return value
    if hasattr(self, "model") and hasattr(self.model, "dis"):
        return getattr(self.model.dis, name, name)
    if hasattr(self, "sim") and hasattr(self.sim, "tdis"):
        return getattr(self.sim.tdis, name, name)
    return name


def _try_resolve_shape(self, field) -> tuple[int | str]:
    dim_names = _parse_dim_names(field.metadata["shape"])
    return tuple([_try_resolve_dim(self, n) for n in dim_names])


def _to_array(value: Optional[ArrayLike]) -> Optional[NDArray]:
    return None if value is None else np.array(value)


def _to_shaped_array(
    value: Optional[ArrayLike | str | PathLike], self_, field
) -> Optional[NDArray]:
    if isinstance(value, (str, PathLike)):
        # TODO handle external arrays
        pass

    value = _to_array(value)
    if value is None:
        return None

    shape = _try_resolve_shape(self_, field)
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        warn(f"Failed to resolve dimension names: {', '.join(unresolved)}")
        return value
    elif value.shape == ():
        return np.ones(shape) ** value.item()
    elif value.shape != shape:
        raise ValueError(
            f"Shape mismatch, got {value.shape}, expected {shape}"
        )
    return value


def _to_shaped_list(
    value: Optional[Iterable | str | PathLike], self_, field
) -> Optional[list]:
    if isinstance(value, (str, PathLike)):
        # TODO handle external lists
        pass

    shape = _try_resolve_shape(self_, field)
    if len(shape) > 1:
        raise ValueError(f"Expected at most 1 dimension, got {len(shape)}")
    unresolved = [dim for dim in shape if not isinstance(dim, int)]
    if any(unresolved):
        warn(f"Failed to resolve dimension names: {', '.join(unresolved)}")
        return value
    elif np.array(value).shape == ():
        return list(repeat(value, shape[0]))
    elif len(value) != shape[0]:
        raise ValueError(
            f"Length mismatch, got {len(value)}, expected {shape[0]}"
        )
    return value


def _to_path(value) -> Optional[Path]:
    return Path(value) if value else None


def datatree(cls):
    post_init_name = "__attrs_post_init__"
    post_init_prev = getattr(cls, post_init_name, None)

    def _set_data_on_self(self, cls):
        fields = fields_dict(cls)
        arrays = {}
        for n, f in fields.items():
            if get_origin(f.type) is np.ndarray:
                value = getattr(self, n)
                if value is None:
                    continue
                arrays[n] = (
                    _parse_dim_names(f.metadata["shape"]),
                    _to_shaped_array(value, self, f),
                )
            elif get_origin(f.type) is list:
                value = getattr(self, n)
                if value is None:
                    continue
                arrays[n] = (
                    _parse_dim_names(f.metadata["shape"]),
                    _to_shaped_list(value, self, f),
                )

        dataset = Dataset(arrays)
        self.data = (
            DataTree(dataset, name=cls.__name__.lower())
            if cls is Sim or issubclass(cls, Model)
            else dataset
        )

    def _set_self_on_parent(self, cls):
        self_name = cls.__name__.lower()
        model = getattr(self, "model", None)
        if model:
            setattr(model, self_name, self)
            data = (
                DataTree(self.data, name=self_name)
                if not isinstance(self.data, DataTree)
                else self.data
            )
            model.data = model.data.assign({self_name: data})
            sim = getattr(model, "sim", None)
            if sim:
                model_name = type(model).__name__.lower()
                setattr(sim, model_name, model)
                sim.data = sim.data.assign({model_name: model.data})
        sim = getattr(self, "sim", None)
        if sim:
            setattr(sim, self_name, self)
            data = (
                DataTree(self.data, name=self_name)
                if not isinstance(self.data, DataTree)
                else self.data
            )
            sim.data = sim.data.assign({self_name: data})

    def __attrs_post_init__(self):
        if post_init_prev:
            post_init_prev(self)

        _set_data_on_self(self, cls)
        _set_self_on_parent(self, cls)

    # TODO: figure out why classes need to have a
    # __attrs_post_init__ method for this to work
    setattr(cls, post_init_name, __attrs_post_init__)
    return cls


class Model:
    pass


@datatree
@define(slots=False)
class Dis:
    nlay: int = field(default=1, metadata={"block": "dimensions"})
    ncol: int = field(default=2, metadata={"block": "dimensions"})
    nrow: int = field(default=2, metadata={"block": "dimensions"})
    delr: NDArray[np.floating] = field(
        converter=_to_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol,)"},
    )
    delc: NDArray[np.floating] = field(
        converter=_to_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(nrow,)"},
    )
    top: NDArray[np.floating] = field(
        converter=_to_array,
        default=1.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow)"},
    )
    botm: NDArray[np.floating] = field(
        converter=_to_array,
        default=0.0,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    idomain: Optional[NDArray[np.integer]] = field(
        converter=_to_array,
        default=1,
        metadata={"block": "griddata", "shape": "(ncol, nrow, nlay)"},
    )
    length_units: str = field(default=None, metadata={"block": "options"})
    nogrb: bool = field(default=False, metadata={"block": "options"})
    xorigin: float = field(default=None, metadata={"block": "options"})
    yorigin: float = field(default=None, metadata={"block": "options"})
    angrot: float = field(default=None, metadata={"block": "options"})
    export_array_netcdf: bool = field(
        default=False, metadata={"block": "options"}
    )
    nodes: int = field(init=False)
    model: Optional[Model] = field(default=None)

    def __attrs_post_init__(self):
        self.nodes = self.nlay * self.ncol * self.nrow


@datatree
@define(slots=False)
class Ic:
    strt: NDArray[np.floating] = field(
        converter=_to_array,
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
    model: Optional[Model] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


@datatree
@define(slots=False)
class Oc:
    @define(slots=False)
    class Format:
        columns: int
        width: int
        digits: int
        format: Literal["exponential", "fixed", "general", "scientific"]

    @define(slots=False)
    class Steps:
        first: Optional[Literal["first"]] = field(default="first")
        last: Optional[Literal["last"]] = field(default=None)
        all: Optional[Literal["all"]] = field(default=None)
        frequency: Optional[int] = field(default=None)
        steps: Optional[list[int]] = field(default=None)

    budget_file: Optional[Path] = field(
        converter=_to_path, default=None, metadata={"block": "options"}
    )
    budget_csv_file: Optional[Path] = field(
        converter=_to_path, default=None, metadata={"block": "options"}
    )
    head_file: Optional[Path] = field(
        converter=_to_path, default=None, metadata={"block": "options"}
    )
    printhead: Optional[Format] = field(
        default=None, metadata={"block": "options"}
    )
    perioddata: list[Steps] = field(
        default=Factory(list),
        metadata={"block": "perioddata", "shape": "(nper,)"},
    )
    model: Optional[Model] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


@datatree
@define(slots=False)
class Gwf(Model):
    dis: Optional[Dis] = field(default=None)
    ic: Optional[Ic] = field(default=None)
    oc: Optional[Oc] = field(default=None)
    sim: Optional["Sim"] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


@datatree
@define(slots=False)
class Tdis:
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
    sim: Optional["Sim"] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


@datatree
@define(slots=False)
class Sim:
    tdis: Optional[Tdis] = field(default=None)
    gwf: Optional[Gwf] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


# Create a model.

sim = Sim()
tdis = Tdis(sim=sim, nper=1, perioddata=[Tdis.PeriodData()])
gwf = Gwf(sim=sim)
dis = Dis(model=gwf)
ic = Ic(model=gwf, strt=1)
oc = Oc(model=gwf, perioddata=[Oc.Steps()])

# View the data tree.
gwf.data
