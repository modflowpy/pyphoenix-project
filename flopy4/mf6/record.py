"""Base class for generated MF6 inner-class record types.

Item (item.py) subclasses Record and adds what a table row needs beyond
this: index/pk/fk renumbering, cellid packing, aux/boundname, and external
parse context. Record itself has none of that -- just a keyword-tagged or
positional compound value.
"""

import types
from pathlib import Path
from typing import Any, Union, cast, get_args, get_origin

import attrs


def keyword_of(cls: type) -> str:
    return vars(cls).get("_keyword", "")


def record_fields(cls: type) -> list[attrs.Attribute]:
    """Non-private fields of a Record (or Item) class, in declaration order."""
    all_fields = attrs.fields(cast(type[attrs.AttrsInstance], cls))
    return [f for f in all_fields if not f.name.startswith("_")]


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


def _tagged_tokens(f: attrs.Attribute, v: Any) -> list:
    """Bare ``NAME`` for a true bool flag, ``NAME value`` otherwise."""
    if isinstance(v, bool):
        return [f.name.upper()] if v else []
    return [f.name.upper(), v]


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
    """Mixin for generated inner-class record types.

    Provides symmetric :meth:`to_tokens`/:meth:`from_tokens`.
    """

    def to_tokens(self) -> tuple:
        inner_cls = type(self)
        keyword = keyword_of(inner_cls)
        tokens: list = [keyword.upper()] if keyword else []
        for tok in vars(inner_cls).get("_extra_tokens", ()):
            tokens.append(tok)
        all_fields = record_fields(inner_cls)
        tagged = [a for a in all_fields if a.metadata.get("tagged")]
        untagged = [a for a in all_fields if not a.metadata.get("tagged")]
        for a in tagged + untagged:
            v = getattr(self, a.name)
            if v is None:
                continue
            if a.metadata.get("tagged"):
                tokens.extend(_tagged_tokens(a, v))
            elif isinstance(v, bool):
                if v:
                    tokens.append(a.name.upper())
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
        if kw := keyword_of(cls):
            skip.append(kw.upper())
        skip.extend(t.upper() for t in vars(cls).get("_extra_tokens", ()))
        if [t.upper() for t in tokens[: len(skip)]] == skip:
            tokens = tokens[len(skip) :]

        all_fields = record_fields(cast(type, cls))
        tagged = {f.name.upper(): f for f in all_fields if f.metadata.get("tagged")}
        untagged = [f for f in all_fields if not f.metadata.get("tagged")]

        kwargs: dict = {}
        consumed: set[int] = set()

        i = 0
        while i < len(tokens):
            f = tagged.get(tokens[i].upper())
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
            for f in all_fields
            if f.metadata.get("tagged") and f.default is attrs.NOTHING and f.name not in kwargs
        ]
        positional_queue = required_tagged + untagged
        remaining = [t for j, t in enumerate(tokens) if j not in consumed]
        for f, tok in zip(positional_queue, remaining):
            kwargs[f.name] = _coerce(tok, f)

        return cls(**kwargs)
