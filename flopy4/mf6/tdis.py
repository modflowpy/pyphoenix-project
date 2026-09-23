from datetime import datetime
from typing import Any, ClassVar, Optional

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import field_validator
from pydantic.dataclasses import dataclass

from flopy4.mf6.item import Item
from flopy4.mf6.package import CFG, Package
from flopy4.mf6.spec import field
from flopy4.mf6.utils.time import Time


@dataclass(config=CFG, kw_only=True)
class Tdis(Package):
    dfn_name: ClassVar[str] = "sim-tdis"

    @dataclass(config=CFG)
    class PeriodData(Item):
        perlen: float
        nstp: int
        tsmult: float

    time_units: Optional[str] = field(default=None, block="options", optional=True)
    start_date_time: Optional[str] = field(
        default=None,
        # A raw ISO datetime like "1970-01-01T00:00:00" tokenizes into TWO
        # file tokens (e.g. [1970, "-01-01T00:00:00"]) -- the reader's
        # numeric-token grammar splits at the leading digits, before the
        # first embedded dash -- and a bare year like "1997" (no rest of an
        # ISO string on the row at all) tokenizes as a plain int, not a
        # str. Under attrs both passed through unvalidated (no type check
        # on this field at all); pydantic's real Optional[str] validation
        # correctly rejects a list or a bare int, so the converter (already
        # needed for the datetime -> isoformat direction) also normalizes
        # both back into one string here.
        converter=lambda v: (
            v.isoformat()
            if isinstance(v, datetime)
            else "".join(str(t) for t in v)
            if isinstance(v, list)
            else str(v)
            if isinstance(v, (int, float))
            else v
        ),
        block="options",
        optional=True,
    )
    nper: int = field(default=1, block="dimensions")
    perlen: NDArray[np.float64] = field(default=1.0)
    nstp: NDArray[np.int64] = field(default=1)
    tsmult: NDArray[np.float64] = field(default=1.0)
    perioddata: Optional[list[PeriodData]] = field(default=None, block="perioddata")

    # perlen/nstp/tsmult aren't Package "griddata" block fields (no
    # block="griddata" metadata), so Package._coerce_arrays' shape-driven
    # check doesn't touch them -- same underlying problem though (a
    # declared array type with a bare-scalar default/override), so this
    # needs its own mode="before" coercion, scoped to just these 3 fields
    # by name rather than metadata.
    @field_validator("perlen", "nstp", "tsmult", mode="before")
    @classmethod
    def _coerce_to_array(cls, v: Any) -> Any:
        if isinstance(v, np.ndarray):
            return v
        return np.asarray(v)

    def __post_init__(self):
        if self.perioddata:
            rows = [
                row
                if isinstance(row, Tdis.PeriodData)
                else Tdis.PeriodData(**row)
                if isinstance(row, dict)
                else Tdis.PeriodData(*row)
                for row in self.perioddata
            ]
            object.__setattr__(self, "perioddata", rows)
            object.__setattr__(self, "perlen", np.array([r.perlen for r in rows], dtype=np.float64))
            object.__setattr__(self, "nstp", np.array([r.nstp for r in rows], dtype=np.int64))
            object.__setattr__(self, "tsmult", np.array([r.tsmult for r in rows], dtype=np.float64))
            super().__post_init__()
            return
        nper = self.nper
        # _coerce_to_array only runs on an EXPLICITLY passed value
        # (pydantic doesn't validate an unused field default unless
        # validate_default=True, not set here) -- so an untouched default
        # (Tdis() with no perlen=/nstp=/tsmult= at all) still arrives here
        # as attrs would have always left it, a bare int/float; an
        # explicit scalar/list override arrives already coerced to a 0-d/
        # plain ndarray by that validator. Both are handled below.
        if isinstance(self.perlen, (int, float)):
            object.__setattr__(self, "perlen", np.full(nper, self.perlen, dtype=np.float64))
        elif self.perlen.size == 1:
            object.__setattr__(self, "perlen", np.full(nper, self.perlen.item(), dtype=np.float64))
        elif self.perlen.dtype != np.float64:
            object.__setattr__(self, "perlen", self.perlen.astype(np.float64))
        if isinstance(self.nstp, (int, float)):
            object.__setattr__(self, "nstp", np.full(nper, int(self.nstp), dtype=np.int64))
        elif self.nstp.size == 1:
            object.__setattr__(self, "nstp", np.full(nper, int(self.nstp.item()), dtype=np.int64))
        elif self.nstp.dtype != np.int64:
            object.__setattr__(self, "nstp", self.nstp.astype(np.int64))
        if isinstance(self.tsmult, (int, float)):
            object.__setattr__(self, "tsmult", np.full(nper, self.tsmult, dtype=np.float64))
        elif self.tsmult.size == 1:
            object.__setattr__(self, "tsmult", np.full(nper, self.tsmult.item(), dtype=np.float64))
        elif self.tsmult.dtype != np.float64:
            object.__setattr__(self, "tsmult", self.tsmult.astype(np.float64))
        rows = [
            Tdis.PeriodData(perlen=float(p), nstp=int(n), tsmult=float(t))
            for p, n, t in zip(self.perlen, self.nstp, self.tsmult)
        ]
        object.__setattr__(self, "perioddata", rows)
        super().__post_init__()

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
