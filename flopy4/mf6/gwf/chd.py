from pathlib import Path
from typing import ClassVar, Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, field


@xattree
class Chd(Package):
    multi_package: ClassVar[bool] = True

    @define(slots=False)
    class Steps:
        all: bool = field()
        first: bool = field()
        last: bool = field()
        steps: list[int] = field()
        frequency: int = field()

    auxiliary: Optional[list[str]] = array(block="options", default=None)
    auxmultname: Optional[str] = field(block="options", default=None)
    boundnames: bool = field(block="options", default=False)
    print_input: bool = field(block="options", default=False)
    print_flows: bool = field(block="options", default=False)
    save_flows: bool = field(block="options", default=False)
    ts_filerecord: Optional[Path] = field(block="options", default=None)
    obs_filerecord: Optional[Path] = field(block="options", default=None)
    dev_no_newton: bool = field(default=False, metadata={"block": "options"})
    maxbound: Optional[int] = field(block="dimensions", default=None)
    head: Optional[NDArray[np.floating]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    aux: Optional[NDArray[np.floating]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    boundname: Optional[NDArray[np.str_]] = array(
        block="period",
        dims=(
            "nper",
            "nnodes",
        ),
        default=None,
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    steps: Optional[NDArray[np.object_]] = array(
        Steps,
        block="period",
        dims=("nper", "nnodes"),
        default=None,
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
