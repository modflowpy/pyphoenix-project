from modflow_devtools.dfns.schema import Array, InputField, Keyword, Union


def valid_as_union(field: InputField) -> InputField:
    """Normalize a ``valid=``-constrained scalar into a synthetic keyword union.

    A ``String``/``Integer`` field restricted to a fixed set of literal
    values (e.g. STO's ``storage`` field: one of ``STEADY-STATE``/
    ``TRANSIENT``) is, for grammar/transform purposes, structurally
    identical to a keystring union of ``Keyword`` arms -- even though the
    dev3 schema doesn't model it as a real ``Union``. Reuses the existing
    dispatch-by-rule-name union machinery instead of adding a second,
    parallel mechanism just for this case.
    """
    valid = getattr(field, "valid", None)
    if not valid:
        return field
    return Union(name=field.name, arms={str(v): Keyword(name=str(v)) for v in valid})


def field_type(field: InputField) -> str:
    if isinstance(field, Array):
        return "array"
    if isinstance(field, Keyword):
        return ""
    if isinstance(field, Union):
        return ""  # keystrings generate their own union rules
    return field.type


def record_child_type(field: InputField) -> str:
    """
    Get the grammar type for a field within a record context.

    In records, string fields should use 'word' instead of 'string'
    to avoid consuming the rest of the line (since string matches token+ NEWLINE).
    """
    if field.type == "string":
        return "word"  # Use word for strings in records to match single tokens
    if field.type in ("double", "integer"):
        return field.type
    if isinstance(field, Keyword):
        return ""
    if isinstance(field, Union):
        return ""  # unions generate their own union rules
    return field.type


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
