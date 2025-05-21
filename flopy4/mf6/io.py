import sys

import numpy as np
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.spec import blocks_dict, fields_dict

env = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["fieldkind"] = filters.fieldkind
env.filters["fieldvalue"] = filters.fieldvalue
env.filters["arraydelayed"] = filters.arraydelayed
env.filters["array2string"] = filters.array2string


class Writer:
    # TODO remove type: ignore statements below.
    # but idk how to properly type a mixin class.
    # this one assumes the presence of attributes:
    # - name
    # - path
    # - data

    def _write_ascii(self) -> None:
        cls = type(self)
        fields = fields_dict(cls)
        blocks = blocks_dict(cls)
        template = env.get_template("blocks.jinja")
        iterator = template.generate(fields=fields, blocks=blocks, data=self.data)  # type: ignore
        # are these printoptions always applicable?
        with np.printoptions(precision=4, linewidth=sys.maxsize, threshold=sys.maxsize):
            # TODO don't hardcode the filename, maybe a filename attribute?
            with open(self.path / self.name, "w") as f:  # type: ignore
                f.writelines(iterator)

    def write(self) -> None:
        # TODO: factor out an ascii writer separately
        self._write_ascii()
        for child in self.children.values():  # type: ignore
            child.write()
