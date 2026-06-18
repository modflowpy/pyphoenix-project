from pathlib import Path
from typing import Any

import cattr
import xattree
from cattr import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter.egress.unstructure import (
    _unstructure_codegen_v2,
    is_codegen_v2,
    unstructure_component,
)
from flopy4.mf6.converter.ingress.structure import (
    structure_array,
    structure_component,
    structure_keyword,
)

__all__ = [
    "structure",
    "unstructure",
    "structure_array",
    "structure_component",
    "unstructure_array",
    "structure_keyword",
    "COMPONENT_CONVERTER",
]


def _make_converter() -> Converter:
    converter = Converter(unstruct_strat=cattr.UnstructureStrategy.AS_TUPLE)
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    # codegen v2 registered last → checked first (LIFO), overrides xattree.has for new packages
    converter.register_unstructure_hook_factory(is_codegen_v2, lambda _: _unstructure_codegen_v2)
    return converter


COMPONENT_CONVERTER = _make_converter()


def structure(data: dict[str, Any], path: Path) -> Component:
    component = COMPONENT_CONVERTER.structure(data, Component)
    if isinstance(component, Context):
        component.workspace = path.parent
    component.filename = path.name
    return component


def unstructure(component: Component) -> dict[str, Any]:
    return COMPONENT_CONVERTER.unstructure(component)
