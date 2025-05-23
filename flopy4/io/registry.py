class Registry:
    def __init__(self):
        self._loaders = {}
        self._writers = {}

    def get_loader(self, cls, format=None):
        return next(
            iter(
                [
                    fn
                    for ((fmt, cls_), fn) in self._loaders.items()
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

    def register_loader(self, cls, format, function):
        if format in self._loaders:
            raise ValueError(f"Reader for format {format} already registered.")
        self._loaders[cls, format] = (cls, function)

    def register_writer(self, cls, format, function):
        if format in self._writers:
            raise ValueError(f"Writer for format {format} already registered.")
        self._writers[cls, format] = (cls, function)

    def load(self, cls, *args, format=None, **kwargs):
        return self.get_loader(cls, format)(*args, **kwargs)

    def write(self, cls, *args, format=None, **kwargs):
        return self.get_writer(cls, format)(*args, **kwargs)


DEFAULT_REGISTRY = Registry()
