"""
Unified IO framework. Program interfaces can plug in custom
load/write routines for pairs of component class and format.

Most of this module is stolen/simplified from astropy, at:
- https://github.com/astropy/astropy/tree/main/astropy/io.
"""

__all__ = ["IO", "Loader", "Writer", "DEFAULT_REGISTRY"]


from typing import Literal


class Registry:
    """
    Registry for IO operations. Loaders and writers
    are registered by format and the class they are
    associated with.
    """

    def __init__(self):
        self._loaders = {}
        self._writers = {}

    def get_loader(self, cls, format=None):
        return next(
            iter(
                [
                    fn
                    for (cls_, fmt), fn in self._loaders.items()
                    if fmt == format and issubclass(cls, cls_)
                ]
            )
        )

    def get_writer(self, cls, format=None):
        return next(
            iter(
                [
                    fn
                    for (cls_, fmt), fn in self._writers.items()
                    if fmt == format and issubclass(cls, cls_)
                ]
            )
        )

    def register_loader(self, cls, format, function):
        if format in self._loaders:
            raise ValueError(f"Loader for format {format} already registered.")
        self._loaders[cls, format] = function

    def register_writer(self, cls, format, function):
        if format in self._writers:
            raise ValueError(f"Writer for format {format} already registered.")
        self._writers[cls, format] = function

    def load(self, cls, instance, *args, format=None, **kwargs):
        _load = self.get_loader(cls, format)
        _load(instance, *args, **kwargs)

    def write(self, cls, instance, *args, format=None, **kwargs):
        _write = self.get_writer(cls, format)
        _write(instance, *args, **kwargs)


DEFAULT_REGISTRY = Registry()


Op = Literal["load", "write"]


class IO(property):
    """Wrap a file IO descriptor as a property."""

    def __get__(self, instance, owner_cls):
        return self.fget(instance, owner_cls)


class IODescriptor:
    """Base class for file IO operations, implemented as descriptors."""

    def __init__(self, instance, cls, op: Op, registry: Registry | None = None):
        self._registry = registry or DEFAULT_REGISTRY
        self._instance = instance
        self._cls = cls
        self._op: Op = op

    @property
    def registry(self):
        return self._registry

    def list_formats(self, out=None):
        formats = self._registry.get_formats(self._cls, self._op)

        if out is None:
            formats.pprint(max_lines=-1, max_width=-1)
        else:
            out.write("\n".join(formats.pformat(max_lines=-1, max_width=-1)))

        return out


class Loader(IODescriptor):
    """Descriptor for loading data from file."""

    def __init__(self, instance, cls):
        super().__init__(instance, cls, "load", registry=DEFAULT_REGISTRY)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.load(self._cls, self._instance, *args, **kwargs)


class Writer(IODescriptor):
    """Descriptor for writing data to file."""

    def __init__(self, instance, cls):
        super().__init__(instance, cls, "write", registry=DEFAULT_REGISTRY)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.write(self._cls, self._instance, *args, **kwargs)
