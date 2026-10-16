import re
from typing import Any

from lark import Token, Transformer

from flopy4.mf6.codec.reader.transformer.rows import BlockRows, NumberRows
from flopy4.mf6.codec.reader.transformer.typed import unquote
from flopy4.utils import parse_number

# A whole token that's a number, allowing Fortran `D` exponents (`1D-5`).
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eEdD][+-]?\d+)?")


def _value(value: str) -> str | int | float:
    """A token's value: a number if it's one, else the word."""
    if _NUMBER.fullmatch(value):
        return parse_number(value.replace("d", "e").replace("D", "E"))
    return value


class _RecordRows(list):
    """RECORDS' rows, which `block` splices in among its other lines."""


class BasicTransformer(Transformer):
    """
    Basic transformer for MF6 input files. Works only with the basic
    grammar. Yields blocks simply as collections of lines of tokens.
    """

    def start(self, items: list[Any]) -> dict[str, Any]:
        blocks = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            block_name = next(iter(item.keys()))
            # A block name repeating in one file is already an anomaly --
            # real MF6 input has at most one of each (period/solutiongroup
            # blocks are told apart by their own number, part of the name).
            # Seen once in the corpus: two complete, alternative versions
            # of one package concatenated (an apparent conversion leftover)
            # -- keep the first, since a later duplicate has looked more
            # like stray content than the intended one every time so far.
            if block_name in blocks:
                continue
            blocks[block_name] = next(iter(item.values()))
        return blocks

    def block(self, items: list[Any]) -> dict[str, Any]:
        # BEGIN name line... END name
        body: list[Any] = []
        for item in items[2:-2]:
            if isinstance(item, _RecordRows):
                body.extend(item)
            else:
                body.append(item)
        if len(body) == 1 and isinstance(body[0], NumberRows):
            return {items[1]: body[0]}
        if any(isinstance(item, NumberRows) for item in body):
            return {items[1]: BlockRows(body)}
        return {items[1]: body}

    def block_name(self, items: list[Any]) -> str:
        # name plus its index (period/solutiongroup number, utl-tas's time),
        # if any -- anything after that is a remark (see basic.lark). A
        # record header (OBS's "CONTINUOUS FILEOUT <file> [BINARY]") is kept
        # whole, in its own case.
        name, *rest = items
        if rest and isinstance(rest[0], (int, float)):
            return f"{name} {rest[0]}"
        if rest:
            return " ".join([str(name), *map(str, rest)])
        return str(name)

    def _list(self, items: list[Any]) -> list[Any]:
        return items[0] if items else []

    def line(self, items: list[Any]) -> list[Any]:
        return [str(i) if isinstance(i, Token) else i for i in items]

    def TOKEN(self, token: Token) -> str | int | float:
        return _value(str(token))

    def RECORDS(self, token: Token) -> _RecordRows:
        # Each line a row, as `line` reads it; blank and comment-only lines
        # aren't rows.
        rows = _RecordRows()
        for line in str(token).replace(",", " ").split("\n"):
            if (values := line.split()) and values[0][0] not in "#!":
                rows.append([_value(v) for v in values])
        return rows

    def NUMBERS(self, token: Token) -> NumberRows:
        return NumberRows(str(token))

    def QUOTED_WORD(self, token: Token) -> str:
        # Quoting forces string interpretation even if content looks numeric.
        return unquote(token)

    def CNAME(self, token: Token) -> str:
        return str(token)

    def INT(self, token: Token) -> int:
        return int(token)
