"""A tabular list's rows as columns, a numpy array per field (like flopy3's
recarrays), read from a block's text in bulk. A table is also a list of
Items: each row is a view that reads and writes the columns."""

import io
import operator
from collections.abc import Iterable, Iterator, MutableSequence
from functools import lru_cache
from typing import Any

import attrs
import numpy as np

from flopy4.mf6._types import to_ts_value, to_ts_values
from flopy4.mf6.codec.reader.transformer.rows import _number, without_comments
from flopy4.mf6.constants import FILL_INT64
from flopy4.mf6.item import (
    Item,
    RowContext,
    _is_one_cellid,
    _plannable,
    _row_plannable,
    _sized_by_field,
    _spans,
    _union_field_arms,
    inline_dim,
    is_cellid,
    number_kind,
)
from flopy4.spec import is_array


def _default(f: attrs.Attribute) -> Any:
    """A field's default value, or None if it has none."""
    d: Any = f.default
    if isinstance(d, attrs.Factory):  # type: ignore[arg-type]
        return d.factory(None) if d.takes_self else d.factory()
    return None if d is attrs.NOTHING else d


def _is_default(value: Any, default: Any) -> bool:
    return value is default or (type(value) is type(default) and value == default)


_DTYPES = {"index": np.int64, "int": np.int64, "float": np.float64, "series": np.float64}


@lru_cache(maxsize=None)
def _dtype(f: attrs.Attribute) -> type | None:
    """A field's column dtype (see `item.number_kind`), or None for
    objects."""
    if is_cellid(f) and not _is_one_cellid(f):
        return None
    return _DTYPES.get(number_kind(f))  # type: ignore[arg-type]


def _typed(f: attrs.Attribute, values: list, width: int | None) -> np.ndarray | None:
    """A field's values as a typed column (``width`` wide for an array or
    cellid, if given), or None if they aren't all numbers of its type."""
    if (dtype := _dtype(f)) is None:
        return None
    kinds = "iu" if dtype is np.int64 else "iuf"
    n = len(values)
    if is_cellid(f):
        cells = [v for v in values if v is not None]
        if len(cells) < n and not f.metadata.get("allow_zero"):
            return None
        if not cells:
            return None if width is None else np.full((n, width), FILL_INT64)
        arr = np.array(cells)
        if arr.ndim != 2 or arr.dtype.kind not in kinds or width not in (None, arr.shape[1]):
            return None
        if len(cells) == n:
            return arr.astype(np.int64)
        out = np.full((n, arr.shape[1]), FILL_INT64)
        out[[v is not None for v in values]] = arr
        return out
    if is_array(f):
        if not all(type(v) is tuple for v in values):
            return None
        if n == 0:
            return np.empty((0, width or 0), dtype)
        arr = np.array(values)
        if arr.ndim != 2 or width not in (None, arr.shape[1]):
            return None
    else:
        if n == 0:
            return np.empty(0, dtype)
        arr = np.array(values)
        if arr.ndim != 1:
            return None
    if arr.dtype.kind not in kinds:
        return None
    return arr.astype(dtype)


def _objects(values: list) -> np.ndarray:
    return np.fromiter(values, dtype=object, count=len(values))


def _fit(f: attrs.Attribute, values: list, width: int | None = None) -> np.ndarray:
    """A field's values as a typed column if they fit, else objects."""
    arr = _typed(f, values, width)
    return _objects(values) if arr is None else arr


def _column_of(f: attrs.Attribute, values: list) -> np.ndarray | None:
    """A field's values as a column, or None if all are the default."""
    default = _default(f)
    if all(_is_default(v, default) for v in values):
        return None
    return _fit(f, values)


def _get(f: attrs.Attribute, col: np.ndarray, i: int) -> Any:
    """Row ``i``'s value of a field's column."""
    if col.dtype == object:
        return col[i]
    if col.ndim == 1:
        return col[i].item()
    row = col[i]
    if row.size and row[0] == FILL_INT64 and is_cellid(f):
        return None
    return tuple(row.tolist())


def _values(f: attrs.Attribute, col: np.ndarray) -> list:
    """A field's column's values, as `_get` gives each."""
    if col.ndim == 1:
        return col.tolist()
    if not col.shape[1]:
        return [()] * len(col)
    rows: list = list(zip(*col.T.tolist()))  # faster than per row
    if is_cellid(f) and (none := col[:, 0] == FILL_INT64).any():
        for i in np.flatnonzero(none).tolist():
            rows[i] = None
    return rows


def _eq_key(row: Item) -> tuple:
    """A row's values as its class' ``__eq__`` compares them."""
    return tuple(
        f.eq_key(v) if f.eq_key else v
        for f in attrs.fields(type(row))  # type: ignore[arg-type]
        if f.eq
        for v in [getattr(row, f.name)]
    )


@lru_cache(maxsize=None)
def _view_class(item_cls: type[Item]) -> type:
    """The class of an `ItemTable`'s rows: an ``item_cls`` subclass whose
    fields are properties on the table's columns. It compares, copies and
    pickles as an ``item_cls``, and calling it makes one."""
    ns: dict[str, Any] = {
        "__slots__": ("_table", "_i"),
        "__module__": item_cls.__module__,
        "__qualname__": item_cls.__qualname__,
    }

    def column(f: attrs.Attribute) -> property:
        def get(self):
            table = self._table
            if (col := table.columns.get(f.name)) is None:
                return _default(f)
            return _get(f, col, self._i)

        def set_(self, value):
            self._table._set(f, self._i, value)

        return property(get, set_)

    for f in attrs.fields(item_cls):  # type: ignore[arg-type]
        ns[f.name] = column(f)

    def __new__(cls, *args, **kwargs):
        return item_cls(*args, **kwargs)

    def __eq__(self, other):
        if not isinstance(other, item_cls):
            return NotImplemented
        return _eq_key(self) == _eq_key(other)

    def __ne__(self, other):
        eq = __eq__(self, other)
        return eq if eq is NotImplemented else not eq

    def __reduce_ex__(self, protocol):
        return _plain, (item_cls, {f.name: getattr(self, f.name) for f in attrs.fields(item_cls)})

    ns |= {"__new__": __new__, "__eq__": __eq__, "__ne__": __ne__, "__reduce_ex__": __reduce_ex__}
    ns["__hash__"] = None
    return type(item_cls.__name__, (item_cls,), ns)


def _plain(item_cls: type[Item], values: dict[str, Any]) -> Item:
    item = object.__new__(item_cls)
    for name, value in values.items():
        object.__setattr__(item, name, value)
    return item


class ItemTable(MutableSequence):
    """A tabular list's rows (see `item._plannable`), a numpy array per
    field:
    - a cellid: ``(n, ncelldim)`` ints, 0-based, `FILL_INT64` for NONE;
    - an array field (aux): ``(n, size)``;
    - any other: ``(n,)`` ints or floats;
    - values not all numbers (a series' name, a boundname): ``(n,)``
      objects.
    A field without a column has its default in every row.

    It's also a list of Items: ``t[i]`` is a write-through view of row
    ``i``."""

    __slots__ = ("item_cls", "columns", "_n")

    def __init__(
        self, item_cls: type[Item], columns: dict[str, np.ndarray], n: int | None = None
    ) -> None:
        self.item_cls = item_cls
        self.columns = columns
        if n is None:
            n = len(next(iter(columns.values()))) if columns else 0
        self._n = n

    @classmethod
    def from_items(cls, item_cls: type[Item], items: Iterable[Item]) -> "ItemTable":
        """A table of ``items``, each an ``item_cls``."""
        items = list(items)
        columns: dict[str, np.ndarray] = {}
        for f in attrs.fields(item_cls):  # type: ignore[arg-type]
            col = _column_of(f, [getattr(item, f.name) for item in items])
            if col is not None:
                columns[f.name] = col
        return cls(item_cls, columns, len(items))

    @classmethod
    def from_columns(
        cls, item_cls: type[Item], n: int, given: dict[str, Any]
    ) -> "ItemTable | None":
        """``n`` rows of a tabular ``item_cls`` from each field's values (a
        numeric array or a list, None for the default), converted and
        validated as the class would. None if the rows aren't tabular or a
        value fails, so rows made one at a time raise it."""
        if not _plannable(item_cls):  # type: ignore[arg-type]  # lru_cache wants Hashable
            return None
        if not n:
            return cls(item_cls, {}, 0)
        columns: dict[str, np.ndarray] = {}
        for f in item_cls.fields():
            vals = given.get(f.name)
            if vals is None:
                if f.default is attrs.NOTHING:
                    return None
                continue
            if isinstance(vals, np.ndarray):
                dtype = _dtype(f)
                if (
                    dtype is not None
                    and vals.dtype.kind in ("iu" if dtype is np.int64 else "iuf")
                    and f.converter in (None, to_ts_value, to_ts_values)  # numbers as they are
                    and f.validator is None
                    and _default(f) in (None, ())
                ):
                    columns[f.name] = vals.astype(dtype)
                    continue
                vals = vals.tolist() if vals.ndim == 1 else [tuple(r) for r in vals.tolist()]
            if any(v is None for v in vals):
                if f.default is attrs.NOTHING:
                    return None
                default = _default(f)
                vals = [default if v is None else v for v in vals]
            convert: Any = f.converter  # attrs types it as a plain callable
            try:
                if convert is not None:
                    if isinstance(convert, attrs.Converter):
                        return None
                    vals = [convert(v) for v in vals]
                if (validate := f.validator) is not None:
                    for v in vals:
                        validate(None, f, v)
            except (TypeError, ValueError):
                return None
            if (col := _column_of(f, vals)) is not None:
                columns[f.name] = col
        return cls(item_cls, columns, n)

    def __len__(self) -> int:
        return self._n

    def _index(self, i: Any) -> int:
        i = operator.index(i)
        if i < 0:
            i += self._n
        if not 0 <= i < self._n:
            raise IndexError(f"row {i} of {self._n}")
        return i

    def _view(self, i: int) -> Item:
        view: Item = object.__new__(_view_class(self.item_cls))  # type: ignore[arg-type]  # lru_cache wants Hashable
        object.__setattr__(view, "_table", self)
        object.__setattr__(view, "_i", i)
        return view

    def __getitem__(self, i):  # type: ignore[override]
        if isinstance(i, slice):
            n = len(range(*i.indices(self._n)))
            return ItemTable(self.item_cls, {k: c[i] for k, c in self.columns.items()}, n)
        return self._view(self._index(i))

    def __iter__(self) -> Iterator[Item]:
        for i in range(self._n):
            yield self._view(i)

    def values(self, name: str) -> list:
        """A field's values, a row's each."""
        f = attrs.fields_dict(self.item_cls)[name]  # type: ignore[arg-type]
        if (col := self.columns.get(name)) is None:
            if isinstance(f.default, attrs.Factory):  # type: ignore[arg-type]
                return [_default(f) for _ in range(self._n)]  # a row's own
            return [_default(f)] * self._n
        return _values(f, col)

    def any_set(self, name: str) -> bool:
        """Whether a row has a value (not None) for the field ``name``."""
        if (col := self.columns.get(name)) is None:
            f = attrs.fields_dict(self.item_cls).get(name)  # type: ignore[arg-type]
            return self._n > 0 and f is not None and _default(f) is not None
        if col.dtype != object:
            return self._n > 0
        return any(v is not None for v in col.tolist())

    def to_items(self) -> list[Item]:
        """An Item per row, as `Item.from_rows` reads them."""
        names = list(self.columns)  # the others take their defaults
        if not names:
            return [self.item_cls() for _ in range(self._n)]
        values = [self.values(name) for name in names]
        return [self.item_cls(**dict(zip(names, row))) for row in zip(*values)]

    def tokens(self) -> list[tuple] | None:
        """Each row's tokens, as `Item.to_tokens` makes them, or None if a
        column isn't numbers."""
        cls = self.item_cls
        if cls.keyword() or cls._columns:
            return None
        cols: list[list] = []
        boundnames = None
        for f in cls.fields():
            col = self.columns.get(f.name)
            if f.name == "boundname":
                boundnames = None if col is None else col.tolist()
                continue
            meta = f.metadata
            if meta.get("_keyword") or meta.get("direction") or meta.get("child"):
                return None
            if col is None:
                if (default := _default(f)) is None or default == ():
                    continue
                return None
            if col.dtype == object:
                return None
            if is_cellid(f):
                col = np.where(col == FILL_INT64, 0, col + 1)
            elif number_kind(f) == "index":
                col = col + 1
            if col.ndim == 1:
                cols.append(col.tolist())
            else:
                cols.extend(col.T.tolist())
        rows = list(zip(*cols)) if cols else [()] * self._n
        if boundnames is not None:
            rows = [(*r, b) if b else r for r, b in zip(rows, boundnames)]
        return rows

    def _width(self, name: str) -> int | None:
        col = self.columns.get(name)
        return col.shape[1] if col is not None and col.ndim == 2 else None

    def _set(self, f: attrs.Attribute, i: int, value: Any) -> None:
        """Set row ``i``'s value of the field ``f``, making its column
        objects if it doesn't fit."""
        col = self.columns.get(f.name)
        if col is None:
            if _is_default(value, _default(f)):
                return
            col = self.columns[f.name] = _objects(self.values(f.name))
        if col.dtype != object:
            if (new := _typed(f, [value], self._width(f.name))) is not None:
                col[i] = new[0]
                return
            col = self.columns[f.name] = _objects(_values(f, col))
        col[i] = value

    def _check(self, item: Any) -> None:
        if not isinstance(item, self.item_cls):
            raise TypeError(f"a table of {self.item_cls.__qualname__} can't hold {item!r}")

    def _splice(self, a: int, b: int, other: "ItemTable") -> None:
        """Replace rows ``a`` to ``b`` with ``other``'s."""
        fields = attrs.fields_dict(self.item_cls)  # type: ignore[arg-type]
        columns: dict[str, np.ndarray] = {}
        for name in {**self.columns, **other.columns}:
            f = fields[name]
            mine = self.columns.get(name)
            theirs = other.columns.get(name)
            if mine is None:
                mine = _fit(f, self.values(name), other._width(name))
            if theirs is None:
                theirs = _fit(f, other.values(name), self._width(name))
            if mine.dtype != theirs.dtype or mine.shape[1:] != theirs.shape[1:]:
                mine, theirs = _objects(_values(f, mine)), _objects(_values(f, theirs))
            columns[name] = np.concatenate([mine[:a], theirs, mine[b:]])
        self.columns = columns
        self._n += len(other) - (b - a)

    def __setitem__(self, i, value) -> None:  # type: ignore[override]
        if isinstance(i, slice):
            start, stop, step = i.indices(self._n)
            if step != 1:
                items = self.to_items()
                items[i] = value
                self._replace(items)
                return
            value = list(value)
            for item in value:
                self._check(item)
            self._splice(start, max(start, stop), ItemTable.from_items(self.item_cls, value))
            return
        i = self._index(i)
        self._check(value)
        values = {f: getattr(value, f.name) for f in attrs.fields(self.item_cls)}  # type: ignore[arg-type]
        for f, v in values.items():
            self._set(f, i, v)

    def __delitem__(self, i) -> None:  # type: ignore[override]
        keep = np.ones(self._n, bool)
        keep[i if isinstance(i, slice) else self._index(i)] = False
        self.columns = {k: c[keep] for k, c in self.columns.items()}
        self._n = int(keep.sum())

    def insert(self, i: int, value: Item) -> None:
        self._check(value)
        i = min(max(i + self._n if i < 0 else i, 0), self._n)
        self._splice(i, i, ItemTable.from_items(self.item_cls, [value]))

    def extend(self, values: Iterable[Item]) -> None:
        values = list(values)
        for item in values:
            self._check(item)
        self._splice(self._n, self._n, ItemTable.from_items(self.item_cls, values))

    def _replace(self, items: list) -> None:
        for item in items:
            self._check(item)
        table = ItemTable.from_items(self.item_cls, items)
        self.columns, self._n = table.columns, table._n

    def copy(self) -> "ItemTable":
        return ItemTable(self.item_cls, {k: c.copy() for k, c in self.columns.items()}, self._n)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ItemTable):
            if other.item_cls is not self.item_cls or len(other) != len(self):
                return False
            mine, theirs = self.columns, other.columns
            if mine.keys() == theirs.keys() and all(
                a.dtype == b.dtype != object and a.shape == b.shape
                for a, b in zip(mine.values(), (theirs[k] for k in mine))
            ):
                return all(np.array_equal(a, theirs[k]) for k, a in mine.items())
        elif not isinstance(other, (list, tuple)):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other))

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return repr(list(self))

    def __getstate__(self):
        return self.item_cls, self.columns, self._n

    def __setstate__(self, state) -> None:
        self.item_cls, self.columns, self._n = state


_SPACE = np.zeros(256, bool)
_SPACE[[9, 10, 13, 32]] = True


def _widths(data: bytes) -> np.ndarray:
    """How many values each non-blank line has."""
    b = np.frombuffer(data, np.uint8)
    space = _SPACE[b]
    start = np.empty_like(space)  # a value's first character
    start[0] = not space[0]
    np.greater(space[:-1], space[1:], out=start[1:])
    lines = np.flatnonzero(b == 10) + 1
    lines = np.concatenate(([0], lines[lines < b.size]))
    counts = np.add.reduceat(start, lines, dtype=np.int32)
    return counts[counts > 0]


def _column(f: attrs.Attribute, took: tuple, values: np.ndarray) -> np.ndarray | None:
    """A field's column from its float values, as `item._plan` converts
    each row's, or None if it converts otherwise."""
    if is_cellid(f):
        if took[0] != "cellid":
            return None  # a row of cellids
        cell = values.astype(np.int64) - 1
        if f.metadata.get("allow_zero"):
            cell[(cell == -1).all(axis=1)] = FILL_INT64
        return cell
    kind = number_kind(f)
    if kind == "index":
        return values.astype(np.int64) - 1
    if kind == "int":
        return values.astype(np.int64)
    if kind in ("float", "series"):
        return values  # a series' values here are all numbers, no names
    return None


def _columns(
    item_cls: type[Item], first: list[str], values: np.ndarray, context: RowContext
) -> dict[str, np.ndarray] | None:
    """Rows' fields as columns, laid out by the first row (see
    `item._spans`), or None if a field doesn't convert by column."""
    try:
        spans = _spans(item_cls, [_number(v) for v in first], context)
    except ValueError:  # no layout: `Item.from_rows` says so
        return None
    if spans is None:
        return None
    at = {f.name: a for f, took, a, _ in spans if f is not None and took[0] == "value"}
    columns: dict[str, np.ndarray] = {}
    for f, took, a, b in spans:
        if f is None or (took[0] == "rest" and _union_field_arms(item_cls, f) is not None):
            return None  # an arm's keyword; arms
        if _sized_by_field(item_cls, f) and len(took) > 2:
            # an array counted by another column: each row's count must match
            if (count_at := at.get(inline_dim(f) or "")) is None:
                return None
            if not (values[:, count_at] == (b - a) // took[2]).all():
                return None
        if (col := _column(f, took, values[:, a:b] if b else values[:, a])) is None:
            return None
        columns[f.name] = col
    return columns


def read_rows(item_cls: type[Item], text: str, context: RowContext) -> "ItemTable | list | None":
    """A block's rows from its text (all numbers), read by column: an
    `ItemTable` if they're tabular and of one width, else Items, grouped
    by width (DISV's cell2d). None to leave them to `Item.from_rows`."""
    if not _row_plannable(item_cls):  # type: ignore[arg-type]  # lru_cache wants Hashable
        return None
    text = without_comments(text)
    if not _plannable(item_cls):  # type: ignore[arg-type]  # lru_cache wants Hashable
        # by width: holds less memory than loadtxt's table
        return _read_ragged(item_cls, text, context)
    if (first := _first_row(text)) is None:
        return None
    try:  # raises on rows of different widths
        values = np.loadtxt(io.StringIO(text), ndmin=2, comments=None)
    except ValueError:
        return _read_ragged(item_cls, text, context)
    if values.shape[1] != len(first):
        return None
    if (columns := _columns(item_cls, first, values, context)) is None:
        return None
    for name, col in columns.items():
        # a view would keep all of `values` alive
        if np.may_share_memory(col, values):
            columns[name] = col.copy()
    return ItemTable(item_cls, columns, len(values))


def _first_row(text: str) -> list[str] | None:
    """The first non-blank line's values, without splitting the rest."""
    start = 0
    while start < len(text):
        end = text.find("\n", start)
        end = len(text) if end == -1 else end
        if values := text[start:end].split():
            return values
        start = end + 1
    return None


def _read_ragged(item_cls: type[Item], text: str, context: RowContext) -> list | None:
    """`read_rows`' Items, grouped by width."""
    try:
        flat = np.array(text.split(), dtype=float)
    except ValueError:
        return None
    widths = _widths(text.encode("ascii"))
    if flat.size != widths.sum():
        return None
    starts = np.concatenate(([0], np.cumsum(widths)[:-1]))
    lines = None  # the non-blank lines, for a width's first row
    items: list = [None] * len(widths)
    for w in np.unique(widths).tolist():
        rows = np.flatnonzero(widths == w)
        if lines is None:
            lines = [line for line in text.split("\n") if line.split()]
        values = flat[starts[rows][:, None] + np.arange(w)]
        if (columns := _columns(item_cls, lines[rows[0]].split(), values, context)) is None:
            return None
        for i, item in zip(rows.tolist(), ItemTable(item_cls, columns, len(rows)).to_items()):
            items[i] = item
    return items
