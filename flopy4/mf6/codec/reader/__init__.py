import io
import mmap
import os
import re
from typing import IO, Any

from lark.exceptions import LarkError

from flopy4.mf6.codec.reader.parser import get_basic_parser, get_typed_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer, get_typed_transformer
from flopy4.mf6.codec.reader.transformer.basic import SOURCE

# Transforms as it parses, from bytes (see `get_basic_parser`).
BASIC_PARSER = get_basic_parser(BasicTransformer(), use_bytes=True)

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


def load(fp: IO[str], *, component: str | None = None) -> Any:
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

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    if component is None and (mapped := _map(fp)) is not None:
        return _parse_basic(*mapped)
    return loads(fp.read(), component=component)


# Files at least this big are mapped (see `_map`): a mapping costs ~4 ms
# at any size (macOS), as much as reading 18 MB of text.
_MAP_SIZE = 16 * 2**20


def _map(fp: IO[str]) -> tuple[mmap.mmap, str] | None:
    """`fp`'s file mapped, and its encoding, if it's big (see `_MAP_SIZE`)
    and its bytes parse as its text would: an ASCII-compatible encoding and
    no carriage returns. A mapping lives in the OS's file cache, not the
    process's memory."""
    try:
        fileno = fp.fileno()
        if fp.tell() != 0 or os.fstat(fileno).st_size < _MAP_SIZE:
            return None
    except (AttributeError, OSError, io.UnsupportedOperation):
        return None
    encoding = getattr(fp, "encoding", None)
    if not encoding or "a\n".encode(encoding) != b"a\n":
        return None
    buffer = mmap.mmap(fileno, 0, access=mmap.ACCESS_READ)
    if buffer.find(b"\r") != -1:
        buffer.close()
        return None
    # Not closed: the parsed values keep it until they're read. It's
    # unmapped when they're gone.
    return buffer, encoding


def loads(data: str, *, component: str | None = None) -> Any:
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

    Returns
    -------
    Any
        Parsed MF6 input file structure
    """
    if component is not None:
        return loads_typed(data, component)
    return loads_basic(data)


def loads_basic(data: str) -> Any:
    """Parse MF6 input file content with the generic, untyped grammar."""
    return _parse_basic(data.encode(), "utf-8")


def _parse_basic(buffer: bytes | mmap.mmap, encoding: str) -> Any:
    """Parse text's bytes, or a buffer of them, in `encoding`."""
    token = SOURCE.set((buffer, encoding))
    try:
        return BASIC_PARSER.parse(buffer)  # type: ignore[arg-type]
    except LarkError:
        data = str(buffer, encoding)
        trimmed = _trim_trailing_garbage(data)
        if trimmed == data:
            raise
        return _parse_basic(trimmed.encode(encoding), encoding)
    finally:
        SOURCE.reset(token)


def loads_typed(data: str, component: str) -> Any:
    """Parse MF6 input file content with ``component``'s typed grammar."""
    parser = get_typed_parser(component)
    transformer = get_typed_transformer()
    try:
        tree = parser.parse(data)
    except LarkError:
        trimmed = _trim_trailing_garbage(data)
        if trimmed == data:
            raise
        tree = parser.parse(trimmed)
    return transformer.transform(tree)
