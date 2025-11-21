"""
Extract record column mappings from generated grammar files.

This module parses the generated Lark grammar files to extract column names
for structured list records. The grammars contain rules like:

    models_record: mtype mfname mname NEWLINE
    solutiongroup_record: slntype slnfname slnmnames+ NEWLINE

From this, we extract column info including whether columns are variadic
(indicated by + or * quantifiers in the grammar).

The mapping is built at import time and cached, so there's no per-call overhead.
This approach uses the grammar as the source of truth - the same artifact used
for parsing - rather than duplicating information elsewhere.

Note: Only certain blocks (like simulation-level bindings) return column names.
Other blocks (like perioddata) continue to return list-of-lists format until
the structuring code is updated to handle dict records.
"""

import re
from pathlib import Path
from typing import NamedTuple


class ColumnInfo(NamedTuple):
    """Information about a record column."""

    name: str
    variadic: bool = False  # True if column accepts multiple values (+ or *)


# Cached mapping of block_name -> column info
_RECORD_COLUMNS: dict[str, list[ColumnInfo]] | None = None

# Blocks that should return dict records (binding blocks).
# Other blocks return list records for backward compatibility.
_DICT_RECORD_BLOCKS = frozenset(
    {
        "models",
        "exchanges",
        "solutiongroup",
        "packages",  # model-level package bindings
    }
)


def _parse_record_columns() -> dict[str, list[ColumnInfo]]:
    """
    Parse all generated grammar files to extract record column mappings.

    Looks for rules matching the pattern:
        block_record: col1 col2 col3+ NEWLINE

    The + or * quantifier indicates a variadic column that accepts multiple values.

    Returns
    -------
    dict[str, list[ColumnInfo]]
        Mapping of block name (e.g., "models") to column info
        (e.g., [ColumnInfo("mtype"), ColumnInfo("mfname"), ColumnInfo("mname")])
    """
    grammar_dir = Path(__file__).parent / "generated"
    columns: dict[str, list[ColumnInfo]] = {}

    if not grammar_dir.exists():
        return columns

    # Pattern matches: rule_record: col1 col2 col3+ NEWLINE
    # Group 1: rule name (e.g., "models_record")
    # Group 2: column definitions (e.g., "mtype mfname mname")
    record_pattern = re.compile(r"^(\w+_record):\s+(.+?)\s+NEWLINE", re.MULTILINE)

    for grammar_file in grammar_dir.glob("*.lark"):
        content = grammar_file.read_text()
        for match in record_pattern.finditer(content):
            rule_name = match.group(1)  # e.g., "models_record"
            body = match.group(2)  # e.g., "mtype mfname mname"

            # Extract column info, detecting variadic columns (+ or *)
            cols: list[ColumnInfo] = []
            for col in body.split():
                col = col.strip()
                variadic = col.endswith("+") or col.endswith("*")
                name = re.sub(r"[+*?]$", "", col)
                cols.append(ColumnInfo(name=name, variadic=variadic))

            # Remove "_record" suffix to get block name
            block_name = rule_name[:-7]  # "models_record" -> "models"
            columns[block_name] = cols

    return columns


def get_record_columns(block_name: str, dict_only: bool = True) -> list[ColumnInfo] | None:
    """
    Get column info for a structured record rule.

    Parameters
    ----------
    block_name : str
        Name of the block (e.g., "models", "exchanges", "solutiongroup")
    dict_only : bool, default True
        If True, only return columns for blocks in _DICT_RECORD_BLOCKS.
        If False, return columns for all blocks with record rules.

    Returns
    -------
    list[ColumnInfo] | None
        List of column info in order, or None if not found/not enabled.
        Each ColumnInfo has `name` and `variadic` attributes.
    """
    global _RECORD_COLUMNS
    if _RECORD_COLUMNS is None:
        _RECORD_COLUMNS = _parse_record_columns()

    # Only return columns for blocks that should produce dict records
    if dict_only and block_name not in _DICT_RECORD_BLOCKS:
        return None

    return _RECORD_COLUMNS.get(block_name)


def get_all_record_columns() -> dict[str, list[ColumnInfo]]:
    """
    Get all record column mappings.

    Returns
    -------
    dict[str, list[ColumnInfo]]
        Complete mapping of block names to column info
    """
    global _RECORD_COLUMNS
    if _RECORD_COLUMNS is None:
        _RECORD_COLUMNS = _parse_record_columns()
    return dict(_RECORD_COLUMNS)
