from typing import Literal

from flopy4.io.registry import Registry

IOMethodName = Literal["load", "write"]


class IO:
    def __init__(self, instance, cls, method_name: IOMethodName, registry: Registry = None):
        self._registry = registry
        self._instance = instance
        self._cls = cls
        self._method_name: IOMethodName = method_name

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


class Loader(IO):
    def __init__(self, instance, cls):
        super().__init__(instance, cls, "load", registry=None)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.load(self._cls, *args, **kwargs)


class Writer(IO):
    def __init__(self, instance, cls):
        super().__init__(instance, cls, "write", registry=None)

    def __call__(self, *args, **kwargs) -> None:
        return self.registry.write(self._cls, *args, **kwargs)
