"""Rule names in the generated typed grammars.

A generated rule's name says how to read it, so the typed transformer
needs nothing but the parse tree. The name is a path of DFN names (a
field, or a record and its part, or a union and its arm), then one or more
kind tags, all joined by ``__``:

- ``val``: a value, or values (``optional_value__val``)
- ``kw``: a keyword, True when given (``print_input__kw``)
- ``arr``: a record part holding a list of values
- ``rec``: a record, read into a dict of its parts
- ``union``: a union, read as its arm's value, or a keyword arm's name
- ``elem``: one element of a list, which collects them
- ``hdr``: a block's record header (OBS's ``CONTINUOUS FILEOUT <file>``)
- ``block``, ``fields``: a block, and its contents

The last path segment is the name the value is read under. DFN names
never contain ``__``, so splitting on it is unambiguous.
"""

SEP = "__"
TAGS = frozenset({"val", "kw", "arr", "rec", "union", "elem", "hdr", "block", "fields"})


def to_rule_name(name: str) -> str:
    """Convert a DFN name to a valid Lark rule name (no hyphens)."""
    return name.replace("-", "_")


def rule_name(*path: str, tags: tuple[str, ...] = ()) -> str:
    """A rule's name from its DFN name path and kind tags."""
    for p in path:
        if SEP in p:
            raise ValueError(f"DFN name {p!r} contains {SEP!r}")
    if unknown := set(tags) - TAGS:
        raise ValueError(f"unknown rule tags: {sorted(unknown)}")
    return SEP.join([*(to_rule_name(p) for p in path), *tags])


def parse_rule_name(rule: str) -> tuple[str, frozenset[str]]:
    """A rule's name and kind tags, or its own name and no tags for a rule
    that isn't tagged (one of typed.lark's)."""
    parts = rule.split(SEP)
    tags = set()
    while len(parts) > 1 and parts[-1] in TAGS:
        tags.add(parts.pop())
    return parts[-1], frozenset(tags)
