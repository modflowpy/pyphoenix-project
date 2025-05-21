import sys
import numpy as np
from jinja2 import Environment, PackageLoader
from flopy4.mf6 import filters
from flopy4.mf6.spec import blocks_dict


env = Environment(
loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["dask_expand"] = filters.dask_expand
env.filters["nparray2string"] = filters.nparray2string


class Writer:
    def _write_ascii(self, path) -> None:
        # TODO: factor out an ascii writer separately

        block_spec = blocks_dict(type(self))
        blocks = {}
        for block_name, block in block_spec.items():
            blocks[block_name] = {}
            for field_name, field in block.items():
                if field_name == "data":
                    continue
                blocks[block_name][field_name] = {
                    "spec": field,
                    "value": getattr(self, field_name),
                }

        template = env.get_template("blocks.jinja")
        iterator = template.generate(blocks=blocks)
        with np.printoptions(
            precision=4, linewidth=sys.maxsize, threshold=sys.maxsize
        ):
            with open(path, "w") as f:
                f.writelines(iterator)

    def write(self) -> None:
        self._write_ascii()
        for child in self.children.values():  # type: ignore
            child.write()
