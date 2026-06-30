"""Base class for generated MF6 inner-class record types."""

import types
from typing import cast, get_args, get_origin

import attrs


def _coerce(token: str, f: attrs.Attribute):
    """Cast a string token to the scalar type declared on an attrs field."""
    t = f.type
    origin = get_origin(t)
    if origin is types.UnionType or origin is getattr(__import__("typing"), "Union", None):
        t = next((a for a in get_args(t) if a is not type(None)), str)
    if t is int:
        return int(token)
    if t is float:
        return float(token)
    return token


class Record:
    """Mixin for generated inner-class record types.

    Provides :meth:`from_tokens` and :meth:`to_tokens` for symmetric
    parsing/serialization of inner-class records.
    """

    def to_tokens(self) -> tuple:
        """Serialize this record to an MF6 token tuple.

        Emits ``_keyword`` (uppercased), ``_extra_tokens``, then field values
        in declaration order (tagged fields emit ``NAME value``, untagged bools
        emit ``NAME`` when True, untagged scalars emit the raw value).
        """
        inner_cls = type(self)
        keyword: str = vars(inner_cls).get("_keyword", "")
        tokens: list = [keyword.upper()] if keyword else []
        for tok in vars(inner_cls).get("_extra_tokens", ()):
            tokens.append(tok)
        all_fields = attrs.fields(inner_cls)  # type: ignore[arg-type]
        tagged = [a for a in all_fields if a.metadata.get("tagged")]
        untagged = [a for a in all_fields if not a.metadata.get("tagged")]
        for a in tagged + untagged:
            v = getattr(self, a.name)
            if v is None:
                continue
            if a.metadata.get("tagged"):
                if isinstance(v, bool):
                    if v:
                        tokens.append(a.name.upper())
                else:
                    tokens.extend([a.name.upper(), v])
            elif isinstance(v, bool):
                if v:
                    tokens.append(a.name.upper())
            else:
                tokens.append(v)
        return tuple(tokens)

    @classmethod
    def from_tokens(cls, tokens: str | list[str]) -> "Record":
        """Construct from a raw token string or list.

        The trigger keyword (``_keyword``) and any fixed syntax tokens
        (``_extra_tokens``) are stripped if the caller included them.

        Two-pass parsing:
        1. Extract ``KEYWORD value`` pairs for tagged fields.
        2. Fill remaining tokens positionally into required tagged fields
           that were not keyword-matched, then into untagged fields.
           Optional tagged fields not supplied by keyword are skipped.

        Examples
        --------
        All three forms are equivalent for ``Oc.Headprint``::

            Oc.Headprint.from_tokens("HEAD PRINT_FORMAT COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
            Oc.Headprint.from_tokens("COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
            Oc.Headprint.from_tokens("exponential")

        Both forms are equivalent for ``Ims.Rclose``::

            Ims.Rclose.from_tokens("INNER_RCLOSE 0.001")
            Ims.Rclose.from_tokens("0.001")
        """
        if isinstance(tokens, str):
            tokens = tokens.split()

        # Strip leading _keyword and _extra_tokens if caller included them.
        skip: list[str] = []
        if kw := vars(cls).get("_keyword", ""):
            skip.append(kw.upper())
        skip.extend(t.upper() for t in vars(cls).get("_extra_tokens", ()))
        if [t.upper() for t in tokens[: len(skip)]] == skip:
            tokens = tokens[len(skip) :]

        all_fields = [
            f
            for f in attrs.fields(cast(type[attrs.AttrsInstance], cls))
            if not f.name.startswith("_")
        ]
        tagged = {f.name.upper(): f for f in all_fields if f.metadata.get("tagged")}
        untagged = [f for f in all_fields if not f.metadata.get("tagged")]

        kwargs: dict = {}
        consumed: set[int] = set()

        # Pass 1: extract KEYWORD value pairs for tagged fields.
        i = 0
        while i < len(tokens):
            tok = tokens[i].upper()
            if tok in tagged and i + 1 < len(tokens):
                f = tagged[tok]
                kwargs[f.name] = _coerce(tokens[i + 1], f)
                consumed.add(i)
                consumed.add(i + 1)
                i += 2
            else:
                i += 1

        # Pass 2: fill remaining tokens positionally.
        # Required tagged fields that were not keyword-matched come first
        # (in declaration order), then all untagged fields.
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
