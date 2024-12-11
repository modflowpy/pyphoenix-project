# # Attrs demo

# This example demonstrates a tentative `attrs`-based object model.

from os import PathLike
from pathlib import Path
from typing import Literal, Optional, get_origin
from warnings import warn

import numpy as np
from attr import define, field, fields_dict
from cattr import Converter
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


def _to_path(value) -> Optional[Path]:
    return Path(value) if value else None


def datatree(cls):
    post_init_name = "__attrs_post_init__"
    post_init_prev = getattr(cls, post_init_name, None)

    def _set_data_on_self(self, cls):
        fields = fields_dict(cls)
        arrays = {}
        for n, f in fields.items():
            if get_origin(f.type) is not np.ndarray:
                continue
            value = getattr(self, n)
            if value is None:
                continue
            arrays[n] = (
                _parse_dim_names(f.metadata["shape"]),
                _to_shaped_array(value, self, f),
            )
        dataset = Dataset(arrays)
        self.data = (
            DataTree(dataset, name=cls.__name__.lower()[3:])
            if issubclass(cls, Model)
            else dataset
        )

    def _set_self_on_model(self, cls):
        model = getattr(self, "model", None)
        if model:
            self_name = cls.__name__.lower()[3:]
            setattr(model, self_name, self)
            model.data = model.data.assign(
                {self_name: DataTree(self.data, name=self_name)}
            )

    def __attrs_post_init__(self):
        if post_init_prev:
            post_init_prev(self)

        _set_data_on_self(self, cls)
        _set_self_on_model(self, cls)

    # TODO: figure out why classes need to have a
    # __attrs_post_init__ method for this to work
    setattr(cls, post_init_name, __attrs_post_init__)
    return cls


class Model:
    pass


@datatree
@define(slots=False)
class GwfDis:
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
class GwfIc:
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
class GwfOc:
    @define
    class Format:
        columns: int
        width: int
        digits: int
        format: Literal["exponential", "fixed", "general", "scientific"]

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
    perioddata: Optional[list[list[tuple]]] = field(
        default=None, metadata={"block": "perioddata"}
    )
    model: Optional[Model] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


@datatree
@define(slots=False)
class Gwf(Model):
    dis: Optional[GwfDis] = field(default=None)
    ic: Optional[GwfIc] = field(default=None)
    oc: Optional[GwfOc] = field(default=None)

    def __attrs_post_init__(self):
        # for some reason this is necessary..
        pass


# We can define a package with some data.


oc = GwfOc(
    budget_file="some/file/path.cbc",
    perioddata=[[("print", "budget", "steps", 1, 3, 5)]],
)
assert isinstance(oc.budget_file, Path)


# We now set up a `cattrs` converter to convert an unstructured
# representation of the package input data to a structured form.

converter = Converter()


# We can load the full package from an unstructured dictionary,
# as would be returned by a separate IO layer in the future.
# (Either hand-written or using e.g. lark.)

oc = converter.structure(
    {
        "budget_file": "some/file/path.cbc",
        "head_file": "some/file/path.hds",
        "printhead": {
            "columns": 1,
            "width": 10,
            "digits": 8,
            "format": "scientific",
        },
        "perioddata": [
            [
                ("print", "budget", "steps", 1, 3, 5),
                ("save", "head", "frequency", 2),
            ]
        ],
    },
    GwfOc,
)
assert oc.budget_file == Path("some/file/path.cbc")
assert oc.printhead.width == 10
assert oc.printhead.format == "scientific"
period = oc.perioddata[0]
assert len(period) == 2
assert period[0] == ("print", "budget", "steps", 1, 3, 5)


# Create a model.


gwf = Gwf()
dis = GwfDis(model=gwf)
ic = GwfIc(model=gwf, strt=1)
oc.model = gwf

# View the data tree.
