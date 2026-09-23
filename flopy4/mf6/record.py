"""Base class for generated MF6 inner-class record types.

Item (item.py) subclasses Record and adds what a table row needs beyond
this: index/pk/fk renumbering, cellid packing, aux/boundname, and external
parse context. Record itself has none of that -- just a keyword-tagged or
positional compound value.

A Record can also compose another Record (a DFN record nested inside
another) rather than flattening the nested one's fields into itself --
see _nested_class, inferred from the field's own type annotation rather
than a declared flag, and make.py's _build_record_class_specs.
"""

import sys
import types
from functools import lru_cache
from pathlib import Path
from typing import Any, Union, cast, get_args, get_origin

import attrs


def _resolve_sibling_class(cls: type, name: str) -> Any | None:
    """Resolve a bare sibling class name one level up from `cls` in
    `__qualname__`, where every generated flat-sibling class (composed
    Records, keystring-union arms) lives regardless of DFN nesting depth.
    No type check here -- callers (`_nested_class`, item.py's
    `_nested_union_classes`) apply their own, against different base
    classes.

    Must resolve at runtime: a class body can't see sibling names from an
    enclosing scope, which is why the qualified string form
    (``"Oc.Format"``) exists at all -- purely for mypy.
    """
    obj = sys.modules[cls.__module__]
    for part in cls.__qualname__.split(".")[:-1]:
        obj = getattr(obj, part)
    return getattr(obj, name, None)


@lru_cache(maxsize=None)
def _nested_class(cls: type, type_str: str) -> "type[Record] | None":
    """If a field's raw type annotation (e.g. ``"Format"`` or
    ``"Optional[Oc.Format]"``) names a Record subclass, return it; else
    None. Resolvability against a real Record subclass is itself the
    signal -- no declared "is this nested" flag needed.

    Cached since to_tokens/from_tokens call this per field, often
    repeatedly while parsing many rows.
    """
    name = type_str
    if name.startswith("Optional[") and name.endswith("]"):
        name = name[len("Optional[") : -1]
    name = name.rsplit(".", 1)[-1]
    resolved = _resolve_sibling_class(cls, name)
    return resolved if isinstance(resolved, type) and issubclass(resolved, Record) else None


def _is_bool_field(f: attrs.Attribute) -> bool:
    t = f.type
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        t = next((a for a in get_args(t) if a is not type(None)), t)
    return t in (bool, "bool")


def _coerce(token: Any, f: attrs.Attribute) -> Any:
    """Cast a raw token to a field's declared type (time_series falls back
    to the raw string if it isn't a float). Only Optional[X] (a single
    non-None union arm) is unwrapped -- a genuine multi-type union like
    Union[float, str] is deliberately ambiguous and left as the raw token."""
    if f.metadata.get("time_series"):
        try:
            return float(token)
        except (ValueError, TypeError):
            return str(token)
    t = f.type
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) != 1:
            return token
        t = args[0]
    if t in (int, "int"):
        return int(float(str(token)))
    if t in (float, "float"):
        return float(token)
    if t in (Path, "Path"):
        return Path(token)
    return token


def _is_list_field(f: attrs.Attribute) -> bool:
    """True for ``list[X]`` or ``Optional[list[X]]``"""
    t = f.type
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        t = next((a for a in get_args(t) if a is not type(None)), t)
        origin = get_origin(t)
    return origin is list


def _list_elem_coerce(token: Any, f: attrs.Attribute) -> Any:
    """Coerce one token to a list field's declared element type."""
    t = f.type
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        t = next((a for a in get_args(t) if a is not type(None)), t)
    args = get_args(t)
    elem_t = args[0] if args else str
    if elem_t is int:
        return int(float(str(token)))
    if elem_t is float:
        return float(token)
    return token


def _tokens(name: str, value: Any) -> list:
    """Bare ``NAME`` for a boolean, ``NAME value`` otherwise"""
    if isinstance(value, bool):
        return [name.upper()] if value else []
    return [name.upper(), value]


def _consume_tagged(tokens: list, i: int, f: attrs.Attribute) -> "tuple[Any, int] | None":
    """Match field f's tagged keyword at tokens[i]; a bool field needs no
    value token, anything else does. None if unmatched or value missing."""
    if str(tokens[i]).upper() != f.name.upper():
        return None
    if _is_bool_field(f):
        return True, 1
    if i + 1 >= len(tokens):
        return None
    return _coerce(tokens[i + 1], f), 2


class Record:
    """Mixin for record types."""

    @classmethod
    def fields(cls: type["Record"]) -> list[attrs.Attribute]:
        """Record (or Item) class' fields, in declaration order."""
        fields = attrs.fields(cast(type[attrs.AttrsInstance], cls))
        return [f for f in fields if not f.name.startswith("_")]

    @classmethod
    def keyword(cls: type["Record"]) -> str:
        return vars(cls).get("_keyword", "")

    def to_tokens(self) -> tuple:
        cls = type(self)
        kw = cls.keyword()
        tokens: list = [kw.upper()] if kw else []
        for tok in vars(cls).get("_extra_tokens", ()):
            tokens.append(tok)
        fields = cls.fields()
        tagged = [a for a in fields if a.metadata.get("tagged")]
        untagged = [a for a in fields if not a.metadata.get("tagged")]
        for a in tagged + untagged:
            v = getattr(self, a.name)
            if v is None:
                continue
            if isinstance(v, Record):
                tokens.extend(v.to_tokens())
            elif a.metadata.get("tagged"):
                tokens.extend(_tokens(a.name, v))
            elif isinstance(v, bool):
                if v:
                    tokens.append(a.name.upper())
            elif isinstance(v, (list, tuple)):
                tokens.extend(v)
            else:
                tokens.append(v)
        return tuple(tokens)

    @classmethod
    def from_tokens(cls, tokens: str | list[str]) -> "Record":
        """Parse a token string/list back into an instance.

        Tagged fields are matched by keyword wherever it appears; whatever's
        left fills required tagged fields (not keyword-matched) then plain
        fields, in declaration order. E.g. for ``Oc.Headprint``, these are
        all equivalent: ``"HEAD PRINT_FORMAT COLUMNS 10 WIDTH 12 DIGITS 6
        exponential"``, ``"COLUMNS 10 WIDTH 12 DIGITS 6 exponential"``,
        ``"exponential"``.
        """
        if isinstance(tokens, str):
            tokens = tokens.split()

        skip: list[str] = []
        if kw := cls.keyword():
            skip.append(kw.upper())
        skip.extend(t.upper() for t in vars(cls).get("_extra_tokens", ()))
        if [str(t).upper() for t in tokens[: len(skip)]] == skip:
            tokens = tokens[len(skip) :]

        fields = cls.fields()

        def _nested(f: attrs.Attribute) -> "type[Record] | None":
            return _nested_class(cast(type, cls), f.type) if isinstance(f.type, str) else None

        nested_fields = [f for f in fields if _nested(f) is not None]
        if nested_fields:
            # A record composed of nested record(s) has, in the current
            # corpus, no other fields of its own once _keyword/_extra_tokens
            # are stripped -- delegate the rest of the tokens wholesale.
            assert len(nested_fields) == 1 and len(nested_fields) == len(fields), (
                f"{cls.__name__}: exactly one nested record field, with no plain "
                "fields of its own, is the only shape supported so far"
            )
            nf = nested_fields[0]
            nested_cls = _nested(nf)
            assert nested_cls is not None
            return cls(**{nf.name: nested_cls.from_tokens(tokens)})

        tagged = {f.name.upper(): f for f in fields if f.metadata.get("tagged")}
        untagged = [f for f in fields if not f.metadata.get("tagged")]

        kwargs: dict = {}
        consumed: set[int] = set()

        i = 0
        while i < len(tokens):
            f = tagged.get(str(tokens[i]).upper())
            result = None if f is None else _consume_tagged(tokens, i, f)
            if f is None or result is None:
                i += 1
                continue
            val, width = result
            kwargs[f.name] = val
            for j in range(width):
                consumed.add(i + j)
            i += width

        required_tagged = [
            f
            for f in fields
            if f.metadata.get("tagged") and f.default is attrs.NOTHING and f.name not in kwargs
        ]
        positional_queue = required_tagged + untagged
        remaining = [t for j, t in enumerate(tokens) if j not in consumed]

        list_field = next((f for f in positional_queue if _is_list_field(f)), None)
        if list_field is not None:
            idx = positional_queue.index(list_field)
            assert idx == len(positional_queue) - 1, (
                f"{cls.__name__}.{list_field.name}: a list-typed record field must be "
                "the last positional field -- it consumes all remaining tokens"
            )
            scalar_fields = positional_queue[:idx]
            for f, tok in zip(scalar_fields, remaining):
                kwargs[f.name] = _coerce(tok, f)
            kwargs[list_field.name] = [
                _list_elem_coerce(tok, list_field) for tok in remaining[len(scalar_fields) :]
            ]
        else:
            for f, tok in zip(positional_queue, remaining):
                kwargs[f.name] = _coerce(tok, f)

        return cls(**kwargs)
