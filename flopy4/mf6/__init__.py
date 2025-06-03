from flopy4.mf6.codec import dump, load
from flopy4.mf6.component import Component
from flopy4.uio import DEFAULT_REGISTRY

# register io methods
# TODO: call this "mf6" or something? since it might include binary files
DEFAULT_REGISTRY.register_loader(Component, "ascii", lambda c: load(c.path))
DEFAULT_REGISTRY.register_writer(Component, "ascii", lambda c: dump(c, c.path))
