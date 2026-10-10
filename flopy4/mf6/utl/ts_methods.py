from collections.abc import Mapping
from typing import TYPE_CHECKING, Optional, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from flopy4.mf6.utl.ts import Ts


class TsMethods:
    """Methods for the generated `Ts`; fields come from the DFN."""

    @classmethod
    def from_series(  # type: ignore[misc]
        cls: type["Ts"],
        data: Union[pd.DataFrame, pd.Series, Mapping[str, pd.Series]],
        method: Union[str, Mapping[str, str]] = "linear",
        sfac: Union[float, Mapping[str, float], None] = None,
        **kwargs,
    ) -> "Ts":
        """Build a TS6 file from its series: a DataFrame, its index the
        times and its columns the names, a named Series, or a mapping of
        names to Series. The series share the file's times, so each must
        have a value at every time.

        ``method`` (``linear`` or ``stepwise``) and ``sfac``
        (a scale factor) are one for all the series, or one per name.
        Times are simulation times, in the model's time units.
        """
        if isinstance(data, pd.Series):
            if data.name is None:
                raise ValueError("a Series needs a name, the time series' name")
            data = data.to_frame()
        elif not isinstance(data, pd.DataFrame):
            data = pd.DataFrame(dict(data))
        names = [str(n) for n in data.columns]
        if not names:
            raise ValueError("no time series given")
        if not pd.api.types.is_numeric_dtype(data.index):
            raise ValueError(f"times must be numbers (simulation times), got {data.index.dtype}")
        if data.isna().any().any():
            missing = [n for n, has in zip(names, data.isna().any()) if has]
            raise ValueError(f"series {missing} have no value at some times")
        data = data.sort_index()

        def per_name(value, field: str):
            """The value for all the series, or a list of one per series."""
            if value is None or not isinstance(value, Mapping):
                return value, None
            if unknown := set(value) - set(names):
                raise ValueError(f"{field} given for unknown series {sorted(unknown)}")
            if absent := [n for n in names if n not in value]:
                raise ValueError(f"no {field} for series {absent}")
            return None, [value[n] for n in names]

        method_all, methods = per_name(method, "interpolation_method")
        sfac_all, sfacs = per_name(sfac, "sfac")
        times = data.index.to_numpy(dtype=np.float64)
        values = data.to_numpy(dtype=np.float64)
        return cls(
            time_series_name=cls.TimeSeriesName(time_series_names=names),
            timeseries=[
                cls.Timeseries(ts_time=t, ts_array=tuple(row))
                for t, row in zip(times.tolist(), values.tolist())
            ],
            interpolation_method=methods,
            interpolation_methodrecord_single=method_all,
            sfac=sfacs,
            sfacrecord_single=sfac_all,
            **kwargs,
        )

    def to_dataframe(self: "Ts") -> pd.DataFrame:  # type: ignore[misc]
        """The series as a DataFrame, its index the times and its columns
        the names (see `from_series`)."""
        names: Optional[list[str]] = (
            self.time_series_name.time_series_names if self.time_series_name else None
        )
        rows = self.timeseries or []
        index = pd.Index([r.ts_time for r in rows], name="time", dtype=np.float64)
        values = np.array([r.ts_array for r in rows], dtype=np.float64).reshape(len(rows), -1)
        return pd.DataFrame(values, index=index, columns=names)
