from functools import lru_cache
from pathlib import Path

from lark import Lark, Transformer
from lark.lexer import BasicLexer, ContextualLexer, LexerState, LexerThread, LineCounter

_LALR = "lalr"
_GRAMMAR_MODULE = Path(__file__).parent / "grammar"


class _Text:
    """A buffer as lark's lexer reads its input (a `TextSlice`'s
    attributes), which only matches regexes on it."""

    __slots__ = ("text", "start", "end")

    def __init__(self, buffer) -> None:
        self.text = buffer
        self.start = 0
        self.end = len(buffer)


class _BufferLexerThread(LexerThread):
    """Lexes any buffer (a file's mmap), not just `str` or `bytes`. Lark
    passes other input here as is."""

    @classmethod
    def from_custom_input(cls, lexer, text) -> LexerThread:
        return cls(lexer, LexerState(_Text(text), LineCounter(b"\n")))  # type: ignore[arg-type]


class _Numbers(bytes):
    """A NUMBERS match whose `str` is empty, so the token doesn't copy its
    text; the transformer reads it by position (see
    `BasicTransformer.NUMBERS`)."""

    __slots__ = ()

    def __str__(self) -> str:
        return ""


class _BytesLexer(BasicLexer):
    def match(self, text, pos):
        res = super().match(text, pos)
        if res is not None and res[1] == "NUMBERS":
            return _Numbers(res[0]), res[1]
        return res


class _BytesContextualLexer(ContextualLexer):
    BasicLexer = _BytesLexer


def get_basic_parser(transformer: Transformer | None = None, use_bytes: bool = False) -> Lark:
    """The basic grammar's parser. With a transformer, `parse` applies it
    as it goes, never holding the whole tree. With `use_bytes`, it parses
    bytes or a buffer (a file's mmap), so the text needn't be in memory."""
    grammar_path = _GRAMMAR_MODULE / "basic.lark"
    with open(grammar_path, "r") as f:
        return Lark(
            f.read(),
            parser=_LALR,
            debug=True,
            import_paths=[str(_GRAMMAR_MODULE)],
            transformer=transformer,
            use_bytes=use_bytes,
            _plugins=(
                {"LexerThread": _BufferLexerThread, "ContextualLexer": _BytesContextualLexer}
                if use_bytes
                else {}
            ),
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
