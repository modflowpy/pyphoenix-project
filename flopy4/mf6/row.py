"""Base class + helpers for generated MF6 list/table row types.

Companion to record.py's Record: where Record is one compound value with a
leading trigger keyword (e.g. an inner options-block record), Row is one row
of a repeating tabular block (packagedata, connectiondata, period data, ...).
There is no separate Schema/Column description -- a Row class's own attrs
fields, with metadata set via field()'s pk=/fk=/cellid=/time_series=/
prefix=/tagged= kwargs, ARE the schema. structure.py/unstructure.py
introspect the Row class directly via attrs.fields(), the same way
record.py's from_tokens/to_tokens already do for Record.

A Row class MAY also declare ``_keyword: ClassVar[str]`` -- this is the
keystring-union-arm case (e.g. LAK/SFR/MAW/UZF period settings, OC's
ocsetting): several Row subclasses share one field (a Python Union of
their types), each identified by its own leading MF6 keyword token
(STATUS/STAGE/RATE/...). Plain (non-union) Row classes simply omit
_keyword, in which case to_row/from_row behave exactly as for any other
tabular row.
"""

import re
import types
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import attrs

_AUX_KEY_RE = re.compile(r"^aux(\d+)$")


def normalize_aux_keys(row: dict) -> dict:
    """Collapse legacy per-column aux0/aux1/... dict keys into a single aux
    tuple key, matching the Row class's single `aux: tuple = ()` field
    (the old recarray dtype addressed aux values as separate named columns;
    Row uses one tuple field instead -- see module docstring)."""
    aux_items = []
    rest = {}
    for k, v in row.items():
        m = _AUX_KEY_RE.match(k)
        if m:
            aux_items.append((int(m.group(1)), v))
        else:
            rest[k] = v
    if aux_items:
        aux_items.sort(key=lambda kv: kv[0])
        rest["aux"] = tuple(v for _, v in aux_items)
    return rest


def _row_fields(cls: type) -> list[attrs.Attribute]:
    """Non-private fields of a Row class, in declaration order."""
    return [f for f in attrs.fields(cls) if not f.name.startswith("_")]


def _cellid_field(cls: type) -> attrs.Attribute | None:
    return next((f for f in _row_fields(cls) if f.metadata.get("cellid")), None)


def _has_aux_field(cls: type) -> bool:
    return any(f.name == "aux" for f in _row_fields(cls))


def _has_boundname_field(cls: type) -> bool:
    return any(f.name == "boundname" for f in _row_fields(cls))


def construct_row(row_cls: type, values) -> "Row":
    """Build a Row instance from a flat positional tuple/list.

    A Row with an ``aux`` field expects (in field-declaration order)
    required columns, then a *single* aux tuple, then optionally a trailing
    ``boundname`` -- but a flat user-supplied tuple carries aux values
    inline, one per position (e.g. ``(cellid, q, 35.0)`` for one aux
    variable, matching how the legacy per-column ``aux0``/``aux1`` dtype
    fields were addressed positionally), with no way to tell "these are 2
    aux values" from "this field has 2 values" by position/count alone.
    Everything from the aux field's position onward is treated as aux,
    except a trailing string when the row also has a ``boundname`` field --
    boundname is always declared last (see row_class()), and a string value
    there unambiguously isn't a numeric aux value.
    """
    fields = _row_fields(row_cls)
    aux_idx = next((i for i, f in enumerate(fields) if f.name == "aux"), None)
    values = list(values)
    if aux_idx is None:
        return row_cls(*values)
    boundname_val = None
    if (
        fields
        and fields[-1].name == "boundname"
        and len(values) > aux_idx
        and isinstance(values[-1], str)
    ):
        boundname_val = values[-1]
        values = values[:-1]
    before = values[:aux_idx]
    aux_vals = tuple(values[aux_idx:])
    if boundname_val is not None:
        return row_cls(*before, aux_vals, boundname=boundname_val)
    return row_cls(*before, aux_vals)


def _keyword_of(cls: type) -> str:
    return vars(cls).get("_keyword", "")


def _n_fixed_tokens(cls: type) -> int:
    """Count of fixed (non-cellid, non-aux, non-boundname) token slots a Row
    consumes -- used to infer a variable-width cellid's element count from a
    row's total token length. Prefix tokens (e.g. LAK tables' "TAB6 FILEIN")
    and a _keyword token count as extra fixed slots; optional fields (whether
    or not they're time_series, e.g. EVT's pxdp/petm/petm0, only written when
    surf_rate_specified) are not counted since they may be entirely absent
    from a given row."""
    n = 1 if _keyword_of(cls) else 0
    for f in _row_fields(cls):
        if f.metadata.get("cellid") or f.name in ("aux", "boundname"):
            continue
        if f.metadata.get("optional"):
            continue
        n += 1 + len(f.metadata.get("prefix", ()))
        if f.metadata.get("inout"):
            n += 1  # the FILEIN/FILEOUT token itself
    return n


def infer_ncelldim(rows: list[list], row_cls: type, *, naux: int = 0) -> int:
    """Infer a Row class's cellid width from the first non-empty raw row.

    Mirrors the token-counting the old Schema/Column-driven parser used:
    total tokens minus fixed columns minus aux minus a trailing boundname
    (if present) is the cellid's element count (2 for DISV, 3 for DIS, ...).
    """
    if _cellid_field(row_cls) is None:
        return 0
    first = next((r for r in rows if r), None)
    if not first:
        return 0
    n_fixed = _n_fixed_tokens(row_cls)
    last = first[-1]
    has_bn = isinstance(last, str) and not _token_fits(last, float)
    return max(1, len(first) - n_fixed - naux - (1 if has_bn else 0))


def _token_fits(token: Any, kind: type) -> bool:
    """True if token can be coerced to kind (int/float) -- used to tell a
    trailing boundname string apart from a trailing numeric value."""
    if isinstance(token, (int, float)):
        return True
    if isinstance(token, str):
        try:
            float(token)
            return True
        except ValueError:
            return False
    return False


def _coerce_scalar(token: Any, f: attrs.Attribute) -> Any:
    """Cast a raw token to a field's declared scalar type.

    time_series fields accept either a float or a time-series-name string
    (float() failure falls back to the raw string, matching how the old
    Column(dtype="np.object_", time_series=True) path worked).
    """
    if f.metadata.get("time_series"):
        try:
            return float(token)
        except (ValueError, TypeError):
            return str(token)
    t = f.type
    if t in (int, "int"):
        return int(float(str(token)))
    if t in (float, "float"):
        return float(token)
    if t in (Path, "Path"):
        return Path(token)
    return token


class Row:
    """Mixin for generated table-row types (plain rows and keystring-union
    arms alike -- see module docstring for the _keyword distinction)."""

    def to_row(self) -> tuple:
        """Serialize this row to an MF6 token tuple.

        pk/fk fields convert back to 1-based; cellid likewise, per element.
        If the class declares _keyword, that token is emitted immediately
        before the first non-index field (matching where MF6 places a
        keystring arm's discriminator: after any leading feature index,
        before the arm's own data). aux and boundname are always last.
        """
        cls = type(self)
        fields = _row_fields(cls)
        keyword = _keyword_of(cls)
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
            elif f.metadata.get("pk") or f.metadata.get("fk"):
                row.append(int(val) + 1)
            elif f.metadata.get("tagged"):
                # Inline optional keyword (e.g. MIXED): emit the token only
                # when truthy, same convention record.py's Record uses.
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
                if inout := f.metadata.get("inout"):
                    row.append("FILEOUT" if inout == "fileout" else "FILEIN")
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
    def from_row(
        cls, tokens: list, *, ncelldim: int = 0, naux: int = 0, boundnames: bool = False
    ) -> "Row":
        """Parse one raw token row into a Row instance (mirror of to_row).

        Required fields are always present and consumed unconditionally.
        Optional, non-tagged value columns (e.g. EVT's pxdp/petm/petm0) have
        no self-identifying marker token -- MF6 writes all of a package's
        such trailing columns together or none at all, gated by some
        OPTIONS-block flag (e.g. SURF_RATE_SPECIFIED), so presence can't be
        decided per-field by just checking "any tokens left" (that would
        misassign aux/boundname tokens to them when they're actually
        absent). Instead, the number present is inferred once from the
        total remaining token budget after reserving aux/boundname slots,
        then that many are taken off the front, in declared order. Tagged
        (inline_keyword) optional fields are self-describing -- they peek
        at their own keyword token -- and don't consume from that budget.
        """
        fields = _row_fields(cls)
        keyword = _keyword_of(cls)
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
            if f.metadata.get("pk") or f.metadata.get("fk"):
                kwargs[f.name] = int(float(str(tokens[tok_idx]))) - 1
                tok_idx += 1
                return
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            if prefix := f.metadata.get("prefix"):
                tok_idx += len(prefix)
            if f.metadata.get("inout"):
                tok_idx += 1  # skip the FILEIN/FILEOUT token itself
            if tok_idx >= n:
                return
            kwargs[f.name] = _coerce_scalar(tokens[tok_idx], f)
            tok_idx += 1

        def width(f: attrs.Attribute) -> int:
            w = 1 + len(f.metadata.get("prefix", ()))
            if f.metadata.get("inout"):
                w += 1
            return w

        main_fields = [f for f in fields if f.name not in ("aux", "boundname")]
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
        if not keyword_skipped:
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


def _unwrap_row_item(item) -> type | tuple[type, ...] | None:
    """A single Row subclass, or a tuple of Row subclasses for a Union
    (keystring-arm) item type -- e.g. ``LakStatusItem | LakStageItem``."""
    if isinstance(item, type) and issubclass(item, Row):
        return item
    origin = get_origin(item)
    if origin is Union or origin is types.UnionType:
        arms = tuple(a for a in get_args(item) if isinstance(a, type) and issubclass(a, Row))
        return arms or None
    return None


def row_list_type(field_type) -> type | tuple[type, ...] | None:
    """If field_type is Optional[list[C]] or Optional[dict[int, list[C]]],
    return C -- or, for a Union item type (keystring arms), the tuple of arm
    classes. The generated field's own type annotation is the schema now --
    no separate Schema/Column lookup."""
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    origin = get_origin(inner)
    if origin is list:
        return _unwrap_row_item(get_args(inner)[0])
    if origin is dict:
        _, val = get_args(inner)
        if get_origin(val) is list:
            return _unwrap_row_item(get_args(val)[0])
    return None


def dispatch_union_row(row: list, arm_classes: tuple[type, ...]) -> type | None:
    """Find which arm class a raw token row belongs to, by locating the
    first token that matches one of the arms' _keyword tokens."""
    kw_map = {_keyword_of(c).upper(): c for c in arm_classes if _keyword_of(c)}
    for t in row:
        arm_cls = kw_map.get(str(t).upper())
        if arm_cls is not None:
            return arm_cls
    return None


def parse_union_rows(
    rows: list, arm_classes: tuple[type, ...], *, naux: int = 0, boundnames: bool = False
) -> list | None:
    """Parse raw token rows into a list of Row instances, dispatching each
    row to the correct arm class by its keyword token (see
    dispatch_union_row). Rows matching no known keyword are skipped."""
    if not rows:
        return None
    result = []
    for row in rows:
        if not row:
            continue
        arm_cls = dispatch_union_row(row, arm_classes)
        if arm_cls is None:
            continue
        result.append(arm_cls.from_row(row, naux=naux, boundnames=boundnames))
    return result or None
