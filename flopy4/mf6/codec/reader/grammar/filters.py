from modflow_devtools.dfns.schema import Array, InputField, Keyword, Union, split_bound


def valid_as_union(field: InputField) -> InputField:
    """Turn a ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    STEADY-STATE/TRANSIENT) into a keyword union with one arm per value, so
    it reuses the existing union grammar/dispatch instead of a second path.
    """
    valid = getattr(field, "valid", None)
    if not valid:
        return field
    return Union(
        name=field.name,
        tagged=field.tagged,
        arms={str(v): Keyword(name=str(v)) for v in valid},
    )


def field_type(field: InputField) -> str:
    if isinstance(field, Array):
        if not field.shape or any(split_bound(s)[0] for s in field.shape):
            return f"{'word' if field.dtype == 'string' else field.dtype}+"
        return "array"
    if isinstance(field, Keyword):
        return ""
    if isinstance(field, Union):
        return ""
    return field.type


def record_child_type(field: InputField) -> str:
    """Get the grammar type for a field within a record context."""
    if field.type == "string":
        return "word"  # Use word for strings in records to match single tokens
    if field.type in ("double", "integer"):
        return field.type
    if isinstance(field, Keyword):
        return ""
    if isinstance(field, Union):
        return ""
    return field.type


def get_recarray_name(block_name: str) -> str:
    """Get the name for a recarray representing period data in a block."""
    # Use similar naming to V1: stress_period_data, perioddata, etc.
    if block_name == "period":
        return "stress_period_data"
    return f"{block_name}data"


def to_rule_name(name: str) -> str:
    """Convert a field name to a valid Lark rule name."""
    # Lark rule names must not contain hyphens
    return name.replace("-", "_")
