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
    from modflow_devtools.dfns import LocalDfnRegistry

    if dfn_path is None:
        # The DFNs the generated classes came from, stored by sync.
        stored = Path(__file__).parents[2] / "dfns"
        if not stored.is_dir():
            raise FileNotFoundError(
                f"flopy4.mf6 has no stored DFNs ({stored}). Run `flopy4 mf6 sync` to re-sync."
            )
        dfn_path = str(stored)
    registry = LocalDfnRegistry(path=Path(dfn_path))
    return registry.spec(schema_version=_DFN_SCHEMA_VERSION).components


def get_component_dfn(name: str, dfn_path: str | Path | None = None) -> Component:
    """Look up a single component's DFN spec.

    Cached per ``(name, dfn_path)`` so repeated lookups (e.g. one per file of
    the same package type) don't reload the whole DFN registry each time.
    ``dfn_path`` defaults to the DFNs sync stored with the generated
    classes (``flopy4/mf6/dfns``).
    """
    return _components(str(dfn_path) if dfn_path is not None else None)[name]
