"""Consecutive number-only lines (the grammars' NUMBERS tokens), kept as text."""

from collections.abc import Iterator, Sequence
from mmap import mmap
from typing import NamedTuple

import numpy as np


class Span(NamedTuple):
    """Where a token's text is in the buffer that was parsed (a file's
    mapping), decoded only when read."""

    buffer: bytes | mmap
    start: int
    end: int
    encoding: str

    def decode(self) -> str:
        return str(memoryview(self.buffer)[self.start : self.end], self.encoding)


class NumberRows(Sequence):
    """A NUMBERS token's rows, each a list of numbers, split when first
    used. A block of only these keeps its text, to read by column (see
    `item_table.read_rows`)."""

    __slots__ = ("_text", "_rows")

    def __init__(self, text: str | Span) -> None:
        # A `Span` keeps the text out of memory until it's read.
        self._text = text
        self._rows: list[list[int | float]] | None = None

    @property
    def text(self) -> str:
        """The lines' text, commas as spaces and `D` exponents as `E`;
        blank and comment-only lines included."""
        text = self._text if isinstance(self._text, str) else self._text.decode()
        text = text.replace(",", " ")
        if "d" in text or "D" in text:
            text = text.replace("d", "e").replace("D", "E")
        return text

    @property
    def rows(self) -> list[list[int | float]]:
        if self._rows is None:
            # blank and comment-only lines aren't rows. (A comment's text
            # may have changed in `text` -- it's skipped.)
            self._rows = [
                [_number(v) for v in values]
                for line in self.text.split("\n")
                if (values := line.split()) and values[0][0] not in "#!"
            ]
        return self._rows

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return True  # NUMBERS has a numeric line (so no need to read them)

    def __getitem__(self, i):  # type: ignore[override]
        return self.rows[i]

    def __iter__(self) -> Iterator[list[int | float]]:
        return iter(self.rows)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, NumberRows):
            other = other.rows
        return self.rows == other

    def __repr__(self) -> str:
        return repr(self.rows)


class BlockRows(Sequence):
    """A block's rows, some of them `NumberRows`, flattened when first
    used. An array block reads their text instead (see `parts`)."""

    __slots__ = ("parts", "_rows")

    def __init__(self, parts: list) -> None:
        self.parts = parts
        self._rows: list | None = None

    @property
    def rows(self) -> list:
        if self._rows is None:
            rows: list = []
            for part in self.parts:
                if isinstance(part, NumberRows):
                    rows.extend(part.rows)
                else:
                    rows.append(part)
            self._rows = rows
        return self._rows

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return bool(self.parts)

    def __getitem__(self, i):  # type: ignore[override]
        return self.rows[i]

    def __iter__(self) -> Iterator:
        return iter(self.rows)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (NumberRows, BlockRows)):
            other = other.rows
        return self.rows == other

    def __repr__(self) -> str:
        return repr(self.rows)


def parts(rows: Sequence) -> list:
    """A block's rows with its NUMBERS tokens kept as such, each
    a `NumberRows`, for reading them by text (an array's data)."""
    if isinstance(rows, BlockRows):
        return rows.parts
    if isinstance(rows, NumberRows):
        return [rows]
    return list(rows)


def _number(value: str) -> int | float:
    """`parse_number` for a value NUMBERS took, `D`s already `E`."""
    if "." in value or "e" in value or "E" in value:
        return float(value)
    return int(value)


def without_comments(text: str) -> str:
    """The text without its comment-only lines (NUMBERS allows them)."""
    if "#" not in text and "!" not in text:
        return text
    return "\n".join(
        line for line in text.split("\n") if not (s := line.lstrip()) or s[0] not in "#!"
    )


def number_values(text: str) -> np.ndarray:
    """NUMBERS' values, in order, as floats (an array's data)."""
    return row_values(NumberRows(text))


def row_values(rows: NumberRows, dtype=float) -> np.ndarray:
    """The rows' values, in order, as `dtype` (an array's data)."""
    values = np.array(without_comments(rows.text).split(), dtype=float)
    return values if dtype is float or dtype == np.float64 else values.astype(dtype)
