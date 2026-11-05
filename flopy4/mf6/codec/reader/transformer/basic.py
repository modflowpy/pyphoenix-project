from contextvars import ContextVar
from mmap import mmap
from typing import Any

from lark import Token, Transformer

from flopy4.mf6.codec.reader.transformer.rows import BlockRows, NumberRows, Span
from flopy4.utils import NUMBER, parse_number

# The buffer being parsed and its encoding (see `BasicTransformer`).
SOURCE: ContextVar[tuple[bytes | mmap, str]] = ContextVar("SOURCE")


class _RecordRows(list):
    """RECORDS' rows, which `block` splices in among its other lines."""


def _text(token: Token) -> str:
    return token.value.decode(SOURCE.get()[1])


class BasicTransformer(Transformer):
    """
    Basic transformer for MF6 input files. Works only with the basic
    grammar, parsing bytes (`get_basic_parser(..., use_bytes=True)`) with
    `SOURCE` set to them. Yields blocks simply as collections of lines of
    tokens, as text (see `from_text`).
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
        # BEGIN name line... END name. The grammar takes a BEGIN inside a
        # block as a row and any name after END, so a block missing its END
        # would swallow the next one; like MF6, stop on both.
        begin, name, end_name = items[0], items[1], items[-1]

        def no_end(found: str) -> ValueError:
            return ValueError(
                f"{name.upper()} block, opened on line {begin.line}, has no END: "
                f"found {found.upper()}"
            )

        body: list[Any] = []
        for item in items[2:-2]:
            if isinstance(item, _RecordRows):
                body.extend(item)
            else:
                if isinstance(item, list) and item and item[0].upper() == "BEGIN":
                    raise no_end(" ".join(item))
                body.append(item)
        if end_name.split()[0].lower() != name.split()[0].lower():
            raise no_end(f"END {end_name}")
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
        if rest and NUMBER.fullmatch(rest[0]):
            return f"{name} {parse_number(rest[0])}"
        if rest:
            return " ".join([str(name), *map(str, rest)])
        return str(name)

    def line(self, items: list[Any]) -> list[Any]:
        return [_text(i) if isinstance(i, Token) else i for i in items]

    def TOKEN(self, token: Token) -> str:
        return _text(token)

    def RECORDS(self, token: Token) -> _RecordRows:
        # Each line a row, as `line` reads it; blank and comment-only lines
        # aren't rows.
        rows = _RecordRows()
        for line in _text(token).replace(",", " ").split("\n"):
            if (values := line.split()) and values[0][0] not in "#!":
                rows.append(values)
        return rows

    def NUMBERS(self, token: Token) -> NumberRows:
        # Where the text is, not the text: it's read from the buffer when
        # it's structured.
        buffer, encoding = SOURCE.get()
        start, end = token.start_pos, token.end_pos
        assert start is not None and end is not None  # the lexer sets both
        return NumberRows(Span(buffer, start, end, encoding))

    def QUOTED_WORD(self, token: Token) -> str:
        # Without its quotes, as MF6 reads it.
        return _text(token)[1:-1]

    def CNAME(self, token: Token) -> str:
        return _text(token)

    def INT(self, token: Token) -> int:
        return int(token.value)
