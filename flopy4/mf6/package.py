import operator
import re
import warnings
from abc import ABC
from pathlib import Path
from typing import Any, Optional

import attrs
import numpy as np
import pandas as pd
import xarray as xr
from modflow_devtools.dfns import dim_input, dim_value
from modflow_devtools.dfns.schema import split_bound
from pandas.api.types import is_scalar

from flopy4.mf6 import period_lists
from flopy4.mf6._types import TimeArraySeriesRef, TimeSeriesRef
from flopy4.mf6.component import Component
from flopy4.mf6.constants import GRID_DIMS, MF6
from flopy4.mf6.dims_provider_methods import DimsProviderMethods
from flopy4.mf6.item import (
    Item,
    RowContext,
    _plannable,
    conditional_fields,
    dim_lookup,
    inline_dim,
    item_list_type,
    item_list_words,
    package_sized_fields,
    sized_by,
    union_value,
)
from flopy4.mf6.item_table import ItemTable
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.period_arrays import (
    dense,
    is_cleared,
    is_grid_package,
    split_tas,
    to_named_period_dict,
    to_period_dict,
)
from flopy4.mf6.spec import to_field_type
from flopy4.mf6.write_context import WriteContext
from flopy4.spec import is_array

# DFN type -> numpy dtype, for broadcasting a scalar griddata default to a
# full array.
_DTYPE_MAP: dict = {
    "integer": np.int64,
    "double": np.float64,
    "double precision": np.float64,
    "string": np.object_,
    "keyword": np.object_,
}

# A list shape's bound operator (DFN "<=maxbound") -> check of row count
# against the dimension. No operator means the shape is exact.
_BOUND_OPS: dict = {
    None: operator.eq,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([ed][+-]?\d+)?", re.IGNORECASE)


def _reads_as_number(text: str) -> bool:
    """Whether MF6 could read a word as a number, with an E or a Fortran D
    exponent."""
    return _NUMBER.fullmatch(text) is not None


def _check_rows(dim: str, declared: int, nrows: int, bound: str | None) -> None:
    if not _BOUND_OPS[bound](nrows, declared):
        raise ValueError(
            f"{dim}={declared} but {nrows} rows were given (need rows {bound or '=='} {dim})"
        )


class PeriodRows(dict):
    """A fill-forward list field's ``{kper: rows}`` (CHD's
    stress_period_data). Rows assigned to a period are coerced as at
    construction (see `Package._coerce_item_list`)."""

    def __init__(self, package: "Package", name: str, periods: dict) -> None:
        super().__init__(periods)
        self._package = package
        self._name = name

    def __setitem__(self, kper: int, rows: Any) -> None:
        super().__setitem__(kper, self._package._coerce_period(self._name, rows))

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        for kper, rows in dict(*args, **kwargs).items():
            self[kper] = rows

    def setdefault(self, kper: int, rows: Any = None) -> Any:  # type: ignore[override]
        if kper not in self:
            self[kper] = rows
        return super().__getitem__(kper)

    def __ior__(self, other: Any) -> "PeriodRows":  # type: ignore[override,misc]
        self.update(other)
        return self

    def copy(self) -> "PeriodRows":
        return PeriodRows(self._package, self._name, self)

    def __reduce__(self):
        # its rows as they are: unpickling assigns them before the
        # package has the state to take them
        return PeriodRows, (self._package, self._name, dict(self))


@attrs.define(kw_only=True, slots=False)
class Package(Component, ABC):
    # Dimensions counting item columns that aren't fields themselves, name ->
    # DFN expression (utl-ts's {"time_series_names": "len(time_series_names)"}).

    def __attrs_post_init__(self) -> None:
        """Post-init for Package subclasses.

        Handles three concerns in order:
        1. Coerce raw list/block/period data into Item-list fields, and
           set each list's row-count dimension.
        2. Normalize griddata (lists to arrays, per-layer values, flat
           shapes), then broadcast scalar griddata values to their DFN
           shape when dims is supplied (e.g. IC(strt=1.0, dims={"nodes":
           900})) or the package provides its own (a grid package).
        3. Chain to Component.__attrs_post_init__() via super() -- LAST,
           after 1-2, in every exit path (including the two early
           returns below). Several of a package's own fields (e.g.
           griddata arrays default to a bare scalar/dict until step 2
           broadcasts them) aren't in their final shape until steps 1-2
           finish, and Component.__attrs_post_init__() (via
           DimensionResolverMixin's chain and _set_child_parents(),
           which walks every attrs field) reads them -- so chaining
           before they're finalized breaks griddata broadcasting and
           dims resolution.
        """
        import attrs as _attrs

        # Detect schema-driven fields by presence of 'block' in field metadata.
        # Package subclasses with no fields of their own (e.g. the
        # Gwfgwe/Gwfgwt/Gwfprt exchange leaves in flopy4/mf6/exg/ -- just
        # dfn_name, no declared fields) no-op through the rest of this method.
        try:
            fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            super().__attrs_post_init__()
            return
        if not any(f.metadata.get("block") is not None for f in fields):
            super().__attrs_post_init__()
            return

        # 1. Item-list coercion.
        self._init_item_lists(fields)
        self._check_lookup_counts(fields)
        self._init_period_arrays(fields)

        # 2. Griddata normalization and broadcasting. A dimension provider
        # (a grid package) sizes its own griddata.
        dims: dict = self._own_dims() if isinstance(self, DimsProviderMethods) else self.dims
        self._normalize_griddata(fields, dims)
        if dims:
            self._broadcast_griddata(fields, dims)

        # 3. Chain to Component's own post-init -- see docstring above for
        # why this must run last, not first.
        super().__attrs_post_init__()

    def _init_item_lists(self, fields) -> None:
        """Coerce raw list/dict block+period data into Item-list fields.

        A list field with `dim` metadata (the DIMENSIONS field counting its
        rows, in DFN shape syntax: exact "nper" or bounded "<=maxats") gets
        that dimension set from its row count, unless it was given
        explicitly. An explicit dimension must equal the row count, or
        satisfy the bound, else it is an error. A list left at a one-row
        default (TDIS's perioddata, from the DFN) gets that row repeated
        `dim` times. `maxbound` (where applicable) is a computed property
        instead, not set here.

        Reads/writes the field's real attribute name (f.name) always --
        aliases (e.g. _stress_period_data's "stress_period_data") only name
        the __init__ parameter; the instance attribute (and __dict__ key
        object.__setattr__ writes to) is still the real name.
        """
        for f in fields:
            if not f.metadata.get("block") or item_list_type(f.type) is None:
                continue
            shape = f.metadata.get("shape")
            bound, dim = split_bound(shape[0]) if shape else (None, None)
            raw = self.__dict__.get(f.name)
            # Identity, not equality: only the default object itself (never
            # a user value, even an equal one) is repeated to fill `dim`.
            if raw is not None and raw is f.default and len(raw) == 1:
                raw = list(raw) * ((getattr(self, dim) if dim else None) or 1)
            if raw is None:
                continue
            value = self._coerce_list_field(f, raw)
            object.__setattr__(self, f.name, value)
            if dim:
                if f.metadata.get("fill_forward"):
                    nrows = max((len(r) for r in value.values()), default=0)
                else:
                    nrows = len(value)
                self._set_dim_from_rows(dim, nrows, bound)

    def _coerce_list_field(self, f: attrs.Attribute, raw: Any) -> Any:
        """An Item-list field's value from user data (see
        `_coerce_item_list`; a fill-forward field's periods as
        `PeriodRows`), on construction or reassignment. Sets the dimensions
        counting its rows' array columns."""
        item_cls = item_list_type(f.type)
        assert item_cls is not None
        words = item_list_words(f.type)
        value: Any
        if f.metadata.get("fill_forward"):
            value = PeriodRows(
                self,
                f.name,
                {kper: self._coerce_item_list(rows, item_cls, words) for kper, rows in raw.items()},
            )
            lists = list(value.values())
        else:
            value = self._coerce_item_list(raw, item_cls, words)
            lists = [value]
        if not isinstance(item_cls, tuple):
            self._set_dims_from_counts(item_cls, lists)  # type: ignore[arg-type]
        return value

    def _coerce_period(self, name: str, rows: Any) -> "list | ItemTable":
        """A period's rows, assigned to the fill-forward field ``name``'s
        `PeriodRows`, as `_coerce_list_field` takes each period's."""
        f = attrs.fields_dict(type(self))[name]  # type: ignore[arg-type]
        item_cls = item_list_type(f.type)
        assert item_cls is not None
        rows = self._coerce_item_list(rows, item_cls, item_list_words(f.type))
        if not isinstance(item_cls, tuple):
            self._set_dims_from_counts(item_cls, [rows])  # type: ignore[arg-type]
        return rows

    def _counted_lists(self):
        """Yield ``(bound, dim, nrows)`` for each list whose rows a
        DIMENSIONS field counts: NPER for TDIS's perioddata, ``<=``MAXATS
        for ATS's. A filled-forward list counts its longest period."""
        fields = attrs.fields(type(self))  # type: ignore[arg-type]
        names = {f.name for f in fields if f.metadata.get("block") == "dimensions"}
        for f in fields:
            if not f.metadata.get("block") or item_list_type(f.type) is None:
                continue
            if not (shape := f.metadata.get("shape")):
                continue
            bound, dim = split_bound(shape[0])
            rows = self.__dict__.get(f.name)
            if dim not in names or rows is None:
                continue
            if f.metadata.get("fill_forward"):
                yield bound, dim, max((len(r) for r in rows.values()), default=0)
            else:
                yield bound, dim, len(rows)

    def _sync_dims(self) -> None:
        """Bring the dimensions counting list rows in step with the lists.

        Appending to or removing from a list in place doesn't fire
        `on_setattr`, so a dimension set at construction (NVERT, NCPL,
        NPER) goes stale. Called wherever dimensions are read or written.
        An exact dimension takes the current row count; a bounded one
        ("<=maxats") is the user's, so it's only checked.
        """
        for bound, dim, nrows in self._counted_lists():
            if bound is None:
                object.__setattr__(self, dim, nrows)
            else:
                self._set_dim_from_rows(dim, nrows, bound)

    def _check_dim_rows(self, dim: str, value: int) -> None:
        """Raise if a dimension being assigned disagrees with the rows of a
        list it counts, which the next sync would otherwise overwrite."""
        for bound, name, nrows in self._counted_lists():
            if name == dim:
                _check_rows(dim, value, nrows, bound)

    def _check_lookup_counts(self, fields) -> None:
        """Check array columns counted by a column of the row another column
        refers to: SFR's ic has packagedata.ncon(ifno) values."""
        for f in fields:
            item_cls = item_list_type(f.type)
            if item_cls is None or isinstance(item_cls, tuple) or f.metadata.get("fill_forward"):
                continue
            if not (rows := self.__dict__.get(f.name)):
                continue
            for col in item_cls.fields():
                shape = inline_dim(col) or ""
                if "(" not in shape:  # not a row lookup
                    continue
                looked_up: list[str] = []
                # each row's count by its key, the first row with it
                counts: dict[str, dict] = {}

                def select(path: str, key: Any, f=f, counts=counts) -> Any:
                    *_, block, count_col = path.split(".")
                    target = next(
                        (g for g in fields if g.metadata.get("block") == block and g is not f), None
                    )
                    if target is None or not (target_rows := self.__dict__.get(target.name)):
                        return None
                    target_cls = item_list_type(target.type)
                    if target_cls is None or isinstance(target_cls, tuple):
                        return None
                    pk = next((g.name for g in target_cls.fields() if g.metadata.get("pk")), None)
                    if pk is None:
                        return None
                    looked_up.append(path)
                    if (by_key := counts.get(path)) is None:
                        by_key = counts[path] = {}
                        keys = _column_values(target_rows, pk)
                        for k, n in zip(keys, _column_values(target_rows, count_col)):
                            by_key.setdefault(k, n)
                    return by_key.get(key)

                # if the count is just a referenced row's (SFR's), check
                # all rows by column rather than evaluating each (SFR's 10k
                # connectiondata rows)
                names: list[str] = []

                def lookup(name: str, first=rows[0], names=names) -> Any:
                    names.append(name)
                    return getattr(first, name, None)

                dim_value(shape, lookup=lookup, select=select)
                if looked_up and len(set(names)) == 1:
                    by_key = counts[looked_up[-1]]
                    keys = _column_values(rows, names[0])
                    for key, value in zip(keys, _column_values(rows, col.name)):
                        if key is None or (expected := by_key.get(key)) is None:
                            continue
                        if (n := len(value or ())) != int(expected):
                            raise ValueError(
                                f"{f.name} {col.name} has {n} values but "
                                f"{looked_up[-1]} is {int(expected)}"
                            )
                    continue
                for r in rows:
                    n = len(getattr(r, col.name) or ())
                    expected = dim_value(
                        shape, lookup=lambda name, r=r: getattr(r, name, None), select=select
                    )
                    if expected is not None and n != expected:
                        raise ValueError(
                            f"{f.name} {col.name} has {n} values but {looked_up[-1]} is {expected}"
                        )

    def _init_period_arrays(self, fields) -> None:
        """Period array fields (WELG's q, RCHA's aux) to ``{kper: array}``, or
        ``{kper: {name: array}}`` for dynamically named ones, whose names must
        be among those the field's fk points at. Dense ``(nper, ...)`` input
        is split by period (see ``flopy4.mf6.period_arrays``). In a grid
        package, a period with no stress in any cell is stored as ``None``,
        and aux can only be given in periods the stress arrays are."""
        grid = is_grid_package(type(self))
        stress_periods: set[int] = set()
        named: list = []
        for f in fields:
            if not f.metadata.get("fill_forward") or item_list_type(f.type) is not None:
                continue
            if (value := self.__dict__.get(f.name)) is None:
                continue
            # like griddata, each period's array has the field's flat DFN
            # shape: (nlay, nrow, ncol) to (nodes,)
            flat = len(f.metadata.get("shape") or ()) == 1
            integer = to_field_type(f.type) == "integer"

            def _normalize(a, kper):
                if a is None:
                    if not grid or f.metadata.get("fk"):
                        raise ValueError(
                            f"{f.name}: period {kper} is None, but only a grid "
                            "package's stress arrays can be cleared"
                        )
                    return None
                if isinstance(a, TimeArraySeriesRef):
                    if not f.metadata.get("time_series"):
                        raise ValueError(f"{f.name} can't come from a time-array series ({a})")
                    return a
                if flat and a.ndim > 1:
                    a = a.ravel()
                if integer and isinstance(a, np.ndarray):
                    a = a.astype(np.int64)
                # (not computing a dask array to check)
                if (
                    grid
                    and not f.metadata.get("fk")
                    and isinstance(a, np.ndarray)
                    and is_cleared(a)
                ):
                    return None
                return a

            if f.metadata.get("fk"):
                periods = {
                    k: {n: _normalize(a, k) for n, a in arrays.items()}
                    for k, arrays in (to_named_period_dict(value) or {}).items()
                }
                named.append((f, periods))
            else:
                periods = {k: _normalize(a, k) for k, a in (to_period_dict(value) or {}).items()}
                stress_periods.update(periods)
            self.__dict__[f.name] = periods
        for f, periods in named:
            key = f.metadata["fk"].rsplit(".", 1)[-1]
            names = getattr(self, key, None)
            allowed = {str(n).lower() for n in np.atleast_1d(names)} if names is not None else set()
            given = {n for arrays in periods.values() for n in arrays}
            if unknown := sorted(n for n in given if n.lower() not in allowed):
                raise ValueError(f"{f.name}: {unknown} not in {key}")
            if grid and (extra := sorted(set(periods) - stress_periods)):
                raise ValueError(
                    f"{f.name} given in periods {extra} with no stress arrays; "
                    "a grid package's period is one unit"
                )

    def _set_dim_from_rows(self, dim: str, nrows: int, bound: str | None = None) -> None:
        declared = getattr(self, dim)
        if declared is None:
            object.__setattr__(self, dim, nrows)
        else:
            _check_rows(dim, declared, nrows, bound)

    def _set_dims_from_counts(self, item_cls: "type[Item]", lists: list) -> None:
        """Set the dimensions counting array columns (GNC's numalphaj, EVT's
        nseg-1) from their lengths in ``lists``, unless given."""
        values = {a.name: getattr(self, a.name) for a in attrs.fields(type(self))}

        def lookup(name: str) -> Any:
            return dim_lookup(values, name)

        for f in package_sized_fields(item_cls):
            shape = inline_dim(f) or ""
            lengths = {n for rows in lists for n in _lengths(rows, f.name)}
            if len(lengths) > 1:
                raise ValueError(f"{f.name} lengths differ across rows: {sorted(lengths)}")
            if not lengths:
                continue
            (n,) = lengths
            if (unset := dim_input(shape, lookup=lookup, length=n)) is not None:
                object.__setattr__(self, *unset)
                values[unset[0]] = unset[1]
            elif (declared := dim_value(shape, lookup=lookup)) is not None and declared != n:
                raise ValueError(f"{shape}={declared} but {f.name} has {n} values")

    def _row_context(self, item_cls: "type[Item] | tuple[type[Item], ...]") -> RowContext:
        """What the layout of a row of ``item_cls`` depends on (see
        `Item.from_values`)."""
        fields = attrs.fields_dict(type(self))  # type: ignore[arg-type]
        values = {name: getattr(self, name) for name in fields}

        def lookup(name: str) -> Any:
            return dim_lookup(values, name)

        sizes = {}
        for shape in sized_by(item_cls):
            if (n := dim_value(shape, lookup=lookup)) is None:
                unset = dim_input(shape, lookup=lookup, length=1)
                if unset is None or (f := fields.get(unset[0])) is None or not is_array(f):
                    continue
                n = 0
            sizes[shape] = n
        ncelldim = None
        if not hasattr(self, "exgmnamea"):
            try:
                ncelldim = self.resolve_dims("ncelldim").get("ncelldim")
            except ValueError:
                pass
        enabled = frozenset(o for o in conditional_fields(item_cls).values() if values.get(o))
        return RowContext(
            ncelldim=ncelldim,
            sizes=sizes,
            enabled=enabled,
        )

    def _coerce_item_list(
        self, data, item_cls: "type[Item] | tuple[type[Item], ...]", words: tuple[str, ...] = ()
    ) -> "list | ItemTable":
        """Convert user-supplied list/dict data to a list of Item instances,
        an `ItemTable` for a tabular list (see `item._plannable`).

        For a plain (non-union) item_cls, accepts:
          - list of item_cls instances → returned as-is
          - list of tuples/lists       → positional (see
                                          `Item.from_values`)
          - list of dicts              → named columns
          - dict of lists              → column-oriented {col_name: [values]}

        For a union item_cls (a tuple of arm classes, e.g. OC's (OcSave,
        OcPrint)): existing arm instances pass through, as do its
        ``words`` (PRP's ALL), in any case;
        tuples/lists are dispatched to the right arm by their keyword token
        and built positionally (see flopy4.mf6.item.construct_union_item);
        dicts are dispatched by a "keyword" key. Raises on a row no arm
        takes. Ambiguous columnar dict-of-lists input isn't supported (no
        single arm to build columns from).

        A row with a field an option turns on (a boundname) sets that
        option.
        """
        items: list | ItemTable
        if isinstance(data, ItemTable) and data.item_cls is item_cls:
            items = data  # as loaded: kept (it isn't a copy, either)
        elif isinstance(data, list) and all(isinstance(row, item_cls) for row in data):
            # Items already (as loaded): no context needed, which is costly
            # to resolve per period
            items = list(data)
        else:
            items = self._items_from(data, item_cls, words, self._row_context(item_cls))
        fields = attrs.fields_dict(type(self))  # type: ignore[arg-type]

        def unset(option: str) -> bool:
            return option in fields and not getattr(self, option)

        # only options not set yet: each check looks at every row
        on = {
            option
            for name, option in conditional_fields(item_cls).items()
            if unset(option) and _any_set(items, name)
        }
        for option in on:
            object.__setattr__(self, option, True)
        if not isinstance(items, ItemTable) and not isinstance(item_cls, tuple):
            if _plannable(item_cls):  # type: ignore[arg-type]  # lru_cache wants Hashable
                items = ItemTable.from_items(item_cls, items)
        return items

    def _items_from(
        self,
        data,
        item_cls: "type[Item] | tuple[type[Item], ...]",
        words: tuple[str, ...],
        context: RowContext,
    ) -> list:
        """The Items user-supplied data gives (see `_coerce_item_list`)."""
        if isinstance(item_cls, tuple):
            items = []
            for row in data:
                item = _union_row(row, item_cls, words, context)
                if item is None:
                    names = [*words, *(c.__name__ for c in item_cls)]
                    raise ValueError(f"no arm of {names} takes row {row!r}")
                items.append(item)
        elif isinstance(data, dict):
            n = len(next(iter(data.values()))) if data else 0
            items = [item_cls(**{name: vals[i] for name, vals in data.items()}) for i in range(n)]
        else:
            items = []
            for row in data:
                if isinstance(row, item_cls):
                    items.append(row)
                elif isinstance(row, dict):
                    items.append(item_cls(**row))
                else:
                    items.append(item_cls.from_values(row, context))
        return items

    def _normalize_griddata(self, fields, dims: dict) -> None:
        """Convert list griddata to arrays, repeat a `layered` array's
        per-layer values across each layer's cells, and flatten structured
        arrays to their flat DFN shape (e.g. `(nlay, nrow, ncol)` to
        `(nodes,)`)."""
        nlay = dims.get("nlay")
        ncpl = dims.get("ncpl") or (dims["nodes"] // nlay if nlay and "nodes" in dims else None)
        for f in fields:
            if f.metadata.get("block") != "griddata":
                continue
            val = self.__dict__.get(f.name)
            dtype = _DTYPE_MAP.get(to_field_type(f.type), np.float64)
            if isinstance(val, (list, tuple)):
                val = np.asarray(val, dtype=dtype)
            if not isinstance(val, np.ndarray):
                continue
            if f.metadata.get("layered") and nlay and ncpl and val.shape == (nlay,):
                val = np.repeat(val, ncpl).astype(dtype)
            elif val.ndim > 1 and len(f.metadata.get("shape") or ()) == 1:
                val = val.ravel()
            self.__dict__[f.name] = val

    def _broadcast_griddata(self, fields, dims: dict) -> None:
        """Expand scalar griddata defaults to full arrays when dims is supplied."""
        _par_data = getattr(self, "_par_data", None)
        _is_vertex = (
            _par_data is not None
            and "ncpl" in _par_data.dims
            and _par_data.dims.get("nrow", 0) == 0
        ) or ("ncpl" in dims and "nrow" not in dims)

        for f in fields:
            if f.metadata.get("block") != "griddata":
                continue
            shape_meta = f.metadata.get("shape")
            if not shape_meta:
                continue
            val = self.__dict__.get(f.name)
            if val is None:
                continue
            _gd_dtype = _DTYPE_MAP.get(to_field_type(f.type), np.float64)
            try:
                resolved = []
                for d in shape_meta:
                    if d == "ncelldim":
                        resolved.append(2 if _is_vertex else 3)
                    else:
                        resolved.append(dims[d])
                shape = tuple(resolved)
            except KeyError:
                continue
            if isinstance(val, (int, float)):
                self.__dict__[f.name] = np.full(shape, val, dtype=_gd_dtype)
            elif isinstance(val, np.ndarray) and val.shape != shape:
                try:
                    self.__dict__[f.name] = val.reshape(shape)
                except ValueError:
                    pass
            elif isinstance(val, dict) and not val:
                default = f.default if isinstance(f.default, (int, float)) else 0
                self.__dict__[f.name] = np.full(shape, default, dtype=_gd_dtype)

    def write(self, format: str = MF6, context: Optional[WriteContext] = None) -> None:
        self._sync_dims()
        self._check_tas_refs()
        self._check_ts_refs()
        self._check_obs_ids()
        super().write(format=format, context=context)

    def _check_tas_refs(self) -> None:
        """Raise if a time-array series reference names a series none of
        the package's TAS6 files define, which MF6 would fail on."""
        defined = self._series_names("utl-tas")
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if not f.metadata.get("time_series") or not f.metadata.get("fill_forward"):
                continue
            for kper, ref in split_tas(getattr(self, f.name) or {})[1].items():
                for r in ref.values() if isinstance(ref, dict) else [ref]:
                    if r.name.lower() not in defined:
                        raise ValueError(
                            f"{type(self).__name__}.{f.name}: period {kper} names "
                            f"time-array series {r.name!r}, which no TAS6 file defines "
                            f"(defined: {sorted(defined) or 'none'})"
                        )

    def _check_ts_refs(self) -> None:
        """Raise if a row's time-series column names a series none of the
        package's TS6 files define, which MF6 would fail on."""
        defined = self._series_names("utl-ts")
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if item_list_type(f.type) is None:
                continue
            value = getattr(self, f.name)
            periods = value if isinstance(value, dict) else {None: value}
            for kper, rows in periods.items():
                for name in _rows_ts_names(rows or []):
                    if name.lower() not in defined:
                        where = f" period {kper}" if kper is not None else ""
                        raise ValueError(
                            f"{type(self).__name__}.{f.name.lstrip('_')}:{where} "
                            f"names time series {name!r}, which no TS6 file "
                            f"defines (defined: {sorted(defined) or 'none'})"
                        )

    def _check_obs_ids(self) -> None:
        """Warn if an observation names a boundname MF6 may read as a cell."""
        boundnames = set()
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if item_list_type(f.type) is None:
                continue
            value = getattr(self, f.name)
            for rows in (value if isinstance(value, dict) else {None: value}).values():
                boundnames |= {b for b in _boundnames(rows or []) if b}
        numeric = {b.lower() for b in boundnames if _reads_as_number(b)}
        if not numeric:
            return
        for obs in self._children_of("utl-obs"):
            for block in obs.continuous or []:
                for row in block.continuous:
                    for id_ in (row.id_, row.id2):
                        if isinstance(id_, str) and id_.lower() in numeric:
                            warnings.warn(
                                f"{type(self).__name__}: observation {row.obsname!r} names "
                                f"boundname {id_!r}, which MF6 may read as a cell, not a "
                                f"boundname; give the boundaries a name that isn't a number",
                                stacklevel=3,
                            )

    def _series_names(self, dfn_name: str) -> set[str]:
        """The series names, lowercase, the package's TS6 or TAS6 files
        (``utl-ts``, ``utl-tas``) define."""
        names: set[str] = set()
        for child in self._children_of(dfn_name):
            if (record := child.time_series_name) is not None:
                (f,) = record.fields()
                names |= {n.lower() for n in getattr(record, f.name)}
        return names

    def _children_of(self, dfn_name: str) -> list[Any]:
        """The package's children with the given DFN name."""
        found = []
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            value = getattr(self, f.name) if f.metadata.get("child") else None
            for child in value if isinstance(value, list) else [value]:
                if getattr(child, "dfn_name", None) == dfn_name:
                    found.append(child)
        return found

    @classmethod
    def load(  # type: ignore[override]
        cls,
        path: Path,
        dims: "dict[str, int] | None" = None,
        name: "str | None" = None,
        *,
        context: LoadContext | None = None,
    ) -> "Package":
        """Load from an MF6 text input file.

        Parameters
        ----------
        path :
            Path to the package input file.
        dims :
            Grid dimension values required to resolve array shapes,
            e.g. ``{"nlay": 3, "nodes": 900}``.  Required for griddata
            packages (NPF, IC, STO, etc.); may be omitted for list-input
            packages (WEL, DRN, etc.). Overrides the context's.
        name :
            Explicit component name (e.g. a namefile binding row's
            pname), overriding the default auto-assigned name.
        context :
            Where the file sits in the simulation (see ``LoadContext``).
            By default, relative paths in the file resolve against its
            own directory. To load a file from a simulation on its own,
            give the simulation directory as the context's workspace.
        """
        from flopy4.mf6.codec.reader import load as _codec_load
        from flopy4.mf6.converter.ingress.structure import structure_component

        path = Path(path)
        context = context or LoadContext(workspace=path.parent)
        if dims:
            context = attrs.evolve(context, dims=dims)
        with open(path) as _f:
            _raw = _codec_load(_f)
        _pkg = structure_component(_raw, cls, context=context, name=name)

        # Standalone packages (not attached to a parent model) resolve
        # dimensions from the ones given, so to_xarray()/to_dataarray() work.
        if context.dims:
            _pkg.dims.update(context.dims)

        return _pkg

    def default_filename(self) -> str:
        """``{stem}.{name}.{ext}``: ``model.wel0.wel``, ``sim.ims0.ims``.

        The stem is the parent's name, or for a package named by a file
        record (TS, OBS, ...) the parent's filename without its suffix
        (``model.wel0.ts0.ts``). The extension is the name-file ftype,
        lowercase, without the ``6`` (a CHDG file is ``.chd``). Names are
        unique among siblings, so default filenames can't collide.
        """
        parent = self._parent  # type: ignore
        if isinstance(parent, Package):
            stem = parent.filename.stem
        elif parent is not None:
            stem = parent._name_or_class()
        else:
            stem = self._name_or_class()
        return f"{stem}.{self._name_or_class()}.{self._file_ext()}"

    def _file_ext(self) -> str:
        """The default filename's extension: the name-file ftype,
        lowercase, without the ``6``s or an exchange's hyphen
        (``CHD6`` -> ``chd``, ``GWF6-GWF6`` -> ``gwfgwf``)."""
        from flopy4.mf6.converter.binding import component_ftype

        return component_ftype(type(self)).lower().replace("6", "").replace("-", "")

    def to_dict(self, blocks: bool = False, strict: bool = False) -> dict:
        """Convert to a dictionary of field values.

        Parameters
        ----------
        blocks : bool
            If True, return nested dict keyed by DFN block name.
        strict : bool
            If True, only include fields with ``block`` metadata.
        """
        import attrs as _attrs

        try:
            all_fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        except _attrs.exceptions.NotAnAttrsClassError:
            return super().to_dict(blocks=blocks, strict=strict)

        # Fall back for a Package subclass with no schema-driven fields of
        # its own (e.g. the exchange leaves in flopy4/mf6/exg/).
        if not any(f.metadata.get("block") for f in all_fields):
            return super().to_dict(blocks=blocks, strict=strict)

        _exclude = {"name", "parent", "_parent", "dims", "_filename", "workspace", "strict"}
        result: dict = {}
        for f in all_fields:
            if f.name in _exclude or f.init is False:
                continue
            block = f.metadata.get("block")
            if not block:
                continue
            key = f.alias if (f.alias and f.name.startswith("_")) else f.name
            val = getattr(self, key, None)
            if blocks:
                result.setdefault(block, {})[key] = val
            else:
                result[key] = val
        return result

    def to_dataframe(self) -> pd.DataFrame:
        """Return stress period data as a tidy DataFrame. Zero cost if not called."""
        _spd = self.__dict__.get("_stress_period_data")
        if not _spd:
            return pd.DataFrame()
        union = isinstance(item_list_type(self._period_item_field().type), tuple)
        frames = []
        for kper in sorted(_spd):
            # object columns in a list of unions, whose arms leave each
            # other's empty: else an int column with gaps would turn float
            dtype = object if union else None
            rows = _spd[kper]
            if isinstance(rows, ItemTable):
                df = pd.DataFrame(_table_dict(rows))
            else:
                df = pd.DataFrame([_row_dict(row, keyword=union) for row in rows], dtype=dtype)
            df.insert(0, "kper", kper)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def from_dataframe(self, df: pd.DataFrame) -> None:
        """Set stress_period_data from a tidy DataFrame.

        The DataFrame must have a ``kper`` column and data columns matching
        the period Item class's own fields (as produced by ``to_dataframe()``),
        and, for a list of unions, a ``keyword`` column naming each row's arm.
        """
        if df.empty:
            setattr(self, self._period_item_field().name, {})
            return
        if "kper" not in df.columns:
            raise ValueError("DataFrame must have a 'kper' column")
        spd: dict[int, list] = {}
        for kper, group in df.groupby("kper"):
            group = group.drop(columns=["kper"])
            # A missing optional column (e.g. boundname), or another arm's
            # in a list of unions, round-trips through pandas as NaN, not
            # absent. Drop it so the Item class's own default applies rather
            # than storing a float in a str field.
            records = [
                {k: v for k, v in row.items() if not (is_scalar(v) and pd.isna(v))}
                for row in group.to_dict("records")
            ]
            spd[int(kper)] = records
        setattr(self, self._period_item_field().name, spd)

    def _period_item_field(self) -> attrs.Attribute:
        for f in attrs.fields(type(self)):  # type: ignore[arg-type]
            if f.metadata.get("fill_forward") and item_list_type(f.type) is not None:
                return f
        raise ValueError(f"{type(self).__name__} has no period Item-list field")

    @property
    def stress_period_data(self):  # type: ignore[override]
        """Stress period data as ``dict[int, list[Item]]`` keyed by 0-based kper."""
        return self.__dict__.get("_stress_period_data")

    @stress_period_data.setter  # type: ignore[attr-defined, no-redef]
    def stress_period_data(self, value) -> None:  # type: ignore[override]
        setattr(self, "_stress_period_data", value)

    def _period_array_fields(self) -> list:
        """Period array fields (not list ones): READARRAY packages' q, recharge, aux, ..."""
        return [
            f
            for f in attrs.fields(type(self))  # type: ignore[arg-type]
            if f.metadata.get("fill_forward") and item_list_type(f.type) is None
        ]

    def _period_dict(self, f) -> Optional[dict]:
        value = self.__dict__.get(f.name)
        return to_named_period_dict(value) if f.metadata.get("fk") else to_period_dict(value)

    def period_array(
        self, name: str, nper: Optional[int] = None, fill_forward: bool = True
    ) -> "np.ndarray | dict[str, np.ndarray] | None":
        """A period array field as a dense ``(nper, ...)`` array.

        With ``fill_forward`` (the default), each period holds the values in
        effect then. Without it, periods the field doesn't give are filled
        with ``FILL_DNODATA`` (floats) or ``FILL_INT64`` (integers). In a grid
        package a given period replaces the previous one as a whole, so a
        field missing from it is filled, not carried.

        Dynamically named arrays (aux) give ``{name: (nper, ...)}``. ``nper``
        defaults to the simulation's, else to one past the last given period.
        """
        fields = self._period_array_fields()
        f = next((f for f in fields if f.name == name), None)
        if f is None:
            raise ValueError(f"{type(self).__name__} has no period array field {name!r}")
        periods = self._period_dict(f)
        if not periods:
            return None
        given = None
        if is_grid_package(type(self)):
            given = sorted({k for g in fields for k in (self._period_dict(g) or {})})
        if nper is None:
            nper = self.resolve_dims("nper").get("nper") or max(given or periods) + 1
        shape = period_shape(self, f)
        if not f.metadata.get("fk"):
            return dense(periods, nper, fill_forward, given, shape)
        names = list(dict.fromkeys(n for arrays in periods.values() for n in arrays))
        return {
            n: dense(
                {k: arrays[n] for k, arrays in periods.items() if n in arrays},
                nper,
                fill_forward,
                given,
                shape,
            )
            for n in names
        }

    def to_dataarray(self, field_name: str) -> "xr.DataArray":
        """Single griddata or period array field as xr.DataArray. A period
        array is the values in effect each period (see `period_array`), with
        a leading "per" dim. Stays lazy if dask-backed."""
        period = any(f.name == field_name for f in self._period_array_fields())
        arr = self.period_array(field_name) if period else getattr(self, field_name)
        if arr is None:
            raise ValueError(f"{field_name!r} is not set")
        if isinstance(arr, dict):
            raise ValueError(f"{field_name!r} holds named arrays, not one array")
        nper = arr.shape[0] if period else None
        _d = self.resolve_dims("nlay", "nrow", "ncol", "ncpl", "nodes")
        _nlay = _d.get("nlay", 1)
        f = attrs.fields_dict(type(self))[field_name]  # type: ignore[arg-type]
        if f.metadata.get("shape") == ("ncpl",) and not f.metadata.get("layered"):
            _nlay = 1  # one layer's worth (RCHA's recharge, DIS's top)
        _nrow = _d.get("nrow")
        _ncol = _d.get("ncol")
        _ncpl = _d.get("ncpl")
        if _ncpl is None and "nodes" in _d and _nlay > 0:
            _ncpl = _d["nodes"] // _nlay
        lead: tuple[int, ...] = () if nper is None else (nper,)
        if _nrow is not None and _ncol is not None:
            arr = arr.reshape(*lead, _nlay, _nrow, _ncol)
            width = 3
        elif _ncpl is not None:
            arr = arr.reshape(*lead, _nlay, _ncpl)
            width = 2
        else:
            arr = arr.reshape(*lead, -1)
            width = 1
        dims = tuple(d for _, d in GRID_DIMS[width])
        if nper is not None:
            dims = ("per", *dims)
        da = xr.DataArray(arr, dims=dims, name=field_name)
        return self._with_cell_centers(da)

    def _with_cell_centers(self, da: xr.DataArray) -> xr.DataArray:
        """Give an array its cell centres as x/y coordinates when its
        model's discretization (or this package, if it's one) has them.
        On a structured grid they're indexed, for `sel(x=..., y=...)`, and
        the array gets its cell sizes as `dx`/`dy` (see `cell_sizes`), and a
        `projection` coordinate placing them in the world (see
        `grid_mapping`). An array on the grid's layers also gets its cells'
        elevations, if the discretization has `top`/`botm` (see
        `z_coords`)."""
        from flopy4.mf6.utils.grid import cell_centers, cell_sizes, grid_mapping, index_xy
        from flopy4.mf6.utils.vertical import z_coords

        dis = self if hasattr(self, "to_grid") else getattr(self._parent, "dis", None)
        coords = {
            k: v
            for k, v in cell_centers(dis).items()
            if v[0] in da.dims and da.sizes[v[0]] == len(v[1])
        }
        if len(coords) < 2:
            return da
        da = da.assign_coords(coords)
        cells = tuple(d for d in da.dims if d != "per")
        top, botm = getattr(dis, "top", None), getattr(dis, "botm", None)
        shape = tuple(da.sizes[d] for d in cells)
        if cells[0] == "layer" and top is not None and botm is not None:
            if np.size(botm) == np.prod(shape):
                da = da.assign_coords(z_coords(top, np.reshape(botm, shape), cells))
            elif da.name == "top" and dis is self and shape[0] == 1:
                # top is the top layer's cells' tops, so it's on layer 0
                full = (np.size(botm) // np.prod(shape[1:]), *shape[1:])
                zc = z_coords(top, np.reshape(botm, full), cells)
                da = da.assign_coords({k: (d, v[:1], a) for k, (d, v, a) in zc.items()})
        if "col" not in da.dims:
            return da
        projection = grid_mapping(
            getattr(dis, "xorigin", None),
            getattr(dis, "yorigin", None),
            getattr(dis, "angrot", None),
            getattr(dis, "crs", None),
        )
        sizes = cell_sizes(
            np.broadcast_to(np.asarray(getattr(dis, "delr"), dtype=np.float64), da.sizes["col"]),
            np.broadcast_to(np.asarray(getattr(dis, "delc"), dtype=np.float64), da.sizes["row"]),
        )
        return index_xy(da.assign_coords(projection=projection, **sizes))

    def to_xarray(  # type: ignore[override]
        self,
        sparse: bool = False,
        duplicates: "period_lists.Duplicates" = "raise",
        grid: bool = False,
    ) -> "xr.Dataset":
        """All set griddata (or period-array) fields as xr.Dataset.

        Stays lazy if dask-backed. A list package's stress period data is a
        variable per column, dense along its rows' key (``grid=True`` for
        the grid through a feature's cell), or with ``sparse=True`` a row
        per entry. ``duplicates`` ("sum", "first", "last") merges rows at
        one position, keeping the last row's boundname ("first": the first
        row's). See ``flopy4.mf6.period_lists``.
        """
        import attrs as _attrs

        fields = _attrs.fields(type(self))  # type: ignore[arg-type]
        for _block in ("griddata", "period"):
            data_vars = {
                a.name: self.to_dataarray(a.name)
                for a in fields
                if a.metadata.get("block") == _block
                and getattr(self, a.name) is not None
                and not a.metadata.get("fk")
                and item_list_type(a.type) is None
            }
            if data_vars:
                return xr.Dataset(data_vars)
        spd = period_lists.period_list_field(type(self))
        if spd is not None and self.__dict__.get(spd.name) is not None:
            return period_lists.to_dataset(self, sparse=sparse, duplicates=duplicates, grid=grid)
        return super().to_xarray()  # type: ignore[return-value]

    def from_xarray(self, ds: xr.Dataset) -> None:
        """Set stress_period_data from ``to_xarray()``'s dense or sparse
        form (see ``flopy4.mf6.period_lists``)."""
        spd = period_lists.period_list_field(type(self))
        if spd is None:
            raise ValueError(f"{type(self).__name__} has no stress period data")
        setattr(self, spd.name, period_lists.from_dataset(self, ds))


def period_shape(component: Any, f: attrs.Attribute) -> tuple[int, ...] | None:
    """A period array field's shape in one period, from its DFN shape and
    the grid's dims (``component``'s), or None if they aren't known."""
    names = f.metadata.get("shape") or ()
    if not names:
        return None
    try:
        dims = component.resolve_dims(*names)
    except ValueError:
        return None
    if any(dims.get(n) is None for n in names):
        return None
    return tuple(int(dims[n]) for n in names)


def _union_row(
    row: Any,
    arms: "tuple[type[Item], ...]",
    words: tuple[str, ...],
    context: RowContext | None = None,
) -> Any:
    """A list of unions' row from user input (see Package._coerce_item_list),
    as a union field's value is (see union_value), or None if no arm
    takes it."""
    if isinstance(row, dict):
        kw = str(row.get("keyword", "")).upper()
        if kw in words and len(row) == 1:
            return kw
        arm = next((c for c in arms if c.keyword().upper() == kw), None)
        return arm(**{k: v for k, v in row.items() if k != "keyword"}) if arm else None
    values = list(row) if isinstance(row, (list, tuple)) else [row]
    return union_value(values, (words, arms), context)


def _column_values(rows: Any, name: str) -> list:
    """The field ``name``'s values in ``rows``, a row's each."""
    if isinstance(rows, ItemTable):
        return rows.values(name)
    return [getattr(r, name) for r in rows]


def _lengths(rows: Any, name: str) -> set[int]:
    """The lengths of the array field ``name``'s values in ``rows``, those
    not empty."""
    if isinstance(rows, ItemTable):
        col = rows.columns.get(name)
        if col is not None and col.dtype != object:
            return {col.shape[1]} if len(col) and col.shape[1] else set()
        rows = rows.values(name)
        return {len(v) for v in rows if v}
    return {len(v) for r in rows if (v := getattr(r, name))}


def _any_set(rows: Any, name: str) -> bool:
    """Whether a row has a value for the field ``name``."""
    if isinstance(rows, ItemTable):
        return rows.any_set(name)
    return any(getattr(row, name, None) is not None for row in rows)


def _row_dict(row: Any, keyword: bool = False) -> dict[str, Any]:
    """A table row as a DataFrame record: `attrs.asdict`, except that
    time-series references and union arms stay as they are (asdict would
    make each a dict), so the frame round-trips through `from_dataframe`.
    With `keyword`, a list of unions' row names its arm, or is its word
    (PRP's ALL), in a "keyword" column."""
    if isinstance(row, str):
        return {"keyword": row}
    record = {"keyword": type(row).keyword().upper()} if keyword else {}
    record |= attrs.asdict(row)
    for f in attrs.fields(type(row)):
        v = getattr(row, f.name)
        if f.metadata.get("time_series"):
            record[f.name] = list(v) if isinstance(v, tuple) else v
        elif isinstance(v, Item):
            record[f.name] = v
    return record


def _boundnames(rows: Any) -> list:
    """The rows' boundnames, a row's each (None for none)."""
    if isinstance(rows, ItemTable):
        if "boundname" not in rows.columns:
            return []
        return rows.values("boundname")
    return [getattr(row, "boundname", None) for row in rows]


def _rows_ts_names(rows: Any) -> list[str]:
    """The time-series names the rows use (see `_ts_names`). A table's are
    in its columns of objects only: the others are all numbers."""
    if not isinstance(rows, ItemTable):
        return [name for row in rows for name in _ts_names(row)]
    names: list[str] = []
    for f in attrs.fields(rows.item_cls):  # type: ignore[arg-type]
        col = rows.columns.get(f.name)
        if col is None or col.dtype != object or not f.metadata.get("time_series"):
            continue
        for value in col.tolist():
            values = value if isinstance(value, tuple) else (value,)
            names += [v.name for v in values if isinstance(v, TimeSeriesRef)]
    return names


def _table_dict(table: ItemTable) -> dict[str, list]:
    """A table's columns as a DataFrame's, as `_row_dict` makes each row."""
    out = {}
    for f in attrs.fields(table.item_cls):  # type: ignore[arg-type]
        values = table.values(f.name)
        if f.metadata.get("time_series"):
            values = [list(v) if isinstance(v, tuple) else v for v in values]
        out[f.name] = values
    return out


def _ts_names(row: Any) -> list[str]:
    """The time-series names a table row uses: the references in its
    time-series columns, including in its nested union arms (not its
    child files, which check their own)."""
    names: list[str] = []
    if isinstance(row, str):
        return names
    for f in attrs.fields(type(row)):
        value = getattr(row, f.name)
        if f.metadata.get("time_series"):
            values = value if isinstance(value, tuple) else (value,)
            names += [v.name for v in values if isinstance(v, TimeSeriesRef)]
        elif isinstance(value, Item):
            names += _ts_names(value)
    return names
