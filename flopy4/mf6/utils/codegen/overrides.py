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

import dataclasses
import tomllib
from pathlib import Path

from modflow_devtools.dfns.schema.field import Field

_OVERRIDES_PATH = Path(__file__).parent / "dfn_overrides.toml"


def _load() -> dict[str, dict[str, dict]]:
    if not _OVERRIDES_PATH.exists():
        return {}
    with _OVERRIDES_PATH.open("rb") as f:
        return tomllib.load(f)


_OVERRIDES: dict[str, dict[str, dict]] = _load()


def apply(dfn_name: str, f: Field) -> Field:
    """Return ``f`` with any registered overrides applied.

    Parameters
    ----------
    dfn_name :
        DFN identifier, e.g. ``"gwf-ic"``.
    f :
        The field to patch.

    Returns
    -------
    Field
        The original field if no overrides exist, otherwise a new
        dataclass instance with the patched attributes.
    """
    patches = _OVERRIDES.get(dfn_name, {}).get(f.name, {})
    # extra_children is consumed by extra_record_children(), not a Field attribute
    patches = {k: v for k, v in patches.items() if k != "extra_children"}
    if not patches:
        return f
    return dataclasses.replace(f, **patches)


def extra_record_children(dfn_name: str, field_name: str) -> list[dict]:
    """Return extra child dicts to inject into an inner-class record.

    Used to flatten nested sub-records that are lost in the v2 TOML conversion
    (dfn2toml does not recurse into records-within-records).  Each dict has the
    same shape as a v2 child dict: name, type, optional, tagged, etc.
    """
    return list(_OVERRIDES.get(dfn_name, {}).get(field_name, {}).get("extra_children", []))


def apply_to_child(dfn_name: str, child: dict) -> dict:
    """Return ``child`` dict with any registered overrides applied.

    Used for record child dicts, which are plain dicts rather than Field
    objects.  Looks up by the child's ``name`` key using the same override
    table as :func:`apply`.

    Parameters
    ----------
    dfn_name :
        DFN identifier, e.g. ``"gwf-npf"``.
    child :
        A record child dict from the v2 TOML schema.

    Returns
    -------
    dict
        The original dict if no overrides exist, otherwise a shallow-merged
        copy with the patched keys.
    """
    patches = _OVERRIDES.get(dfn_name, {}).get(child.get("name", ""), {})
    if not patches:
        return child
    return {**child, **patches}
