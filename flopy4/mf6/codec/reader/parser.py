from pathlib import Path

from lark import Lark


def make_generic_parser() -> Lark:
    grammar_path = Path(__file__).parent / "grammar" / "mf6.lark"
    with open(grammar_path, "r") as f:
        grammar = f.read()
    return Lark(grammar, parser="lalr", debug=True)
