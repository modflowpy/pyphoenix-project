import re
from typing import IO, Any

from lark.exceptions import LarkError

from flopy4.mf6.codec.reader.parser import get_basic_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer

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


def load(fp: IO[str]) -> Any:
    """
    Load and parse an MF6 input file.

    Parameters
    ----------
    path : str | PathLike
        Path to the MF6 input file

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    return loads(fp.read())


def loads(data: str) -> Any:
    """
    Parse MF6 input file content from string.

    Parameters
    ----------
    data : str
        MF6 input file content as string

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """

    try:
        tree = BASIC_PARSER.parse(data)
    except LarkError:
        trimmed = _trim_trailing_garbage(data)
        if trimmed == data:
            raise
        tree = BASIC_PARSER.parse(trimmed)
    return BASIC_TRANSFORMER.transform(tree)
