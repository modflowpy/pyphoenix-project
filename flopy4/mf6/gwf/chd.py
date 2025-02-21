from pathlib import Path
from typing import Optional

import numpy as np
from attr import field
from attrs import define
from numpy.typing import NDArray
from xattree import array, xattree

from flopy4.mf6 import Package


@xattree
class Chd(Package):
    multi = True

    @define(slots=False)
    class Steps:
        all: bool = field()
        first: bool = field()
        last: bool = field()
        steps: list[int] = field()
        frequency: int = field()

    @define
    class Period:
        steps: "Chd.Steps" = field()
        cellid: tuple[int, ...] = field()
        head: float = field()
        aux: Optional[float] = field(default=None)
        boundname: Optional[str] = field(default=None)

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
    stress_period_data: Optional[NDArray[np.object_]] = array(
        Period,
        dims=("nper",),
        default=None,
        metadata={"block": "period"},
    )
