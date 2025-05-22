import sys

import numpy as np
from cattrs import unstructure
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.spec import blocks_dict, fields_dict

# below stolen/simplified from https://github.com/astropy/astropy/tree/main/astropy/io
# just sketching things.. haven't plugged it all together yet


class Registry:
    def __init__(self):
        self._readers = {}
        self._writers = {}

    def get_reader(self, cls, format=None):
        return next(
            iter(
                [
                    fn
                    for ((fmt, cls_), fn) in self._readers.items()
                    if fmt == format and issubclass(cls, cls_)
                ]
            )
        )

    def get_writer(self, cls, format=None):
        return next(
            iter(
                [
                    fn
                    for ((fmt, cls_), fn) in self._writers.items()
                    if fmt == format and issubclass(cls, cls_)
                ]
            )
        )

    def register_reader(self, cls, format, function):
        if format in self._readers:
            raise ValueError(f"Reader for format {format} already registered.")
        self._readers[cls, format] = (cls, function)

    def register_writer(self, cls, format, function):
        if format in self._writers:
            raise ValueError(f"Writer for format {format} already registered.")
        self._writers[cls, format] = (cls, function)

    def read(self, cls, *args, format=None, **kwargs):
        return self.get_reader(cls, format)(*args, **kwargs)

    def write(self, cls, *args, format=None, **kwargs):
        return self.get_writer(cls, format)(*args, **kwargs)


class IO:
    def __init__(self, instance, cls, method_name, registry=None):
        self._registry = registry
        self._instance = instance
        self._cls = cls
        self._method_name = method_name  # 'read' or 'write'

    @property
    def registry(self):
        return self._registry

    def list_formats(self, out=None):
        formats = self._registry.get_formats(self._cls, self._method_name)

        if out is None:
            formats.pprint(max_lines=-1, max_width=-1)
        else:
            out.write("\n".join(formats.pformat(max_lines=-1, max_width=-1)))

        return out


class IOMethod(property):
    def __get__(self, instance, owner_cls):
        return self.fget(instance, owner_cls)


class ComponentReader(IO):
    def __init__(self, instance, cls):
        super().__init__(instance, cls, "read", registry=None)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.read(self._cls, *args, **kwargs)


class ComponentWriter(IO):
    def __init__(self, instance, cls):
        super().__init__(instance, cls, "write", registry=None)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.write(self._cls, *args, **kwargs)


env = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["fieldkind"] = filters.fieldkind
env.filters["fieldvalue"] = filters.fieldvalue
env.filters["arraydelayed"] = filters.arraydelayed
env.filters["array2string"] = filters.array2string


def _write_ascii(self) -> None:
    cls = type(self)
    fields = fields_dict(cls)
    blocks = blocks_dict(cls)
    template = env.get_template("blocks.jinja")
    iterator = template.generate(fields=fields, blocks=blocks, data=unstructure(self.data))  # type: ignore
    # are these printoptions always applicable?
    with np.printoptions(precision=4, linewidth=sys.maxsize, threshold=sys.maxsize):
        # TODO don't hardcode the filename, maybe a filename attribute?
        with open(self.path / self.name, "w") as f:  # type: ignore
            f.writelines(iterator)
