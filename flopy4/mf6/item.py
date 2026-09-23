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

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Union, cast, get_args, get_origin

from flopy4.mf6.record import Record, _coerce

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


def _cellid_field(cls: type) -> Any | None:
    return next(
        (
            f
            for f in cast(type[Record], cls).fields().values()
            if (f.json_schema_extra or {}).get("cellid")
        ),
        None,
    )


def _has_aux_field(cls: type) -> bool:
    return "aux" in cast(type[Record], cls).fields()


def _has_boundname_field(cls: type) -> bool:
    return "boundname" in cast(type[Record], cls).fields()


def _is_item_union(annotation: Any) -> "tuple[type[Item], ...] | None":
    """If a field's (already-resolved) annotation is a Union of sibling
    Item classes (e.g. OC's ``All | First | Last | Frequency | Steps``),
    return the tuple of arm classes; else None.

    Replaces the attrs original's `_nested_union_classes()` -- a
    qualname-walking parse of the field's raw, unresolved forward-ref
    string. Not needed here: by the time `Record.fields()` has run,
    `annotation` (a pydantic `FieldInfo.annotation`) IS the real union of
    resolved classes already.
    """
    origin = get_origin(annotation)
    if origin is Union or origin is type(int | str):
        arms = tuple(a for a in get_args(annotation) if isinstance(a, type) and issubclass(a, Item))
        return arms or None
    return None


def construct_item(item_cls: type, values) -> "Item":
    """Build an Item from a flat positional tuple, e.g. ``(cellid, q, 35.0)``
    for one aux variable, or ``("HEAD", "FREQUENCY", 2)`` for OC's Save
    (rtype, ocsetting). Everything from the aux/array/nested-union field's
    position onward collects into that one field's value, except a
    trailing string when the class also has boundname (always declared
    last) -- a string there unambiguously isn't a numeric aux value.
    """
    fields = list(cast(type[Record], item_cls).fields().items())
    tuple_idx = next(
        (
            i
            for i, (name, f) in enumerate(fields)
            if name == "aux"
            or (f.json_schema_extra or {}).get("array")
            or _is_item_union(f.annotation) is not None
        ),
        None,
    )
    values = list(values)
    if tuple_idx is None:
        return cast("Item", item_cls(*values))
    _, nested_finfo = fields[tuple_idx]
    arm_classes = _is_item_union(nested_finfo.annotation)
    boundname_val = None
    if (
        fields
        and fields[-1][0] == "boundname"
        and len(values) > tuple_idx
        and isinstance(values[-1], str)
        and arm_classes is None
    ):
        boundname_val = values[-1]
        values = values[:-1]
    before = values[:tuple_idx]
    trailing = values[tuple_idx:]
    tuple_vals = (
        construct_union_item(trailing, arm_classes) if arm_classes is not None else tuple(trailing)
    )
    if boundname_val is not None:
        return cast("Item", item_cls(*before, tuple_vals, boundname=boundname_val))
    return cast("Item", item_cls(*before, tuple_vals))


def _n_fixed_tokens(cls: type) -> int:
    """Fixed (non-cellid/aux/boundname, non-optional) token slots -- used to
    infer a variable-width cellid's element count from total token length."""
    cls = cast(type[Record], cls)
    n = 1 if cls.keyword() else 0
    for name, f in cls.fields().items():
        meta = f.json_schema_extra or {}
        if meta.get("cellid") or name in ("aux", "boundname"):
            continue
        if meta.get("optional"):
            continue
        n += 1 + (1 if meta.get("_keyword") else 0)
        if meta.get("direction"):
            n += 1
    return n


def ncelldim_from_dims(dims: "dict | None") -> "int | None":
    """Cellid element count implied by grid dimensions -- 3 for a
    structured (DIS) grid, 2 for vertex (DISV), 1 for unstructured (DISU).
    `None` if `dims` doesn't clearly say (or wasn't supplied), meaning the
    caller should fall back to inferring it from row width instead."""
    if not dims:
        return None
    if "nrow" in dims and "ncol" in dims:
        return 3
    if "ncpl" in dims:
        return 2
    if "nodes" in dims:
        return 1
    return None


def infer_ncelldim(
    items: list[list], item_cls: "type[Item]", *, naux: int = 0, dims: "dict | None" = None
) -> int:
    """Infer an Item class's cellid width, preferring grid dimensions
    (unambiguous) when available. Falls back to counting the first
    non-empty raw item's tokens -- total minus fixed columns minus aux
    minus a trailing boundname -- when `dims` isn't supplied or doesn't
    say; this heuristic overcounts if the row itself carries an extra
    trailing token the current Item class doesn't model (e.g. a field
    dropped from a newer DFN revision than the fixture predates)."""
    if _cellid_field(item_cls) is None:
        return 0
    from_dims = ncelldim_from_dims(dims)
    if from_dims is not None:
        return from_dims
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
        fields = cls.fields()
        keyword = cls.keyword()
        row: list[Any] = []
        keyword_emitted = not keyword
        for name, f in fields.items():
            if name in ("aux", "boundname"):
                continue
            val = getattr(self, name)
            if val is None:
                continue
            meta = f.json_schema_extra or {}
            if meta.get("cellid"):
                row.extend(int(c) + 1 for c in val)
            elif meta.get("index"):
                row.append(int(val) + 1)
            elif meta.get("array"):
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                row.extend(val)
            elif meta.get("tagged"):
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                if val:
                    row.append(name.upper())
            elif isinstance(val, Record):
                # Nested keystring-union field (OC's ocsetting) -- val is
                # already the resolved arm instance and knows how to
                # serialize itself.
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                row.extend(val.to_tokens())
            else:
                if not keyword_emitted:
                    row.append(keyword.upper())
                    keyword_emitted = True
                if file_kw := meta.get("_keyword"):
                    row.append(file_kw.upper())
                if direction := meta.get("direction"):
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
        fields = cls.fields()
        keyword = cls.keyword()
        keyword_skipped = not keyword
        has_boundname = _has_boundname_field(cls) and boundnames
        has_aux = _has_aux_field(cls)
        kwargs: dict[str, Any] = {}
        tok_idx = 0
        n = len(tokens)

        def consume(name: str, f: Any) -> None:
            nonlocal tok_idx, keyword_skipped
            meta = f.json_schema_extra or {}
            if meta.get("cellid"):
                cellid = tuple(int(tokens[tok_idx + j]) - 1 for j in range(ncelldim))
                kwargs[name] = cellid
                tok_idx += ncelldim
                return
            if meta.get("index"):
                kwargs[name] = int(float(str(tokens[tok_idx]))) - 1
                tok_idx += 1
                return
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            if meta.get("_keyword"):
                tok_idx += 1
            if meta.get("direction"):
                tok_idx += 1
            if tok_idx >= n:
                return
            kwargs[name] = _coerce(tokens[tok_idx], f)
            tok_idx += 1

        def width(f: Any) -> int:
            meta = f.json_schema_extra or {}
            w = 1 + (1 if meta.get("_keyword") else 0)
            if meta.get("direction"):
                w += 1
            return w

        main_fields = [(name, f) for name, f in fields.items() if name not in ("aux", "boundname")]
        nested_union_fields = [
            (name, f) for name, f in main_fields if _is_item_union(f.annotation) is not None
        ]
        main_fields = [item for item in main_fields if item not in nested_union_fields]
        array_fields = [
            (name, f) for name, f in main_fields if (f.json_schema_extra or {}).get("array")
        ]
        main_fields = [item for item in main_fields if item not in array_fields]
        required_fields = [
            (name, f) for name, f in main_fields if not (f.json_schema_extra or {}).get("optional")
        ]
        optional_fields = [
            (name, f) for name, f in main_fields if (f.json_schema_extra or {}).get("optional")
        ]

        for name, f in required_fields:
            consume(name, f)

        has_bn_token = False
        if has_boundname and n > tok_idx:
            last = tokens[-1]
            has_bn_token = isinstance(last, str) and not _token_fits(last, float)
        remaining = n - tok_idx - (1 if has_bn_token else 0) - (naux if has_aux else 0)

        budget_fields = [
            (name, f)
            for name, f in optional_fields
            if not (f.json_schema_extra or {}).get("tagged")
        ]
        n_opt_present = 0
        used = 0
        for name, f in budget_fields:
            w = width(f)
            if used + w > remaining:
                break
            used += w
            n_opt_present += 1

        budget_idx = 0
        for name, f in optional_fields:
            meta = f.json_schema_extra or {}
            if meta.get("tagged"):
                if not keyword_skipped:
                    tok_idx += 1
                    keyword_skipped = True
                kw = name.upper()
                if tok_idx < n and str(tokens[tok_idx]).upper() == kw:
                    kwargs[name] = str(tokens[tok_idx])
                    tok_idx += 1
                continue
            present = budget_idx < n_opt_present
            budget_idx += 1
            if present:
                consume(name, f)

        if array_fields:
            # Consumes everything left up to aux/boundname's own reserved
            # slots -- a keyword-plus-trailing-values setting (PRP's
            # Steps.steps/Fraction's leaf field: "n1 n2 ..."), coerced
            # numeric-or-string per token like aux (see below) since the
            # arity and type aren't fixed.
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            name, _f = array_fields[0]
            end = n - (1 if has_bn_token else 0) - (naux if has_aux else 0)
            vals = []
            while tok_idx < end:
                tok = tokens[tok_idx]
                try:
                    vals.append(float(tok))
                except (ValueError, TypeError):
                    vals.append(tok)
                tok_idx += 1
            kwargs[name] = tuple(vals)
        elif nested_union_fields:
            # Nested keystring-union field (OC's ocsetting) -- same span
            # logic as array_fields above, but dispatches a typed arm
            # instance instead of collecting a raw tuple.
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            name, f = nested_union_fields[0]
            arm_classes = _is_item_union(f.annotation)
            assert arm_classes is not None
            end = n - (1 if has_bn_token else 0) - (naux if has_aux else 0)
            nested_tokens = list(tokens[tok_idx:end])
            arm_cls = dispatch_union_item(nested_tokens, arm_classes)
            if arm_cls is None:
                raise ValueError(
                    f"{cls.__name__}.{name}: no matching arm in {arm_classes} "
                    f"for tokens {nested_tokens}"
                )
            kwargs[name] = arm_cls.from_tokens(nested_tokens)
            tok_idx = end
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


def _unwrap_skip_validation(t: Any) -> Any:
    """Strip one `Annotated[X, SkipValidation()]` layer, if present.

    Item-list fields are pydantic.SkipValidation-wrapped (codegen emits
    this -- see Package._init_item_lists' own docstring for why: pydantic
    validates an Item-list field's raw tuple/dict input eagerly by
    default, unlike attrs, which applies no validation there at all).
    get_origin() on the raw annotation returns Annotated, not dict/list,
    so the unwrapping below needs this extra step attrs never did.
    """
    if get_origin(t) is Annotated:
        return get_args(t)[0]
    return t


def item_list_type(field_type) -> "type[Item] | tuple[type[Item], ...] | None":
    """For Optional[list[C]] or Optional[dict[int, list[C]]] (each
    optionally SkipValidation-wrapped), return C (or the tuple of arm
    classes for a Union item type)."""
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    inner = _unwrap_skip_validation(inner)
    origin = get_origin(inner)
    if origin is list:
        return _unwrap_item(get_args(inner)[0])
    if origin is dict:
        _, val = get_args(inner)
        val = _unwrap_skip_validation(val)
        if get_origin(val) is list:
            return _unwrap_item(get_args(val)[0])
    return None


def dispatch_union_item(item: list, arm_classes: "tuple[type[Item], ...]") -> "type[Item] | None":
    """Find which arm class a raw token item belongs to, by its leading
    _keyword token."""
    kw_map = {c.keyword().upper(): c for c in arm_classes if c.keyword()}
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
    kw = arm_cls.keyword().upper()
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
