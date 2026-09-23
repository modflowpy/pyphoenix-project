"""
Pydantic prototype: does `flopy4/mf6/record.py`/`item.py` (the `Record`/
`Item` row-type subsystem `Chd.StressPeriodData`, `Oc.Headprint`, etc. are
generated from) need to migrate off attrs at all, and if it does, can it
target a pydantic dataclass -- the same target
`pydantic_dis_prototype.py`/`pydantic_chd_prototype.py` chose for
`Component`/`Package` -- or does it need something else (plain stdlib
`dataclasses.dataclass`)?

Answers, both confirmed by running this file:

1. Record/Item's own mechanics (`to_tokens`/`from_tokens`, a metadata-
   driven field walk) use NO attrs-specific validation/conversion feature
   -- no `attrs.field(validator=...)` or `converter=` is ever declared on
   a Record/Item field in the real codebase (grepped: `converter=` only
   appears on `Component`/`Package`-level fields, e.g. `Gwf.dis`'s
   `convert_grid`). `_coerce()` does its own manual, explicit coercion,
   called directly from `from_tokens()` -- not wired through attrs at all.
   So nothing here *requires* attrs specifically.

2. BUT one real behavior IS load-bearing and attrs-specific: `_nested_class()`
   (record.py) exists because a composed/nested record field (e.g.
   `Oc.Headprint.fmt: "Oc.Format"`) is declared with a STRING type
   annotation naming a SIBLING class inside the same enclosing class --
   unresolvable via any module-global lookup at class-body-execution time
   (Python class bodies can't see sibling names in an enclosing class's
   scope), so attrs' default behavior of leaving `f.type` as the literal,
   unevaluated string is exactly what makes this possible: resolution is
   deferred to `_nested_class()`, called lazily, well after the whole
   module (and all its sibling classes) has finished loading.

   Confirmed here: this is NOT an attrs-specific behavior -- plain stdlib
   `dataclasses.dataclass` does the exact same thing (`dataclasses.fields
   (cls)[i].type` is *also* just the raw, unevaluated string) since it's a
   property of how Python stores string-literal annotations, not of
   attrs. A straight, mechanical port of `Record`'s current shape to a
   stdlib dataclass needs zero changes to `_nested_class()`.

   Pydantic dataclasses behave differently, but not in the way a first
   guess would suggest ("eager resolution breaks forward refs"): pydantic
   defers schema-building for an unresolvable annotation
   (`cls.__pydantic_complete__` is `False` right after decoration) and
   resolves it LAZILY -- confirmed: constructing an instance with no
   explicit fixup call at all just works, self-healing on first use, via
   the same effective mechanism `typing.get_type_hints()` uses (`eval()`
   against the defining module's globals plus qualified attribute access,
   e.g. `eval("Oc.Format", sys.modules[cls.__module__].__dict__)` --
   which succeeds once `Oc.Format` exists as a real attribute of `Oc`,
   regardless of whether `Headprint` or `Format` was defined first in the
   source). The ONE real gap: something that inspects `cls.__pydantic_
   fields__` BEFORE any instance is ever constructed -- exactly what
   `from_tokens()` does, since it calls `record_fields(cls)` before
   building the returned instance -- sees the annotation still as an
   unresolved `ForwardRef`, not the real class. Fixed with one guarded
   `pydantic.dataclasses.rebuild_dataclass(cls)` call inside
   `record_fields()` itself (see below) -- small, centralized,
   confirmed working even with zero instances of the target class ever
   constructed first.

3. Genuine WIN for pydantic over stdlib dataclasses here, confirmed by
   testing: once resolved (lazily, or via the `rebuild_dataclass()` guard
   below), a pydantic dataclass's `FieldInfo.annotation` is the REAL
   `Oc.Format` class object, not a string -- so `_nested_class()`'s entire
   ~15-line custom qualname-walking resolver becomes UNNECESSARY code, not
   just working code: `isinstance(finfo.annotation, type) and issubclass
   (finfo.annotation, Record)` (after unwrapping `Optional`) replaces it
   outright. A stdlib-dataclass port would need to KEEP `_nested_class()`
   unchanged (its `.type` never resolves, same as attrs today).

4. `attrs.NOTHING` (required-field sentinel, used in `from_tokens()`'s
   `required_tagged` computation) -> `FieldInfo.is_required()` on a
   pydantic dataclass -- direct swap, confirmed.

5. `attrs.asdict(row)` (`Package.to_dataframe()`) -> `dataclasses.asdict
   (row)` works UNCHANGED on a pydantic dataclass instance, confirmed --
   pydantic dataclasses ARE real stdlib dataclasses under the hood.

6. Positional construction (`construct_item`'s `item_cls(*values)`,
   `cls(*before, tuple_vals)`) needs `kw_only` left at its default
   (`False`) -- unlike `Component`/`Package`'s `kw_only=True` -- confirmed
   working the same as attrs' current non-`kw_only` `Item`/`Record`
   classes.

7. `.metadata` (dict, read via `f.metadata.get(...)` throughout record.py/
   item.py) -> `Field(json_schema_extra={...})`, same convention already
   chosen for `Component`/`Package` fields (`pydantic_dis_prototype.py`) --
   confirmed a plain stdlib-style `Field(metadata={...})` kwarg is
   deprecated/unsupported on pydantic's `Field()`, so this is the only
   viable convention, which is also the *consistent* one across the
   codebase (one metadata convention, not two).

CONCLUSION: Record/Item does NOT need to keep attrs, and a straight port
to `pydantic.dataclasses.dataclass` (not `BaseModel` -- positional
construction, see #6) is not just possible but strictly simplifies one
piece of real code (`_nested_class()` goes away). Nothing here requires
falling back to plain stdlib `dataclasses.dataclass` instead -- pydantic
is the better target, matching `Component`/`Package`'s choice, keeping
ONE field-metadata idiom (`json_schema_extra`) across the whole object
model rather than two.

Run directly: `python docs/dev/prototypes/pydantic_record_prototype.py`
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, ClassVar, Optional, Union, get_args, get_origin

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass, rebuild_dataclass

_CFG = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True, extra="forbid")


# ============================================================================
# record_fields(): attrs.fields() -> __pydantic_fields__, with the one new
# piece of support code this migration needs -- see finding #2 above.
# ============================================================================


def record_fields(cls: type) -> dict[str, Any]:
    """Non-private fields of a Record (or Item) class, in declaration
    order. NEW vs. the real attrs-based version: the guarded
    `rebuild_dataclass()` call -- confirmed necessary (and sufficient) so
    that a nested/composed field's annotation is the real class, not a
    stale `ForwardRef`, even when called before any instance of `cls` has
    ever been constructed (exactly what `from_tokens()` does)."""
    if not cls.__pydantic_complete__:  # type: ignore[attr-defined]
        rebuild_dataclass(cls, force=True, _parent_namespace_depth=4)  # type: ignore[arg-type]
    return {n: f for n, f in cls.__pydantic_fields__.items() if not n.startswith("_")}  # type: ignore[attr-defined]


def keyword_of(cls: type) -> str:
    return vars(cls).get("_keyword", "")


def _nested_class(cls: type, annotation: Any) -> "type[RecordBase] | None":
    """Replaces attrs-based `_nested_class()`'s custom qualname-walking
    string resolver entirely (finding #3): once `record_fields()` above
    has resolved the field, `annotation` (a pydantic `FieldInfo.
    annotation`) IS the real class object already -- no sys.modules/
    qualname lookup needed."""
    args = get_args(annotation)
    candidate = next((a for a in args if a is not type(None)), annotation)
    return candidate if isinstance(candidate, type) and issubclass(candidate, RecordBase) else None


def _is_bool_field(finfo: Any) -> bool:
    t = finfo.annotation
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        t = next((a for a in get_args(t) if a is not type(None)), t)
    return t is bool


def _coerce(token: Any, finfo: Any) -> Any:
    meta = finfo.json_schema_extra or {}
    if isinstance(meta, dict) and meta.get("time_series"):
        try:
            return float(token)
        except (ValueError, TypeError):
            return str(token)
    t = finfo.annotation
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) != 1:
            return token
        t = args[0]
    if t is int:
        return int(float(str(token)))
    if t is float:
        return float(token)
    if t is Path:
        return Path(token)
    return token


def _is_tagged(finfo: Any) -> bool:
    return bool((finfo.json_schema_extra or {}).get("tagged"))


def _tagged_tokens(name: str, v: Any) -> list:
    if isinstance(v, bool):
        return [name.upper()] if v else []
    return [name.upper(), v]


def _consume_tagged(tokens: list, i: int, name: str, finfo: Any) -> "tuple[Any, int] | None":
    if str(tokens[i]).upper() != name.upper():
        return None
    if _is_bool_field(finfo):
        return True, 1
    if i + 1 >= len(tokens):
        return None
    return _coerce(tokens[i + 1], finfo), 2


class RecordBase:
    """Mixin for generated Record/Item types -- ported from
    `flopy4.mf6.record.Record`. Provides symmetric
    `to_tokens`/`from_tokens`, same shape as the attrs original, just
    reading `__pydantic_fields__`/`json_schema_extra` instead of
    `attrs.fields()`/`.metadata` (finding #7)."""

    def to_tokens(self) -> tuple:
        inner_cls = type(self)
        keyword = keyword_of(inner_cls)
        tokens: list = [keyword.upper()] if keyword else []
        for tok in vars(inner_cls).get("_extra_tokens", ()):
            tokens.append(tok)
        all_fields = record_fields(inner_cls)
        tagged = [(n, f) for n, f in all_fields.items() if _is_tagged(f)]
        untagged = [(n, f) for n, f in all_fields.items() if not _is_tagged(f)]
        for name, finfo in tagged + untagged:
            v = getattr(self, name)
            if v is None:
                continue
            if isinstance(v, RecordBase):
                tokens.extend(v.to_tokens())
            elif (finfo.json_schema_extra or {}).get("tagged"):
                tokens.extend(_tagged_tokens(name, v))
            elif isinstance(v, bool):
                if v:
                    tokens.append(name.upper())
            else:
                tokens.append(v)
        return tuple(tokens)

    @classmethod
    def from_tokens(cls, tokens: "str | list[str]") -> "RecordBase":
        if isinstance(tokens, str):
            tokens = tokens.split()

        skip: list[str] = []
        if kw := keyword_of(cls):
            skip.append(kw.upper())
        skip.extend(t.upper() for t in vars(cls).get("_extra_tokens", ()))
        if [t.upper() for t in tokens[: len(skip)]] == skip:
            tokens = tokens[len(skip) :]

        all_fields = record_fields(cls)

        nested_fields = [(n, f, _nested_class(cls, f.annotation)) for n, f in all_fields.items()]
        nested_fields = [(n, f, nc) for n, f, nc in nested_fields if nc is not None]
        if nested_fields:
            assert len(nested_fields) == 1 and len(nested_fields) == len(all_fields), (
                f"{cls.__name__}: exactly one nested record field, with no plain "
                "fields of its own, is the only shape supported so far"
            )
            n, _f, nested_cls = nested_fields[0]
            return cls(**{n: nested_cls.from_tokens(tokens)})  # type: ignore[call-arg]

        tagged = {n.upper(): (n, f) for n, f in all_fields.items() if _is_tagged(f)}
        untagged = [(n, f) for n, f in all_fields.items() if not _is_tagged(f)]

        kwargs: dict = {}
        consumed: set[int] = set()
        i = 0
        while i < len(tokens):
            entry = tagged.get(str(tokens[i]).upper())
            result = None if entry is None else _consume_tagged(tokens, i, entry[0], entry[1])
            if entry is None or result is None:
                i += 1
                continue
            name, _finfo = entry
            val, width = result
            kwargs[name] = val
            for j in range(width):
                consumed.add(i + j)
            i += width

        required_tagged = [
            (n, f)
            for n, f in all_fields.items()
            if _is_tagged(f) and f.is_required() and n not in kwargs
        ]
        positional_queue = required_tagged + untagged
        remaining = [t for j, t in enumerate(tokens) if j not in consumed]
        for (name, finfo), tok in zip(positional_queue, remaining):
            kwargs[name] = _coerce(tok, finfo)

        return cls(**kwargs)  # type: ignore[call-arg]


# ============================================================================
# Demonstration: Oc.Headprint / Oc.Format, the exact nested-sibling-class
# shape _nested_class() exists for -- ported to pydantic dataclasses.
# ============================================================================


class Oc:
    @dataclass(config=_CFG)
    class Format(RecordBase):
        _keyword: ClassVar[str] = "PRINT_FORMAT"
        columns: int = Field(default=10, json_schema_extra={"tagged": True})
        width: int = Field(default=12, json_schema_extra={"tagged": True})
        digits: int = Field(default=6, json_schema_extra={"tagged": True})

    @dataclass(config=_CFG)
    class Headprint(RecordBase):
        """References its SIBLING `Format` -- via a literal string
        annotation, fully qualified exactly like real codegen emits
        (`package.py.jinja` line 38/40: `"Optional[{{ spec.class_name }}.
        {{ f.type_annotation }}]"`), and declared BEFORE `Format` in
        source order (the harder of the two orderings -- see finding #2).
        """

        _keyword: ClassVar[str] = "HEAD"
        fmt: "Optional[Oc.Format]" = Field(default=None)


# ============================================================================
# A plain (non-nested) tagged/positional record, for the required-field
# (attrs.NOTHING -> is_required()) and to_tokens/from_tokens round-trip.
# ============================================================================


@dataclass(config=_CFG)
class Save(RecordBase):
    _keyword: ClassVar[str] = "SAVE"
    frequency: int = Field(json_schema_extra={"tagged": True})  # required -- no default
    print_input: bool = Field(default=False, json_schema_extra={"tagged": True})


def demo() -> None:
    print("=" * 70)
    print("Pydantic Record/Item prototype")
    print("=" * 70)

    complete = Oc.Headprint.__pydantic_complete__
    print(f"\nOc.Headprint.__pydantic_complete__ before any use: {complete}")

    hp = Oc.Headprint(fmt=Oc.Format(columns=5, width=10, digits=3))
    print(f"constructed via nested composition: {hp}")
    print(f"__pydantic_complete__ after construction: {Oc.Headprint.__pydantic_complete__}")

    tokens = hp.to_tokens()
    print(f"to_tokens(): {tokens}")
    assert tokens == ("HEAD", "PRINT_FORMAT", "COLUMNS", 5, "WIDTH", 10, "DIGITS", 3)

    round_tripped = Oc.Headprint.from_tokens(list(tokens))
    print(f"from_tokens() round-trip: {round_tripped}")
    assert round_tripped == hp

    print("\nrecord_fields() resolves the nested field to a REAL class object")
    print("(not a string -- _nested_class() needs no sys.modules/qualname walk):")
    fields = record_fields(Oc.Headprint)
    resolved = _nested_class(Oc.Headprint, fields["fmt"].annotation)
    print(f"  fields['fmt'].annotation -> {fields['fmt'].annotation}")
    print(f"  _nested_class() -> {resolved}")
    assert resolved is Oc.Format

    print("\nrequired-field detection (attrs.NOTHING -> FieldInfo.is_required()):")
    save = Save.from_tokens("SAVE FREQUENCY 5")
    print(f"  Save.from_tokens('SAVE FREQUENCY 5') -> {save}")
    assert save.frequency == 5 and save.print_input is False
    print(f"  to_tokens() round-trip: {save.to_tokens()}")
    assert save.to_tokens() == ("SAVE", "FREQUENCY", 5)

    print("\nAll assertions passed.")


if __name__ == "__main__":
    demo()
