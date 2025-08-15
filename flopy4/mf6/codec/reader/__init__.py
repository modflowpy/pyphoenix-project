from os import PathLike
from pathlib import Path
from typing import Any

from flopy4.mf6.codec.reader.parser import make_basic_parser
from flopy4.mf6.codec.reader.transformer import BasicTransformer


def load(path: str | PathLike) -> Any:
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
    path = Path(path)
    with open(path, "r") as f:
        data = f.read()
    return loads(data)


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

    parser = make_basic_parser()
    transformer = BasicTransformer()
    return transformer.transform(parser.parse(data))
