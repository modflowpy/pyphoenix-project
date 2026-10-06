"""Period array fields (WELG's q, RCHA's recharge/irch/aux), stored per period.

Each field holds only the periods it's given, keyed by 0-based stress period:
``{0: arr, 3: arr}``. A period with no key carries the previous one forward,
as a period block missing from the file does in MF6. Aux nests the same way,
``aux[kper][name]``.

How a period carries forward depends on the package:

- Grid packages (CHDG, WELG, ...; those with a ``readarraygrid`` option)
  read a period as one unit. Every period block resets the boundary set, so
  a field missing from a period that's given is empty, not carried. A period
  whose stress arrays are entirely ``FILL_DNODATA`` clears every boundary.
- Layer-array packages (RCHA, EVTA, SPCA) carry each array forward on its
  own until it's given again.

In layer-array packages a period's value can instead be the name of a
time-array series (a ``str``), whose arrays MF6 interpolates in time:
``recharge={0: "rchseries"}``, written ``RECHARGE TIMEARRAYSERIES rchseries``.
"""

import warnings
from collections.abc import Mapping
from typing import Any, Optional

import attrs
import numpy as np

from flopy4.mf6.constants import FILL_DNODATA, FILL_INT64


def is_grid_package(cls: type) -> bool:
    """Whether a package reads its period blocks as grid packages do (CHDG,
    WELG, ...): those have a ``readarraygrid`` option."""
    return "readarraygrid" in attrs.fields_dict(cls)


def _is_int(arr: Any) -> bool:
    return np.dtype(arr.dtype).kind in "iu"


def all_nodata(arr: Any) -> bool:
    """Whether an array is entirely ``FILL_DNODATA``: no stress in any cell."""
    return bool((arr == FILL_DNODATA).all())


def _as_array(value: Any) -> Any:
    # Keep anything array-like (dask included) as it is, and a time-array
    # series' name.
    return value if hasattr(value, "shape") or isinstance(value, str) else np.asarray(value)


def split_tas(periods: Mapping[int, Any]) -> tuple[dict[int, Any], dict[int, Any]]:
    """Split ``{kper: value}`` into its arrays and its time-array series
    references (names), for either form (aux's ``{kper: {name: value}}`` too).
    """
    arrays: dict[int, Any] = {}
    refs: dict[int, Any] = {}
    for kper, value in periods.items():
        if isinstance(value, Mapping):
            a = {n: v for n, v in value.items() if not isinstance(v, str)}
            r = {n: v for n, v in value.items() if isinstance(v, str)}
            if a or not r:
                arrays[kper] = a
            if r:
                refs[kper] = r
        elif isinstance(value, str):
            refs[kper] = value
        else:
            arrays[kper] = value
    return arrays, refs


def split_periods(value: Any) -> dict[int, Any]:
    """Split a dense ``(nper, ...)`` array into ``{kper: array}``.

    A float period that's entirely ``FILL_DNODATA`` means the period isn't
    given, so it's dropped and the previous period carries forward. To clear
    a grid package's period, use the dict form. Integer arrays have no such
    value and keep every period.
    """
    value = _as_array(value)
    if value.ndim < 2:
        raise ValueError(f"dense period array needs a leading nper axis, got shape {value.shape}")
    keep_all = _is_int(value)
    return {
        kper: value[kper]
        for kper in range(value.shape[0])
        if keep_all or not all_nodata(value[kper])
    }


def to_period_dict(value: Any) -> Optional[dict[int, Any]]:
    """Convert a period array field's value to ``{kper: array}``.

    Accepts the dict form (kept, with each value made an array) or a dense
    ``(nper, ...)`` array (see ``split_periods``).
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {int(kper): _as_array(arr) for kper, arr in sorted(value.items())}
    return split_periods(value)


def to_named_period_dict(value: Any) -> Optional[dict[int, dict[str, Any]]]:
    """Convert dynamically named period arrays (aux) to ``{kper: {name: array}}``.

    Accepts that form, or the by-name form ``{name: dense (nper, ...) array}``,
    whose periods are split as ``split_periods`` does.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"expected a dict of named period arrays, got {type(value).__name__}")
    if all(isinstance(k, str) for k in value):
        periods: dict[int, dict[str, Any]] = {}
        for name, dense in value.items():
            for kper, arr in split_periods(dense).items():
                periods.setdefault(kper, {})[name] = arr
        return dict(sorted(periods.items()))
    return {
        int(kper): {str(name): _as_array(arr) for name, arr in arrays.items()}
        for kper, arrays in sorted(value.items())
    }


def _fill_value(arr: Any) -> Any:
    return FILL_INT64 if _is_int(arr) else FILL_DNODATA


def dense(
    periods: Mapping[int, Any],
    nper: int,
    carry_forward: bool = True,
    given: Optional[list[int]] = None,
) -> np.ndarray:
    """Stack ``{kper: array}`` into a dense ``(nper, ...)`` array.

    A period missing from ``periods`` holds the last value at or before it
    (``carry_forward``), or a fill value: ``FILL_DNODATA`` for floats and
    ``FILL_INT64`` for integers. With ``given`` (a grid package's periods,
    over all its fields), a period that's given but missing from ``periods``
    is filled, not carried: a grid period block replaces the whole period.
    Periods past ``nper`` are dropped, with a warning.
    """
    if not periods:
        raise ValueError("no periods to stack")
    if refs := split_tas(periods)[1]:
        raise ValueError(
            f"periods {sorted(refs)} come from a time-array series, which can't be made dense yet"
        )
    if past := [kper for kper in periods if kper >= nper]:
        warnings.warn(f"periods {past} are past NPER ({nper}), dropped", stacklevel=2)
    first = _as_array(next(iter(periods.values())))
    fill = _fill_value(first)
    out = np.full((nper, *first.shape), fill, dtype=first.dtype)
    starts = sorted(set(given or ()) | set(periods))
    for i, kper in enumerate(starts):
        if kper >= nper:
            break
        stop = (starts[i + 1] if i + 1 < len(starts) else nper) if carry_forward else kper + 1
        if kper in periods:
            out[kper:stop] = np.asarray(periods[kper])
    return out
