from modflow_devtools.dfn import Field


def field_type(field: Field) -> str:
    match field["type"]:
        case t if t in ["string", "integer", "double precision"] and "shape" in field:
            if "period" in field["block"]:
                return "list"
            return "array"
        case "keyword":
            return ""
        case "keystring":
            return ""  # keystrings generate their own union rules
        case _:
            return field["type"]


def record_child_type(field: Field) -> str:
    """Get the grammar type for a field within a record context."""
    match field["type"]:
        case "string":
            return "string"
        case "integer":
            return "integer"
        case "double precision":
            return "double"
        case "keyword":
            return ""
        case "keystring":
            return ""  # keystrings generate their own union rules
        case _:
            return field["type"]


def keystring_children(field: Field) -> dict:
    """Get the children of a keystring field for union generation."""
    if field["type"] != "keystring":
        return {}
    return field.get("children", {})
