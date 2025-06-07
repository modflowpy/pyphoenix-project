from datetime import datetime
from typing import Optional

import attrs
import numpy as np
from attrs import Converter, define
from flopy.discretization.modeltime import ModelTime
from numpy.typing import NDArray
from xattree import ROOT, xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field


@xattree
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = 1.0
        nstp: int = 1
        tsmult: float = 1.0

    nper: int = dim(
        block="dimensions",
        coord="per",
        default=1,
        scope=ROOT,
    )
    time_units: Optional[str] = field(block="options", default=None)
    start_date_time: Optional[datetime] = field(block="options", default=None)
    perioddata: NDArray[np.object_] = array(
        PeriodData,
        block="perioddata",
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
        reader="urword",
    )

    def to_time(self) -> ModelTime:
        """Convert to a `ModelTime` object."""
        perioddata = np.rec.fromrecords([attrs.astuple(pd) for pd in self.perioddata.to_numpy()])
        return ModelTime(
            nper=self.nper,
            time_units=self.time_units,
            start_date_time=self.start_date_time,
            perlen=perioddata.perlen,
            nstp=perioddata.nstp,
            tsmult=perioddata.tsmult,
        )

    @classmethod
    def from_time(cls, time: ModelTime) -> "Tdis":
        """Create a time discretization from a `ModelTime`."""
        perioddata = np.rec.fromrecords(
            *zip(time.perlen, time.nstp, time.tsmult),
            dtype=[("perlen", float), ("nstp", int), ("tsmult", float)],
        )
        return cls(
            nper=time.nper,
            time_units=time.time_units,
            start_date_time=time.start_datetime,
            perioddata=perioddata,
        )
