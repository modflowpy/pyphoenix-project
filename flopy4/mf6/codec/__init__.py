import sys
from os import PathLike
from typing import Any

import numpy as np
import xattree
from cattrs import Converter
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.codec.converter import (
    unstructure_array,
    unstructure_chd,
    unstructure_component,
    unstructure_oc,
    unstructure_tdis,
)

_JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
_JINJA_ENV.filters["dict_blocks"] = filters.dict_blocks
_JINJA_ENV.filters["list_blocks"] = filters.list_blocks
_JINJA_ENV.filters["field_type"] = filters.field_type
_JINJA_ENV.filters["field_value"] = filters.field_value
_JINJA_ENV.filters["array_how"] = filters.array_how
_JINJA_ENV.filters["array_chunks"] = filters.array_chunks
_JINJA_ENV.filters["array2string"] = filters.array2string

_JINJA_TEMPLATE_NAME = "blocks.jinja"

_PRINT_OPTIONS = {
    "precision": 4,
    "linewidth": sys.maxsize,
    "threshold": sys.maxsize,
}


def _make_converter() -> Converter:
    # TODO: document what is converter's responsibility vs Jinja's
    # TODO: how can we make sure writing remains lazy for list input?
    # don't eagerly unstructure to dict, lazily access from the template?

    from flopy4.mf6.component import Component
    from flopy4.mf6.gwf.chd import Chd
    from flopy4.mf6.gwf.oc import Oc
    from flopy4.mf6.tdis import Tdis

    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    converter.register_unstructure_hook(Tdis, unstructure_tdis)
    converter.register_unstructure_hook(Chd, unstructure_chd)
    converter.register_unstructure_hook(Oc, unstructure_oc)
    return converter


_CONVERTER = _make_converter()


def loads(data: str) -> Any:
    # TODO
    pass


def load(path: str | PathLike) -> Any:
    # TODO
    pass


def dumps(data) -> str:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    with np.printoptions(**_PRINT_OPTIONS):  # type: ignore
        return template.render(dfn=type(data).dfn, data=_CONVERTER.unstructure(data))


def dump(data, path: str | PathLike) -> None:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    iterator = template.generate(dfn=type(data).dfn, data=_CONVERTER.unstructure(data))
    with np.printoptions(**_PRINT_OPTIONS), open(path, "w") as f:  # type: ignore
        f.writelines(iterator)


__all__ = [
    "unstructure_array",
    "loads",
    "load",
    "dumps",
    "dump",
]
