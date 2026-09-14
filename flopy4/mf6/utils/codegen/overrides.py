"""
Local DFN field overrides pending upstream modflow6 repository PRs.

Overrides are stored in ``dfn_overrides.toml`` alongside this module.
Each entry patches specific ``FieldV2`` attributes for a named field in a
named DFN.  When the corresponding upstream PR merges and the DFN is
re-fetched, remove the entry.

Format (dfn_overrides.toml)::

    ["gwf-ic".strt]
    # strt should default to 1.0; see modflow6 PR #NNNN
    default = 1.0

Usage::

    from flopy4.mf6.utils.codegen.overrides import apply
    patched_field = apply("gwf-ic", field)
"""

import tomllib
from pathlib import Path
from typing import TypeVar

from modflow_devtools.dfns.schema import InputFieldBase

_OVERRIDES_PATH = Path(__file__).parent / "dfn_overrides.toml"

FieldT = TypeVar("FieldT", bound=InputFieldBase)


def _load() -> dict[str, dict[str, dict]]:
    if not _OVERRIDES_PATH.exists():
        return {}
    with _OVERRIDES_PATH.open("rb") as f:
        return tomllib.load(f)


_OVERRIDES: dict[str, dict[str, dict]] = _load()


def apply(dfn_name: str, f: FieldT) -> FieldT:
    """Return ``f`` with any registered overrides applied.

    Parameters
    ----------
    dfn_name :
        DFN identifier, e.g. ``"gwf-ic"``.
    f :
        The pydantic field (dev3 Scalar/Array/Record/Union/List instance) to patch.

    Returns
    -------
    FieldT
        The original field if no overrides exist, otherwise a copy with the
        patched attributes (``model_copy(update=...)``).
    """
    patches = _OVERRIDES.get(dfn_name, {}).get(f.name, {})
    if not patches:
        return f
    return f.model_copy(update=patches)
