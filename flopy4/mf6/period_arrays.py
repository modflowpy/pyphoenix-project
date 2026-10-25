"""Period array fields (WELG's q, RCHA's recharge/irch/aux), stored per period.

Each field holds only the periods it's given, keyed by 0-based stress period:
``{0: arr, 3: arr}``. Periods fill forward: a period with no key repeats the
previous one, as a period block missing from the file does in MF6. Aux nests
the same way, ``aux[kper][name]``.

How a period fills forward depends on the package:

- Layer-array packages (RCHA, EVTA, SPCA) fill each array forward on its
  own until it's given again.
- Grid packages (CHDG, WELG, ...; those with a ``readarraygrid`` option)
  do too, as MF6's loader does, but MF6 keeps a period's values only at its
  active cells, so a carried array must match them (``check_grid_periods``).
  A ``None`` period, ``q={3: None}``, clears that field, and every boundary
  if each stress field is cleared, as an empty period block does. An array
  that's entirely ``FILL_DNODATA`` means the same, and is stored as
  ``None``. (The DFNs say stress arrays are required in each period block
  and only aux carries forward; flopy4 follows the loader for now.)

In layer-array packages a period's value can instead be a time-array
series, by name (`TimeArraySeriesRef`), whose arrays MF6 interpolates in
time: ``recharge={0: TimeArraySeriesRef("rchseries")}``, written
``RECHARGE TIMEARRAYSERIES rchseries``. A plain name, ``{0: "rchseries"}``,
works at runtime too, but isn't the typed form: mypy rejects it, since the
conversion happens in ``Package._init_period_arrays``, after init.
"""

import warnings
from collections.abc import Mapping
from typing import Any, Optional

import attrs
import numpy as np

from flopy4.mf6._types import TimeArraySeriesRef
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


def is_cleared(value: Any) -> bool:
    """Whether a grid package's period array means no stress in any cell:
    ``None``, or a float array entirely ``FILL_DNODATA``."""
    return value is None or (hasattr(value, "shape") and not _is_int(value) and all_nodata(value))


def _as_array(value: Any) -> Any:
    # Keep anything array-like (dask included) as it is, a time-array series
    # reference, given by name or not, and None (a cleared grid period).
    if value is None:
        return None
    if isinstance(value, str):
        return TimeArraySeriesRef(value)
    if hasattr(value, "shape") or isinstance(value, TimeArraySeriesRef):
        return value
    return np.asarray(value)


def split_tas(periods: Mapping[int, Any]) -> tuple[dict[int, Any], dict[int, Any]]:
    """Split ``{kper: value}`` into its arrays and its time-array series
    references, for either form (aux's ``{kper: {name: value}}`` too).
    """
    arrays: dict[int, Any] = {}
    refs: dict[int, Any] = {}
    for kper, value in periods.items():
        if isinstance(value, Mapping):
            a = {n: v for n, v in value.items() if not isinstance(v, TimeArraySeriesRef)}
            r = {n: v for n, v in value.items() if isinstance(v, TimeArraySeriesRef)}
            if a or not r:
                arrays[kper] = a
            if r:
                refs[kper] = r
        elif isinstance(value, TimeArraySeriesRef):
            refs[kper] = value
        else:
            arrays[kper] = value
    return arrays, refs


def check_grid_periods(
    stress: Mapping[str, Mapping[int, Any]], aux: Optional[Mapping[int, Mapping[str, Any]]]
) -> None:
    """Check a grid package's periods read as MF6's grid-array loader reads them.

    In each period block, the first array written (stress fields as declared,
    then aux) with a value in any cell sets the active cells, and MF6 keeps
    values only there. So each other array in the block needs a value in every
    active cell, and an array carried from an earlier block needs the same
    active cells it was last given with. Cleared (None) fields aren't checked
    until given again, nor are blocks with dask arrays.
    """
    last: dict[str, np.ndarray] = {}  # active cells each array was last given with
    for kper in sorted({k for p in stress.values() for k in p} | set(aux or {})):
        block = {n: p[kper] for n, p in stress.items() if kper in p}
        block |= {f"aux {n!r}": a for n, a in (aux or {}).get(kper, {}).items()}
        for name in block:
            last.pop(name, None)
        given = {n: a != FILL_DNODATA for n, a in block.items() if a is not None}
        if not all(isinstance(h, np.ndarray) for h in given.values()):
            continue
        first, active = next(((n, h) for n, h in given.items() if h.any()), (None, None))
        if active is None:
            continue
        for name, has in given.items():
            has, act = np.broadcast_arrays(has, active)
            if not has[act].all():
                raise ValueError(
                    f"period {kper}: {name} has no value in some of the cells "
                    f"{first} sets; MF6 would read FILL_DNODATA there"
                )
        for name, cells in last.items():
            cells, act = np.broadcast_arrays(cells, active)
            if not np.array_equal(cells, act):
                raise ValueError(
                    f"period {kper}: {first} sets other cells than {name} was "
                    f"last given with, so MF6 would carry {name} to the wrong "
                    f"cells; give {name} again in period {kper}"
                )
        last |= dict.fromkeys(given, active)


def split_periods(value: Any) -> dict[int, Any]:
    """Split a dense ``(nper, ...)`` array into ``{kper: array}``.

    A float period that's entirely ``FILL_DNODATA`` means the period isn't
    given, so it's dropped and the previous period fills forward. To clear
    a grid package's period, use the dict form. Integer arrays have no such
    value and keep every period.
    """
    value = value if hasattr(value, "shape") else np.asarray(value)
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
    fill_forward: bool = True,
    shape: Optional[tuple[int, ...]] = None,
) -> np.ndarray:
    """Stack ``{kper: array}`` into a dense ``(nper, ...)`` array.

    A 0-d array (a period given as one value, a CONSTANT) fills its periods.
    Each period's shape is that of the periods given in full, else
    ``shape``, which must then be given.

    A period missing from ``periods`` holds the last value at or before it
    (``fill_forward``), or a fill value: ``FILL_DNODATA`` for floats and
    ``FILL_INT64`` for integers. A ``None`` (cleared) period is filled too.
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
    arrays = [a for a in periods.values() if a is not None]
    if not arrays:
        raise ValueError("every period is cleared, so no array gives the shape")
    first = _as_array(arrays[0])
    full = next((a for a in arrays if np.ndim(a) > 0), None)
    if full is not None:
        shape = _as_array(full).shape
    elif shape is None:
        raise ValueError("every period is one value, so no array gives the shape")
    fill = _fill_value(first)
    out = np.full((nper, *shape), fill, dtype=first.dtype)
    starts = sorted(periods)
    for i, kper in enumerate(starts):
        if kper >= nper:
            break
        stop = (starts[i + 1] if i + 1 < len(starts) else nper) if fill_forward else kper + 1
        if periods.get(kper) is not None:
            out[kper:stop] = np.asarray(periods[kper])
    return out
