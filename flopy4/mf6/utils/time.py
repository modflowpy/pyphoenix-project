import numpy as np
import pandas as pd
from flopy.discretization.modeltime import ModelTime
from numpy.typing import ArrayLike


class Time(ModelTime):
    """Extend flopy3's ModelTime"""

    @classmethod
    def from_timestamps(
        cls,
        timestamps: ArrayLike,
        nstp: ArrayLike | None = None,
        tsmult: ArrayLike | None = None,
    ) -> "Time":
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
        Time
            Time discretization object
        """

        unique_times = np.unique(np.hstack(pd.to_datetime(timestamps)))  # np.unique also sorts
        if len(unique_times) < 2:
            raise ValueError("Need at least two timestamps to create time discretization")

        timedeltas = to_timedeltas(unique_times)
        perlen = np.array(
            [delta.total_seconds() / 86400.0 for delta in timedeltas], dtype=np.float64
        )
        nper = len(perlen)

        if nstp is None:
            nstp_array = np.ones(nper, dtype=np.int64)
        elif np.isscalar(nstp):
            nstp_array = np.full(nper, nstp, dtype=np.int64)
        else:
            nstp_array = np.array(nstp, dtype=np.int64)
            if len(nstp_array) != nper:
                raise ValueError(
                    f"nstp length ({len(nstp_array)}) must match number of periods ({nper})"
                )

        if tsmult is None:
            tsmult_array = np.ones(nper, dtype=np.float64)
        elif np.isscalar(tsmult):
            tsmult_array = np.full(nper, tsmult, dtype=np.float64)
        else:
            tsmult_array = np.array(tsmult, dtype=np.float64)
            if len(tsmult_array) != nper:
                raise ValueError(
                    f"tsmult length ({len(tsmult_array)}) must match number of periods ({nper})"
                )

        return cls(
            perlen=perlen,
            nstp=nstp_array,
            tsmult=tsmult_array,
            time_units="days",
            start_datetime=pd.to_datetime(unique_times[0]).to_pydatetime(),
        )


def to_timedeltas(
    timestamps: ArrayLike,
) -> list[pd.Timedelta]:
    """
    Converts a sequence of datetime-like objects to a list of timedelta
    objects representing the durations between consecutive time points.

    Parameters
    ----------
    timestamps : sequence of datetime-likes
        A sequence of datetime-like objects representing time points.

    Returns
    -------
    timedeltas : list of pd.Timedelta
        A list of durations between consecutive time points.
    """
    if len(np.atleast_1d(timestamps)) < 2:
        return []

    timestamps = pd.to_datetime(timestamps)
    return [pd.Timedelta(end - start) for start, end in zip(timestamps[:-1], timestamps[1:])]  # type: ignore
