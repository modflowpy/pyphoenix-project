import sys
from typing import IO, Iterator

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6.codec import filters as shared_filters
from flopy4.mf6.codec.writer import filters as writer_filters

_JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6.codec.writer"),
    trim_blocks=True,
    lstrip_blocks=True,
)
_JINJA_ENV.filters["field_type"] = shared_filters.field_type
_JINJA_ENV.filters["array_how"] = writer_filters.array_how
_JINJA_ENV.filters["array2const"] = writer_filters.array2const
_JINJA_ENV.filters["array2chunks"] = writer_filters.array2chunks
_JINJA_ENV.filters["array2string"] = writer_filters.array2string
_JINJA_ENV.filters["data2list"] = writer_filters.data2list
_JINJA_ENV.filters["data2lines"] = writer_filters.data2lines
_JINJA_TEMPLATE_NAME = "blocks.jinja"


def _get_print_options(context=None):
    """Get numpy print options from WriteContext."""
    if context is not None:
        return context.to_numpy_printoptions()
    # Default options
    return {
        "precision": 4,
        "linewidth": sys.maxsize,
        "threshold": sys.maxsize,
    }


def _clean_last_chunk(iterator: Iterator[str]) -> Iterator[str]:
    """Strip extra newline at the end of last chunk."""
    try:
        current_chunk = next(iterator)
    except StopIteration:
        return

    # Look ahead to find last chunk
    for next_chunk in iterator:
        yield current_chunk
        current_chunk = next_chunk

    # When for-loop ends, if current_chunk is "\n\n", strip one newline
    if current_chunk == "\n\n":
        yield "\n"
    else:
        yield current_chunk


def dumps(data, context=None) -> str:
    """
    Serialize data to MF6 format string.

    Parameters
    ----------
    data : dict
        Data to serialize
    context : WriteContext, optional
        Configuration context for writing

    Returns
    -------
    str
        Serialized MF6 format string
    """
    from flopy4.mf6.write_context import WriteContext

    if context is None:
        context = WriteContext.default()

    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    print_opts = _get_print_options(context)
    with np.printoptions(**print_opts):  # type: ignore
        result = template.render(blocks=data, context=context)

    return result


def dump(data, fp: IO[str], context=None) -> None:
    """
    Serialize data to MF6 format and write to file.

    Parameters
    ----------
    data : dict
        Data to serialize
    fp : IO[str]
        File pointer to write to
    context : WriteContext, optional
        Configuration context for writing
    """
    from flopy4.mf6.write_context import WriteContext

    if context is None:
        context = WriteContext.default()

    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    iterator = template.generate(blocks=data, context=context)
    print_opts = _get_print_options(context)
    with np.printoptions(**print_opts):  # type: ignore
        fp.writelines(_clean_last_chunk(iterator))
