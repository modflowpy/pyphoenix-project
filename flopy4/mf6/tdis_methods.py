from typing import TYPE_CHECKING, Optional

import numpy as np
from numpy.typing import ArrayLike

from flopy4.mf6.utils.time import Time

if TYPE_CHECKING:
    from flopy4.mf6.tdis import Tdis


class TdisMethods:
    """Methods for the generated `Tdis`; fields come from the DFN."""

    def get_dims(self: "Tdis") -> dict[str, int]:  # type: ignore[misc]
        """Get all dimensions."""
        return {"nper": self.nper or len(self.perioddata or [])}

    def to_time(self: "Tdis") -> Time:  # type: ignore[misc]
        """Convert to a `Time` object."""
        perlen, nstp, tsmult = zip(*((r.perlen, r.nstp, r.tsmult) for r in self.perioddata or []))
        return Time(
            time_units=self.time_units,
            start_datetime=self.start_date_time,
            perlen=np.array(perlen, dtype=np.float64),
            nstp=np.array(nstp, dtype=np.int64),
            tsmult=np.array(tsmult, dtype=np.float64),
        )

    @classmethod
    def from_time(cls: type["Tdis"], time: Time) -> "Tdis":  # type: ignore[misc]
        """Create a time discretization from a `Time` object."""
        start = time.start_datetime
        return cls(
            nper=time.nper,
            time_units=None if time.time_units in [None, "unknown"] else time.time_units,
            start_date_time=start.isoformat() if start is not None else None,
            perioddata=list(zip(time.perlen, time.nstp, time.tsmult)),  # type: ignore[arg-type]
        )

    def to_xarray(self: "Tdis"):  # type: ignore[misc]
        """Return Tdis data as an xr.Dataset with kper coordinate."""
        import pandas as pd
        import xarray as xr

        time = self.to_time()
        ds = xr.Dataset(
            {
                "perlen": ("kper", time.perlen),
                "nstp": ("kper", time.nstp),
                "tsmult": ("kper", time.tsmult),
            },
            coords={"kper": np.arange(time.nper)},
        )
        if self.start_date_time:
            ds.attrs["start_date_time"] = pd.Timestamp(self.start_date_time)
        if self.time_units:
            ds.attrs["time_units"] = self.time_units
        return ds

    @classmethod
    def from_timestamps(  # type: ignore[misc]
        cls: type["Tdis"],
        timestamps: ArrayLike,
        nstp: Optional[ArrayLike] = None,
        tsmult: Optional[ArrayLike] = None,
    ) -> "Tdis":
        """Create a time discretization from stress period start times.

        `nstp` and `tsmult` may be scalars (applied to all periods) and
        default to 1 and 1.0; see `Time.from_timestamps`.
        """
        return cls.from_time(Time.from_timestamps(timestamps, nstp=nstp, tsmult=tsmult))
