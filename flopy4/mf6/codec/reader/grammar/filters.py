from collections.abc import Mapping

from modflow_devtools.dfns.schema.v2 import FieldV2


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


def record_child_type(field: FieldV2 | dict) -> str:
    """
    Get the grammar type for a field within a record context.

    In records, string fields should use 'word' instead of 'string'
    to avoid consuming the rest of the line (since string matches token+ NEWLINE).

    Handles both FieldV2 objects and dicts (from nested children).
    """
    field_type = field.get("type") if isinstance(field, dict) else field.type
    match field_type:
        case "string":
            return "word"  # Use word for strings in records to match single tokens
        case t if t in ["double", "integer"]:
            return t
        case "keyword":
            return ""
        case "union":
            return ""  # unions generate their own union rules
        case _:
            return field_type or ""


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


def to_rule_name(name: str) -> str:
    """Convert a field name to a valid Lark rule name.

    Lark rule names must not contain hyphens, so we replace them with underscores.
    """
    return name.replace("-", "_")


def get_list_columns(field: FieldV2) -> list[dict] | None:
    """
    Extract column definitions from a list-type field.

    List fields have a nested structure:
        list_field (type=list)
          └── children[field_name] (type=record)
                └── children:
                      ├── col1 (type=string)
                      ├── col2 (type=string)
                      └── col3 (type=string)

    Returns a list of column dicts with 'name', 'type', and 'shape' keys,
    or None if the field doesn't have column definitions.
    """
    if field.type not in ("list", "recarray"):
        return None

    if not field.children:
        return None

    # The list's children should contain a record with the same name
    # that holds the actual column definitions
    record_child = field.children.get(field.name)
    if record_child is None:
        # Try first child if name doesn't match
        record_child = next(iter(field.children.values()), None)

    if record_child is None:
        return None

    # record_child may be a dict or a FieldV2
    if isinstance(record_child, dict):
        record_children = record_child.get("children", {})
    else:
        record_children = record_child.children or {}

    if not record_children:
        return None

    columns = []
    for col_name, col_data in record_children.items():
        if isinstance(col_data, dict):
            columns.append(
                {
                    "name": col_data.get("name", col_name),
                    "type": col_data.get("type", "string"),
                    "shape": col_data.get("shape"),
                }
            )
        else:
            columns.append(
                {
                    "name": getattr(col_data, "name", col_name),
                    "type": getattr(col_data, "type", "string"),
                    "shape": getattr(col_data, "shape", None),
                }
            )

    return columns if columns else None


def list_child_type(col: dict) -> str:
    """
    Get the grammar type for a column within a list record.

    Similar to record_child_type but works with column dicts.
    """
    col_type = col.get("type", "string")
    match col_type:
        case "string":
            return "word"
        case t if t in ["double", "integer"]:
            return t
        case "keyword":
            return ""
        case _:
            return col_type
