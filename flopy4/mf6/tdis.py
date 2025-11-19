from datetime import datetime
from typing import Optional

import numpy as np
from attrs import Converter, define
from numpy.typing import ArrayLike, NDArray
from xattree import ROOT, xattree

from flopy4.mf6.converter import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field
from flopy4.mf6.utils.time import Time


@xattree
class Tdis(Package):
    @define
    class PeriodData:
        perlen: float
        nstp: int
        tsmult: float

    nper: int = dim(block="dimensions", coord="kper", default=1, scope=ROOT)
    time_units: Optional[str] = field(block="options", default=None)
    start_date_time: Optional[datetime] = field(block="options", default=None)
    perlen: NDArray[np.float64] = array(
        block="perioddata",
        default=1.0,
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    nstp: NDArray[np.int64] = array(
        block="perioddata",
        default=1,
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )
    tsmult: NDArray[np.float64] = array(
        block="perioddata",
        default=1.0,
        dims=("nper",),
        converter=Converter(structure_array, takes_self=True, takes_field=True),
    )

    def to_time(self) -> Time:
        """Convert to a `Time` object."""
        return Time(
            nper=self.nper,
            time_units=self.time_units,
            start_date_time=self.start_date_time,
            perlen=self.perlen,
            nstp=self.nstp,
            tsmult=self.tsmult,
        )

    @classmethod
    def from_time(cls, time: Time) -> "Tdis":
        """Create a time discretization from a `Time` object."""
        return cls(
            nper=time.nper,
            time_units=None if time.time_units in [None, "unknown"] else time.time_units,
            start_date_time=time.start_datetime,
            perlen=time.perlen,
            nstp=time.nstp,
            tsmult=time.tsmult,
        )

    @classmethod
    def from_timestamps(
        cls,
        timestamps: ArrayLike,
        nstp: Optional[ArrayLike] = None,
        tsmult: Optional[ArrayLike] = None,
    ) -> "Tdis":
        """
        Create a time discretization from timestamps.

        Parameters
        ----------
        timestamps : sequence of datetime-likes
            Stress period start times
        nstp : int or sequence of int, optional
            Number of timesteps per stress period. If scalar, applied to all periods.
            If None, defaults to 1 for all periods.
        tsmult : float or sequence of float, optional
            Timestep multiplier per stress period. If scalar, applied to all periods.
            If None, defaults to 1.0 for all periods.

        Returns
        -------
        Tdis
            Time discretization object
        """

        time = Time.from_timestamps(timestamps, nstp=nstp, tsmult=tsmult)
        return cls.from_time(time)
