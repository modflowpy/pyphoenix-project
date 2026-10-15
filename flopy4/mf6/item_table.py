"""A tabular list's rows as columns: one numpy array per field of the Item
class, the column layout of the record schema its DFN gives (flopy3's
recarrays were the same). Read from a block's text in bulk, by the layout
`item._positions` solves from its first row."""

from typing import Any

import attrs
import numpy as np

from flopy4.mf6.codec.reader.transformer.basic import _number
from flopy4.mf6.constants import FILL_INT64
from flopy4.mf6.item import (
    Item,
    RowContext,
    _array_elem_type,
    _positions,
    _signed,
    is_cellid,
)
from flopy4.utils import unwrap_optional


@attrs.define(eq=False)
class ItemTable:
    """A tabular list's rows (see `item._plannable`), as a numpy array per
    field, by name:
    - a cellid: ``(n, ncelldim)`` ints, 0-based, a row of `FILL_INT64` for
      NONE;
    - an array field (aux): ``(n, size)``;
    - any other: ``(n,)``, ints or floats as the field is."""

    item_cls: type[Item]
    columns: dict[str, np.ndarray]

    def __len__(self) -> int:
        return len(next(iter(self.columns.values()))) if self.columns else 0

    def to_items(self) -> list[Item]:
        """An Item per row, as `Item.from_rows` reads them."""
        fields = attrs.fields_dict(self.item_cls)  # type: ignore[arg-type]
        values: list[list] = []
        for name, col in self.columns.items():
            if col.ndim == 1:
                values.append(col.tolist())
                continue
            rows: list[tuple | None] = list(zip(*col.T.tolist()))  # faster than per row
            if is_cellid(fields[name]) and (none := col[:, 0] == FILL_INT64).any():
                for i in np.flatnonzero(none).tolist():
                    rows[i] = None
            values.append(rows)
        names = list(self.columns)
        return [self.item_cls(**dict(zip(names, row))) for row in zip(*values)]


def _rows_text(text: str) -> str:
    """The text without its comment-only lines (NUMBER_LINES allows them)."""
    if "#" not in text and "!" not in text:
        return text
    return "\n".join(
        line for line in text.split("\n") if not (s := line.lstrip()) or s[0] not in "#!"
    )


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
    """A field's column from its values' floats, as `item._plan`'s readers
    convert each row's, or None if they convert it otherwise."""
    if took[0] == "cellid":
        cell = values.astype(np.int64) - 1
        if f.metadata.get("allow_zero"):
            cell[(cell == -1).all(axis=1)] = FILL_INT64
        return cell
    if took[0] == "value":
        if f.metadata.get("index"):
            return values.astype(np.int64) - 1
        if f.metadata.get("time_series"):
            return values  # all numbers here, no series names
        t = unwrap_optional(f.type)
        if t in (int, "int"):
            return values.astype(np.int64)
        if t in (float, "float"):
            return values
        return None
    if is_cellid(f):
        return None  # a row of cellids
    if _signed(f):
        return values.astype(np.int64)
    if f.metadata.get("index"):
        return values.astype(np.int64) - 1
    elem = _array_elem_type(f)
    if elem is int:
        return values.astype(np.int64)
    if elem in (float, None):
        return values
    return None


def read_table(item_cls: type[Item], text: str, context: RowContext) -> ItemTable | None:
    """A block's rows from its text (NUMBER_LINES', all numbers), if each
    has as many values, in the same layout (see `item._positions`), and
    every field converts by column; else None, for `Item.from_rows`."""
    text = _rows_text(text)
    first = next((line.split() for line in text.split("\n") if line.strip()), None)
    if first is None:
        return None
    spans = _positions(item_cls, [_number(v) for v in first], context)
    if spans is None:
        return None
    data = text.encode("ascii")
    if not ((widths := _widths(data)) == len(first)).all():
        return None
    flat = np.fromstring(data, sep=" ")  # type: ignore[call-overload]
    if flat.size != widths.size * len(first):
        return None
    values = flat.reshape(-1, len(first))
    columns: dict[str, Any] = {}
    for f, took, a, b in spans:
        if f is None:
            return None  # a boundname, all digits: read as a word, by row
        if (col := _column(f, took, values[:, a:b] if b else values[:, a])) is None:
            return None
        columns[f.name] = col
    return ItemTable(item_cls, columns)
