"""Runs of number-only lines (the grammars' NUMBER_LINES), kept as text."""

from collections.abc import Iterator, Sequence

import numpy as np


class NumberRows(Sequence):
    """NUMBER_LINES' rows, each a list of numbers as basic's `line` or
    typed's `record` reads it, read when first used. A list that's only
    these lines keeps them as such, so its text can be read by column
    instead (see `item_table.read_table`); both transformers splice them in
    among any other rows."""

    __slots__ = ("_text", "_rows")

    def __init__(self, text: str) -> None:
        self._text = text
        self._rows: list[list[int | float]] | None = None

    @property
    def text(self) -> str:
        """The lines' text, commas as spaces and `D` exponents as `E`;
        blank and comment-only lines included."""
        text = self._text.replace(",", " ")
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
        return True  # NUMBER_LINES has a numeric line (so no need to read them)

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


def _number(value: str) -> int | float:
    """`parse_number` for a value NUMBER_LINES took, `D`s already `E`."""
    if "." in value or "e" in value or "E" in value:
        return float(value)
    return int(value)


def without_comments(text: str) -> str:
    """The text without its comment-only lines (NUMBER_LINES allows them)."""
    if "#" not in text and "!" not in text:
        return text
    return "\n".join(
        line for line in text.split("\n") if not (s := line.lstrip()) or s[0] not in "#!"
    )


def number_values(text: str) -> np.ndarray:
    """NUMBER_LINES' values, in order, as floats (an array's data)."""
    return np.array(without_comments(NumberRows(text).text).split(), dtype=float)
