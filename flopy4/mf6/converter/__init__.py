from pathlib import Path
from typing import Any

import cattr
from cattr import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter.egress.unstructure import (
    unstructure_component,
)
from flopy4.mf6.converter.ingress.structure import (
    structure_component,
)

__all__ = [
    "structure",
    "unstructure",
    "structure_component",
    "COMPONENT_CONVERTER",
]


def _make_converter() -> Converter:
    converter = Converter(unstruct_strat=cattr.UnstructureStrategy.AS_TUPLE)
    converter.register_unstructure_hook(Component, unstructure_component)
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
