from flopy4.mf6.codec import dump
from flopy4.mf6.component import Component
from flopy4.mf6.converter import COMPONENT_CONVERTER
from flopy4.uio import DEFAULT_REGISTRY

# register io methods
# TODO: call format "mf6" or something? since it might include binary files
DEFAULT_REGISTRY.register_writer(
    Component, "ascii", lambda c: dump(COMPONENT_CONVERTER.unstructure(c), c.path)
)
