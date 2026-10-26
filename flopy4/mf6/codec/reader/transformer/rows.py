"""Consecutive number-only lines (the grammars' NUMBERS tokens), kept as text."""

import re
from collections.abc import Iterator, Sequence
from mmap import mmap
from typing import NamedTuple

import numpy as np

from flopy4.utils import D_EXPONENT, fortran_float, parse_number


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
    def raw_text(self) -> str:
        """The lines' text as written."""
        return self._text if isinstance(self._text, str) else self._text.decode()

    @property
    def text(self) -> str:
        """The lines' text, commas as spaces and `D` exponents as `E`;
        blank and comment-only lines included."""
        text = self.raw_text.replace(",", " ")
        if "d" in text or "D" in text:
            text = text.replace("d", "e").replace("D", "E")
        return text

    @property
    def rows(self) -> list[list[int | float]]:
        if self._rows is None:
            # blank and comment-only lines aren't rows. (A comment's text
            # may have changed in `text` -- it's skipped.)
            lines = [
                values
                for line in self.text.split("\n")
                if (values := line.split()) and values[0][0] not in "#!"
            ]
            try:
                self._rows = [[parse_number(v) for v in values] for values in lines]
            except ValueError:
                # NUMBERS takes repeat counts, for arrays (see `array_values`)
                if (tok := next((v for vs in lines for v in vs if "*" in v), None)) is None:
                    raise
                raise ValueError(
                    f"repeat count {tok!r} in a list row: MF6 reads them only in an array's values"
                ) from None
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


def without_comments(text: str) -> str:
    """The text without its comment-only lines (NUMBERS allows them)."""
    if "#" not in text and "!" not in text:
        return text
    return "\n".join(
        line for line in text.split("\n") if not (s := line.lstrip()) or s[0] not in "#!"
    )


def number_values(text: str) -> np.ndarray:
    """NUMBERS' values, in order, as floats (an array's data)."""
    return array_values(without_comments(text))


# A null value: two commas with only whitespace between them.
_NULL = re.compile(r",\s*,")


def array_values(
    text: str, dtype=np.float64, count: int | None = None, source: object = ""
) -> np.ndarray:
    """An array's values (the first ``count``, or all), read as MF6 reads
    them (Fortran list-directed input): repeat counts, ``D`` exponents,
    ``/`` ending the read. Comments aren't allowed, as in MF6. ``source``
    prefixes errors."""
    if "/" in text:
        text = text[: text.index("/")]
    integer = np.dtype(dtype).kind in "iu"
    if not integer and ("d" in text or "D" in text):
        text = text.translate(D_EXPONENT)
    if "," in text:
        if (at := _null_value(text)) and (count is None or at <= count):
            raise ValueError(f"{_prefix(source)}null value (empty between commas) at value {at}")
        text = text.replace(",", " ")
    tokens = text.split()
    if "*" in text:
        tokens = _expand_repeats(tokens, count, source)
    if count is not None and len(tokens) > count:
        tokens = tokens[:count]
    try:
        values = np.array(tokens, dtype=dtype)
    except ValueError:
        values = np.array([_fortran_number(t, integer, source) for t in tokens], dtype=dtype)
    if count is not None and len(values) < count:
        raise ValueError(f"{_prefix(source)}expected {count} values, got {len(values)}")
    return values


def _null_value(text: str) -> int:
    """Which value (from 1) of ``text`` is the first null one, or 0."""
    if text.lstrip().startswith(","):
        return 1
    if m := _NULL.search(text):
        return len(text[: m.start()].replace(",", " ").split()) + 1
    return 0


def _prefix(source: object) -> str:
    return f"{source}: " if source else ""


def _expand_repeats(tokens: list[str], count: int | None, source: object) -> list[str]:
    """``tokens`` with each ``r*c`` expanded, up to ``count`` values."""
    out: list[str] = []
    for tok in tokens:
        if count is not None and len(out) >= count:
            break
        r, star, c = tok.partition("*")
        if not star:
            out.append(tok)
            continue
        if not r.isdigit() or int(r) == 0:
            raise ValueError(f"{_prefix(source)}bad repeat count {tok!r}")
        if not c:
            raise ValueError(f"{_prefix(source)}null values ({tok!r}) at value {len(out) + 1}")
        out.extend([c] * int(r))
    return out


def _fortran_number(token: str, integer: bool, source: object) -> int | float:
    """A value numpy can't parse, read as Fortran does."""
    try:
        return int(token) if integer else fortran_float(token)
    except ValueError:
        kind = "integer" if integer else "number"
        raise ValueError(f"{_prefix(source)}not a valid {kind}: {token!r}") from None
