from collections.abc import Mapping

from modflow_devtools.dfn.schema.v2 import FieldV2


def field_type(field: FieldV2) -> str:
    match field.type:
        case t if t in ["string", "integer", "double"] and field.shape:
            if "period" in field.block:
                return "list"
            return "array"
        case "keyword":
            return ""
        case "union":
            return ""  # keystrings generate their own union rules
        case _:
            return field.type


def record_child_type(field: FieldV2) -> str:
    """Get the grammar type for a field within a record context."""
    match field.type:
        case t if t in ["string", "double", "integer"]:
            return t
        case "keyword":
            return ""
        case "union":
            return ""  # keystrings generate their own union rules
        case _:
            return field.type


def keystring_children(field: FieldV2) -> dict:
    """Get the children of a keystring field for union generation."""
    return {} if field.type != "union" else field.children


def is_period_list_field(field: FieldV2) -> bool:
    """Check if a field is part of a period block list/recarray."""
    if not field.shape or not field.block:
        return False
    return (
        "period" in field.block
        and field.type in ["string", "integer", "double"]
        and field.shape is not None
    )


def group_period_fields(block_fields: Mapping[str, FieldV2]) -> dict[str, list[str]]:
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


def get_recarray_columns(
    field_names: list[str], block_fields: Mapping[str, FieldV2]
) -> list[tuple[str, bool]]:
    """
    Get column names for a recarray with optionality info.

    Returns list of (column_name, is_optional) tuples like:
    [('cellid', False), ('q', False), ('aux', True), ('boundname', True)]
    """
    columns = []

    # Check if any field has spatial dimensions (indicates cellid is needed)
    has_spatial = False
    for name in field_names:
        field = block_fields[name]
        if field.shape and any(
            dim in field.shape for dim in ["nnodes", "ncells", "nlay", "nrow", "ncol"]
        ):
            has_spatial = True
            break

    if has_spatial:
        columns.append(("cellid", False))  # cellid is always required

    # Add the field names as columns with their optionality
    for name in field_names:
        field = block_fields[name]
        is_optional = getattr(field, "optional", False)
        columns.append((name, is_optional))

    return columns


def get_all_grouped_field_names(blocks: Mapping[str, Mapping[str, FieldV2]]) -> set[str]:
    """
    Get all field names that are grouped into recarrays across all blocks.

    Returns a set of field names that should not have individual rules generated.
    """
    grouped = set()
    for block_fields in blocks.values():
        period_groups = group_period_fields(block_fields)
        for field_list in period_groups.values():
            grouped.update(field_list)
    return grouped
