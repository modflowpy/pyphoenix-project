"""Period list fields (CHD's, SFR's stress_period_data) as xarray.

Each period's rows are placed by their key, which sets the dense form's
dims:

- one ``cellid`` (CHD, WEL): the grid;
- a foreign key to another block's table (UZF's, SFR's ``ifno``): that
  table's dim (``nreaches``), or with ``grid=True`` the grid via its cellid;
- the package's own index (SPC's ``bndno``): a dim named for it.

``to_dataset`` gives each value column a ``(per, ...)`` variable, plus one
per aux name and, for keystring packages (SFR, LAK, MAW), per setting. An
array column (EVT's pxdp) gets a dim for its size (``nseg-1``). Unset
positions are ``FILL_DNODATA``, ``FILL_INT64`` or ``None``.

Periods fill forward as in MF6: a plain block replaces the last, keystring
settings hold until set again. A time-series value is NaN, its series named
in a ``<variable>_ts`` coordinate; boundnames are a ``boundname``
coordinate.

Two rows at one position raise unless ``duplicates`` ("sum", "first",
"last") merges them. "sum" adds every value column, aux included; a series
can't be summed. The merged position keeps one boundname: the first row's
for "first", the last row's for "sum" and "last". ``sparse=True`` keeps
every row along an ``entry`` dim, with period, key and setting as
coordinates; rows without a single key (HFB, MVR, OC) have only this form.

Use ``ds["head"]``, not ``ds.head``, which is ``Dataset.head()``.

``from_dataset`` inverts either form. From the dense form it writes a
period block only where a period changes, giving the same model but not
necessarily the same rows.
"""

import warnings
from collections.abc import Iterator
from typing import Any, Literal, Optional, cast, get_args

import attrs
import numpy as np
import pandas as pd
import xarray as xr
from modflow_devtools.dfns.schema import split_bound

from flopy4.mf6._types import TimeSeriesRef
from flopy4.mf6.constants import FILL_DNODATA, FILL_INT64, GRID_DIMS
from flopy4.mf6.item import (
    Item,
    _may_be_absent,
    _union_field_arms,
    item_list_type,
    item_list_words,
)
from flopy4.mf6.item_table import ItemTable, _column_of, _default
from flopy4.spec import is_array

Duplicates = Literal["raise", "sum", "first", "last"]
Kind = Literal["float", "int", "object"]


def period_list_field(cls: type) -> Optional[attrs.Attribute]:
    """A package's period list field (``_stress_period_data``), if any."""
    return next(
        (
            f
            for f in attrs.fields(cls)
            if f.metadata.get("block") == "period" and item_list_type(f.type) is not None
        ),
        None,
    )


def _row_type(pkg: Any) -> Any:
    """The package's row class, or the arm classes of a list of unions."""
    field = period_list_field(type(pkg))
    if field is None:
        raise ValueError(f"{type(pkg).__name__} has no stress period data")
    return item_list_type(field.type)


def _kind(f: attrs.Attribute) -> Kind:
    """How a column's values are stored: floats (time series too),
    integers, or objects (text, words, child files)."""
    if f.metadata.get("time_series"):
        return "float"
    t = f.type
    if is_array(f):
        t = next(iter(get_args(t)), None)
    if t is float:
        return "float"
    if t is int:
        return "int"
    return "object"


def _none(v: Any) -> bool:
    """Whether an object value is missing: xarray makes None NaN, and
    NetCDF makes it ''."""
    if isinstance(v, str):
        return not v
    return v is None or (isinstance(v, float) and np.isnan(v))


def _missing(kind: Kind) -> Any:
    return {"float": FILL_DNODATA, "int": FILL_INT64, "object": None}[kind]


def _dtype(kind: Kind) -> Any:
    return {"float": np.float64, "int": np.int64, "object": object}[kind]


def _is_key(f: attrs.Attribute) -> bool:
    return _is_cellid(f) or bool(f.metadata.get("fk") or f.metadata.get("pk"))


def _is_cellid(f: attrs.Attribute) -> bool:
    """Whether a field is one cellid."""
    return f.metadata.get("type") == "cellid"


def _aux_names(pkg: Any) -> list[str]:
    aux = getattr(pkg, "auxiliary", None)
    if isinstance(aux, (int, np.integer)):
        # a count, set from rows' aux values when no names were given
        if aux:
            raise ValueError("aux values have no names; give the package auxiliary=")
        return []
    return [] if aux is None else [str(n) for n in aux]


@attrs.frozen
class _Column:
    """A value column of a row or setting."""

    field: attrs.Attribute
    kind: Kind
    aux: bool = False  # a variable per aux name
    size: Optional[str] = None  # an array column's extra dim


@attrs.frozen
class _Setting:
    """The columns a plain row or keystring arm sets. ``pivot`` is the
    field naming the variable (AUXILIARY's auxname); ``extras`` are the
    setting's own index fields (diversion idv)."""

    arm: Optional[type]
    key: attrs.Attribute
    columns: tuple[_Column, ...]
    extras: tuple[str, ...] = ()
    pivot: Optional[str] = None


@attrs.frozen
class _Layout:
    """How a package's period rows break down into settings."""

    item: Any  # the row class, or the arm classes of a list of unions
    arms_field: Optional[str]  # the row's union field (SFR's sfrsetting)
    settings: tuple[_Setting, ...]

    @property
    def persistent(self) -> bool:
        """Whether settings hold until set again (keystring packages),
        rather than each period block replacing the last."""
        return self.settings[0].arm is not None

    def setting(self, row: Any) -> tuple[_Setting, Any, Any]:
        """A row's setting, the object holding its values, and its key."""
        if isinstance(row, str):
            raise ValueError(f"the row {row!r} has no dense form; use sparse=True")
        arm = row if self.arms_field is None else getattr(row, self.arms_field)
        if isinstance(arm, str):
            raise ValueError(f"the setting {arm!r} has no dense form; use sparse=True")
        setting = next((s for s in self.settings if s.arm is None or isinstance(arm, s.arm)), None)
        if setting is None:
            raise ValueError(f"no setting takes {type(arm).__name__}")
        holder = row if setting.arm is None or self.arms_field is not None else arm
        return setting, arm, getattr(holder, setting.key.name)


def _setting(fields: list[attrs.Attribute], key: attrs.Attribute, arm: Optional[type]) -> _Setting:
    rest = [f for f in fields if f is not key and f.name != "boundname"]
    extras = tuple(
        f.name for f in rest if arm is not None and f.metadata.get("index") and _kind(f) == "int"
    )
    rest = [f for f in rest if f.name not in extras]
    pivot = None
    if arm is not None and len(rest) > 1 and rest[0].type is str:
        pivot, rest = rest[0].name, rest[1:]
    columns = []
    for f in rest:
        shape = f.metadata.get("shape") or ()
        if is_array(f) and shape == ("auxiliary",):
            columns.append(_Column(f, _kind(f), aux=True))
        elif is_array(f) and shape:
            columns.append(_Column(f, _kind(f), size=str(shape[0])))
        elif is_array(f):
            columns.append(_Column(f, "object"))  # unsized, as a tuple
        else:
            columns.append(_Column(f, _kind(f)))
    return _Setting(arm, key, tuple(columns), extras, pivot)


def _layout(pkg: Any) -> Optional[_Layout]:
    """The package's rows as settings, or None if they have no single key
    (HFB, MVR, OC, ...), so no dense form."""
    item = _row_type(pkg)
    if isinstance(item, tuple):  # a list of unions: each arm has its own key
        settings: list[_Setting] = []
        for arm in item:
            fields = list(attrs.fields(arm))
            if len(keys := [f for f in fields if _is_key(f)]) != 1:
                return None
            settings.append(_setting(fields, keys[0], arm))
        return _Layout(item, None, tuple(settings))
    fields = list(item.fields())
    union = next((f for f in fields if _union_field_arms(item, f) is not None), None)
    keys = [f for f in fields if f is not union and _is_key(f)]
    if len(keys) != 1:
        return None
    if union is None:
        return _Layout(item, None, (_setting(fields, keys[0], None),))
    _, arms = cast(tuple, _union_field_arms(item, union))
    return _Layout(
        item, union.name, tuple(_setting(list(attrs.fields(a)), keys[0], a) for a in arms)
    )


@attrs.define
class _Key:
    """Where a key's rows are: dims and sizes, and the map between key
    values and positions."""

    dims: tuple[str, ...]
    sizes: list[int]  # 0 until known
    cell: bool  # the key value is a cellid
    cells: Optional[dict] = None  # grid view: key value -> cellid

    def position(self, value: Any) -> tuple[int, ...]:
        if self.cells is not None:
            if value not in self.cells:
                raise ValueError(f"{value} has no cell")
            value = self.cells[value]
        if isinstance(value, (tuple, list)):
            return tuple(int(v) for v in value)
        return (int(value),)

    def value(self, at: tuple[int, ...], back: Optional[dict] = None) -> Any:
        if back is not None:
            if at not in back:
                raise ValueError(f"cell {at} has values but no feature")
            return back[at]
        return at if self.cell else at[0]


def _grid(pkg: Any, width: int) -> tuple[tuple[str, ...], list[int]]:
    grid = GRID_DIMS[width]
    sizes = pkg.resolve_dims(*(s for s, _ in grid))
    if missing := [s for s, _ in grid if not sizes.get(s)]:
        raise ValueError(
            f"{type(pkg).__name__} needs the grid's {', '.join(missing)} to put its "
            "periods on the grid; add it to a model or give it dims="
        )
    return tuple(d for _, d in grid), [sizes[s] for s, _ in grid]


def _target(pkg: Any, key: attrs.Attribute) -> tuple[Optional[attrs.Attribute], str]:
    """The package field a foreign key refers to, and the referenced
    column (``packagedata.ifno`` -> packagedata, "ifno")."""
    block, _, column = str(key.metadata.get("fk") or "").partition(".")
    target = next(
        (f for f in attrs.fields(type(pkg)) if block and f.metadata.get("block") == block),
        None,
    )
    return target, column


def _key(pkg: Any, key: attrs.Attribute, grid: bool, width: Optional[int]) -> _Key:
    """A key's dims: the grid for a cellid, the referenced table's dim (or
    with ``grid``, the grid via its cellid), or a dim named for the key."""
    if _is_cellid(key):
        if width is None:
            raise ValueError("no row gives a cellid, so the grid's shape is unknown")
        return _Key(*_grid(pkg, width), cell=True)
    target, column = _target(pkg, key)
    rows = (getattr(pkg, target.name, None) if target else None) or []
    if grid:
        item = item_list_type(target.type) if target else None
        cellids = (
            []
            if item is None or isinstance(item, tuple)
            else [f for f in item.fields() if _is_cellid(f)]
        )
        if len(cellids) != 1:
            raise ValueError(f"{key.name} doesn't refer to a table with a cellid, so grid=True")
        if not rows:
            raise ValueError(f"{key.name} finds its cells through {target.name}, which isn't set")  # type: ignore[union-attr]
        cells = {getattr(r, column): tuple(getattr(r, cellids[0].name)) for r in rows}
        dims, sizes = _grid(pkg, len(next(iter(cells.values()))))
        return _Key(dims, sizes, cell=False, cells=cells)
    tshape = target.metadata.get("shape") if target else None
    dim = (split_bound(tshape[0])[1] if tshape else None) or key.name
    size = pkg.resolve_dims(dim).get(dim) or len(rows)
    return _Key((dim,), [size], cell=False)


def _periods(pkg: Any) -> dict[int, Any]:
    """The period rows, each period's a list or an `ItemTable`."""
    field = period_list_field(type(pkg))
    return (pkg.__dict__.get(field.name) if field else None) or {}


def _nper(pkg: Any, periods: dict[int, list]) -> int:
    return pkg.resolve_dims("nper").get("nper") or max(periods) + 1


def _values(
    pkg: Any, setting: _Setting, arm: Any
) -> Iterator[tuple[str, _Column, tuple[int, ...], Any]]:
    """A row's values: ``(variable, column, extra position, value)``."""
    base = tuple(int(getattr(arm, e)) for e in setting.extras)
    for c in setting.columns:
        value = getattr(arm, c.field.name)
        if setting.pivot is not None:
            yield str(getattr(arm, setting.pivot)), c, base, value
        elif c.aux:
            for i, name in enumerate(_aux_names(pkg)):
                yield name, c, base, value[i] if value is not None and len(value) > i else None
        elif c.size is not None:
            for i, v in enumerate(value or ()):
                yield c.field.name, c, (*base, i), v
        else:
            yield c.field.name, c, base, value


@attrs.define
class _Var:
    setting: _Setting
    column: _Column
    key: _Key
    extra_dims: tuple[str, ...]
    extra_sizes: list[int]


def _var_dims(setting: _Setting, column: _Column) -> tuple[str, ...]:
    return (*setting.extras, *((column.size,) if column.size else ()))


def to_dataset(
    pkg: Any, sparse: bool = False, duplicates: Duplicates = "raise", grid: bool = False
) -> xr.Dataset:
    """A list package's period rows as xarray (see the module docstring)."""
    if duplicates not in get_args(Duplicates):
        raise ValueError(f"duplicates must be one of {get_args(Duplicates)}, got {duplicates!r}")
    periods = _periods(pkg)
    if not periods:
        return xr.Dataset()
    layout = _layout(pkg)
    if sparse or layout is None:
        return _to_sparse(pkg, periods)
    nper = _nper(pkg, periods)
    if (ds := _dense_tables(pkg, layout, periods, nper, duplicates, grid)) is not None:
        return ds

    # a pass over the rows for the variables, their positions and values
    keys: dict[str, _Key] = {}
    variables: dict[str, _Var] = {}
    events: list[tuple[int, str, tuple[int, ...], Any, Optional[str]]] = []
    for kper, rows in sorted(periods.items()):
        for row in rows:
            setting, arm, value = layout.setting(row)
            if setting.key.name not in keys:
                width = len(value) if _is_cellid(setting.key) else None
                keys[setting.key.name] = _key(pkg, setting.key, grid, width)
            key = keys[setting.key.name]
            at = key.position(value)
            boundname = getattr(row, "boundname", None)
            for name, column, extra, v in _values(pkg, setting, arm):
                var = variables.get(name)
                if var is None:
                    dims = _var_dims(setting, column)
                    var = variables[name] = _Var(setting, column, key, dims, [0] * len(dims))
                elif var.setting is not setting or var.column is not column:
                    raise ValueError(f"two columns give {name!r}")
                for i, e in enumerate(extra):
                    var.extra_sizes[i] = max(var.extra_sizes[i], e + 1)
                if v is not None:
                    events.append((kper, name, (*extra, *at), v, boundname))
    if not events:
        return xr.Dataset()
    for key in keys.values():
        for i, size in enumerate(key.sizes):
            if not size:
                key.sizes[i] = 1 + max(
                    at[len(variables[n].extra_dims) + i]
                    for _, n, at, _, _ in events
                    if variables[n].key is key
                )

    def shape(var: _Var) -> tuple[int, ...]:
        return (*var.extra_sizes, *var.key.sizes)

    given = {name for _, name, _, _, _ in events}
    variables = {n: v for n, v in variables.items() if n in given}
    state = {
        n: np.full(shape(v), _missing(v.column.kind), _dtype(v.column.kind))
        for n, v in variables.items()
    }
    ts: dict[str, np.ndarray] = {}
    bkey = layout.settings[0].key.name if not layout.persistent else None
    bnames = (
        np.full(tuple(keys[bkey].sizes), None, dtype=object)
        if bkey in keys and any(bn is not None for *_, bn in events)
        else None
    )
    frames: dict[str, dict[int, np.ndarray]] = {
        n: {} for n in [*variables, *(["boundname"] if bnames is not None else [])]
    }
    ts_frames: dict[str, dict[int, np.ndarray]] = {}
    by_kper: dict[int, list] = {kper: [] for kper in periods}
    for event in events:
        by_kper[event[0]].append(event)
    for kper in sorted(periods):
        if not layout.persistent:  # a block replaces the last
            for n, v in variables.items():
                state[n] = np.full(shape(v), _missing(v.column.kind), _dtype(v.column.kind))
            ts = {n: np.full(a.shape, None, object) for n, a in ts.items()}
            if bnames is not None:
                bnames = np.full(bnames.shape, None, object)
        seen: dict[tuple, Any] = {}
        for _, name, at, value, boundname in by_kper[kper]:
            var = variables[name]
            ref = value.name if isinstance(value, TimeSeriesRef) else None
            number = np.nan if ref is not None else value
            if var.column.kind != "object" and ref is None:
                number = float(value) if var.column.kind == "float" else int(value)
            if (name, at) in seen:
                if duplicates == "raise":
                    raise ValueError(
                        f"period {kper} sets {name} at {at} twice; to_xarray(sparse=True) "
                        "keeps every row, or duplicates='sum', 'first' or 'last' merges them"
                    )
                if duplicates == "first":
                    continue
                if duplicates == "sum":
                    if (
                        ref is not None
                        or seen[(name, at)] is not None
                        or var.column.kind == "object"
                    ):
                        raise ValueError(f"period {kper}'s {name} at {at} can't be summed")
                    number = state[name][at] + number
            seen[(name, at)] = ref
            state[name][at] = number
            if ref is not None or name in ts:
                if name not in ts:
                    ts[name] = np.full(state[name].shape, None, object)
                ts[name][at] = ref
            if bnames is not None and var.setting.arm is None:
                bnames[at[len(var.extra_dims) :]] = boundname
        for n in variables:
            frames[n][kper] = state[n].copy()
        for n, a in ts.items():
            ts_frames.setdefault(n, {})[kper] = a.copy()
        if bnames is not None:
            frames["boundname"][kper] = bnames.copy()

    data_vars = {}
    coords = {}
    for n, var in variables.items():
        dims = ("per", *var.extra_dims, *var.key.dims)
        data_vars[n] = xr.DataArray(_stack(frames[n], nper), dims=dims)
        if n in ts_frames:
            none = np.full(shape(var), None, object)  # periods before its first series
            series = {k: ts_frames[n].get(k, none) for k in sorted(periods)}
            coords[f"{n}_ts"] = (dims, _stack(series, nper))
    if bnames is not None:
        coords["boundname"] = (("per", *keys[bkey].dims), _stack(frames["boundname"], nper))  # type: ignore[index]
    return xr.Dataset(data_vars, coords=coords)


def _numbers(c: _Column, a: np.ndarray) -> Optional[tuple[np.ndarray, Optional[np.ndarray]]]:
    """A table column's values as a variable holds them, and the series
    names if any; None if a row has no value (or one dense can't hold)."""
    if a.dtype != object:
        if c.kind == "object" or (c.kind == "int" and a.dtype.kind == "f"):
            return None
        return a.astype(_dtype(c.kind)), None
    values = a.tolist()
    if any(v is None for v in values):
        return None
    if c.kind == "object":
        if any(isinstance(v, (tuple, list, TimeSeriesRef)) for v in values):
            return None
        return a, None
    refs = [v.name if isinstance(v, TimeSeriesRef) else None for v in values]
    convert = float if c.kind == "float" else int
    numbers = np.array(
        [np.nan if r is not None else convert(v) for v, r in zip(values, refs)], _dtype(c.kind)
    )
    return numbers, (np.array(refs, dtype=object) if any(r is not None for r in refs) else None)


def _dense_tables(
    pkg: Any,
    layout: _Layout,
    periods: dict[int, Any],
    nper: int,
    duplicates: Duplicates,
    grid: bool,
) -> Optional[xr.Dataset]:
    """`to_dataset`'s dense form of plain (not keystring) rows, by column,
    or None to build it row by row."""
    if layout.persistent or not all(
        isinstance(t, ItemTable) and t.item_cls is layout.item for t in periods.values()
    ):
        return None
    setting = layout.settings[0]
    kf = setting.key
    key: Optional[_Key] = None
    variables: dict[str, _Var] = {}
    # per period: positions, each variable's values (and series names),
    # and the boundnames
    plans: dict[int, tuple[np.ndarray, list, Optional[np.ndarray]]] = {}
    for kper, t in sorted(periods.items()):
        if not len(t):
            continue
        kcol = t.columns.get(kf.name)
        if kcol is None or kcol.dtype.kind != "i":
            return None
        if _is_cellid(kf):
            if kcol.ndim != 2 or (kcol == FILL_INT64).any():
                return None
            if key is None:
                key = _key(pkg, kf, grid, kcol.shape[1])
            if kcol.shape[1] != len(key.dims):
                return None
            at = kcol
        else:
            if kcol.ndim != 1:
                return None
            if key is None:
                key = _key(pkg, kf, grid, None)
            if key.cells is None:
                at = kcol[:, None]
            else:
                at = np.array([key.position(v) for v in kcol.tolist()], dtype=np.int64)
        units: list[tuple[str, _Column, np.ndarray]] = []
        for c in setting.columns:
            col = t.columns.get(c.field.name)
            if col is None:
                if (default := _default(c.field)) is not None and default != ():
                    return None
                continue  # no values
            if c.aux:
                if col.dtype == object:
                    rows = col.tolist()
                    if any(r is None for r in rows) or len({len(r) for r in rows}) != 1:
                        return None
                    parts = [
                        np.array([r[i] for r in rows], dtype=object) for i in range(len(rows[0]))
                    ]
                else:
                    parts = [col[:, i] for i in range(col.shape[1])]
                units += [(name, c, a) for name, a in zip(_aux_names(pkg), parts)]
            elif c.size is not None:
                if col.dtype == object or col.ndim != 2:
                    return None
                if col.shape[1]:
                    units.append((c.field.name, c, col))
            elif col.ndim != 1:
                return None
            else:
                units.append((c.field.name, c, col))
        values = []
        for name, c, a in units:
            if (got := _numbers(c, a)) is None:
                return None
            var = variables.get(name)
            if var is None:
                dims = _var_dims(setting, c)
                var = variables[name] = _Var(setting, c, key, dims, [0] * len(dims))
            elif var.column is not c:
                raise ValueError(f"two columns give {name!r}")
            if c.size is not None:
                var.extra_sizes[0] = max(var.extra_sizes[0], a.shape[1])
            values.append((name, *got))
        if values:
            bcol = t.columns.get("boundname")
            bnames = None if bcol is None else np.array(bcol.tolist(), dtype=object)
            plans[kper] = (at, values, bnames)
    if not plans or key is None:
        return xr.Dataset()
    for i, size in enumerate(key.sizes):
        if not size:
            key.sizes[i] = 1 + max(int(at[:, i].max()) for at, _, _ in plans.values())
    sizes = np.array(key.sizes)
    if any(((at < 0) | (at >= sizes)).any() for at, _, _ in plans.values()):
        return None  # the rows' indexing (wrapping, raising) decides
    cells = int(np.prod(key.sizes))
    with_bnames = any(
        b is not None and any(x is not None for x in b.tolist()) for _, _, b in plans.values()
    )

    def shape(var: _Var) -> tuple[int, ...]:
        return (*var.extra_sizes, *var.key.sizes)

    frames: dict[str, dict[int, np.ndarray]] = {n: {} for n in variables}
    ts_frames: dict[str, dict[int, np.ndarray]] = {n: {} for n in variables}
    has_ts: set[str] = set()
    bframes: dict[int, np.ndarray] = {}
    for kper in sorted(periods):
        state = {
            n: np.full(shape(v), _missing(v.column.kind), _dtype(v.column.kind))
            for n, v in variables.items()
        }
        for n in variables:
            frames[n][kper] = state[n]
        if with_bnames:
            bframes[kper] = np.full(tuple(key.sizes), None, object)
        if kper in plans:
            at, values, bvals = plans[kper]
            lin = np.ravel_multi_index(tuple(at.T), tuple(key.sizes))
            order = np.argsort(lin, kind="stable")
            same = lin[order][1:] == lin[order][:-1]
            rows = np.arange(len(lin))
            first = last = rows
            if same.any():
                again, before = order[1:][same], order[:-1][same]
                if duplicates == "raise":
                    j = int(again.min())
                    name, c, _, _ = next((n, variables[n].column, v, r) for n, v, r in values)
                    where = (*((0,) if c.size else ()), *(int(x) for x in at[j]))
                    raise ValueError(
                        f"period {kper} sets {name} at {where} twice; to_xarray(sparse=True) "
                        "keeps every row, or duplicates='sum', 'first' or 'last' merges them"
                    )
                first = order[np.concatenate(([True], ~same))]
                last = order[np.concatenate((~same, [True]))]
                if duplicates == "sum":
                    bad = []
                    for k, (n, _, refs) in enumerate(values):
                        c = variables[n].column
                        if c.kind == "object":
                            hit = again
                        elif refs is not None:
                            hit = again[(refs[again] != None) | (refs[before] != None)]  # noqa: E711
                        else:
                            continue
                        if len(hit):
                            bad.append((int(hit.min()), k))
                    if bad:
                        j, k = min(bad)
                        n = values[k][0]
                        c = variables[n].column
                        where = (*((0,) if c.size else ()), *(int(x) for x in at[j]))
                        raise ValueError(f"period {kper}'s {n} at {where} can't be summed")
            pick = first if duplicates == "first" else last
            for n, numbers, refs in values:
                # an array column's extra dim first, as wide as this period's
                flat = state[n].reshape(-1, cells)[: 1 if numbers.ndim == 1 else numbers.shape[1]]
                if duplicates == "sum" and len(first) < len(lin):
                    total = np.zeros((cells, *numbers.shape[1:]), numbers.dtype)
                    np.add.at(total, lin, numbers)
                    flat[:, lin[first]] = total[lin[first]].T
                else:
                    flat[:, lin[pick]] = numbers[pick].T
                if refs is not None:
                    # a series is kept if a row giving one was taken
                    if any(r is not None for r in (refs[first] if duplicates == "first" else refs)):
                        has_ts.add(n)
                    ts = ts_frames[n][kper] = np.full(state[n].shape, None, object)
                    ts.reshape(cells)[lin[pick]] = refs[pick]
            if with_bnames and bvals is not None:
                bframes[kper].reshape(cells)[lin[pick]] = bvals[pick]

    data_vars = {}
    coords = {}
    for n, var in variables.items():
        dims = ("per", *var.extra_dims, *var.key.dims)
        data_vars[n] = xr.DataArray(_stack(frames[n], nper), dims=dims)
        if n in has_ts:
            none = np.full(shape(var), None, object)  # periods without series
            series = {k: ts_frames[n].get(k, none) for k in sorted(periods)}
            coords[f"{n}_ts"] = (dims, _stack(series, nper))
    if with_bnames:
        coords["boundname"] = (("per", *key.dims), _stack(bframes, nper))
    return xr.Dataset(data_vars, coords=coords)


def _stack(frames: dict[int, np.ndarray], nper: int) -> np.ndarray:
    """``{kper: array}`` as ``(nper, ...)``, each period holding the last
    block at or before it, missing before the first."""
    if past := [k for k in frames if k >= nper]:
        warnings.warn(f"periods {past} are past NPER ({nper}), dropped", stacklevel=3)
    blocks = sorted(k for k in frames if k < nper)
    first = frames[blocks[0] if blocks else min(frames)]  # all past NPER: all missing
    fill = (
        None if first.dtype == object else FILL_INT64 if first.dtype.kind in "iu" else FILL_DNODATA
    )
    out = np.full((nper, *first.shape), fill, dtype=first.dtype)
    for i, kper in enumerate(blocks):
        out[kper : blocks[i + 1] if i + 1 < len(blocks) else nper] = frames[kper]
    return out


def _is_missing(a: np.ndarray, kind: Kind) -> np.ndarray:
    if kind == "object":
        # None, NaN or '', as `_none`
        return (np.asarray(pd.isna(a), dtype=bool) | (a == "")).reshape(a.shape)
    return a == _missing(kind)


def _changed(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.dtype == object or b.dtype == object:
        if not a.size:
            return np.zeros(a.shape, bool)
        same = np.equal(a, b, dtype=object).astype(bool)
        return ~(same | (_is_missing(a, "object") & _is_missing(b, "object")))
    return ~((a == b) | (np.isnan(a) & np.isnan(b)) if a.dtype.kind == "f" else a == b)


def from_dataset(pkg: Any, ds: xr.Dataset) -> dict[int, Any]:
    """Period rows from ``to_dataset``'s dense or sparse form: a period's
    an `ItemTable` if its rows are tabular (as loaded), else a list."""
    if "entry" in ds.dims:
        return _from_sparse(pkg, ds)
    layout = _layout(pkg)
    if layout is None:
        raise ValueError(f"{type(pkg).__name__}'s rows have no dense form; give the sparse form")
    if not ds.data_vars:
        return {}
    dense = _Dense(ds, _match(pkg, layout, ds))
    keys = _dense_keys(pkg, ds, dense.found)
    if layout.persistent:
        return _setting_rows(layout, dense, keys)
    return _block_rows(layout, dense, keys)


Found = list[tuple[str, _Setting, _Column]]


def _match(pkg: Any, layout: _Layout, ds: xr.Dataset) -> Found:
    """The dataset's variables, each with its setting and column: columns
    by name first, then aux and named settings (AUXILIARY's) by name."""
    aux = _aux_names(pkg)
    found: Found = []
    claimed: set[str] = set()
    for s in layout.settings:
        for c in s.columns:
            if s.pivot is None and not c.aux and c.field.name in ds.data_vars:
                found.append((c.field.name, s, c))
                claimed.add(c.field.name)
    for s in layout.settings:
        for c in s.columns:
            if c.aux or s.pivot is not None:
                for n in aux or [str(v) for v in ds.data_vars]:
                    if n in ds.data_vars and n not in claimed:
                        found.append((n, s, c))
                        claimed.add(n)
    if unknown := [n for n in ds.data_vars if n not in claimed]:
        raise ValueError(f"{type(pkg).__name__} has no column for {unknown}")
    return found


def _dense_keys(pkg: Any, ds: xr.Dataset, found: Found) -> dict[str, tuple[_Key, Optional[dict]]]:
    """Each key's dims, from its variables' trailing dims, and in the grid
    view of feature rows, the map from cell back to feature."""
    keys: dict[str, tuple[_Key, Optional[dict]]] = {}
    for name, s, c in found:
        if s.key.name in keys:
            continue
        ndim = len(ds[name].dims) - 1 - len(_var_dims(s, c))
        key_dims = tuple(str(d) for d in ds[name].dims[-ndim:])
        width = next((w for w, g in GRID_DIMS.items() if tuple(d for _, d in g) == key_dims), None)
        cell = _is_cellid(s.key)
        key = _key(pkg, s.key, not cell and width is not None, width if cell else None)
        back: Optional[dict] = None
        if key.cells is not None:
            back = {}
            for k, at in key.cells.items():
                if at in back:
                    raise ValueError(f"cell {at} has two features, so the grid view is ambiguous")
                back[at] = k
        key.sizes = [ds.sizes[d] for d in key_dims]
        keys[s.key.name] = (key, back)
    return keys


@attrs.define
class _Dense:
    """A dense dataset's variables, read a period at a time."""

    ds: xr.Dataset
    found: Found

    def period(self, p: int) -> dict[str, np.ndarray]:
        """Each variable's values in period ``p``, with its series names
        (``<name>_ts``) and the boundnames."""
        now = {n: self.ds[n].values[p] for n, _, _ in self.found}
        for n, _, _ in self.found:
            if f"{n}_ts" in self.ds.coords:
                now[f"{n}_ts"] = self.ds.coords[f"{n}_ts"].values[p]
        if "boundname" in self.ds.coords:
            now["boundname"] = self.ds.coords["boundname"].values[p]
        return now

    @staticmethod
    def value(now: dict, n: str, c: _Column, at: tuple) -> Any:
        """A value as a row holds it, or None if missing."""
        ref = now.get(f"{n}_ts")
        return _dense_value(now[n][at], None if ref is None else ref[at], c)

    @staticmethod
    def column(now: dict, n: str, c: _Column, at: tuple) -> Any:
        """`value` at the positions ``at``: a numeric array if all are set
        numbers, else a list."""
        v = now[n][at]
        ref = now.get(f"{n}_ts")
        refs = None if ref is None else ref[at]
        if (refs is None or _is_missing(refs, "object").all()) and c.kind != "object":
            if not (v == _missing(c.kind)).any():
                return v
        if refs is None:
            return [_dense_value(x, None, c) for x in v.tolist()]
        return [_dense_value(x, r, c) for x, r in zip(v.tolist(), refs.tolist())]

    @staticmethod
    def values(now: dict, n: str, c: _Column, at: tuple, axis: int) -> Optional[tuple]:
        """An array column's values along its extra dim (at ``axis`` of
        ``at``), or None if all are missing; raises if some are."""
        size = now[n].shape[axis]
        vals = [_Dense.value(now, n, c, (*at[:axis], i, *at[axis:])) for i in range(size)]
        if all(v is None for v in vals):
            return None
        if any(v is None for v in vals):
            raise ValueError(f"{n} is missing values at {at}")
        return tuple(vals)


def _dense_value(v: Any, ref: Any, c: _Column) -> Any:
    if ref is not None and not _none(ref):
        return TimeSeriesRef(str(ref))
    if _none(v) if c.kind == "object" else v == _missing(c.kind):
        return None
    return float(v) if c.kind == "float" else int(v) if c.kind == "int" else v


def _whole(parts: list) -> Any:
    """An array field's values from its elements' columns: a numeric array,
    or a tuple per row (None if all missing); False if a row is missing
    only some."""
    if all(isinstance(p, np.ndarray) for p in parts):
        return np.stack(parts, axis=1)
    rows = list(zip(*(p.tolist() if isinstance(p, np.ndarray) else p for p in parts)))
    out: list = []
    for r in rows:
        if all(v is None for v in r):
            out.append(None)
        elif any(v is None for v in r):
            return False
        else:
            out.append(tuple(r))
    return out


def _period_rows(
    layout: _Layout,
    dense: _Dense,
    now: dict,
    key: _Key,
    back: Optional[dict],
    mask: np.ndarray,
    p: int,
) -> "ItemTable | list":
    """A period's rows, one per position with a value, as an `ItemTable`,
    or as Items if the columns don't make one (so a bad value raises)."""
    setting = layout.settings[0]
    pos = np.argwhere(mask)
    at = tuple(pos.T)
    n = len(pos)
    given: dict[str, Any] = {}
    if back is not None:
        given[setting.key.name] = [key.value(tuple(q), back) for q in pos.tolist()]
    else:
        given[setting.key.name] = pos if key.cell else pos[:, 0]
    for c in setting.columns:
        ns = [n_ for n_, _, cc in dense.found if cc is c]
        got: Any = None
        if c.aux:
            if ns:
                got = _whole([_Dense.column(now, n_, c, at) for n_ in ns])
        elif ns and c.size is not None:
            if size := now[ns[0]].shape[0]:
                got = _whole([_Dense.column(now, ns[0], c, (i, *at)) for i in range(size)])
        elif ns:
            got = _Dense.column(now, ns[0], c, at)
        if got is False:
            raise ValueError(f"{c.field.name} is missing some of its values in period {p}")
        if got is not None and not isinstance(got, np.ndarray) and all(v is None for v in got):
            got = None
        # an array column (aux, pxdp) may be absent, but not from some rows only
        some = isinstance(got, list) and None in got
        if (got is None or some) and not _may_be_absent(c.field) or some and (c.aux or c.size):
            q = pos[0] if got is None else pos[got.index(None)]
            raise ValueError(
                f"{c.field.name} has no value at {tuple(q.tolist())} in period {p}, "
                "where other columns do"
            )
        if got is not None:
            given[c.field.name] = got
    if "boundname" in now:
        names = [None if _none(b) else b for b in now["boundname"][at].tolist()]
        if any(b is not None for b in names):
            given["boundname"] = names
    if (table := ItemTable.from_columns(layout.item, n, given)) is not None:
        return table
    columns = {k: _as_list(v) for k, v in given.items()}
    return [
        layout.item(**{k: vs[i] for k, vs in columns.items() if vs[i] is not None})
        for i in range(n)
    ]


def _as_list(values: Any) -> list:
    """A column's values (an array, a row each, or a list) as a list."""
    if not isinstance(values, np.ndarray):
        return values
    return values.tolist() if values.ndim == 1 else [tuple(r) for r in values.tolist()]


def _positions(mask: np.ndarray) -> list[tuple[int, ...]]:
    return [tuple(int(i) for i in ix) for ix in np.argwhere(mask)]


def _block_rows(
    layout: _Layout, dense: _Dense, keys: dict[str, tuple[_Key, Optional[dict]]]
) -> dict[int, Any]:
    """Plain rows: a period block where a period differs from the last,
    a row at each position some variable has a value."""
    key, back = keys[layout.settings[0].key.name]
    spd: dict[int, Any] = {}
    prev: Optional[dict] = None
    for p in range(dense.ds.sizes["per"]):
        now = dense.period(p)
        if prev is not None and not any(_changed(now[n], prev[n]).any() for n in now):
            continue
        mask = np.zeros(tuple(key.sizes), dtype=np.bool_)
        for n, _, c in dense.found:
            present = ~_is_missing(now[n], c.kind)
            if (ref := now.get(f"{n}_ts")) is not None:
                present |= ~_is_missing(ref, "object")
            mask |= present.reshape(-1, *mask.shape).any(axis=0)
        rows = _period_rows(layout, dense, now, key, back, mask, p)
        if len(rows) or prev is not None:
            spd[p] = rows
        prev = now
    return spd


def _setting_rows(
    layout: _Layout, dense: _Dense, keys: dict[str, tuple[_Key, Optional[dict]]]
) -> dict[int, list]:
    """Keystring rows: a row where a setting changes. A named setting
    (AUXILIARY) is a row per name."""
    first = dense.period(0)
    prev = {
        n: np.full(a.shape, None, object)
        if a.dtype == object
        else np.full_like(a, _missing(c.kind))
        for (n, _, c), a in zip(dense.found, (first[n] for n, _, _ in dense.found))
    }
    for n in [n for n in prev if f"{n}_ts" in first]:
        prev[f"{n}_ts"] = np.full(prev[n].shape, None, object)
    spd: dict[int, list] = {}
    for p in range(dense.ds.sizes["per"]):
        now = dense.period(p)
        changed = {n: _changed(now[n], prev[n]) for n in prev if not n.endswith("_ts")}
        for n in changed:
            if f"{n}_ts" in prev:
                changed[n] |= _changed(now[f"{n}_ts"], prev[f"{n}_ts"])
        rows = []
        for kname, (key, back) in keys.items():
            group = [(n, s, c) for n, s, c in dense.found if s.key.name == kname]
            mask = np.zeros(tuple(key.sizes), dtype=np.bool_)
            for n, _, _ in group:
                mask |= changed[n].reshape(-1, *mask.shape).any(axis=0)
            for at in _positions(mask):
                for s in layout.settings:
                    units = [(n, c) for n, ss, c in group if ss is s]
                    if not units:
                        continue
                    for extra in np.ndindex(*now[units[0][0]].shape[: len(s.extras)]):
                        for unit in [[u] for u in units] if s.pivot else [units]:
                            kwargs = _setting_values(s, unit, now, changed, extra, at)
                            if kwargs is not None:
                                rows.append(_build(layout, s, key.value(at, back), kwargs))
        if rows:
            spd[p] = rows
        prev = now
    return spd


def _setting_values(
    s: _Setting,
    unit: list[tuple[str, _Column]],
    now: dict,
    changed: dict,
    extra: tuple,
    at: tuple,
) -> Optional[dict]:
    """A setting's values at a position, if any changed: its index fields'
    and columns' (and a named setting's name)."""

    def where(c: _Column) -> tuple:
        return (*extra, *(() if c.size is None else (slice(None),)), *at)

    if not any(changed[n][where(c)].any() for n, c in unit):
        return None
    kwargs: dict[str, Any] = {e: int(i) for e, i in zip(s.extras, extra)}
    for n, c in unit:
        if c.size is not None:
            v: Any = _Dense.values(now, n, c, (*extra, *at), len(extra))
        else:
            v = _Dense.value(now, n, c, (*extra, *at))
        if v is None:
            raise ValueError(f"{n} at {at} is unset; a setting can't be unset")
        if s.pivot:
            kwargs[s.pivot] = n
        kwargs[c.field.name] = v
    return kwargs


def _build(layout: _Layout, s: _Setting, keyval: Any, kwargs: dict) -> Any:
    """A keystring row: the arm, keyed itself (LAK's), or in a keyed row."""
    arm = cast(type, s.arm)
    if layout.arms_field is None:
        return arm(**{s.key.name: keyval}, **kwargs)
    return layout.item(**{s.key.name: keyval, layout.arms_field: arm(**kwargs)})


# --- sparse form ------------------------------------------------------------


def _row_fields(
    layout_item: Any, row: Any
) -> tuple[Optional[str], list[tuple[attrs.Attribute, Any]]]:
    """A row's setting keyword (for keystring rows) and its fields' values,
    an arm's after the row's own."""
    if isinstance(row, str):
        return row, []
    out: list[tuple[attrs.Attribute, Any]] = []
    keyword = None
    if isinstance(layout_item, tuple):
        keyword = type(row).keyword()
        return keyword, [(f, getattr(row, f.name)) for f in attrs.fields(type(row))]
    for f in attrs.fields(type(row)):
        v = getattr(row, f.name)
        if _union_field_arms(type(row), f) is not None:
            if isinstance(v, str):
                keyword = v
            else:
                keyword = type(v).keyword()
                out += [(g, getattr(v, g.name)) for g in attrs.fields(type(v))]
        else:
            out.append((f, v))
    return keyword, out


def _cell_names(f: attrs.Attribute, width: int) -> list[str]:
    """A cellid's columns, by the grid's dims: ``cellid_layer``, ..."""
    return [f"{f.name}_{d}" for _, d in GRID_DIMS[width]]


def _row_classes(item: Any) -> list[type]:
    """The row class and its arm classes, or a list of unions' arms."""
    if isinstance(item, tuple):
        return list(item)
    arms = [a for f in item.fields() for a in (_union_field_arms(item, f) or ((), ()))[1]]
    return [item, *arms]


def _put_value(put: Any, aux: list[str], f: attrs.Attribute, i: int, v: Any) -> None:
    """Entry ``i``'s value of the field ``f`` into its sparse column(s)."""
    if v is None:
        return
    shape = f.metadata.get("shape") or ()
    if _is_cellid(f):
        for name, x in zip(_cell_names(f, len(v)), v):
            put(name, "int", True, i, int(x))
    elif is_array(f) and shape == ("auxiliary",):
        for name, x in zip(aux, v):
            put(name, "float", False, i, x)
    elif is_array(f) and shape and _kind(f) != "object":
        put(f.name, _kind(f), False, i, tuple(v), size=str(shape[0]))
    elif is_array(f) or f.metadata.get("child") or isinstance(v, Item):
        put(f.name, "object", False, i, v)
    elif f.name == "boundname" or f.metadata.get("index") or _is_key(f):
        put(f.name, _kind(f), True, i, v)
    else:
        put(f.name, _kind(f), False, i, v)


def _put_block(
    put_block: Any, aux: list[str], f: attrs.Attribute, start: int, col: np.ndarray
) -> bool:
    """Put a table's numeric column into its sparse column(s) from entry
    ``start``, as `_put_value` would; False for objects."""
    if col.dtype == object:
        return False
    shape = f.metadata.get("shape") or ()
    kind = _kind(f)
    if _is_cellid(f):
        if col.ndim != 2:
            return False
        if (col[:, 0] != FILL_INT64).any():  # a NONE row is missing
            for j, name in enumerate(_cell_names(f, col.shape[1])):
                put_block(name, "int", True, start, col[:, j])
    elif is_array(f) and shape == ("auxiliary",):
        if col.ndim != 2:
            return False
        for j, name in enumerate(aux[: col.shape[1]]):
            put_block(name, "float", False, start, col[:, j].astype(np.float64))
    elif kind == "object" or (kind == "int" and col.dtype.kind == "f"):
        return False
    elif is_array(f) and shape:
        if col.ndim != 2:
            return False
        put_block(f.name, kind, False, start, col.astype(_dtype(kind)), size=str(shape[0]))
    elif is_array(f) or f.metadata.get("child") or col.ndim != 1:
        return False
    else:
        coord = f.name == "boundname" or bool(f.metadata.get("index")) or _is_key(f)
        put_block(f.name, kind, coord, start, col.astype(_dtype(kind)))
    return True


def _to_sparse(pkg: Any, periods: dict[int, Any]) -> xr.Dataset:
    item = _row_type(pkg)
    union = isinstance(item, tuple) or any(
        _union_field_arms(item, f) is not None for f in item.fields()
    )
    aux = _aux_names(pkg)
    fields = {f.name for c in _row_classes(item) for f in attrs.fields(c)}
    if clash := sorted(fields & set(aux)):
        raise ValueError(f"aux {clash} has the name of a column")
    columns: dict[str, dict] = {}  # name -> {kind, coord, size, values, blocks}

    def column(name: str, kind: Kind, coord: bool, size: Optional[str]) -> dict:
        col = columns.setdefault(
            name, {"kind": kind, "coord": coord, "size": size, "values": {}, "blocks": []}
        )
        if col["kind"] != kind:
            col["kind"] = "object"
        return col

    def put(name: str, kind: Kind, coord: bool, i: int, v: Any, size: Optional[str] = None) -> None:
        column(name, kind, coord, size)["values"][i] = v

    def put_block(
        name: str, kind: Kind, coord: bool, start: int, a: np.ndarray, size: Optional[str] = None
    ) -> None:
        column(name, kind, coord, size)["blocks"].append((start, a))

    # a table's rows go in by column, a list's by row
    per: list[np.ndarray] = []
    keywords: list = []
    n = 0
    for kper, rows in sorted(periods.items()):
        if isinstance(rows, ItemTable) and rows.item_cls is item:
            for f in item.fields() if len(rows) else ():
                a = rows.columns.get(f.name)
                if a is not None and _put_block(put_block, aux, f, n, a):
                    continue
                for i, v in enumerate(rows.values(f.name), n):
                    _put_value(put, aux, f, i, v)
        else:
            for i, row in enumerate(rows, n):
                keyword, row_values = _row_fields(item, row)
                keywords.append(keyword)
                for f, v in row_values:
                    _put_value(put, aux, f, i, v)
        per.append(np.full(len(rows), kper, dtype=np.int64))
        n += len(rows)

    data_vars: dict[str, Any] = {}
    coords: dict[str, Any] = {"per": ("entry", np.concatenate(per))}
    if union:
        coords["setting"] = ("entry", np.array(keywords, dtype=object))
    for name, col in columns.items():
        kind, values, blocks = col["kind"], col["values"], col["blocks"]
        arr: np.ndarray
        ts: Optional[np.ndarray] = None
        if col["size"] is not None:
            width = max([len(v) for v in values.values()] + [b.shape[1] for _, b in blocks])
            arr = np.full((n, width), _missing(kind), _dtype(kind))
            for start, b in blocks:
                arr[start : start + len(b), : b.shape[1]] = b
            for i, vs in values.items():
                for j, x in enumerate(vs):
                    if isinstance(x, TimeSeriesRef):
                        if ts is None:
                            ts = np.full((n, width), None, object)
                        arr[i, j], ts[i, j] = np.nan, x.name
                    else:
                        arr[i, j] = x
            dims: tuple[str, ...] = ("entry", col["size"])
        else:
            arr = np.full((n,), _missing(kind), _dtype(kind))
            for start, b in blocks:
                arr[start : start + len(b)] = b
            for i, x in values.items():
                if isinstance(x, TimeSeriesRef):
                    if ts is None:
                        ts = np.full((n,), None, object)
                    arr[i], ts[i] = np.nan, x.name
                else:
                    arr[i] = x
            dims = ("entry",)
        if col["coord"]:
            coords[name] = (dims, arr)
        else:
            data_vars[name] = (dims, arr)
        if ts is not None:
            coords[f"{name}_ts"] = (dims, ts)
    ds = xr.Dataset(data_vars, coords=coords)
    ds.attrs["periods"] = np.array(sorted(periods), dtype=np.int64)
    return ds


def _entry_value(v: Any, ts: Any) -> Any:
    """An entry's value of a sparse variable, with its series name if
    any, as a row holds it, or None if missing."""
    if np.ndim(v):
        if ts is None:
            ts = [None] * len(v)
        out = [x if _none(t) else TimeSeriesRef(t) for x, t in zip(v.tolist(), ts)]
        out = [x for x in out if not (isinstance(x, float) and x == FILL_DNODATA)]
        return tuple(out) or None
    if not _none(ts):
        return TimeSeriesRef(str(ts))
    if _none(v) or (isinstance(v, (float, np.floating)) and v == FILL_DNODATA):
        return None
    if isinstance(v, (np.integer,)) and v == FILL_INT64:
        return None
    return v.item() if isinstance(v, np.generic) else v


def _sparse_column(ds: xr.Dataset, names: dict, name: str) -> Any:
    """`_entry_value` of every entry: a numeric array if each has a value
    and none is a series', else a list; None if there's no variable."""
    if name not in names:
        return None
    v = names[name].values
    ts = ds.coords[f"{name}_ts"].values if f"{name}_ts" in ds.coords else None
    if ts is None and v.dtype.kind in "iuf" and (v.ndim == 1 or v.shape[1]):
        if v.dtype.kind == "f":
            missing = (v == FILL_DNODATA) if v.ndim > 1 else np.isnan(v) | (v == FILL_DNODATA)
        else:
            missing = (v == FILL_INT64) if v.ndim == 1 else np.zeros(v.shape, bool)
        if not missing.any():
            return v
    if ts is None:
        return [_entry_value(x, None) for x in v]
    return [_entry_value(x, t) for x, t in zip(v, ts)]


def _sparse_tables(pkg: Any, ds: xr.Dataset, item: Any, names: dict) -> Optional[dict[int, Any]]:
    """`_from_sparse`'s plain rows as an `ItemTable` per period, by
    column; None to leave them to it."""
    n = ds.sizes["entry"]
    aux = _aux_names(pkg)
    given: dict[str, Any] = {}
    for f in item.fields():
        shape = f.metadata.get("shape") or ()
        got: Any = None
        if _is_cellid(f):
            for width in (3, 2, 1):
                parts = [_sparse_column(ds, names, c) for c in _cell_names(f, width)]
                if all(isinstance(p, np.ndarray) for p in parts):  # each row has this cell
                    got = np.stack(parts, axis=1).astype(np.int64)
                    break
                if any(isinstance(p, list) and any(x is not None for x in p) for p in parts):
                    return None  # some rows have it: by row
        elif is_array(f) and shape == ("auxiliary",):
            parts = [_sparse_column(ds, names, a) for a in aux]
            if parts and all(isinstance(p, np.ndarray) for p in parts):
                got = np.stack(parts, axis=1)
            elif parts:
                cols = [
                    [None] * n if p is None else p.tolist() if isinstance(p, np.ndarray) else p
                    for p in parts
                ]
                got = [tuple(r) if any(x is not None for x in r) else None for r in zip(*cols)]
        else:
            got = _sparse_column(ds, names, f.name)
        if got is not None:
            given[f.name] = got
    table = ItemTable.from_columns(item, n, given)
    if table is None:
        return None
    per = ds.coords["per"].values.astype(np.int64)
    spd: dict[int, Any] = {int(k): ItemTable(item, {}, 0) for k in ds.attrs.get("periods", [])}
    order = np.argsort(per, kind="stable")
    kpers, starts = np.unique(per[order], return_index=True)
    bounds = [*starts.tolist(), n]
    fields = attrs.fields_dict(item)
    for i, kper in enumerate(kpers.tolist()):
        rows = order[bounds[i] : bounds[i + 1]]
        columns: dict[str, np.ndarray] = {}
        for k, c in table.columns.items():
            if c.dtype != object:
                columns[k] = c[rows]
                continue
            # a period's own: numbers if it has no series, none if defaults
            f = fields[k]
            if (col := _column_of(f, c[rows].tolist())) is not None:
                columns[k] = col
        spd[kper] = ItemTable(item, columns, len(rows))
    return dict(sorted(spd.items()))


def _from_sparse(pkg: Any, ds: xr.Dataset) -> dict[int, Any]:
    item = _row_type(pkg)
    words = item_list_words(cast(attrs.Attribute, period_list_field(type(pkg))).type)
    arm_field = None
    arms: tuple = ()
    if isinstance(item, tuple):
        arms = item
    else:
        arm_field = next((f for f in item.fields() if _union_field_arms(item, f) is not None), None)
        if arm_field is not None:
            words, arms = cast(tuple, _union_field_arms(item, arm_field))
    by_keyword = {a.keyword().upper(): a for a in arms}
    aux = _aux_names(pkg)
    names = {**ds.data_vars, **{c: ds.coords[c] for c in ds.coords if c not in ("per", "setting")}}
    if not arms and "setting" not in ds.coords:
        if (tables := _sparse_tables(pkg, ds, item, names)) is not None:
            return tables

    def get(name: str, i: int) -> Any:
        if name not in names:
            return None
        ts = ds.coords[f"{name}_ts"].values[i] if f"{name}_ts" in ds.coords else None
        return _entry_value(names[name].values[i], ts)

    def kwargs_for(cls: type, i: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in attrs.fields(cls):
            if arm_field is not None and f.name == arm_field.name:
                continue
            shape = f.metadata.get("shape") or ()
            if _is_cellid(f):
                for width in (3, 2, 1):
                    cell = [get(n, i) for n in _cell_names(f, width)]
                    if all(c is not None for c in cell):
                        out[f.name] = tuple(int(c) for c in cell)
                        break
            elif is_array(f) and shape == ("auxiliary",):
                vals = [get(n, i) for n in aux]
                if any(v is not None for v in vals):
                    out[f.name] = tuple(vals)
            elif (v := get(f.name, i)) is not None:
                out[f.name] = v
        return out

    n = ds.sizes["entry"]
    spd: dict[int, list] = {int(k): [] for k in ds.attrs.get("periods", [])}
    for i in range(n):
        kper = int(ds.coords["per"].values[i])
        keyword = ds.coords["setting"].values[i] if "setting" in ds.coords else None
        if keyword is not None and str(keyword).upper() in words:
            row: Any = str(keyword).upper()
            if arm_field is not None:
                row = item(**kwargs_for(item, i), **{arm_field.name: row})
        elif keyword is not None:
            arm = by_keyword[str(keyword).upper()]
            if arm_field is None:
                row = arm(**kwargs_for(arm, i))
            else:
                row = item(**kwargs_for(item, i), **{arm_field.name: arm(**kwargs_for(arm, i))})
        else:
            row = item(**kwargs_for(item, i))
        spd.setdefault(kper, []).append(row)
    return dict(sorted(spd.items()))
