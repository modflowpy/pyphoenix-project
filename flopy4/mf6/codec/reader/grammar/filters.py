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
