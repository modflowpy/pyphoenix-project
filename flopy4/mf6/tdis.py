from datetime import datetime
from typing import ClassVar, Optional

import attrs
import numpy as np
from numpy.typing import ArrayLike, NDArray

from flopy4.mf6.package import Package
from flopy4.mf6.schema import Column, Schema
from flopy4.mf6.spec import field
from flopy4.mf6.utils.time import Time


@attrs.define(kw_only=True, slots=False)
class Tdis(Package):
    @attrs.define
    class PeriodData:
        perlen: float
        nstp: int
        tsmult: float

    class _PeriodDataSchema(Schema):
        perlen = Column("perlen", role="value", dfn_type="double")
        nstp = Column("nstp", role="value", dfn_type="integer")
        tsmult = Column("tsmult", role="value", dfn_type="double")

    __perioddata_schema__: ClassVar[type[Schema]] = _PeriodDataSchema
    time_units: Optional[str] = field(default=None, block="options", optional=True)
    start_date_time: Optional[str] = field(
        default=None,
        converter=lambda v: v.isoformat() if isinstance(v, datetime) else v,
        block="options",
        optional=True,
    )
    nper: int = field(default=1, block="dimensions")
    perlen: NDArray[np.float64] = attrs.field(default=1.0)
    nstp: NDArray[np.int64] = attrs.field(default=1)
    tsmult: NDArray[np.float64] = attrs.field(default=1.0)
    perioddata: Optional[np.recarray] = field(
        default=None, block="perioddata", schema="__perioddata_schema__"
    )

    def __attrs_post_init__(self):
        if isinstance(self.perioddata, np.recarray):
            pd = self.perioddata
            object.__setattr__(self, "perlen", pd["perlen"].copy())
            object.__setattr__(self, "nstp", pd["nstp"].copy())
            object.__setattr__(self, "tsmult", pd["tsmult"].copy())
            super().__attrs_post_init__()
            return
        nper = self.nper
        if isinstance(self.perlen, (int, float)):
            object.__setattr__(self, "perlen", np.full(nper, self.perlen, dtype=np.float64))
        elif not isinstance(self.perlen, np.ndarray):
            object.__setattr__(self, "perlen", np.asarray(self.perlen, dtype=np.float64))
        if isinstance(self.nstp, (int, float)):
            object.__setattr__(self, "nstp", np.full(nper, int(self.nstp), dtype=np.int64))
        elif not isinstance(self.nstp, np.ndarray):
            object.__setattr__(self, "nstp", np.asarray(self.nstp, dtype=np.int64))
        if isinstance(self.tsmult, (int, float)):
            object.__setattr__(self, "tsmult", np.full(nper, self.tsmult, dtype=np.float64))
        elif not isinstance(self.tsmult, np.ndarray):
            object.__setattr__(self, "tsmult", np.asarray(self.tsmult, dtype=np.float64))
        dtype = np.dtype([("perlen", np.float64), ("nstp", np.int64), ("tsmult", np.float64)])
        arr = np.zeros(nper, dtype=dtype)
        arr["perlen"] = self.perlen
        arr["nstp"] = self.nstp
        arr["tsmult"] = self.tsmult
        object.__setattr__(self, "perioddata", arr.view(np.recarray))
        super().__attrs_post_init__()

    def get_dims(self) -> dict[str, int]:
        """Get all dimensions."""
        return {"nper": self.nper}

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
    ) -> "Tdis":
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
