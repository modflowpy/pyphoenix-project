from typing import Any

from lark import Token, Transformer

from flopy4.utils import parse_number


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
        return {items[0]: items[1 : (len(items) - 1)]}

    def block_name(self, items: list[Any]) -> str:
        return " ".join([str(item) for item in items if item is not None])

    def _list(self, items: list[Any]) -> list[Any]:
        return items[0] if items else []

    def line(self, items: list[Any]) -> list[Any]:
        return items

    def item(self, items: list[Any]) -> str | float | int:
        return items[0]

    def word(self, items: list[Token]) -> str:
        return str(items[0])

    def NUMBER(self, token: Token) -> int | float:
        return parse_number(str(token))

    def CNAME(self, token: Token) -> str:
        return str(token)

    def INT(self, token: Token) -> int:
        return int(token)
