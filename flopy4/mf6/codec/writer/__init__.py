import sys
from typing import IO

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6.codec.writer import filters

_JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6.codec.writer"),
    trim_blocks=True,
    lstrip_blocks=True,
)
_JINJA_ENV.filters["field_type"] = filters.field_type
_JINJA_ENV.filters["array_how"] = filters.array_how
_JINJA_ENV.filters["array2chunks"] = filters.array2chunks
_JINJA_ENV.filters["array2string"] = filters.array2string
_JINJA_ENV.filters["array2const"] = filters.array2const
_JINJA_ENV.filters["data2list"] = filters.data2list
_JINJA_TEMPLATE_NAME = "blocks.jinja"
_PRINT_OPTIONS = {
    "precision": 4,
    "linewidth": sys.maxsize,
    "threshold": sys.maxsize,
}


def dumps(data) -> str:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    with np.printoptions(**_PRINT_OPTIONS):  # type: ignore
        return template.render(blocks=data)


def dump(data, fp: IO[str]) -> None:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    iterator = template.generate(blocks=data)
    with np.printoptions(**_PRINT_OPTIONS):  # type: ignore
        fp.writelines(iterator)
