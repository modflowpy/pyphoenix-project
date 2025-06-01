import sys
from os import PathLike
from typing import Any

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.codec.converter import structure_array, unstructure_array

_JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
_JINJA_ENV.filters["blocks"] = filters.blocks
_JINJA_ENV.filters["field_type"] = filters.field_type
_JINJA_ENV.filters["field_value"] = filters.field_value
_JINJA_ENV.filters["is_list"] = filters.is_list
_JINJA_ENV.filters["array_how"] = filters.array_how
_JINJA_ENV.filters["array_chunks"] = filters.array_chunks
_JINJA_ENV.filters["array2string"] = filters.array2string

_JINJA_TEMPLATE_NAME = "blocks.jinja"

_PRINT_OPTIONS = {
    "precision": 4,
    "linewidth": sys.maxsize,
    "threshold": sys.maxsize,
}


def unstructure(data):
    # TODO unstructure arrays into sparse dicts
    # TODO combine OC fields into list input as defined in the MF6 dfn
    # TODO return a dictionary instead of the component itself, then
    # update filters to use dictinoary access instead of getattr()
    return data


def loads(data: str) -> Any:
    # TODO
    pass


def load(path: str | PathLike) -> Any:
    # TODO
    pass


def dumps(data) -> str:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    with np.printoptions(**_PRINT_OPTIONS):  # type: ignore
        return template.render(dfn=type(data).dfn, data=unstructure(data))


def dump(data, path: str | PathLike) -> None:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    iterator = template.generate(dfn=type(data).dfn, data=unstructure(data))
    with np.printoptions(**_PRINT_OPTIONS), open(path, "w") as f:  # type: ignore
        f.writelines(iterator)


__all__ = [
    "structure_array",
    "unstructure_array",
    "loads",
    "load",
    "dumps",
    "dump",
]
