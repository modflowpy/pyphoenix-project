from importlib import import_module
from json import dump as dump_json
from json import load as load_json
from pathlib import Path
from typing import TYPE_CHECKING

from tomli import load as load_toml
from tomli_w import dump as dump_toml

try:
    from flopy4.mf6._contract import DFN_SCHEMA_VERSION, MF6_VERSION
except ImportError:
    DFN_SCHEMA_VERSION = "unknown"
    MF6_VERSION = "unknown"

# Nothing imported eagerly here may import a generated module, so
# `flopy4 mf6 sync` still runs when the generated classes are broken
# or out of date. Generated components load on first use (__getattr__).
from flopy4.mf6 import solution, utils
from flopy4.mf6._sync import SyncError, SyncResult, sync
from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.codec import dump as dump_mf6
from flopy4.mf6.codec import load as load_mf6
from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter import structure, unstructure
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.netcdf import NetCDFModel
from flopy4.uio import DEFAULT_REGISTRY

if TYPE_CHECKING:
    from flopy4.mf6 import ems as ems
    from flopy4.mf6 import exg, gwe, gwf, gwt, prt, simulation
    from flopy4.mf6 import ims as ims
    from flopy4.mf6 import tdis as tdis
    from flopy4.mf6 import utl as utl
    from flopy4.mf6.ems import Ems
    from flopy4.mf6.ims import Ims
    from flopy4.mf6.simulation import Simulation
    from flopy4.mf6.tdis import Tdis

# Modules holding the generated components. Importing them all
# registers every component class (see FNAMES in component.py).
_COMPONENT_MODULES = ("exg", "gwe", "gwf", "gwt", "prt", "utl", "simulation", "ems", "ims", "tdis")

# Lazy attributes: name -> (module, attribute or None for the module).
_LAZY = {
    **{m: (m, None) for m in _COMPONENT_MODULES},
    "Ems": ("ems", "Ems"),
    "Ims": ("ims", "Ims"),
    "Simulation": ("simulation", "Simulation"),
    "Tdis": ("tdis", "Tdis"),
}


def _import_components() -> None:
    """Import every generated component module."""
    for name in _COMPONENT_MODULES:
        import_module(f"{__name__}.{name}")


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _import_components()
    module, attr = _LAZY[name]
    value = import_module(f"{__name__}.{module}")
    if attr is not None:
        value = getattr(value, attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "exg",
    "gwf",
    "gwt",
    "gwe",
    "prt",
    "simulation",
    "solution",
    "utils",
    "Ems",
    "NetCDFFormat",
    "Ims",
    "LoadContext",
    "NetCDFModel",
    "Tdis",
    "Simulation",
    "TimeArraySeriesRef",
    "MF6_VERSION",
    "DFN_SCHEMA_VERSION",
    "sync",
    "SyncResult",
    "SyncError",
]


class WriteError(Exception):
    """An error occurred while writing a component."""

    pass


def _load_mf6(
    cls, path: Path, name: "str | None" = None, context: LoadContext | None = None
) -> Component:
    from flopy4.mf6.converter.ingress.structure import structure_component

    path = Path(path)
    context = context or LoadContext(workspace=path.parent)
    assert context.workspace is not None
    with open(path, "r") as fp:
        raw = load_mf6(fp)
    instance = structure_component(raw, cls, context=context, name=name)
    if isinstance(instance, Context):
        instance.workspace = context.workspace
    # The file's path as an input file would name it, relative to the
    # simulation directory (gwf/m.nam).
    try:
        instance.filename = path.absolute().relative_to(context.workspace.absolute())
    except ValueError:
        instance.filename = path
    return instance


def _load_json(cls, path: Path, name: "str | None" = None, context=None) -> Component:
    with open(path, "r") as fp:
        return structure(load_json(fp), path)


def _load_toml(cls, path: Path, name: "str | None" = None, context=None) -> Component:
    with open(path, "rb") as fp:
        return structure(load_toml(fp), path)


def _open_for_write(component: Component, mode: str = "w"):
    # a model's files can be in a subdirectory of the simulation workspace
    component.path.parent.mkdir(parents=True, exist_ok=True)
    return open(component.path, mode)


def _write_mf6(component: Component, context=None, **kwargs) -> None:
    from flopy4.mf6.write_context import WriteContext

    ctx = context if context is not None else WriteContext.default()

    with _open_for_write(component) as fp:
        data = unstructure(component)
        try:
            dump_mf6(data, fp, context=ctx)
        except Exception as e:
            raise WriteError(
                f"Failed to write MF6 format file for component '{component.name}' "  # type: ignore
                f"of type {component.__class__.__name__}"
            ) from e


def _write_json(component: Component) -> None:
    with _open_for_write(component) as fp:
        data = unstructure(component)
        dump_json(data, fp, indent=4)


def _write_toml(component: Component) -> None:
    with _open_for_write(component, "wb") as fp:
        data = unstructure(component)
        dump_toml(data, fp)


DEFAULT_REGISTRY.register_loader(Component, "mf6", _load_mf6)
DEFAULT_REGISTRY.register_loader(Component, "json", _load_json)
DEFAULT_REGISTRY.register_loader(Component, "toml", _load_toml)
DEFAULT_REGISTRY.register_writer(Component, "mf6", _write_mf6)
DEFAULT_REGISTRY.register_writer(Component, "json", _write_json)
DEFAULT_REGISTRY.register_writer(Component, "toml", _write_toml)
