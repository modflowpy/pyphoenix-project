from modflow_devtools.dfns.schema import (
    Array,
    InputField,
    Keyword,
    Record,
    String,
    Union,
    split_bound,
)


def valid_as_union(field: InputField) -> InputField:
    """Turn a ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    STEADY-STATE/TRANSIENT) into a keyword union with one arm per value, so
    it reuses the existing union grammar/dispatch instead of a second path.
    A union never begins with its own name, so whether a tagged scalar's
    name precedes the value is up to the caller (see ``union_field``).
    """
    valid = getattr(field, "valid", None)
    if not valid:
        return field
    return Union(name=field.name, arms={str(v): Keyword(name=str(v)) for v in valid})


def keyword_literal(field: InputField) -> str:
    """A field's keyword as a case-insensitive literal, or an alternation
    if MF6 accepts other spellings (utl-ts's NAMES or NAME)."""
    names = [field.name, *getattr(field, "aliases", [])]
    literals = " | ".join(f'"{n}"i' for n in names)
    return literals if len(names) == 1 else f"({literals})"


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


def is_dynamically_named_array(field: InputField) -> bool:
    if not isinstance(field, Record) or len(field.fields or {}) < 2:
        return False
    first, *_, last = field.fields.values()
    return (
        isinstance(first, String)
        and not first.tagged
        and first.fk is not None
        and isinstance(last, Array)
        and not last.tagged
        and field_type(last) == "array"
    )


def record_child_type(field: InputField) -> str:
    """Get the grammar type for a field within a record context."""
    if field.type == "string":
        return "word"  # Use word for strings in records to match single tokens
    if field.type in ("double", "integer"):
        return field.type
    if isinstance(field, Array):
        return f"{'word' if field.dtype == 'string' else field.dtype}+"
    if isinstance(field, Keyword):
        return ""
    if isinstance(field, Union):
        return ""
    return field.type


def part_tag(field: InputField) -> str:
    """The kind tag of a record part's or union arm's rule (see grammar.names)."""
    if isinstance(field, Keyword):
        return "kw"
    if isinstance(field, Union):
        return "union"
    if isinstance(field, Record):
        return "rec"
    if isinstance(field, Array):
        return "arr"
    return "val"


def get_recarray_name(block_name: str) -> str:
    """Get the name for a recarray representing period data in a block."""
    # Use similar naming to V1: stress_period_data, perioddata, etc.
    if block_name == "period":
        return "stress_period_data"
    return f"{block_name}data"
