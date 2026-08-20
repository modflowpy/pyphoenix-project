from json import dump as dump_json
from json import load as load_json
from pathlib import Path

from tomli import load as load_toml
from tomli_w import dump as dump_toml

try:
    from flopy4.mf6._contract import DFN_SCHEMA_VERSION, MF6_VERSION
except ImportError:
    DFN_SCHEMA_VERSION = "unknown"
    MF6_VERSION = "unknown"

# Import submodules to make them accessible via flopy4.mf6.*
from flopy4.mf6 import gwe, gwf, gwt, prt, simulation, solution, utils
from flopy4.mf6._compat import check_mf6_compatibility
from flopy4.mf6.codec import dump as dump_mf6
from flopy4.mf6.codec import load as load_mf6
from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter import structure, unstructure
from flopy4.mf6.ems import Ems
from flopy4.mf6.enums import NetCDFFormat
from flopy4.mf6.exchange import GwfGwe, GwfGwt
from flopy4.mf6.ims import Ims
from flopy4.mf6.netcdf import NetCDFModel
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.uio import DEFAULT_REGISTRY

__all__ = [
    "gwf",
    "gwt",
    "gwe",
    "prt",
    "simulation",
    "solution",
    "utils",
    "Ems",
    "NetCDFFormat",
    "GwfGwe",
    "GwfGwt",
    "Ims",
    "NetCDFModel",
    "Tdis",
    "Simulation",
    "MF6_VERSION",
    "DFN_SCHEMA_VERSION",
]


class WriteError(Exception):
    """An error occurred while writing a component."""

    pass


def _load_mf6(cls, path: Path, name: "str | None" = None) -> Component:
    """Load MF6 format file into a component instance.

    Mirrors Package.load()'s working pattern (same codec reader,
    structure_component) rather than the generic cattrs-based `structure()`
    below, which has no structure hook registered for the abstract
    `Component` base and isn't functional.

    `name`, if given, overrides xattree's default auto-assigned name (e.g.
    a namefile binding row's pname, threaded down by a parent's
    `_resolve_bindings` call when loading this component as a child).
    """
    from flopy4.mf6.converter.ingress.structure import structure_component

    with open(path, "r") as fp:
        raw = load_mf6(fp)
    instance = structure_component(raw, cls, workspace=path.parent, name=name)
    if isinstance(instance, Context):
        instance.workspace = path.parent
    instance.filename = path.name
    return instance


def _load_json(cls, path: Path, name: "str | None" = None) -> Component:
    """Load JSON format file into a component instance."""
    with open(path, "r") as fp:
        return structure(load_json(fp), path)


def _load_toml(cls, path: Path, name: "str | None" = None) -> Component:
    """Load TOML format file into a component instance."""
    with open(path, "rb") as fp:
        return structure(load_toml(fp), path)


def _write_mf6(component: Component, context=None, **kwargs) -> None:
    from flopy4.mf6.write_context import WriteContext

    # Use provided context or default
    ctx = context if context is not None else WriteContext.default()

    with open(component.path, "w") as fp:
        data = unstructure(component)
        try:
            dump_mf6(data, fp, context=ctx)
        except Exception as e:
            raise WriteError(
                f"Failed to write MF6 format file for component '{component.name}' "  # type: ignore
                f"of type {component.__class__.__name__}"
            ) from e


def _write_json(component: Component) -> None:
    with open(component.path, "w") as fp:
        data = unstructure(component)
        dump_json(data, fp, indent=4)


def _write_toml(component: Component) -> None:
    with open(component.path, "wb") as fp:
        data = unstructure(component)
        dump_toml(data, fp)


DEFAULT_REGISTRY.register_loader(Component, "mf6", _load_mf6)
DEFAULT_REGISTRY.register_loader(Component, "json", _load_json)
DEFAULT_REGISTRY.register_loader(Component, "toml", _load_toml)
DEFAULT_REGISTRY.register_writer(Component, "mf6", _write_mf6)
DEFAULT_REGISTRY.register_writer(Component, "json", _write_json)
DEFAULT_REGISTRY.register_writer(Component, "toml", _write_toml)

check_mf6_compatibility()
