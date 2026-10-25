"""Period array fields (WELG's q, RCHA's recharge/irch/aux), stored per period.

Each field holds only the periods it's given, keyed by 0-based stress period:
``{0: arr, 3: arr}``. Periods fill forward: a period with no key repeats the
previous one, as a period block missing from the file does in MF6. Aux nests
the same way, ``aux[kper][name]``.

How a period fills forward depends on the package:

- Layer-array packages (RCHA, EVTA, SPCA) fill each array forward on its
  own until it's given again. Each column has its own boundary, so a value
  carried forward stays with its cell.
- Grid packages (CHDG, WELG, ...; those with a ``readarraygrid`` option)
  fill each array forward on its own too, as MF6's loader does, but their
  boundaries are a packed list each period block rebuilds from its first
  array, and an array a block leaves out keeps its values in the order of
  the list it was last read with. So a value carried forward only stays
  with its cell if the block's cells are the ones it was last read with.
  ``check_grid_periods`` checks that, and that each array read after the
  first has a value in every cell the first sets. A ``None`` period,
  ``q={3: None}``, is given with no stress: it clears that field, and
  every boundary if each stress field is cleared, as an empty period block
  does. An array that's entirely ``FILL_DNODATA`` means the same, and is
  stored as ``None``. (MF6's DFNs say a grid package's stress arrays are
  required in each period block, and its aux arrays carry forward; flopy4
  follows what the loader does instead, for now.)

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


def _cells(arr: Any) -> Optional[np.ndarray]:
    """Where an array has a value (isn't ``FILL_DNODATA``), or None if that
    can't be told without computing it (dask) or it isn't an array."""
    if not isinstance(arr, np.ndarray):
        return None
    return np.asarray(arr != FILL_DNODATA)


def _same_cells(a: np.ndarray, b: np.ndarray) -> bool:
    shape = np.broadcast_shapes(a.shape, b.shape)
    return np.array_equal(np.broadcast_to(a, shape), np.broadcast_to(b, shape))


def _covers(arr: np.ndarray, cells: np.ndarray) -> bool:
    shape = np.broadcast_shapes(arr.shape, cells.shape)
    return bool(np.broadcast_to(arr, shape)[np.broadcast_to(cells, shape)].all())


def check_grid_periods(
    stress: Mapping[str, Mapping[int, Any]], aux: Optional[Mapping[int, Mapping[str, Any]]]
) -> None:
    """Check a grid package's periods read as MF6's grid-array loader
    (``GridArrayLoadType``, Mf6FileGridArray.f90) reads them.

    The loader keeps one packed list of boundaries. Each period block
    rebuilds it from the first array read there (in the order written: the
    stress fields as declared, then aux) with a value in any cell; arrays
    read after that are taken at those cells only. An array a block leaves
    out isn't read, so it keeps the values it had, in the order of the
    list as it was when it was last read. So:

    - an array read after the first must have a value in each of the
      block's cells, or ``FILL_DNODATA`` becomes the value there, and
    - an array a block leaves out must have been last read with the same
      cells the block has, or its values land on the wrong cells.

    A period a field is cleared in (None) isn't checked for that field, nor
    is a field after it's cleared, until it's given again. Arrays that
    aren't numpy (dask) aren't checked, nor are their periods.
    """
    aux = aux or {}
    # each array's cells when it was last read: its values' order
    read_at: dict[str, np.ndarray] = {}
    active: dict[str, bool] = {}
    for kper in sorted({k for p in stress.values() for k in p} | set(aux)):
        block = [(n, p[kper]) for n, p in stress.items() if kper in p]
        block += [(f"aux {n!r}", a) for n, a in aux.get(kper, {}).items()]
        for name, arr in block:
            active[name] = arr is not None
        given = [(n, a, _cells(a)) for n, a in block if a is not None]
        if any(c is None for _, _, c in given):
            for name, _, _ in given:
                read_at.pop(name, None)
            continue
        first = next(((n, c) for n, _, c in given if c.any()), None)
        if first is None:
            continue
        first_name, cells = first
        for name, arr, _ in given:
            if name != first_name and not _covers(arr != FILL_DNODATA, cells):
                raise ValueError(
                    f"period {kper}: {name} has no value in some of the cells "
                    f"{first_name} sets there; MF6 would take FILL_DNODATA as "
                    "the value"
                )
        names = {n for n, _, _ in given}
        for name, prev in read_at.items():
            if name not in names and active.get(name) and not _same_cells(prev, cells):
                raise ValueError(
                    f"period {kper}: {first_name} sets cells that differ from "
                    f"those {name} was last given with, and MF6 would carry "
                    f"{name}'s values to the wrong cells; give {name} again in "
                    f"period {kper}, or give {first_name} those same cells"
                )
        for name in names:
            read_at[name] = cells


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
