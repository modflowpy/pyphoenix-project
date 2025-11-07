from pathlib import Path
from typing import Any

import cattr
import xattree
from cattr import Converter
from cattrs.gen import make_hetero_tuple_unstructure_fn

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter.structure import structure_array, structure_keyword
from flopy4.mf6.converter.unstructure import (
    unstructure_component,
)
from flopy4.mf6.gwf.oc import Oc

__all__ = [
    "structure",
    "unstructure",
    "structure_array",
    "unstructure_array",
    "structure_keyword",
    "COMPONENT_CONVERTER",
]


def _make_converter() -> Converter:
    converter = Converter(unstruct_strat=cattr.UnstructureStrategy.AS_TUPLE)
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    converter.register_unstructure_hook(
        Oc.PrintSaveSetting, make_hetero_tuple_unstructure_fn(Oc.PrintSaveSetting, converter)
    )
    converter.register_unstructure_hook(
        Oc.Steps, make_hetero_tuple_unstructure_fn(Oc.Steps, converter)
    )
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
