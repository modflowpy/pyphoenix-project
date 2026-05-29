from collections.abc import Mapping

from modflow_devtools.dfn.schema import Field


def field_type(field: Field) -> str:
    match field["type"]:
        case t if t in ["string", "integer", "double"] and field.get("shape", None):
            if "period" in field["block"]:
                return "list"
            return "array"
        case "keyword":
            return ""
        case "union":
            return ""  # keystrings generate their own union rules
        case _:
            return field["type"]


def record_child_type(field: Field) -> str:
    """
    Get the grammar type for a field within a record context.

    In records, string fields should use 'word' instead of 'string'
    to avoid consuming the rest of the line (since string matches token+ NEWLINE).
    """
    match field["type"]:
        case "string":
            return "word"  # Use word for strings in records to match single tokens
        case t if t in ["double", "integer"]:
            return t
        case "keyword":
            return ""
        case "union":
            return ""  # unions generate their own union rules
        case _:
            return field["type"]


def is_period_list_field(field: Field) -> bool:
    """Check if a field is part of a period block list/recarray."""
    if not field.get("shape", None) or not field.get("block", None):
        return False
    return (
        "period" in field["block"]
        and field["type"] in ["string", "integer", "double"]
        and field["shape"] is not None
    )


def group_period_fields(block_fields: Mapping[str, Field]) -> dict[str, list[str]]:
    """
    Group period block fields that should be combined into a single list.

    Returns a dict mapping the first field name to a list of all field names
    in the group. Fields are grouped if they share similar shapes (same base
    dimensions like nper, nnodes).
    """
    period_fields = {
        name: field for name, field in block_fields.items() if is_period_list_field(field)
    }

    if not period_fields:
        return {}

    # All period fields in the same block should be combined into one recarray
    # Return a single group with all field names
    field_names = list(period_fields.keys())
    if field_names:
        return {field_names[0]: field_names}
    return {}


def get_recarray_name(block_name: str) -> str:
    """Get the name for a recarray representing period data in a block."""
    # Use similar naming to V1: stress_period_data, perioddata, etc.
    if block_name == "period":
        return "stress_period_data"
    return f"{block_name}data"


def to_rule_name(name: str) -> str:
    """Convert a field name to a valid Lark rule name.

    Lark rule names must not contain hyphens, so we replace them with underscores.
    """
    return name.replace("-", "_")
