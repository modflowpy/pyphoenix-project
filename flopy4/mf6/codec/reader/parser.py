from functools import lru_cache
from pathlib import Path

from lark import Lark, Transformer

_LALR = "lalr"
_GRAMMAR_MODULE = Path(__file__).parent / "grammar"


def get_basic_parser(transformer: Transformer | None = None) -> Lark:
    """The basic grammar's parser. With a transformer, `parse` applies it
    as it goes and returns its result, never holding the whole tree (with
    its tokens, each the text it matched twice over: a big list block's
    many times the file's size)."""
    grammar_path = _GRAMMAR_MODULE / "basic.lark"
    with open(grammar_path, "r") as f:
        return Lark(
            f.read(),
            parser=_LALR,
            debug=True,
            import_paths=[str(_GRAMMAR_MODULE)],
            transformer=transformer,
        )


@lru_cache(maxsize=None)
def get_typed_parser(name: str) -> Lark:
    grammar_path = _GRAMMAR_MODULE / "generated" / f"{name}.lark"
    if not grammar_path.exists():
        raise FileNotFoundError(f"Grammar file not found: {grammar_path}")
    with open(grammar_path, "r") as f:
        return Lark(
            f.read(),
            parser=_LALR,
            debug=True,
            import_paths=[str(_GRAMMAR_MODULE)],
        )
