from modflow_devtools.dfns.schema import Array, InputField, Keyword, Union


def valid_as_union(field: InputField, block_name: str | None = None) -> InputField:
    """Turn a ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    STEADY-STATE/TRANSIENT) into a keyword union with one arm per value, so
    it reuses the existing union grammar/dispatch instead of a second path.

    Whether the field's own name must precede the chosen value in real files
    (e.g. NPF's "ALTERNATIVE_CELL_AVERAGING LOGARITHMIC") or not (STO's bare
    "STEADY-STATE"/"TRANSIENT", no "STORAGE" prefix -- confirmed against a
    real fixture) is *not* reliably given by ``field.tagged``: several of
    these fields (including STO's ``storage``) are synthesized by
    ``modflow_devtools``'s own DFN migration step from a pair of bare
    ``Keyword`` fields (see its ``_collapse_sto_keywords``), which builds the
    replacement ``String`` without setting ``tagged`` at all -- it silently
    picks up the class default (``True``) regardless of real syntax. Real
    per-block-field DFN entries never declare ``tagged`` for these fields
    either, so there's no upstream signal to trust either way. The one
    correlation confirmed across every case checked in the real corpus:
    PERIOD-block valid-restricted fields are bare per-step selectors (like
    the record-level keystrings, e.g. OC's ocsetting), while every other
    block's valid-restricted fields are prefixed options -- so block context,
    not ``field.tagged``, decides.
    """
    valid = getattr(field, "valid", None)
    if not valid:
        return field
    return Union(
        name=field.name,
        tagged=block_name != "period",
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
