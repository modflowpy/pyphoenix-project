import sys

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.component import Component
from flopy4.mf6.spec import blocks_dict, fields_dict
from flopy4.uio import DEFAULT_REGISTRY

JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
JINJA_ENV.filters["field_kind"] = filters.field_kind
JINJA_ENV.filters["fieldvalue"] = filters.fieldvalue
JINJA_ENV.filters["arraydelayed"] = filters.arraydelayed
JINJA_ENV.filters["array2string"] = filters.array2string
JINJA_ENV.filters["is_dict"] = filters.is_dict
JINJA_TEMPLATE_NAME = "blocks.jinja"


def _load_ascii(self) -> None:
    # TODO
    pass


def _write_ascii(self) -> None:
    cls = type(self)
    fields = fields_dict(cls)
    blocks = blocks_dict(cls)
    template = JINJA_ENV.get_template(JINJA_TEMPLATE_NAME)
    iterator = template.generate(fields=fields, blocks=blocks, data=unstructure(self.data))  # type: ignore
    # are these printoptions always applicable?
    with np.printoptions(precision=4, linewidth=sys.maxsize, threshold=sys.maxsize):
        # TODO don't hardcode the filename, maybe a filename attribute?
        with open(self.path / self.name, "w") as f:  # type: ignore
            f.writelines(iterator)


# TODO: where to do this? probably not here..on plugin discovery?
DEFAULT_REGISTRY.register_loader(Component, "ascii", _load_ascii)
DEFAULT_REGISTRY.register_writer(Component, "ascii", _write_ascii)
