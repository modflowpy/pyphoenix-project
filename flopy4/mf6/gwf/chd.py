from pathlib import Path
from typing import Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import array, field, xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package


@xattree
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
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    aux: Optional[NDArray[np.floating]] = array(
        dims=(
            "per",
            "node",
        ),
        default=None,
        metadata={"block": "period"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    boundname: Optional[NDArray[np.str_]] = array(
        dims=(
            "per",
            "node",
        ),
        default=None,
        metadata={"block": "period"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    steps: Optional[NDArray[np.object_]] = array(
        Steps,
        dims=("per", "node"),
        default=None,
        metadata={"block": "period"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
