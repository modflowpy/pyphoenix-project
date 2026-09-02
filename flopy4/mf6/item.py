"""Item(Record): one row of a repeating tabular block (packagedata,
connectiondata, period data, ...).

Adds what Record doesn't need: index/pk/fk renumbering, cellid packing,
aux/boundname trailing columns, and external parse context (ncelldim/naux/
boundnames -- facts about the surrounding list/package, not one row). A
tagged field here is always a bare presence flag (e.g. LAK tables' MIXED) --
unlike Record's tagged fields, which may carry a value.

An Item class MAY declare ``_keyword: ClassVar[str]`` for the
keystring-union-arm case (e.g. LAK/SFR/MAW/UZF period settings): several
Item subclasses share one field (a Union of their types), each identified
by its own leading keyword token (STATUS/STAGE/RATE/...).
"""

import re
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import attrs

from flopy4.mf6.record import Record, _coerce, keyword_of, record_fields

_AUX_KEY_RE = re.compile(r"^aux(\d+)$")


def normalize_aux_keys(item: dict) -> dict:
    """Collapse legacy aux0/aux1/... dict keys into one aux tuple key."""
    aux_items = []
    rest = {}
    for k, v in item.items():
        m = _AUX_KEY_RE.match(k)
        if m:
            aux_items.append((int(m.group(1)), v))
        else:
            rest[k] = v
    if aux_items:
        aux_items.sort(key=lambda kv: kv[0])
        rest["aux"] = tuple(v for _, v in aux_items)
    return rest


def _cellid_field(cls: type) -> attrs.Attribute | None:
    return next((f for f in record_fields(cls) if f.metadata.get("cellid")), None)


def _has_aux_field(cls: type) -> bool:
    return any(f.name == "aux" for f in record_fields(cls))


def _has_boundname_field(cls: type) -> bool:
    return any(f.name == "boundname" for f in record_fields(cls))


def construct_item(item_cls: type, values) -> "Item":
    """Build an Item from a flat positional tuple, e.g. ``(cellid, q, 35.0)``
    for one aux variable, or ``("HEAD", "FREQUENCY", 2)`` for OC's Save
    (rtype, ocsetting). Everything from the aux/array field's position
    onward collects into that one field's tuple, except a trailing string
    when the class also has boundname (always declared last) -- a string
    there unambiguously isn't a numeric aux value.
    """
    fields = record_fields(item_cls)
    tuple_idx = next(
        (i for i, f in enumerate(fields) if f.name == "aux" or f.metadata.get("array")), None
    )
    values = list(values)
    if tuple_idx is None:
        return item_cls(*values)
    boundname_val = None
    if (
        fields
        and fields[-1].name == "boundname"
        and len(values) > tuple_idx
        and isinstance(values[-1], str)
    ):
        boundname_val = values[-1]
        values = values[:-1]
    before = values[:tuple_idx]
    tuple_vals = tuple(values[tuple_idx:])
    if boundname_val is not None:
        return item_cls(*before, tuple_vals, boundname=boundname_val)
    return item_cls(*before, tuple_vals)


def _n_fixed_tokens(cls: type) -> int:
    """Fixed (non-cellid/aux/boundname, non-optional) token slots -- used to
    infer a variable-width cellid's element count from total token length."""
    n = 1 if keyword_of(cls) else 0
    for f in record_fields(cls):
        if f.metadata.get("cellid") or f.name in ("aux", "boundname"):
            continue
        if f.metadata.get("optional"):
            continue
        n += 1 + len(f.metadata.get("prefix", ()))
        if f.metadata.get("direction"):
            n += 1
    return n


def infer_ncelldim(items: list[list], item_cls: "type[Item]", *, naux: int = 0) -> int:
    """Infer an Item class's cellid width from the first non-empty raw item:
    total tokens minus fixed columns minus aux minus a trailing boundname."""
    if _cellid_field(item_cls) is None:
        return 0
    first = next((r for r in items if r), None)
    if not first:
        return 0
    n_fixed = _n_fixed_tokens(item_cls)
    last = first[-1]
    has_bn = isinstance(last, str) and not _token_fits(last, float)
    return max(1, len(first) - n_fixed - naux - (1 if has_bn else 0))


def _token_fits(token: Any, kind: type) -> bool:
    """True if token coerces to kind -- tells a trailing boundname string
    apart from a trailing numeric value."""
    if isinstance(token, (int, float)):
        return True
    if isinstance(token, str):
        try:
            float(token)
            return True
        except ValueError:
            return False
    return False


class Item(Record):
    """Mixin for generated table-item types (plain items and keystring-union
    arms alike -- see module docstring)."""

    def to_tokens(self) -> tuple:
        """index -> 1-based; cellid likewise per element. _keyword (if any)
        is emitted before the first non-index field. aux/boundname last.
        """
        cls = type(self)
        fields = record_fields(cls)
        keyword = keyword_of(cls)
        row: list[Any] = []
        keyword_emitted = not keyword
        for f in fields:
            if f.name in ("aux", "boundname"):
                continue
            val = getattr(self, f.name)
            if val is None:
                continue
            if f.metadata.get("cellid"):
                row.extend(int(c) + 1 for c in val)
            elif f.metadata.get("index"):
                row.append(int(val) + 1)
            elif f.metadata.get("array"):
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                row.extend(val)
            elif f.metadata.get("tagged"):
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                if val:
                    row.append(f.name.upper())
            else:
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                if prefix := f.metadata.get("prefix"):
                    row.extend(prefix)
                if direction := f.metadata.get("direction"):
                    row.append("FILEOUT" if direction == "out" else "FILEIN")
                row.append(str(val) if isinstance(val, Path) else val)
        if not keyword_emitted:
            row.append(keyword.upper())
        aux = getattr(self, "aux", None)
        if aux:
            row.extend(aux)
        boundname = getattr(self, "boundname", None)
        if boundname:
            row.append(boundname)
        return tuple(row)

    @classmethod
    def from_tokens(  # type: ignore[override]
        cls, tokens: list, *, ncelldim: int = 0, naux: int = 0, boundnames: bool = False
    ) -> "Item":
        """Mirror of to_tokens. Optional untagged columns (e.g. EVT's
        pxdp/petm/petm0) have no marker token -- MF6 writes a whole trailing
        group or none, gated by an unrelated OPTIONS flag -- so presence is
        inferred once from the token budget left after reserving aux/
        boundname, not per-field. Tagged optional fields self-identify by
        keyword and skip that budget.
        """
        fields = record_fields(cls)
        keyword = keyword_of(cls)
        keyword_skipped = not keyword
        has_boundname = _has_boundname_field(cls) and boundnames
        has_aux = _has_aux_field(cls)
        kwargs: dict[str, Any] = {}
        tok_idx = 0
        n = len(tokens)

        def consume(f: attrs.Attribute) -> None:
            nonlocal tok_idx, keyword_skipped
            if f.metadata.get("cellid"):
                cellid = tuple(int(tokens[tok_idx + j]) - 1 for j in range(ncelldim))
                kwargs[f.name] = cellid
                tok_idx += ncelldim
                return
            if f.metadata.get("index"):
                kwargs[f.name] = int(float(str(tokens[tok_idx]))) - 1
                tok_idx += 1
                return
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            if prefix := f.metadata.get("prefix"):
                tok_idx += len(prefix)
            if f.metadata.get("direction"):
                tok_idx += 1
            if tok_idx >= n:
                return
            kwargs[f.name] = _coerce(tokens[tok_idx], f)
            tok_idx += 1

        def width(f: attrs.Attribute) -> int:
            w = 1 + len(f.metadata.get("prefix", ()))
            if f.metadata.get("direction"):
                w += 1
            return w

        main_fields = [f for f in fields if f.name not in ("aux", "boundname")]
        array_fields = [f for f in main_fields if f.metadata.get("array")]
        main_fields = [f for f in main_fields if not f.metadata.get("array")]
        required_fields = [f for f in main_fields if not f.metadata.get("optional")]
        optional_fields = [f for f in main_fields if f.metadata.get("optional")]

        for f in required_fields:
            consume(f)

        has_bn_token = False
        if has_boundname and n > tok_idx:
            last = tokens[-1]
            has_bn_token = isinstance(last, str) and not _token_fits(last, float)
        remaining = n - tok_idx - (1 if has_bn_token else 0) - (naux if has_aux else 0)

        budget_fields = [f for f in optional_fields if not f.metadata.get("tagged")]
        n_opt_present = 0
        used = 0
        for f in budget_fields:
            w = width(f)
            if used + w > remaining:
                break
            used += w
            n_opt_present += 1

        budget_idx = 0
        for f in optional_fields:
            if f.metadata.get("tagged"):
                if not keyword_skipped:
                    tok_idx += 1
                    keyword_skipped = True
                kw = f.name.upper()
                if tok_idx < n and str(tokens[tok_idx]).upper() == kw:
                    kwargs[f.name] = str(tokens[tok_idx])
                    tok_idx += 1
                continue
            present = budget_idx < n_opt_present
            budget_idx += 1
            if present:
                consume(f)

        if array_fields:
            # Consumes everything left up to aux/boundname's own reserved
            # slots -- a keyword-plus-trailing-values setting (OC/PRP's
            # ocsetting/releasesetting: bare ALL/FIRST/LAST, "FREQUENCY n",
            # or "STEPS n1 n2 ..."), coerced numeric-or-string per token
            # like aux (see below) since the arity and type aren't fixed.
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            f = array_fields[0]
            end = n - (1 if has_bn_token else 0) - (naux if has_aux else 0)
            vals = []
            while tok_idx < end:
                tok = tokens[tok_idx]
                try:
                    vals.append(float(tok))
                except (ValueError, TypeError):
                    vals.append(tok)
                tok_idx += 1
            kwargs[f.name] = tuple(vals)
        elif not keyword_skipped:
            tok_idx += 1

        if has_aux:
            aux_vals = []
            end = n - (1 if has_bn_token else 0)
            while tok_idx < end:
                tok = tokens[tok_idx]
                try:
                    aux_vals.append(float(tok))
                except (ValueError, TypeError):
                    aux_vals.append(tok)
                tok_idx += 1
            kwargs["aux"] = tuple(aux_vals)

        if has_bn_token:
            kwargs["boundname"] = str(tokens[-1])

        return cls(**kwargs)


def _unwrap_item(item) -> "type[Item] | tuple[type[Item], ...] | None":
    """A single Item subclass, or the tuple of arm subclasses for a Union
    (keystring-arm) item type."""
    if isinstance(item, type) and issubclass(item, Item):
        return item
    origin = get_origin(item)
    if origin is Union or origin is type(int | str):
        arms = tuple(a for a in get_args(item) if isinstance(a, type) and issubclass(a, Item))
        return arms or None
    return None


def item_list_type(field_type) -> "type[Item] | tuple[type[Item], ...] | None":
    """For Optional[list[C]] or Optional[dict[int, list[C]]], return C (or
    the tuple of arm classes for a Union item type)."""
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    origin = get_origin(inner)
    if origin is list:
        return _unwrap_item(get_args(inner)[0])
    if origin is dict:
        _, val = get_args(inner)
        if get_origin(val) is list:
            return _unwrap_item(get_args(val)[0])
    return None


def dispatch_union_item(item: list, arm_classes: "tuple[type[Item], ...]") -> "type[Item] | None":
    """Find which arm class a raw token item belongs to, by its leading
    _keyword token."""
    kw_map = {keyword_of(c).upper(): c for c in arm_classes if keyword_of(c)}
    for t in item:
        arm_cls = kw_map.get(str(t).upper())
        if arm_cls is not None:
            return arm_cls
    return None


def construct_union_item(values, arm_classes: "tuple[type[Item], ...]") -> "Item | None":
    """Build an Item from a flat user-supplied positional tuple for a
    keystring-union field, e.g. ``(0, "STATUS", "ACTIVE")``.

    Dispatches to the right arm by keyword token, same as dispatch_union_item,
    then drops that token and builds the rest positionally via construct_item
    -- unlike parse_union_items/from_tokens, the remaining values are already
    Python-side (a 0-based int, a real float, ...), not raw 1-based/string
    file tokens, so they must NOT go through from_tokens's index/type
    conversion a second time.
    """
    values = list(values)
    arm_cls = dispatch_union_item(values, arm_classes)
    if arm_cls is None:
        return None
    kw = keyword_of(arm_cls).upper()
    kw_idx = next((i for i, v in enumerate(values) if str(v).upper() == kw), None)
    if kw_idx is not None:
        values = values[:kw_idx] + values[kw_idx + 1 :]
    return construct_item(arm_cls, values)


def parse_union_items(
    items: list, arm_classes: "tuple[type[Item], ...]", *, naux: int = 0, boundnames: bool = False
) -> list | None:
    """Parse raw token items into Item instances, dispatching each by
    keyword (see dispatch_union_item); unmatched items are skipped."""
    if not items:
        return None
    result = []
    for item in items:
        if not item:
            continue
        arm_cls = dispatch_union_item(item, arm_classes)
        if arm_cls is None:
            continue
        result.append(arm_cls.from_tokens(item, naux=naux, boundnames=boundnames))
    return result or None
