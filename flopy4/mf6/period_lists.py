"""Period list fields (CHD's, SFR's stress_period_data) as xarray.

A list package's period block gives its rows: ``{kper: [row, ...]}``. Each
row is at a position given by its key, and the key decides the dense form:

- one ``cellid`` (CHD, WEL, TVK): the grid, ``(layer, row, col)``,
  ``(layer, cell)`` or ``(node,)``;
- a foreign key to another block's table (UZF's, SFR's ``ifno``): that
  table's sizing dimension, ``(nuzfcells,)``, ``(nreaches,)``; with
  ``grid=True``, the grid, through the table's cellid;
- an index of the package's own (SPC's ``bndno``): a dim named for it.

``to_dataset`` gives each value column a ``(per, ...)`` variable: one per
aux name, and, for a keystring package (SFR, LAK, MAW, ...), one per
setting (``status``, ``inflow``, ...), with a named setting (AUXILIARY
``conc 1.0``) a variable per name. An array column (EVT's pxdp) has an
extra dim named for its size (``nseg-1``), and a setting's own index
(SFR's diversion ``idv``) one named for the index. Positions a period
doesn't set are missing: ``FILL_DNODATA`` (floats), ``FILL_INT64``
(integers) or ``None`` (text and objects; xarray shows it as NaN).

Periods carry forward as in MF6. A plain period block replaces the one
before it as a whole; a keystring package's settings each hold until set
again. A period with no block holds the last one.

A row with a time-series value has NaN there, the series named in the
``<variable>_ts`` coordinate. Boundnames are a ``boundname`` coordinate.

Two rows at a position in a period raise; ``duplicates`` merges them
("sum", "first" or "last"), which loses rows. ``sparse=True`` keeps every
row, an ``entry`` dim over all the periods' rows with each row's period,
key and setting as coordinates, a cellid's by the grid's dims
(``cellid_layer``, ``cellid_row``, ``cellid_col``). A package whose rows have no single key (HFB's
two cellids, MVR, OC) has only the sparse form.

``from_dataset`` is the inverse of either. From the dense form it writes a
period block where a period differs from the one before it, so periods
that only repeat the last load as carried, and a keystring row where a
setting changes. That gives the same model, not the same rows: their
order, and settings that repeat a value, aren't kept.

The dense form is built eagerly, a full array per period.
"""

import warnings
from collections.abc import Iterator
from typing import Any, Literal, Optional, cast, get_args

import attrs
import numpy as np
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
    """Whether an object value is missing: xarray makes None NaN."""
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
    """What a kind of row sets: a plain row's columns, or a keystring
    arm's. ``pivot`` names the field that names the variable (AUXILIARY's
    auxname); ``extras`` the setting's own index fields (diversion idv)."""

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
    """A key's dims: the grid for a cellid, else the referenced table's
    sizing dim (or, with ``grid``, the grid through its cellid), else a dim
    named for the key."""
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


def _periods(pkg: Any) -> dict[int, list]:
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
            coords[f"{n}_ts"] = (dims, _stack(ts_frames[n], nper))
    if bnames is not None:
        coords["boundname"] = (("per", *keys[bkey].dims), _stack(frames["boundname"], nper))  # type: ignore[index]
    return xr.Dataset(data_vars, coords=coords)


def _stack(frames: dict[int, np.ndarray], nper: int) -> np.ndarray:
    """``{kper: array}`` as ``(nper, ...)``, each period holding the last
    block at or before it, missing before the first."""
    if past := [k for k in frames if k >= nper]:
        warnings.warn(f"periods {past} are past NPER ({nper}), dropped", stacklevel=3)
    blocks = sorted(k for k in frames if k < nper)
    first = frames[blocks[0]]
    fill = (
        None if first.dtype == object else FILL_INT64 if first.dtype.kind in "iu" else FILL_DNODATA
    )
    out = np.full((nper, *first.shape), fill, dtype=first.dtype)
    for i, kper in enumerate(blocks):
        out[kper : blocks[i + 1] if i + 1 < len(blocks) else nper] = frames[kper]
    return out


def _is_missing(a: np.ndarray, kind: Kind) -> np.ndarray:
    if kind == "object":
        return np.vectorize(_none, otypes=[bool])(a) if a.size else np.zeros(a.shape, bool)
    return a == _missing(kind)


def _same(x: Any, y: Any) -> bool:
    return (_none(x) and _none(y)) or x is y or bool(x == y)


def _changed(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.dtype == object or b.dtype == object:
        if not a.size:
            return np.zeros(a.shape, bool)
        return ~np.vectorize(_same, otypes=[bool])(a, b)
    return ~((a == b) | (np.isnan(a) & np.isnan(b)) if a.dtype.kind == "f" else a == b)


def from_dataset(pkg: Any, ds: xr.Dataset) -> dict[int, list]:
    """Period rows from ``to_dataset``'s dense or sparse form."""
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
        v = now[n][at]
        if (ref := now.get(f"{n}_ts")) is not None and not _none(ref[at]):
            return TimeSeriesRef(str(ref[at]))
        if _none(v) if c.kind == "object" else v == _missing(c.kind):
            return None
        return float(v) if c.kind == "float" else int(v) if c.kind == "int" else v

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


def _positions(mask: np.ndarray) -> list[tuple[int, ...]]:
    return [tuple(int(i) for i in ix) for ix in np.argwhere(mask)]


def _block_rows(
    layout: _Layout, dense: _Dense, keys: dict[str, tuple[_Key, Optional[dict]]]
) -> dict[int, list]:
    """Plain rows: a period block where a period differs from the last,
    a row at each position some variable has a value."""
    setting = layout.settings[0]
    key, back = keys[setting.key.name]
    names = {id(c): [n for n, _, cc in dense.found if cc is c] for c in setting.columns}
    spd: dict[int, list] = {}
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
        rows = []
        for at in _positions(mask):
            kwargs: dict[str, Any] = {setting.key.name: key.value(at, back)}
            for c in setting.columns:
                ns = names[id(c)]
                if c.aux:
                    vals = [dense.value(now, n, c, at) for n in ns]
                    if any(v is not None for v in vals):
                        if any(v is None for v in vals):
                            raise ValueError(f"aux is missing values at {at} in period {p}")
                        kwargs[c.field.name] = tuple(vals)
                elif ns and c.size is not None:
                    if (vs := dense.values(now, ns[0], c, at, 0)) is not None:
                        kwargs[c.field.name] = vs
                elif ns and (v := dense.value(now, ns[0], c, at)) is not None:
                    kwargs[c.field.name] = v
                if c.field.name not in kwargs and not _may_be_absent(c.field):
                    raise ValueError(
                        f"{c.field.name} has no value at {at} in period {p}, where other columns do"
                    )
            if "boundname" in now and not _none(now["boundname"][at]):
                kwargs["boundname"] = now["boundname"][at]
            rows.append(layout.item(**kwargs))
        if rows or prev is not None:
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


def _to_sparse(pkg: Any, periods: dict[int, list]) -> xr.Dataset:
    item = _row_type(pkg)
    union = isinstance(item, tuple) or any(
        _union_field_arms(item, f) is not None for f in item.fields()
    )
    flat = [
        (kper, *_row_fields(item, row)) for kper, rows in sorted(periods.items()) for row in rows
    ]
    aux = _aux_names(pkg)
    fields = {f.name for c in _row_classes(item) for f in attrs.fields(c)}
    if clash := sorted(fields & set(aux)):
        raise ValueError(f"aux {clash} has the name of a column")
    n = len(flat)
    columns: dict[str, dict] = {}  # name -> {kind, coord, size, values}

    def put(name: str, kind: Kind, coord: bool, i: int, v: Any, size: Optional[str] = None) -> None:
        col = columns.setdefault(name, {"kind": kind, "coord": coord, "size": size, "values": {}})
        if col["kind"] != kind:
            col["kind"] = "object"
        col["values"][i] = v

    for i, (_, _, values) in enumerate(flat):
        for f, v in values:
            if v is None:
                continue
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

    data_vars: dict[str, Any] = {}
    coords: dict[str, Any] = {"per": ("entry", np.array([k for k, _, _ in flat], dtype=np.int64))}
    if union:
        coords["setting"] = ("entry", np.array([kw for _, kw, _ in flat], dtype=object))
    for name, col in columns.items():
        kind, values = col["kind"], col["values"]
        arr: np.ndarray
        ts: np.ndarray
        if col["size"] is not None:
            width = max(len(v) for v in values.values())
            arr = np.full((n, width), _missing(kind), _dtype(kind))
            ts = np.full((n, width), None, object)
            for i, vs in values.items():
                for j, x in enumerate(vs):
                    if isinstance(x, TimeSeriesRef):
                        arr[i, j], ts[i, j] = np.nan, x.name
                    else:
                        arr[i, j] = x
            dims: tuple[str, ...] = ("entry", col["size"])
        else:
            arr = np.full((n,), _missing(kind), _dtype(kind))
            ts = np.full((n,), None, object)
            for i, x in values.items():
                if isinstance(x, TimeSeriesRef):
                    arr[i], ts[i] = np.nan, x.name
                else:
                    arr[i] = x
            dims = ("entry",)
        if col["coord"]:
            coords[name] = (dims, arr)
        else:
            data_vars[name] = (dims, arr)
        if any(t is not None for t in ts.flat):
            coords[f"{name}_ts"] = (dims, ts)
    ds = xr.Dataset(data_vars, coords=coords)
    ds.attrs["periods"] = np.array(sorted(periods), dtype=np.int64)
    return ds


def _from_sparse(pkg: Any, ds: xr.Dataset) -> dict[int, list]:
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

    def get(name: str, i: int) -> Any:
        if name not in names:
            return None
        v = names[name].values[i]
        ts = ds.coords[f"{name}_ts"].values[i] if f"{name}_ts" in ds.coords else None
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
