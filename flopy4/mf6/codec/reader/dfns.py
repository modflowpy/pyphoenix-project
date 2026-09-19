"""Cached DFN component lookups for the reader.

Kept separate from ``flopy4.mf6.utils.codegen`` (which loads DFNs to
*generate* Python classes) -- this is for a *running* typed reader that
needs the ``Component`` spec matching a given generated class's ``dfn_name``.
"""

from functools import lru_cache
from pathlib import Path

from modflow_devtools.dfns.schema import Component

_DFN_SCHEMA_VERSION = "2.0.0.dev3"


@lru_cache(maxsize=None)
def _components(dfn_path: str | None) -> dict[str, Component]:
    from modflow_devtools.dfns import LocalDfnRegistry, RemoteDfnRegistry

    if dfn_path is not None:
        registry = LocalDfnRegistry(path=Path(dfn_path))
    else:
        from flopy4.mf6._contract import MF6_VERSION

        registry = RemoteDfnRegistry(release_id=f"MODFLOW-ORG/modflow6@{MF6_VERSION}")
    return registry.spec(schema_version=_DFN_SCHEMA_VERSION).components


def get_component_dfn(name: str, dfn_path: str | Path | None = None) -> Component:
    """Look up a single component's DFN spec.

    Cached per ``(name, dfn_path)`` so repeated lookups (e.g. one per file of
    the same package type) don't reload the whole DFN registry each time.
    ``dfn_path`` defaults to the release recorded in ``_contract.py`` (a
    network fetch); tests should pass the local ``dfn_path`` fixture instead.
    """
    return _components(str(dfn_path) if dfn_path is not None else None)[name]
