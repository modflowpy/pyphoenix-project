import sys
from os import PathLike

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters

JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
JINJA_ENV.filters["blocks"] = filters.blocks
JINJA_ENV.filters["field_type"] = filters.field_type
JINJA_ENV.filters["field_value"] = filters.field_value
JINJA_ENV.filters["array_delay"] = filters.array_delay
JINJA_ENV.filters["array2string"] = filters.array2string
JINJA_ENV.filters["is_dict"] = filters.is_dict
JINJA_TEMPLATE_NAME = "blocks.jinja"


def load(path: str | PathLike) -> None:
    # TODO
    pass


def dump(data, path: str | PathLike) -> None:
    template = JINJA_ENV.get_template(JINJA_TEMPLATE_NAME)
    iterator = template.generate(dfn=type(data).dfn, data=data)
    # are these printoptions always applicable?
    with np.printoptions(precision=4, linewidth=sys.maxsize, threshold=sys.maxsize):
        # TODO don't hardcode the filename, maybe a filename attribute?
        with open(path, "w") as f:  # type: ignore
            f.writelines(iterator)
