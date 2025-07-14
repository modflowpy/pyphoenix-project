from pathlib import Path
from typing import Any

import xattree
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.spec import get_blocks


def _transform_path_to_record(field_name: str, path_value: Path) -> tuple:
    """Transform a Path field to its corresponding MF6 record format."""
    # Infer record structure from field name
    if field_name.endswith("_file"):
        base_name = field_name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(path_value))
    
    # Default fallback
    return (field_name.upper(), "FILEOUT", str(path_value))


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blockspec = get_blocks(value.dfn)
    blocks = {}
    for block_name, block in blockspec.items():
        blocks[block_name] = {}
        for field_name in block.keys():
            field_value = data[field_name]
            
            # Transform Path fields to record format
            if isinstance(field_value, Path) and field_value is not None:
                field_value = _transform_path_to_record(field_name, field_value)
            
            blocks[block_name][field_name] = field_value
    return blocks


def _make_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = _make_converter()
