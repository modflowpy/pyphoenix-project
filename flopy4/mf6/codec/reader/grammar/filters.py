from modflow_devtools.dfns.schema import Array, InputField, Keyword, Union


def valid_as_union(field: InputField, block_name: str | None = None) -> InputField:
    """Turn a ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    STEADY-STATE/TRANSIENT) into a keyword union with one arm per value, so
    it reuses the existing union grammar/dispatch instead of a second path.

    Whether the field's own name must precede the chosen value in real files
    (e.g. NPF's "ALTERNATIVE_CELL_AVERAGING LOGARITHMIC") or not (*-STO's
    bare "STEADY-STATE"/"TRANSIENT", no "STORAGE" prefix -- confirmed
    against a real fixture) is *not* reliably given by ``field.tagged`` for
    *-STO's ``storage`` specifically: it's synthesized by
    ``modflow_devtools``'s own DFN migration step from a pair of bare
    ``Keyword`` fields (see its ``_collapse_sto_keywords``), which builds the
    replacement ``String`` without setting ``tagged`` at all -- it silently
    picks up the class default (``True``) regardless of real syntax (tracked
    upstream: modflow-devtools todo.md, "STO's synthesized `storage` field
    defaults to tagged=True"). Every *other* real ``valid=``-restricted field
    checked in the current corpus (``rtype``, ``slntype``, ``scheme``,
    ``alternative_cell_averaging``, ``sorption``, ``thermal_formulation``,
    ``dry_tracking_method``, ``coordinate_check_method``, ``cell_averaging``,
    ``adv_scheme``) already has a correct ``tagged`` value straight from the
    real DFN source -- either explicitly declared (``rtype``/``slntype`` both
    have a literal ``tagged false`` line) or correctly defaulting to
    ``True`` when omitted (every OPTIONS-block one checked). ``storage`` is
    the only field in the current spec where the block-context heuristic
    below (PERIOD-block valid-restricted fields are bare per-step selectors,
    every other block's are prefixed options) actually overrides
    ``field.tagged`` -- so once the upstream fix lands, this heuristic can
    likely be dropped in favor of trusting ``field.tagged`` directly (kept
    for now since the installed ``modflow_devtools`` still has the bug).
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
