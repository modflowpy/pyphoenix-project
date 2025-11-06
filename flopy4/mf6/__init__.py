from json import dump as dump_json
from json import load as load_json
from pathlib import Path

from tomli import load as load_toml
from tomli_w import dump as dump_toml

# Import submodules to make them accessible via flopy4.mf6.*
from flopy4.mf6 import gwf, simulation, solution, utils
from flopy4.mf6.codec import dump as dump_mf6
from flopy4.mf6.codec import load as load_mf6
from flopy4.mf6.component import Component
from flopy4.mf6.converter import structure, unstructure
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.uio import DEFAULT_REGISTRY

__all__ = ["gwf", "simulation", "solution", "utils", "Ims", "Tdis", "Simulation"]


class WriteError(Exception):
    """An error occurred while writing a component."""

    pass


def _load_mf6(path: Path) -> Component:
    with open(path, "r") as fp:
        return structure(load_mf6(fp), path)


def _load_json(path: Path) -> Component:
    with open(path, "r") as fp:
        return structure(load_json(fp), path)


def _load_toml(path: Path) -> Component:
    with open(path, "rb") as fp:
        return structure(load_toml(fp), path)


def _write_mf6(component: Component) -> None:
    with open(component.path, "w") as fp:
        data = unstructure(component)
        try:
            dump_mf6(data, fp)
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
