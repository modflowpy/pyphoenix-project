import re
from typing import IO, Any

from lark.exceptions import LarkError

from flopy4.mf6.codec.reader.parser import get_basic_parser, get_typed_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer, get_typed_transformer

BASIC_PARSER = get_basic_parser()
BASIC_TRANSFORMER = BasicTransformer()

# Some real-world fixtures (mf5to15-converted ones observed so far) carry
# non-MF6 legacy content -- e.g. a classic MODFLOW-2005/NWT flat-format
# block -- appended after the file's last real BEGIN/END block. Matches
# each well-formed block in turn; used as a fallback to trim anything
# after the last one when the file fails to parse as-is.
_BLOCK_RE = re.compile(
    r"^[ \t]*begin\s+\S+.*?^[ \t]*end\s+\S+[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _trim_trailing_garbage(data: str) -> str:
    """Truncate to just past the last recognized BEGIN...END block."""
    matches = list(_BLOCK_RE.finditer(data))
    if not matches:
        return data
    return data[: matches[-1].end()]


def load(fp: IO[str], *, component: str | None = None, dfn_path: str | None = None) -> Any:
    """
    Load and parse an MF6 input file.

    Parameters
    ----------
    path : str | PathLike
        Path to the MF6 input file
    component :
        DFN name (e.g. ``"gwf-wel"``) of the file's package/component. If
        given, parses with that component's typed grammar/transformer
        instead of the generic basic grammar.
    dfn_path :
        Local DFN directory to resolve ``component`` against. Only used
        when ``component`` is given; defaults to the release recorded in
        ``_contract.py`` (a network fetch) if omitted.

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    return loads(fp.read(), component=component, dfn_path=dfn_path)


def loads(data: str, *, component: str | None = None, dfn_path: str | None = None) -> Any:
    """
    Parse MF6 input file content from string.

    Parameters
    ----------
    data : str
        MF6 input file content as string
    component :
        DFN name (e.g. ``"gwf-wel"``) of the file's package/component. If
        given, parses with that component's typed grammar/transformer
        instead of the generic basic grammar.
    dfn_path :
        Local DFN directory to resolve ``component`` against. Only used
        when ``component`` is given; defaults to the release recorded in
        ``_contract.py`` (a network fetch) if omitted.

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    if component is not None:
        return loads_typed(data, component, dfn_path=dfn_path)
    return loads_basic(data)


def loads_basic(data: str) -> Any:
    """Parse MF6 input file content with the generic, untyped grammar."""
    try:
        tree = BASIC_PARSER.parse(data)
    except LarkError:
        trimmed = _trim_trailing_garbage(data)
        if trimmed == data:
            raise
        tree = BASIC_PARSER.parse(trimmed)
    return BASIC_TRANSFORMER.transform(tree)


def loads_typed(data: str, component: str, *, dfn_path: str | None = None) -> Any:
    """Parse MF6 input file content with ``component``'s typed grammar."""
    parser = get_typed_parser(component)
    transformer = get_typed_transformer(component, dfn_path)
    try:
        tree = parser.parse(data)
    except LarkError:
        trimmed = _trim_trailing_garbage(data)
        if trimmed == data:
            raise
        tree = parser.parse(trimmed)
    return transformer.transform(tree)
