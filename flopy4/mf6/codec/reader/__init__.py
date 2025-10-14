from typing import IO, Any

from flopy4.mf6.codec.reader.parser import make_basic_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer

BASIC_PARSER = make_basic_parser()
BASIC_TRANSFORMER = BasicTransformer()


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

    return BASIC_TRANSFORMER.transform(BASIC_PARSER.parse(data))
