from modflow_devtools.dfns.schema import Array, InputField, Keyword, Union


def valid_as_union(field: InputField) -> InputField:
    """Turn a ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    STEADY-STATE/TRANSIENT) into a keyword union with one arm per value, so
    it reuses the existing union grammar/dispatch instead of a second path.

    Trusts ``field.tagged`` directly for whether the field's own name must
    precede the chosen value in real files (e.g. NPF's
    "ALTERNATIVE_CELL_AVERAGING LOGARITHMIC") or not (*-STO's bare
    "STEADY-STATE"/"TRANSIENT", no "STORAGE" prefix). This previously needed
    a PERIOD-block-vs-not heuristic instead, because *-STO's ``storage`` is
    synthesized by ``modflow_devtools``'s DFN migration (``_collapse_sto_keywords``)
    without setting ``tagged``, silently defaulting to ``True`` regardless of
    real syntax. Fixed upstream (modflow-devtools#tagged-sto-storage,
    ``migrate_to_v2_0_0_dev2.py``'s ``_collapse_sto_keywords`` now passes
    ``tagged=False``) -- confirmed every other real ``valid=``-restricted
    field already had a correct ``tagged`` value from the DFN source, so
    ``storage`` was the only case the heuristic was covering.
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
