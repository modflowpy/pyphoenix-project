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

from modflow_devtools.dfn import Field

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
    patches = _OVERRIDES.get(dfn_name, {}).get(f["name"], {})
    # extra_children is consumed by extra_record_children(), not a Field attribute
    patches = {k: v for k, v in patches.items() if k != "extra_children"}
    if not patches:
        return f
    return {**f, **patches}


def extra_list_blocks(dfn_name: str) -> list[dict]:
    """Return extra list block definitions for a DFN missing from v2 TOML conversion.

    Used for list blocks dropped by dfn2toml (e.g. SSM's sources recarray, which
    has no dimensions block and is not captured in v2 TOML).  Each dict has keys:
    ``block``, ``dim``, and ``columns`` (list of column dicts with name/type/longname).
    """
    return list(
        _OVERRIDES.get("_package_extras", {}).get(dfn_name, {}).get("extra_list_blocks", [])
    )


def replace_list_fields(dfn_name: str) -> list[dict]:
    """Return path field definitions that replace a list block in a DFN.

    Used when a packagedata block has heterogeneous rows (e.g. prt-fmi's
    GWFHEAD/GWFBUDGET/GWFSPDIS rows) that are more naturally represented as
    individual Optional[Path] fields than as columnar arrays.  Each dict has
    keys: ``block``, ``name``, ``inout``, and ``longname``.
    """
    return list(
        _OVERRIDES.get("_package_extras", {}).get(dfn_name, {}).get("replace_list_fields", [])
    )


def replace_list_blocks(dfn_name: str) -> set[str]:
    """Return the set of block names whose list fields are replaced in this DFN."""
    return {entry["block"] for entry in replace_list_fields(dfn_name)}


def extra_period_fields(dfn_name: str) -> list[dict]:
    """Return embedded-keystring period field definitions for a DFN.

    Used for advanced packages (LAK, MAW, SFR) whose period block uses
    ``feature_num KEYWORD value`` rows rather than columnar arrays.  Each
    dict requires ``keyword`` and ``feature_dim``; ``prefix`` is optional
    (py_name is derived as ``{prefix}_{keyword.lower()}`` when set, else
    ``keyword.lower()``); ``dtype`` defaults to ``"double precision"``.
    """
    return list(
        _OVERRIDES.get("_package_extras", {}).get(dfn_name, {}).get("extra_period_fields", [])
    )


def extra_record_children(dfn_name: str, field_name: str) -> list[dict]:
    """Return extra child dicts to inject into an inner-class record.

    Used to flatten nested sub-records that are lost in the v2 TOML conversion
    (dfn2toml does not recurse into records-within-records).  Each dict has the
    same shape as a v2 child dict: name, type, optional, tagged, etc.
    """
    return list(_OVERRIDES.get(dfn_name, {}).get(field_name, {}).get("extra_children", []))


def block_dim_override(dfn_name: str, block_name: str) -> str | None:
    """Return an explicit dim name for a block, or None to use auto-resolution.

    Used when a DFN has no DIMENSIONS block but the correct dim comes from a
    coupled package (e.g. gwt-lkt/gwe-lke packagedata rows are indexed by
    nlakes from the paired gwf-lak).
    """
    key = f"{block_name}_dim"
    return _OVERRIDES.get("_package_extras", {}).get(dfn_name, {}).get(key)


def always_emit_blocks(dfn_name: str) -> list[str]:
    """Return block names that must be emitted even when no data is set.

    Used for blocks like SSM SOURCES that MF6 requires to be present in the
    input file even when empty (otherwise MF6 raises an error on read).
    """
    return list(
        _OVERRIDES.get("_package_extras", {}).get(dfn_name, {}).get("always_emit_blocks", [])
    )


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
