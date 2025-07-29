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
            return "record"
        case _:
            return field["type"]
