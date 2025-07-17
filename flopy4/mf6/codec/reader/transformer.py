from typing import Any

from lark import Token, Transformer


class GenericTransformer(Transformer):
    """
    Generic transformer for MF6 input files. Works only with the generic
    grammar. Returns structures of blocks consisting of lines of tokens.
    """

    def start(self, items: list[Any]) -> dict[str, Any]:
        blocks = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            block_name = next(iter(item.keys()))
            blocks[block_name] = next(iter(item.values()))
        return blocks

    def block(self, items: list[Any]) -> dict[str, Any]:
        return {items[0]: items[1 : (len(items) - 1)]}

    def block_name(self, items: list[Any]) -> str:
        return " ".join([str(item) for item in items if item is not None])

    def line(self, items: list[Any]) -> list[Any]:
        return items[1:]

    def item(self, items: list[Any]) -> str | float | int:
        return items[0]

    def word(self, items: list[Token]) -> str:
        return str(items[0])

    def NUMBER(self, token: Token) -> int | float:
        value = str(token)
        try:
            if "." in value or "e" in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return float(value)

    def CNAME(self, token: Token) -> str:
        return str(token)

    def INT(self, token: Token) -> int:
        return int(token)
