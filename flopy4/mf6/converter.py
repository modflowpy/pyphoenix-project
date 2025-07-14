from typing import Any

import xattree
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.spec import get_blocks


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blockspec = get_blocks(value.dfn)
    blocks = {}
    for block_name, block in blockspec.items():
        blocks[block_name] = {}
        for field_name in block.keys():
            blocks[block_name][field_name] = data[field_name]
    return blocks


def _make_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = _make_converter()
