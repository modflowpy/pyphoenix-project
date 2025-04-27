from datetime import datetime
from typing import Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import NDArray
from xattree import ROOT, array, dim, field, xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package


@xattree
class Tdis(Package):
    @define
    class PeriodData:
        perlen: float
        nstp: int
        tsmult: float

    nper: int = dim(
        coord="per",
        default=1,
        scope=ROOT,
        metadata={"block": "dimensions"},
    )
    time_units: Optional[str] = field(
        default=None, metadata={"block": "options"}
    )
    start_date_time: Optional[datetime] = field(
        default=None, metadata={"block": "options"}
    )
    perlen: NDArray[np.floating] = array(
        default=1.0,
        dims=("nper",),
        metadata={"block": "perioddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    nstp: NDArray[np.integer] = array(
        default=1,
        dims=("nper",),
        metadata={"block": "perioddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    tsmult: NDArray[np.floating] = array(
        default=1.0,
        dims=("nper",),
        metadata={"block": "perioddata"},
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
