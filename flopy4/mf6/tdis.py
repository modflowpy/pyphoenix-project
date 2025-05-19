from datetime import datetime
from typing import Optional

import numpy as np
from attrs import Converter, define
from flopy.discretization.modeltime import ModelTime
from numpy.typing import NDArray
from xattree import ROOT, xattree

from flopy4.mf6.converters import convert_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field


@xattree
class Tdis(Package):
    @define
    class PeriodData:
        perlen: float
        nstp: int
        tsmult: float

    nper: int = dim(
        block="dimensions",
        coord="per",
        default=1,
        scope=ROOT,
    )
    time_units: Optional[str] = field(block="options", default=None)
    start_date_time: Optional[datetime] = field(block="options", default=None)
    perlen: NDArray[np.floating] = array(
        block="perioddata",
        default=1.0,
        dims=("nper",),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    nstp: NDArray[np.integer] = array(
        block="perioddata",
        default=1,
        dims=("nper",),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )
    tsmult: NDArray[np.floating] = array(
        block="perioddata",
        default=1.0,
        dims=("nper",),
        converter=Converter(convert_array, takes_self=True, takes_field=True),
    )

    def to_time(self) -> ModelTime:
        """Convert to a `ModelTime` object."""
        return ModelTime(
            nper=self.nper,
            time_units=self.time_units,
            start_date_time=self.start_date_time,
            perlen=self.perlen,
            nstp=self.nstp,
            tsmult=self.tsmult,
        )

    @classmethod
    def from_time(cls, time: ModelTime) -> "Tdis":
        """Create a time discretization from a `ModelTime`."""
        return cls(
            nper=time.nper,
            time_units=time.time_units,
            start_date_time=time.start_datetime,
            perlen=time.perlen,
            nstp=time.nstp,
            tsmult=time.tsmult,
        )
