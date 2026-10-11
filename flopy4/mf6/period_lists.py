"""Period list fields (CHD's, WEL's stress_period_data) on the model grid.

A list package's period block gives its boundaries row by row, each at a
cell: ``{kper: [row, ...]}``. ``to_dataset`` puts each value column on the
grid, one ``(per, ...grid)`` variable per column (aux, one per aux name),
``FILL_DNODATA`` where a period has no boundary. Periods carry forward as
in MF6: a period block replaces the previous one as a whole, and a period
with no block holds the last one given. ``from_dataset`` is the inverse.

The grid form loses what doesn't fit on a grid; ``Package.to_dataframe()``
is the lossless form. Boundnames are dropped, with a warning, and these
raise:

- two rows at one cell in a period,
- a time-series value,
- a package whose rows aren't each at one cell: keystring settings (SFR,
  LAK, MAW, TVK, ...), two cellids (HFB), or none (STO, MVR, ...).

A row can find its cell through another block: UZF's period rows give the
UZF cell number (``ifno``), which packagedata maps to a cell.
"""

import warnings
from typing import Any, Optional

import attrs
import numpy as np
import xarray as xr

from flopy4.mf6._types import TimeSeriesRef
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.item import Item, item_list_type
from flopy4.mf6.period_arrays import dense

# cellid width -> the grid's (size, dim) pairs, dims named as
# Package.to_dataarray names them
_GRIDS: dict[int, tuple[tuple[str, str], ...]] = {
    3: (("nlay", "layer"), ("nrow", "y"), ("ncol", "x")),
    2: (("nlay", "layer"), ("ncpl", "face")),
    1: (("nodes", "node"),),
}


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


def _item_cls(pkg: Any) -> "type[Item]":
    field = period_list_field(type(pkg))
    item_cls = item_list_type(field.type) if field else None
    if item_cls is None or isinstance(item_cls, tuple):
        raise ValueError(
            f"{type(pkg).__name__}'s period rows are keystring settings, which have no "
            "grid form; use to_dataframe()"
        )
    return item_cls


def _cellid_fields(cls: "type[Item]") -> list[attrs.Attribute]:
    return [f for f in cls.fields() if f.metadata.get("cellid")]


def _locator(pkg: Any, item_cls: "type[Item]") -> tuple[str, Optional[dict]]:
    """The row field that finds a row's cell, and, when it finds it through
    another block (UZF's ifno, through packagedata), ``{key: cellid}``."""
    cellids = _cellid_fields(item_cls)
    if len(cellids) == 1:
        return cellids[0].name, None
    if not cellids:
        for f in item_cls.fields():
            block, _, pk = str(f.metadata.get("fk") or "").partition(".")
            other = next(
                (g for g in attrs.fields(type(pkg)) if g.metadata.get("block") == block), None
            )
            if other is None:
                continue
            other_cls = item_list_type(other.type)
            if other_cls is None or isinstance(other_cls, tuple):
                continue
            if len(other_cellids := _cellid_fields(other_cls)) != 1:
                continue
            rows = getattr(pkg, other.name) or []
            if not rows:
                raise ValueError(
                    f"{type(pkg).__name__}'s period rows find their cells through "
                    f"{other.name}, which isn't set"
                )
            return f.name, {getattr(r, pk): getattr(r, other_cellids[0].name) for r in rows}
    raise ValueError(
        f"{type(pkg).__name__}'s period rows aren't each at one cell, so they have no "
        "grid form; use to_dataframe()"
    )


def _grid(pkg: Any, width: int) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """The grid's shape and dims, for cellids of ``width``."""
    grid = _GRIDS[width]
    sizes = pkg.resolve_dims(*(s for s, _ in grid))
    if missing := [s for s, _ in grid if not sizes.get(s)]:
        raise ValueError(
            f"{type(pkg).__name__} needs the grid's {', '.join(missing)} to put its "
            "periods on the grid; add it to a model or give it dims="
        )
    return tuple(sizes[s] for s, _ in grid), tuple(d for _, d in grid)


def _columns(pkg: Any, item_cls: "type[Item]", key: str) -> dict[str, tuple[attrs.Attribute, Any]]:
    """``{variable: (column, part)}``: a scalar column's variable (part None),
    one per aux name (part its position), and an array column's variable
    with an extra dim (part ``slice(None)``)."""
    out: dict[str, tuple[attrs.Attribute, Any]] = {}
    for f in item_cls.fields():
        if f.name in (key, "boundname"):
            continue
        if f.metadata.get("shape") == ("auxiliary",):
            names = [] if pkg.auxiliary is None else [str(n) for n in pkg.auxiliary]
            for i, name in enumerate(names):
                if name in out or name in {g.name for g in item_cls.fields()}:
                    raise ValueError(f"aux {name!r} has the name of a column")
                out[name] = (f, i)
        elif f.metadata.get("array"):
            out[f.name] = (f, slice(None))
        else:
            out[f.name] = (f, None)
    return out


def _number(value: Any, column: str) -> float:
    if isinstance(value, TimeSeriesRef):
        raise ValueError(
            f"{column} is from time series {value.name!r}, which can't be put on the grid yet"
        )
    if isinstance(value, str):
        raise ValueError(f"{column} is text ({value!r}), which can't be put on the grid")
    return FILL_DNODATA if value is None else float(value)


def to_dataset(pkg: Any) -> xr.Dataset:
    """A list package's period rows on the grid (see the module docstring)."""
    item_cls = _item_cls(pkg)
    key, cells = _locator(pkg, item_cls)
    field = period_list_field(type(pkg))
    periods: dict[int, list] = (pkg.__dict__.get(field.name) if field else None) or {}
    rows = [row for kper_rows in periods.values() for row in kper_rows]
    if not rows:
        return xr.Dataset()

    def cell(row: Item) -> tuple:
        value = getattr(row, key)
        return tuple(value if cells is None else cells[value])

    shape, grid_dims = _grid(pkg, len(cell(rows[0])))
    nper = pkg.resolve_dims("nper").get("nper") or max(periods) + 1
    columns = _columns(pkg, item_cls, key)
    # extra dim sizes, for array columns (EVT's pxdp)
    extra = {
        name: max(len(getattr(r, f.name)) for r in rows)
        for name, (f, part) in columns.items()
        if isinstance(part, slice)
    }
    if any(r.boundname for r in rows if hasattr(r, "boundname")):
        warnings.warn("boundnames have no grid form, dropped", stacklevel=3)

    grids: dict[str, dict[int, np.ndarray]] = {name: {} for name in columns}
    given: set[str] = set()
    for kper, kper_rows in sorted(periods.items()):
        for name in columns:
            grids[name][kper] = np.full(
                (extra[name], *shape) if name in extra else shape, FILL_DNODATA
            )
        seen: set[tuple] = set()
        for row in kper_rows:
            at = cell(row)
            # Summing a cell's rows is another option (several WEL rows in a
            # cell add up), but a sum can't be split back into rows.
            if at in seen:
                raise ValueError(f"period {kper} has two rows at cell {at}")
            seen.add(at)
            for name, (f, part) in columns.items():
                value = getattr(row, f.name)
                if isinstance(part, slice):
                    if len(value) != extra[name]:
                        raise ValueError(f"{f.name} has rows of different lengths")
                    if extra[name]:
                        grids[name][kper][(slice(None), *at)] = [_number(v, f.name) for v in value]
                        given.add(name)
                    continue
                if part is not None:
                    value = value[part] if len(value) > part else None
                if value is not None:
                    given.add(name)
                grids[name][kper][at] = _number(value, name)

    data_vars = {}
    for name in columns:
        if name not in given:
            continue  # an optional column no row gives (EVT's petm0)
        dims = ("per", *((f"{name}_dim0",) if name in extra else ()), *grid_dims)
        data_vars[name] = xr.DataArray(dense(grids[name], nper), dims=dims, name=name)
    return xr.Dataset(data_vars)


def from_dataset(pkg: Any, ds: xr.Dataset) -> dict[int, list]:
    """Period rows from ``to_dataset``'s grid form. A period block is made
    where a period differs from the one before it."""
    item_cls = _item_cls(pkg)
    key, cells = _locator(pkg, item_cls)
    keys = None if cells is None else {tuple(c): k for k, c in cells.items()}
    columns = {n: c for n, c in _columns(pkg, item_cls, key).items() if n in ds.data_vars}
    if not columns:
        return {}
    for f in item_cls.fields():
        if f.name not in (key, "boundname") and not f.metadata.get("optional"):
            if f.name not in {c.name for c, _ in columns.values()}:
                raise ValueError(f"the dataset has no {f.name!r}")
    arrays = {n: ds[n].values for n in columns}
    nper = ds.sizes["per"]
    var_dims = ds[next(iter(columns))].dims
    ndim = next(w for w, grid in _GRIDS.items() if var_dims[-w:] == tuple(d for _, d in grid))
    # aux names per aux column, to check a row gives all of them
    nparts = {f.name: sum(c is f for c, _ in columns.values()) for f, _ in columns.values()}

    spd: dict[int, list] = {}
    prev: Optional[dict[str, np.ndarray]] = None
    for kper in range(nper):
        now = {n: a[kper] for n, a in arrays.items()}
        if prev is not None and all(np.array_equal(now[n], prev[n]) for n in now):
            continue
        mask = np.zeros(next(iter(now.values())).shape[-ndim:], dtype=bool)
        for a in now.values():
            mask |= (a != FILL_DNODATA).reshape(-1, *mask.shape).any(axis=0)
        rows = []
        for at in (tuple(int(i) for i in ix) for ix in np.argwhere(mask)):
            kwargs: dict[str, Any] = {}
            parts: dict[str, dict[int, float]] = {}
            for name, (f, part) in columns.items():
                if isinstance(part, slice):
                    values = now[name][(slice(None), *at)]
                    if (values == FILL_DNODATA).all():
                        continue
                    if (values == FILL_DNODATA).any():
                        raise ValueError(f"{name} is missing values at cell {at} in period {kper}")
                    kwargs[f.name] = tuple(float(v) for v in values)
                elif (value := now[name][at]) == FILL_DNODATA:
                    if part is None and not f.metadata.get("optional"):
                        raise ValueError(
                            f"{name} has no value at cell {at} in period {kper}, "
                            "where other columns do"
                        )
                elif part is None:
                    kwargs[f.name] = float(value)
                else:
                    parts.setdefault(f.name, {})[part] = float(value)
            for col, values in parts.items():
                if len(values) != nparts[col]:
                    raise ValueError(f"{col} is missing values at cell {at} in period {kper}")
                kwargs[col] = tuple(values[i] for i in range(len(values)))
            if keys is None:
                kwargs[key] = at
            elif at in keys:
                kwargs[key] = keys[at]
            else:
                raise ValueError(f"cell {at} has values in period {kper} but no {key}")
            rows.append(item_cls(**kwargs))
        if rows or prev is not None:
            spd[kper] = rows
        prev = now
    return spd
