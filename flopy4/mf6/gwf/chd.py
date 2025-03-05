from pathlib import Path
from typing import Optional

import attrs
import numpy as np
from attrs import define
from numpy.typing import NDArray
from xattree import _get_xatspec, array, field, xattree

from flopy4.mf6 import Package

dnodata = 1e30


def _get_nn(ncol, nrow, k, i, j):
    return k * nrow * ncol + i * ncol + j


def _convert_array(value, self_, field):
    if not isinstance(value, dict):
        return value

    inherited_dims = self_.__dict__.get("dims", {})
    spec = _get_xatspec(type(self_))
    field = spec.arrays["head"]
    shape = field.dims
    if not shape:
        raise ValueError()
    dims = [inherited_dims.get(d, d) for d in shape]
    # TODO pull out dtype from annotation
    a = np.full(dims, fill_value=dnodata, dtype=np.float64)
    for kper, period in value.items():
        if kper == "*":
            kper = 0
        for cellid, v in period.items():
            nn = _get_nn(inherited_dims["col"], inherited_dims["row"], *cellid)
            a[kper, nn] = v
    return a


@xattree(multi="list")
class Chd(Package):
    @define(slots=False)
    class Steps:
        all: bool = field()
        first: bool = field()
        last: bool = field()
        steps: list[int] = field()
        frequency: int = field()

    auxiliary: Optional[list[str]] = array(
        default=None, metadata={"block": "options"}
    )
    auxmultname: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    boundnames: bool = field(default=False, metadata={"block": "options"})
    print_input: bool = field(default=False, metadata={"block": "options"})
    print_flows: bool = field(default=False, metadata={"block": "options"})
    save_flows: bool = field(default=False, metadata={"block": "options"})
    ts_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    obs_filerecord: Optional[Path] = field(
        default=None, metadata={"block": "options"}
    )
    dev_no_newton: bool = field(default=False, metadata={"block": "options"})
    maxbound: Optional[int] = field(
        default=None, metadata={"block": "dimensions"}
    )
    head: Optional[NDArray[np.floating]] = array(
        dims=(
            "per",
            "node",
        ),
        default=None,
        metadata={"block": "period"},
        converter=attrs.Converter(
            _convert_array, takes_self=True, takes_field=True
        ),
    )
    aux: Optional[NDArray[np.floating]] = array(
        dims=(
            "per",
            "node",
        ),
        default=None,
        metadata={"block": "period"},
    )
    boundname: Optional[NDArray[np.str_]] = array(
        dims=(
            "per",
            "node",
        ),
        default=None,
        metadata={"block": "period"},
    )
    steps: Optional[NDArray[np.object_]] = array(
        Steps, dims=("per", "node"), default=None, metadata={"block": "period"}
    )
