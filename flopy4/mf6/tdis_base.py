from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Self

import attrs
import numpy as np
from numpy.typing import ArrayLike, NDArray

from flopy4.mf6.package import Package
from flopy4.mf6.utils.time import Time


@attrs.define(kw_only=True, slots=False)
class TdisBase(Package):
    """Time discretization behavior; see the generated Tdis for the fields.

    `perioddata` is the only stored period data. `perlen`, `nstp` and
    `tsmult` are read-only column views of it.
    """

    if TYPE_CHECKING:
        # declared on the generated Tdis
        time_units: Optional[str]
        start_date_time: Optional[str]
        nper: Optional[int]
        perioddata: Any

    def __attrs_post_init__(self):
        if isinstance(self.start_date_time, datetime):
            object.__setattr__(self, "start_date_time", self.start_date_time.isoformat())
        if self.perioddata is None:
            # DFN default_value: ((1.0, 1, 1.0),) per stress period
            object.__setattr__(self, "perioddata", [(1.0, 1, 1.0)] * (self.nper or 1))
        super().__attrs_post_init__()
        n = len(self.perioddata)
        if self.nper in (None, 1):
            object.__setattr__(self, "nper", n)
        elif self.nper != n:
            raise ValueError(f"nper={self.nper} but perioddata has {n} rows")

    @property
    def perlen(self) -> NDArray[np.float64]:
        return np.array([r.perlen for r in self.perioddata], dtype=np.float64)

    @property
    def nstp(self) -> NDArray[np.int64]:
        return np.array([r.nstp for r in self.perioddata], dtype=np.int64)

    @property
    def tsmult(self) -> NDArray[np.float64]:
        return np.array([r.tsmult for r in self.perioddata], dtype=np.float64)

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions."""
        return {"nper": self.nper or len(self.perioddata)}

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
    def from_time(cls, time: Time) -> Self:
        """Create a time discretization from a `Time` object."""
        kwargs: dict[str, Any] = dict(
            nper=time.nper,
            time_units=None if time.time_units in [None, "unknown"] else time.time_units,
            start_date_time=time.start_datetime,
            perioddata=list(zip(time.perlen, time.nstp, time.tsmult)),
        )
        return cls(**kwargs)

    def to_xarray(self):
        """Return Tdis data as an xr.Dataset with kper coordinate."""
        import pandas as _pd
        import xarray as _xr

        kper = np.arange(self.nper)
        ds = _xr.Dataset(
            {
                "perlen": ("kper", self.perlen),
                "nstp": ("kper", self.nstp),
                "tsmult": ("kper", self.tsmult),
            },
            coords={"kper": kper},
        )
        if self.start_date_time:
            ds.attrs["start_date_time"] = _pd.Timestamp(self.start_date_time)
        if self.time_units:
            ds.attrs["time_units"] = self.time_units
        return ds

    @classmethod
    def from_timestamps(
        cls,
        timestamps: ArrayLike,
        nstp: Optional[ArrayLike] = None,
        tsmult: Optional[ArrayLike] = None,
    ) -> Self:
        """Create a time discretization from timestamps.

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
