"""Item(Record): one row of a repeating tabular block (packagedata,
connectiondata, period data, ...).

Adds what Record doesn't need: index/pk/fk renumbering, cellid packing,
sized trailing columns, and external parse context (ncelldim/sizes/
enabled options -- facts about the surrounding list/package, not one row). An
inline array sized by the package (aux, by its ``auxiliary``) holds as many
values as the named package field has. A
tagged field here is always a bare presence flag (e.g. LAK tables' MIXED) --
unlike Record's tagged fields, which may carry a value.

An Item class MAY declare ``_keyword: ClassVar[str]`` when it's one arm
of a union (OC's Save/Print, LKT's Status/Concentration/...): several Item
subclasses share one list or field (a Union of their types), each
identified by its own keyword token (SAVE/PRINT, STATUS/CONCENTRATION/...).
"""

import ast
from collections.abc import Callable, Mapping
from functools import lru_cache, partial
from pathlib import Path
from typing import Any, ClassVar, Literal, Union, cast, get_args, get_origin

import attrs
import numpy as np

from flopy4.mf6._types import TimeSeriesRef
from flopy4.mf6.record import Record, _coerce, _resolve_sibling_class
from flopy4.spec import is_array
from flopy4.utils import unwrap_optional


def is_cellid(f: attrs.Attribute) -> bool:
    """Whether a field is a cellid, or an array of them (GNC's cellidsj)."""
    return f.metadata.get("type") == "cellid" or f.metadata.get("dtype") == "cellid"


def inline_dim(f: attrs.Attribute) -> str | None:
    """The dimension counting an inline array's values, or None if it has
    none (it takes the rest of the row)."""
    shape = f.metadata.get("shape") or ()
    return shape[0] if shape else None


def _is_one_cellid(f: attrs.Attribute) -> bool:
    """Whether a field is one cellid: one value in a row, of its grid's
    width."""
    return f.metadata.get("type") == "cellid"


def cellid_widths(rows: "list[Item]") -> dict[str, int]:
    """Each cellid column's width, by name, from the first of ``rows`` that
    gives it a cell."""
    widths: dict[str, int] = {}
    for row in rows:
        for f in type(row).fields():
            if f.name in widths or not is_cellid(f) or (val := getattr(row, f.name)) is None:
                continue
            cells = [val] if _is_one_cellid(f) else val
            if (cell := next((c for c in cells if c is not None), None)) is not None:
                widths[f.name] = len(cell)
    return widths


def _signed(f: attrs.Attribute) -> bool:
    return f.metadata.get("index") == "signed"


def _sized_by_field(cls: type, f: attrs.Attribute) -> bool:
    """Whether another field of the record sizes the inline array ``f`` (cell2d's
    icvert, by ncvert)."""
    return inline_dim(f) in attrs.fields_dict(cls)  # type: ignore[arg-type]


def _sized_by_lookup(f: attrs.Attribute) -> bool:
    """Whether the inline array ``f`` is sized by a field of the row another
    field refers to (SFR's ic, by packagedata.ncon(ifno)). A shape names a
    dim, which may be offset, or looks up a row: only a lookup has a call."""
    return bool((dim := inline_dim(f)) and "(" in dim)


def _sized_by_package(cls: type, f: attrs.Attribute) -> bool:
    """Whether a package field or dimension sizes the inline array ``f`` (aux,
    by auxiliary; GNC's cellidsj, by numalphaj; EVT's pxdp, by nseg-1)."""
    return inline_dim(f) is not None and not _sized_by_field(cls, f) and not _sized_by_lookup(f)


@lru_cache(maxsize=None)
def _counted_fields(cls: type) -> dict[str, attrs.Attribute]:
    """Count field name -> the inline array it counts (cell2d's ncvert ->
    icvert). Cached, since each row checks it; don't modify it."""
    return {
        inline_dim(f): f  # type: ignore[misc]
        for f in cast(type[Record], cls).fields()
        if _sized_by_field(cls, f)
    }


def _lookup(values: Mapping[str, Any], name: str) -> Any:
    """A field's value by name, at the top level or in a record (utl-ts's
    time_series_names, in its NAMES record)."""
    if (v := values.get(name)) is not None:
        return v
    for v in values.values():
        if isinstance(v, Record) and any(f.name == name for f in v.fields()):
            return getattr(v, name)
    return None


def dim_lookup(values: Mapping[str, Any], name: str) -> Any:
    """The value of a dim a shape names: the field of that name, or its length
    if it holds an array (aux's ``auxiliary``). None if it isn't set."""
    v = _lookup(values, name)
    return len(v) if hasattr(v, "__len__") else v


def package_sized_fields(cls: type) -> list[attrs.Attribute]:
    """An item class's inline arrays sized by a package field or dimension."""
    return [f for f in cast(type[Record], cls).fields() if _sized_by_package(cls, f)]


def sized_by(item_cls: "type[Item] | tuple[type[Item], ...]") -> set[str]:
    """The shape expressions of an item class's columns sized by the package."""
    classes = item_cls if isinstance(item_cls, tuple) else (item_cls,)
    return {inline_dim(f) or "" for c in classes for f in package_sized_fields(c)}


def conditional_fields(item_cls: "type[Item] | tuple[type[Item], ...]") -> dict[str, str]:
    """An item class's fields an option turns on (the DFN's ``when``), by
    name, to the option."""
    classes = item_cls if isinstance(item_cls, tuple) else (item_cls,)
    return {
        f.name: option
        for c in classes
        for f in cast(type[Record], c).fields()
        if (option := f.metadata.get("when"))
    }


def _may_be_absent(f: attrs.Attribute) -> bool:
    """Whether a field may be missing from a row."""
    return bool(f.metadata.get("optional") or f.metadata.get("when"))


@lru_cache(maxsize=None)
def _union_arms(
    cls: type, type_str: str
) -> "tuple[tuple[str, ...], tuple[type[Item], ...]] | None":
    """If a field's raw type annotation is a `` | ``-joined union of words
    and forward references to sibling Item classes (OC's ocsetting,
    ``"Literal['ALL', 'FIRST', 'LAST'] | Oc.Frequency | Oc.Steps"``, see
    make.py's _union_arm_specs), return its words and resolved classes;
    else None. Resolvability is itself the signal, same as record.py's
    _nested_class.

    Cached since to_tokens/from_tokens call this per field, often
    repeatedly while parsing many rows.
    """
    parts = type_str.split(" | ")
    if len(parts) < 2:
        return None
    words: list[str] = []
    classes: list[type[Item]] = []
    for part in parts:
        if part.startswith("Literal[") and part.endswith("]"):
            words.extend(ast.literal_eval(f"({part[len('Literal[') : -1]},)"))
            continue
        arm = _resolve_sibling_class(cls, part.rsplit(".", 1)[-1])
        if not (isinstance(arm, type) and issubclass(arm, Item)):
            return None
        classes.append(arm)
    return (tuple(words), tuple(classes)) if classes else None


def _union_field_arms(
    cls: type, f: attrs.Attribute
) -> "tuple[tuple[str, ...], tuple[type[Item], ...]] | None":
    """A field's words and arm classes, if it's a union with arm classes."""
    t = _field_type_str(f)
    # mypy false positive: type[Item] vs. Hashable (lru_cache arg)
    return _union_arms(cls, t) if t is not None else None  # type: ignore[arg-type]


def to_union_arm(value: Any, self: Any, f: attrs.Attribute) -> Any:
    """Convert a union field's value (OC's ocsetting, LKT's laksetting) to
    one of its words or arm instances: an arm's values build it by its
    keyword, ``("STATUS", "ACTIVE")`` a Status. Raises if no arm takes it."""
    if value is None or (arms := _union_field_arms(type(self), f)) is None:
        return value
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    if (converted := union_value(values, arms)) is None:
        raise ValueError(f"{type(self).__name__}.{f.name}: no arm of {f.type} takes {value!r}")
    return converted


def union_value(
    values: list,
    arms: "tuple[tuple[str, ...], tuple[type[Item], ...]]",
    context: "RowContext | None" = None,
) -> Any:
    """A union field's value from the user-supplied values it spans: one of
    its words, an arm instance given as is, or an arm built from them by
    its keyword (see construct_union_item)."""
    words, classes = arms
    if len(values) == 1:
        (value,) = values
        if isinstance(value, classes):
            return value
        if isinstance(value, str) and value.upper() in words:
            return value.upper()
    return construct_union_item(values, classes, context)


def _array_elem_type(f: attrs.Attribute) -> "type | None":
    """int or float for a ``tuple[int, ...]``/``tuple[float, ...]`` column
    (OC's STEPS), else None."""
    args = get_args(f.type)
    if len(args) == 2 and args[1] is Ellipsis and args[0] in (int, float):
        return args[0]
    return None


def _field_type_str(f: attrs.Attribute) -> "str | None":
    """attrs stubs type `Attribute.type` as `type | None`, but attrs
    actually stores the raw annotation there -- a string for a forward
    reference (every nested-sibling-union field). None otherwise."""
    t: Any = f.type
    return t if isinstance(t, str) else None


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


def _float_or_str(token: Any) -> Any:
    """A numeric token as a float, else (a time series name) as is."""
    try:
        return float(token)
    except (ValueError, TypeError):
        return token


def _ts_token(value: Any) -> Any:
    """A time-series reference as its name, the token MF6 reads; anything
    else as is."""
    return value.name if isinstance(value, TimeSeriesRef) else value


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


def _integral(token: Any) -> bool:
    try:
        return float(str(token)).is_integer()
    except ValueError:
        return False


def _read_unions(
    fields: list[attrs.Attribute],
    tokens: list,
    ncelldim: int,
    prefer: str,
    forms: "tuple[tuple[str, ...], ...] | None" = None,
) -> dict[str, Any]:
    """Read trailing untagged union columns, choosing each one's arm.

    ``forms``, if known, are the ones the row's observation type takes
    (see a package's ``observations``), each the kinds of the columns it
    fills, in order: the first form the tokens fit wins, and columns past
    it are absent. Otherwise guess: a non-numeric token is a string arm (a
    boundname). Numbers could be a cellid or an index: take the reading
    that uses every token, preferring the ``prefer`` arm (the parent's:
    indexes for a package keyed by one, e.g. LAK's lake number, or an
    exchange; cellids otherwise), so a row unlike its parent's (CSUB's
    cellid observations) still reads by its width. A number no arm fits is
    kept as is. Unknown grid width: any of 3, 2 or 1."""
    widths = (ncelldim,) if ncelldim else (3, 2, 1)

    def arms(kinds: tuple[str, ...], pos: int):
        """(value, width, cost) for each arm the tokens at pos can be."""
        tok = tokens[pos]
        numeric = _token_fits(tok, float)
        fits = False
        for kind in kinds:
            cost = 0 if kind == prefer else 1
            if kind == "string" and not numeric:
                yield str(tok), 1, 0
                fits = True
            elif kind in ("index", "integer") and _integral(tok):
                yield int(float(str(tok))) - (kind == "index"), 1, cost
                fits = True
            elif kind == "double" and numeric:
                yield float(tok), 1, cost
                fits = True
            elif kind == "cellid":
                for w in widths:
                    cell = tokens[pos : pos + w]
                    if len(cell) == w and all(_integral(t) for t in cell):
                        yield tuple(int(float(str(t))) - 1 for t in cell), w, cost
                        fits = True
        if numeric and not fits and forms is None:
            yield _float_or_str(tok), 1, 10

    def solve(i: int, pos: int, form: "tuple[str, ...] | None") -> "tuple[int, list] | None":
        if i == len(fields):
            return (0, []) if pos == len(tokens) else None
        if pos == len(tokens) or (form is not None and i == len(form)):
            # trailing optional columns may be absent, but not a form's
            ends = pos == len(tokens) and (i == len(form) if form else True)
            absent = ends and _may_be_absent(fields[i])
            return (0, [None] * (len(fields) - i)) if absent else None
        best = None
        kinds = fields[i].metadata["union"] if form is None else (form[i],)
        for value, w, cost in arms(kinds, pos):
            if (rest := solve(i + 1, pos + w, form)) is not None and (
                best is None or cost + rest[0] < best[0]
            ):
                best = (cost + rest[0], [value, *rest[1]])
        return best

    # Like MF6, ignore any tokens past what the columns take (a note after
    # a row, as in "1 1.0 (UZF CELL 1)").
    full = tokens
    for end in range(len(full), 0, -1):
        tokens = full[:end]
        for form in forms or (None,):
            if (solved := solve(0, 0, form)) is not None:
                return {f.name: v for f, v in zip(fields, solved[1]) if v is not None}
    if forms:  # ids its observation type doesn't take: guess
        return _read_unions(fields, full, ncelldim, prefer)
    names = ", ".join(f.name for f in fields)
    raise ValueError(f"can't read {names} from {full}")


def _union_tokens(val: Any, arms: tuple[str, ...]) -> list:
    """A union column's tokens: cellids and indexes 1-based."""
    if isinstance(val, tuple):
        return [int(c) + 1 for c in val]
    if isinstance(val, int) and "index" in arms:
        return [val + 1]
    return [val]


def _in_columns(cls: "type[Item]", fields: list[attrs.Attribute]) -> list[attrs.Attribute]:
    """Fields in the class's column order; any not listed go last."""
    columns = cls._columns
    return sorted(
        fields, key=lambda f: columns.index(f.name) if f.name in columns else len(columns)
    )


def _is_row_key(f: attrs.Attribute) -> bool:
    """A pk/fk or cellid column identifying the row (e.g. SFR's ifno, TVK's
    cellid). These precede a union arm's _keyword; every other field follows
    it, including other index columns (`ifno DIVERSION idv divflow`)."""
    return bool(f.metadata.get("pk") or f.metadata.get("fk") or is_cellid(f))


@attrs.frozen
class RowContext:
    """What a row's layout depends on besides its own values."""

    ncelldim: int | Mapping[str, int] | None = None
    sizes: Mapping[str, int] = attrs.field(factory=dict)
    enabled: frozenset[str] | None = None

    def cellid_width(self, f: attrs.Attribute) -> int | None:
        if isinstance(self.ncelldim, Mapping):
            return self.ncelldim.get(f.name)
        return self.ncelldim or None


@attrs.frozen
class _Slot:
    """A part of a row: a field, an arm's keyword, or untagged unions."""

    kind: str
    field: Any = None
    group: tuple = ()


def _kind(cls: type, f: attrs.Attribute) -> str:
    if f.metadata.get("tagged"):
        return "flag"  # a bare presence flag (LAK tables' MIXED)
    if _is_one_cellid(f):
        return "cellid"
    if is_array(f):
        if _sized_by_package(cls, f):
            return "sized"  # aux, by auxiliary
        if _sized_by_field(cls, f):
            return "sibling"  # cell2d's icvert, by ncvert
        return "rest"  # self-sizing, or sized by a lookup (SFR's ic)
    if _union_field_arms(cls, f) is not None:
        return "rest"  # OC's ocsetting
    return "value"


@lru_cache(maxsize=None)
def _slots(cls: type, file: bool) -> tuple[_Slot, ...]:
    """A row's slots, in column order."""
    fields = list(cast(type[Record], cls).fields())
    if cast(type[Item], cls)._columns:
        fields = _in_columns(cast(type[Item], cls), fields)
    unions = tuple(
        f for f in fields if (kinds := f.metadata.get("union")) and "keyword" not in kinds
    )
    slots = []
    keyword = file and bool(cast(type[Record], cls).keyword())
    for f in fields:
        if keyword and not _is_row_key(f):
            slots.append(_Slot("keyword"))
            keyword = False
        if f in unions:
            if f is unions[0]:
                slots.append(_Slot("unions", f, unions))
        else:
            slots.append(_Slot(_kind(cls, f), f))
    if keyword:
        slots.append(_Slot("keyword"))
    return tuple(slots)


def _is_seq(v: Any) -> bool:
    """Whether a Python value is a sequence, not a string."""
    return isinstance(v, (list, tuple)) or (isinstance(v, np.ndarray) and v.ndim > 0)


def _is_whole(v: Any) -> bool:
    """Whether a Python value is a whole field: a sequence, or None."""
    return v is None or _is_seq(v)


def _takes_sequence(f: attrs.Attribute) -> bool:
    """Whether a value field holds a sequence: a union with a cellid arm."""
    return "cellid" in (f.metadata.get("union") or ())


def _layout(
    cls: type,
    values: list,
    context: RowContext,
    *,
    file: bool,
    union_arm: str = "cellid",
    union_forms: Callable[[Mapping[str, Any]], Any] | None = None,
    load_child: Callable[[attrs.Attribute, str], Any] | None = None,
) -> dict[str, Any]:
    """Split a row's values into its fields, by position, as MF6 does.
    An unknown width (no grid yet) is solved from the value count, and
    raises if more than one fits."""
    out = _solve(cls, values, context, file=file)
    return _convert(cls, out, context, file, union_arm, union_forms, load_child)


def _solve(cls: type, values: list, context: RowContext, *, file: bool) -> dict[str, Any]:
    """What each field takes of a row's values (see `_layout`): its kind of
    value and the values, by field name."""
    n = len(values)
    slots = _slots(cls, file)
    gated = conditional_fields(cls)
    if context.enabled is None:
        off: frozenset[str] = frozenset()
        on: frozenset[str] = frozenset()
    else:
        off = frozenset(name for name, o in gated.items() if o not in context.enabled)
        on = frozenset(gated) - off

    def cellid_widths(f: attrs.Attribute, unknown: dict) -> list[tuple[int, dict]]:
        if (w := context.cellid_width(f)) is not None:
            return [(w, unknown)]
        key = ("ncelldim", f.metadata.get("model"))
        if key in unknown:
            return [(unknown[key], unknown)]
        return [(w, {**unknown, key: w}) for w in (3, 2, 1)]

    def flat(span: list) -> bool:
        """Whether values are a field's values, not whole fields."""
        return file or not any(_is_seq(x) or isinstance(x, Record) for x in span)

    def fits(slot: _Slot, pos: int, end: int, out: dict, unknown: dict, conditional: bool):
        """Each way the slot can take values from ``pos``."""
        f = slot.field
        left = end - pos
        v = values[pos] if left else None
        optional = f is not None and _may_be_absent(f)
        if conditional and f is not None:
            if f.name in off:
                yield pos, None, unknown
                return
            if f.name in on:
                optional = bool(f.metadata.get("optional"))
        if slot.kind == "keyword":
            if left and str(v).upper() == cast(type[Record], cls).keyword().upper():
                yield pos + 1, None, unknown
            return
        if slot.kind == "flag":
            if file and left and str(v).upper() == f.name.upper():
                yield pos + 1, ("flag", True), unknown
            elif not file and left and (v is None or isinstance(v, bool)):
                yield pos + 1, ("py", v), unknown
            else:
                yield pos, None, unknown
            return
        if slot.kind == "unions":
            if file:
                yield end, ("unions", values[pos:end], slot.group), unknown
                return
            required = sum(1 for g in slot.group if not _may_be_absent(g))
            for m in range(min(len(slot.group), left), required - 1, -1):
                yield pos + m, ("unions", values[pos : pos + m], slot.group), unknown
            return
        if not file and left and slot.kind != "value" and (_is_whole(v) or isinstance(v, Record)):
            yield pos + 1, ("py", v), unknown  # the whole field
            if optional:
                yield pos, None, unknown
            return
        if slot.kind == "value":
            w = (
                1
                if not file
                else 1 + bool(f.metadata.get("_keyword")) + bool(f.metadata.get("direction"))
            )
            if left >= w and (file or not _is_seq(v) or _takes_sequence(f)):
                yield pos + w, ("value", values[pos + w - 1]), unknown
        elif slot.kind == "cellid":
            if file and left and f.metadata.get("allow_zero") and str(v).upper() == "NONE":
                yield pos + 1, ("none", None), unknown  # MF6's deprecated form
            for w, unknown2 in cellid_widths(f, unknown):
                if left >= w and flat(values[pos : pos + w]):
                    yield pos + w, ("cellid", values[pos : pos + w]), unknown2
        elif slot.kind in ("sized", "sibling"):
            dim = inline_dim(f) or ""
            if slot.kind == "sibling":
                if (count := out.get(dim)) is None:
                    yield end, ("array", values[pos:end]), unknown  # the rest
                    return
                counts = [(int(float(str(count[1]))), unknown)]
            elif (count := context.sizes.get(dim)) is not None:
                counts = [(count, unknown)]
            elif file:
                if not optional:
                    raise ValueError(f"{cls.__name__}.{f.name}: {dim} unknown")
                counts = [(0, unknown)]
            elif ("size", dim) in unknown:
                counts = [(unknown[("size", dim)], unknown)]
            else:
                counts = [(c, {**unknown, ("size", dim): c}) for c in range(left, -1, -1)]
            for c, unknown2 in counts:
                widths = cellid_widths(f, unknown2) if is_cellid(f) else [(1, unknown2)]
                for w, unknown3 in widths:
                    if left >= c * w and flat(span := values[pos : pos + c * w]):
                        yield pos + c * w, ("array", span, w) if c else None, unknown3
            return
        elif slot.kind == "rest":
            yield end, ("rest", values[pos:end]) if left else None, unknown
            return
        if optional:
            yield pos, None, unknown

    # MVR's model names are all there or none are
    together = [
        s.field.name
        for s in slots
        if cast(type[Item], cls)._columns and s.kind == "value" and _may_be_absent(s.field)
    ]

    def walk(
        k: int, pos: int, end: int, out: dict, unknown: dict, surplus: bool, conditional: bool
    ):
        if k == len(slots):
            if len({name in out for name in together}) > 1:
                return
            if pos == end or (surplus and pos < end):
                yield out, unknown
            return
        slot = slots[k]
        for pos2, took, unknown2 in fits(slot, pos, end, out, unknown, conditional):
            out2 = out if took is None else {**out, slot.field.name: took}
            yield from walk(k + 1, pos2, end, out2, unknown2, surplus, conditional)

    def solve(surplus: bool = False, conditional: bool = True):
        yield from walk(0, 0, n, {}, {}, surplus, conditional)

    fields = attrs.fields_dict(cls)  # type: ignore[arg-type]

    def optionals(out: dict) -> int:
        """How many optional fields a layout has."""
        return sum(1 for k in out if k in fields and _may_be_absent(fields[k]))

    def first(solutions) -> "dict | None":
        """The first layout, or, if it assumed a width, the one with the
        fewest optional fields."""
        best = next(solutions, None)
        if best is None or not best[1]:
            return best and best[0]
        layouts = [best, *solutions]
        fewest = min(optionals(out) for out, _ in layouts)
        layouts = [(out, u) for out, u in layouts if optionals(out) == fewest]
        if len({tuple(sorted(u.items(), key=str)) for _, u in layouts}) > 1:
            raise ValueError(
                f"{cls.__name__}: can't tell the widths of {values} without the grid or "
                f"package; give each cellid and inline array as a tuple"
            )
        return layouts[0][0]

    out = first(solve())
    if out is None and not file and (off or on):
        out = first(solve(conditional=False))
    if out is None and file:
        out = first(solve(surplus=True))
    if out is None:
        raise ValueError(f"{cls.__name__}: can't read a row from {values}")
    return out


def _file_cellid(f: attrs.Attribute, tokens: list) -> tuple[int, ...] | None:
    cell = tuple(int(float(str(t))) - 1 for t in tokens)
    return None if f.metadata.get("allow_zero") and all(c == -1 for c in cell) else cell


def _file_array(f: attrs.Attribute, tokens: list) -> tuple:
    if _signed(f):
        return tuple(int(float(str(t))) for t in tokens)  # see spec.to_signed_indexes
    if f.metadata.get("index"):
        return tuple(int(float(str(t))) - 1 for t in tokens)
    if (elem := _array_elem_type(f)) is not None:
        return tuple(elem(float(str(t))) for t in tokens)
    return tuple(_float_or_str(t) for t in tokens)


@lru_cache(maxsize=None)
def _plannable(cls: type) -> bool:
    """Whether a file row's layout depends only on how many values it has,
    not what they are: it has no keyword, flag, count column or untagged
    unions, and no column that reads a child or a union arm (see `_plan`)."""
    for slot in _slots(cls, True):
        if slot.kind not in ("value", "cellid", "sized", "rest"):
            return False
        if slot.kind == "value" and slot.field.metadata.get("child"):
            return False
        if slot.kind == "rest" and _union_field_arms(cls, slot.field) is not None:
            return False
    return True


@lru_cache(maxsize=None)
def _row_plannable(cls: type) -> bool:
    """Whether a file row's layout depends only on how many values it has,
    as for `_plannable`, though it may also have an arm's keyword, an array
    counted by another column (DISV's icvert, by ncvert: a row of the same
    length has the same count), or end with a union of arms (SFR's
    sfrsetting) read by the arm its values name. Not tabular, so only for
    `Item.from_rows`."""
    for slot in _slots(cls, True):
        if slot.kind not in ("value", "cellid", "sized", "sibling", "rest", "keyword"):
            return False
        if slot.kind == "value" and slot.field.metadata.get("child"):
            return False
    return True


def _ts_value(token: Any) -> Any:
    """A time series column's token, as `_coerce` reads it: a number, or
    else a name."""
    try:
        return float(token)
    except (ValueError, TypeError):
        return str(token)


NumberKind = Literal["index", "int", "float", "series"]


@lru_cache(maxsize=None)
def number_kind(f: attrs.Attribute) -> NumberKind | None:
    """What a field's values are as numbers (a cellid's or an array's,
    each element): an index (1-based in a file, 0-based here; a cellid's
    elements too), an int, a float, or a time series' (a float, or else a
    series' name). None if they aren't numbers, or not one per element
    (signed indexes, see spec.to_signed_indexes). The readers and writers
    of a row's values, and of a table's columns, convert by it."""
    if is_array(f) and _signed(f):
        return None
    if is_cellid(f) or f.metadata.get("index"):
        return "index"
    if f.metadata.get("time_series"):
        return "series"
    t = _array_elem_type(f) if is_array(f) else unwrap_optional(f.type)
    if t in (int, "int"):
        return "int"
    if t in (float, "float") or (t is None and is_array(f)):
        return "float"
    return None


@lru_cache(maxsize=None)
def _value_reader(f: attrs.Attribute) -> Callable[[Any], Any]:
    """A file token to a scalar field's value, as `_convert` reads it."""
    kind = number_kind(f)
    if kind == "index":
        return lambda t: int(float(str(t))) - 1
    if kind == "series":
        return _ts_value
    if kind == "int":
        return lambda v: int(float(str(v)))
    if kind == "float":
        return float
    return lambda v: _coerce(v, f)


def _spans(
    cls: type, values: list, context: RowContext
) -> "list[tuple[attrs.Attribute | None, tuple, int, int]] | None":
    """Where each field of a file row with as many values as ``values`` is,
    which `_solve` lays out, for a class whose rows' layout depends only
    on that (see `_row_plannable`): the field, what it took, and its
    values' span (a scalar at ``a``, with ``b`` 0). An arm's keyword has
    no field and takes ``("keyword",)``."""
    out = _solve(cls, values, context, file=True)
    if any(took[0] == "none" for took in out.values()):
        return None
    spans: list[tuple[attrs.Attribute | None, tuple, int, int]] = []
    pos = 0
    for slot in _slots(cls, True):
        f = slot.field
        if slot.kind == "keyword":
            spans.append((None, ("keyword",), pos, 0))
            pos += 1
            continue
        if (took := out.get(f.name)) is None:
            continue
        if took[0] == "value":
            w = 1 + bool(f.metadata.get("_keyword")) + bool(f.metadata.get("direction"))
            spans.append((f, took, pos + w - 1, 0))
        else:
            w = len(took[1])
            spans.append((f, took, pos, pos + w))
        pos += w
    return spans


def _union_reader(
    cls: type,
    f: attrs.Attribute,
    context: RowContext,
    load_child: Callable[[attrs.Attribute, str], Any] | None,
) -> Callable[[list], Any]:
    """A union of arms' values to one of its words or arm instances, as
    `_convert` reads them, each arm by a plan per length (see `_plan`)."""
    arms = _union_field_arms(cls, f)
    assert arms is not None
    words, classes = arms
    by_keyword = {c.keyword().upper(): c for c in classes if c.keyword()}
    plans: dict[tuple[type, int], Callable[[list], dict[str, Any] | None] | None] = {}

    def read(raw: list) -> Any:
        if len(raw) == 1 and str(raw[0]).upper() in words:
            return str(raw[0]).upper()
        arm = next((c for t in raw if (c := by_keyword.get(str(t).upper()))), None)
        if arm is None:
            raise ValueError(f"{cls.__name__}.{f.name}: no arm of {f.type} reads {raw}")
        if (key := (arm, len(raw))) not in plans:
            try:
                plans[key] = _plan(arm, raw, context, load_child)
            except ValueError:
                plans[key] = None
        if (plan := plans[key]) is not None and (kwargs := plan(raw)) is not None:
            return arm(**kwargs)
        return arm.from_tokens(raw, context, load_child=load_child)

    return read


def _plan(
    cls: type,
    values: list,
    context: RowContext,
    load_child: Callable[[attrs.Attribute, str], Any] | None = None,
) -> "Callable[[list], dict[str, Any] | None] | None":
    """How to read the fields of a file row with as many values as
    ``values``, if every such row's layout is the same (see `_spans`).
    The reader returns None for a row it can't convert (a cellid of NONE,
    another arm's keyword), which `_layout` then reads."""
    if not _row_plannable(cls) or (spans := _spans(cls, values, context)) is None:
        return None
    readers: list[tuple[str, int, int, Callable[[Any], Any]]] = []
    # an array counted by another column: the count's position, and the count
    counts: list[tuple[int, int]] = []
    at = {f.name: a for f, took, a, _ in spans if f is not None and took[0] == "value"}
    for f, took, a, b in spans:
        read: Callable[[Any], Any]
        if f is not None and _sized_by_field(cls, f) and len(took) > 2:
            if (count_at := at.get(inline_dim(f) or "")) is None:
                return None
            counts.append((count_at, (b - a) // took[2]))
        if took[0] == "keyword":
            readers.append(
                ("", a, b, partial(_check_keyword, cast(type[Record], cls).keyword().upper()))
            )
            continue
        assert f is not None  # only a keyword's span has none
        if took[0] == "rest" and _union_field_arms(cls, f) is not None:
            read = _union_reader(cls, f, context, load_child)
        elif took[0] == "value":
            read = _value_reader(f)
        elif took[0] == "cellid":
            read = partial(_file_cellid, f)
        elif is_cellid(f):
            cw = took[2] if len(took) > 2 else 1
            read = partial(_file_cellids, f, cw)
        else:
            read = partial(_file_array, f)
        readers.append((f.name, a, b, read))

    def read_row(row: list) -> "dict[str, Any] | None":
        try:
            if any(int(float(str(row[a]))) != count for a, count in counts):
                return None
            kwargs = {name: read(row[a:b] if b else row[a]) for name, a, b, read in readers}
        except (ValueError, TypeError):
            return None
        kwargs.pop("", None)  # the keyword's
        return kwargs

    return read_row


def _check_keyword(keyword: str, token: Any) -> None:
    """Raise unless a token is the arm's keyword."""
    if str(token).upper() != keyword:
        raise ValueError(f"not {keyword}: {token}")


def _file_cellids(f: attrs.Attribute, width: int, tokens: list) -> tuple:
    return tuple(_file_cellid(f, tokens[i : i + width]) for i in range(0, len(tokens), width))


def _convert(
    cls: type,
    out: dict,
    context: RowContext,
    file: bool,
    union_arm: str,
    union_forms: Callable[[Mapping[str, Any]], Any] | None,
    load_child: Callable[[attrs.Attribute, str], Any] | None,
) -> dict[str, Any]:
    """The fields' values from what each took of the row."""
    fields = attrs.fields_dict(cls)  # type: ignore[arg-type]
    kwargs: dict[str, Any] = {}
    unions = None
    for name, took in out.items():
        f = fields[name]
        kind, raw = took[0], took[1]
        if kind == "unions":
            unions = took  # read last: their forms depend on the other columns
        elif kind == "py":
            kwargs[name] = raw
        elif kind == "flag":
            if raw is not None:
                kwargs[name] = raw
        elif kind == "none":
            kwargs[name] = None
        elif kind == "cellid":
            kwargs[name] = _file_cellid(f, raw) if file else tuple(raw)
        elif kind == "value":
            if not file:
                # a string column's value as text (a boundname given as 5)
                text = f.metadata.get("type") == "string" and isinstance(raw, (int, float))
                kwargs[name] = str(raw) if text and not isinstance(raw, bool) else raw
            elif f.metadata.get("child"):
                if load_child is None:
                    raise ValueError(f"{cls.__name__}.{name}: no way to load {raw}")
                kwargs[name] = load_child(f, str(raw))
            elif f.metadata.get("index"):
                kwargs[name] = int(float(str(raw))) - 1
            else:
                kwargs[name] = _coerce(raw, f)
        elif kind == "array":
            w = took[2] if len(took) > 2 else 1
            if is_cellid(f) and file:
                kwargs[name] = _file_cellids(f, w, raw)
            elif is_cellid(f):
                kwargs[name] = tuple(tuple(raw[i : i + w]) for i in range(0, len(raw), w))
            else:
                kwargs[name] = _file_array(f, raw) if file else tuple(raw)
        elif kind == "rest":
            arms = _union_field_arms(cls, f)
            if arms is None:
                kwargs[name] = _file_array(f, raw) if file else tuple(raw)
            elif not file:
                kwargs[name] = union_value(list(raw), arms)
            elif len(raw) == 1 and str(raw[0]).upper() in arms[0]:
                kwargs[name] = str(raw[0]).upper()
            elif (arm := dispatch_union_item(raw, arms[1])) is not None:
                kwargs[name] = arm.from_tokens(raw, context, load_child=load_child)
            else:
                raise ValueError(f"{cls.__name__}.{name}: no arm of {f.type} reads {raw}")
    if unions is not None:
        _, raw, group = unions
        if not file:
            kwargs.update({g.name: v for g, v in zip(group, raw) if v is not None})
        else:
            ncelldim = context.ncelldim if isinstance(context.ncelldim, int) else 0
            forms = union_forms(kwargs) if union_forms else None
            kwargs.update(_read_unions(list(group), raw, ncelldim, union_arm, forms))
    # arrays and cellids as tuples
    for name, v in kwargs.items():
        if _is_seq(v) and (is_array(fields[name]) or _is_one_cellid(fields[name])):
            kwargs[name] = tuple(x.item() if isinstance(x, np.generic) else x for x in v)
    return kwargs


class Item(Record):
    """Mixin for generated table-item types (plain items and union arms
    alike -- see module docstring)."""

    __slots__ = ()  # as Record's

    # Column order, when it differs from the field order (see from_tokens).
    _columns: ClassVar[tuple[str, ...]] = ()

    def __attrs_post_init__(self) -> None:
        """Fill each count field (cell2d's ncvert) from the array it counts,
        so an item compares equal whether it was built or loaded."""
        if not (counted := _counted_fields(type(self))):  # type: ignore[arg-type]  # lru_cache wants Hashable
            return
        columns = attrs.fields_dict(type(self))  # type: ignore[arg-type]
        for count_name, array_field in counted.items():
            if count_name not in columns:
                continue  # counted by a package dimension, not a column
            n = len(getattr(self, array_field.name))
            if (given := getattr(self, count_name)) is None:
                setattr(self, count_name, n)
            elif given != n:
                raise ValueError(
                    f"{type(self).__name__}.{count_name}={given} "
                    f"but {array_field.name} has {n} values"
                )

    def to_tokens(self, *, ncelldim: int | Mapping[str, int] | None = None) -> tuple:
        """index -> 1-based; cellid likewise per element. _keyword (if any)
        is emitted before the first non-row-key field.
        ``ncelldim`` is the cellid width, or each cellid column's, by name
        (see from_tokens), needed only to write a cellid of no cell as
        zeros; otherwise that of another of the row's cellids in the same
        grid.
        """
        cls = type(self)
        fields = cls.fields()
        if cls._columns:
            fields = _in_columns(cls, fields)
        keyword = cls.keyword()
        counted = _counted_fields(cls)  # type: ignore[arg-type]  # lru_cache wants Hashable
        row: list[Any] = []
        keyword_emitted = not keyword
        for f in fields:
            val = getattr(self, f.name)
            if f.name in counted:
                n = len(getattr(self, counted[f.name].name))
                if val is not None and val != n:
                    raise ValueError(
                        f"{cls.__name__}.{f.name}={val} but {counted[f.name].name} has {n} values"
                    )
                val = n
            if val is None and not (_is_one_cellid(f) and f.metadata.get("allow_zero")):
                if _is_one_cellid(f) and not _may_be_absent(f):
                    raise ValueError(f"{cls.__name__}.{f.name}: no cellid given")
                continue
            if not keyword_emitted and not _is_row_key(f):
                row.append(keyword.upper())
                keyword_emitted = True
            if _is_one_cellid(f):
                row.extend(self._cellid_tokens(f, val, ncelldim))
            elif is_cellid(f):
                row.extend(t for cell in val for t in self._cellid_tokens(f, cell, ncelldim))
            elif arms := f.metadata.get("union"):
                row.extend(_union_tokens(val, arms))
            elif is_array(f) and _signed(f):
                row.extend((int(i) + 1) * sign for i, sign in val)
            elif is_array(f) and f.metadata.get("index"):
                row.extend(int(v) + 1 for v in val)
            elif f.metadata.get("index"):
                row.append(int(val) + 1)
            elif is_array(f):
                row.extend(_ts_token(v) for v in val)
            elif f.metadata.get("tagged"):
                if val:
                    row.append(f.name.upper())
            elif isinstance(val, Record):
                # A union field's arm (OC's ocsetting, LKT's laksetting) --
                # val is already the resolved arm instance and knows how to
                # serialize itself.
                row.extend(val.to_tokens())
            elif _union_field_arms(cls, f) is not None:
                row.append(str(val).upper())  # one of its words (OC's ALL)
            else:
                if file_kw := f.metadata.get("_keyword"):
                    row.append(file_kw.upper())
                if direction := f.metadata.get("direction"):
                    row.append("FILEOUT" if direction == "out" else "FILEIN")
                if f.metadata.get("child"):
                    from flopy4.mf6.converter.egress.unstructure import _child_path

                    val = _child_path(val)
                row.append(val.as_posix() if isinstance(val, Path) else _ts_token(val))
        if not keyword_emitted:
            row.append(keyword.upper())
        return tuple(row)

    def _cellid_tokens(
        self,
        f: attrs.Attribute,
        cell: tuple[int, ...] | None,
        ncelldim: int | Mapping[str, int] | None,
    ) -> list[int]:
        """A cellid's tokens: its components 1-based, or, for no cell (None,
        if it may ``allow_zero``), a zero for each of its grid's."""
        if cell is not None:
            return [int(c) + 1 for c in cell]
        name = f"{type(self).__name__}.{f.name}"
        if not f.metadata.get("allow_zero"):
            raise ValueError(f"{name}: no cellid given")
        width = ncelldim if isinstance(ncelldim, int) else (ncelldim or {}).get(f.name)
        if not width:
            # another cellid of the row, in the same grid
            model = f.metadata.get("model")
            cells = [
                c
                for g in type(self).fields()
                if is_cellid(g) and g.metadata.get("model") == model
                for v in [getattr(self, g.name)]
                for c in (v if not _is_one_cellid(g) and v is not None else [v])
            ]
            width = next((len(c) for c in cells if c is not None), None)
        if not width:
            raise ValueError(f"{name}: no cell, but the grid's ncelldim is unknown")
        return [0] * width

    @classmethod
    def from_tokens(  # type: ignore[override]
        cls,
        tokens: "str | list",
        context: RowContext | None = None,
        *,
        union_arm: str = "cellid",
        union_forms: Callable[[Mapping[str, Any]], Any] | None = None,
        load_child: Callable[[attrs.Attribute, str], Any] | None = None,
    ) -> "Item":
        """An item from a file row's tokens."""
        values = tokens.split() if isinstance(tokens, str) else list(tokens)
        kwargs = _layout(
            cls,
            values,
            context or RowContext(),
            file=True,
            union_arm=union_arm,
            union_forms=union_forms,
            load_child=load_child,
        )
        return cls(**kwargs)

    @classmethod
    def from_rows(
        cls,
        rows: list,
        context: RowContext | None = None,
        *,
        union_arm: str = "cellid",
        union_forms: Callable[[Mapping[str, Any]], Any] | None = None,
        load_child: Callable[[attrs.Attribute, str], Any] | None = None,
    ) -> "list[Item]":
        """Items from a file block's rows, as `from_tokens` reads each. Rows
        of a tabular list (as most are: each the same number of values, in
        the same columns) are laid out once, by the first (see `_plan`)."""
        context = context or RowContext()
        plans: dict[int, Callable[[list], dict[str, Any] | None] | None] = {}
        items = []
        for tokens in rows:
            values = tokens.split() if isinstance(tokens, str) else tokens
            if (n := len(values)) not in plans:
                plans[n] = _plan(cls, values, context, load_child)
            if (plan := plans[n]) is not None and (kwargs := plan(values)) is not None:
                items.append(cls(**kwargs))
                continue
            items.append(
                cls.from_tokens(
                    values,
                    context,
                    union_arm=union_arm,
                    union_forms=union_forms,
                    load_child=load_child,
                )
            )
        return items

    @classmethod
    def from_values(cls, values: Any, context: RowContext | None = None) -> "Item":
        """An item from a row of Python values, flat or tupled: CHD's
        ``((0, 0, 0), 1.0)`` or ``(0, 0, 0, 1.0)``."""
        return cls(**_layout(cls, list(values), context or RowContext(), file=False))


def _unwrap_item(item) -> "type[Item] | tuple[type[Item], ...] | None":
    """A single Item subclass, or the tuple of arm subclasses for a Union
    item type."""
    if isinstance(item, type) and issubclass(item, Item):
        return item
    origin = get_origin(item)
    if origin is Union or origin is type(int | str):
        arms = tuple(a for a in get_args(item) if isinstance(a, type) and issubclass(a, Item))
        return arms or None
    return None


def _list_elem(field_type) -> Any:
    """For Optional[list[C]] or Optional[dict[int, list[C]]], C."""
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    origin = get_origin(inner)
    if origin is list:
        return get_args(inner)[0]
    if origin is dict:
        _, val = get_args(inner)
        if get_origin(val) is list:
            return get_args(val)[0]
    return None


def item_list_type(field_type) -> "type[Item] | tuple[type[Item], ...] | None":
    """For Optional[list[C]] or Optional[dict[int, list[C]]], return C (or
    the tuple of arm classes for a Union item type)."""
    elem = _list_elem(field_type)
    return None if elem is None else _unwrap_item(elem)


def item_list_words(field_type) -> tuple[str, ...]:
    """The words a list of unions' rows may be, besides its arm classes
    (PRP's ALL, FIRST and LAST)."""
    elem = _list_elem(field_type)
    return tuple(w for a in get_args(elem) if get_origin(a) is Literal for w in get_args(a))


def dispatch_union_item(item: list, arm_classes: "tuple[type[Item], ...]") -> "type[Item] | None":
    """Find which arm class a raw token item belongs to, by its leading
    _keyword token."""
    kw_map = {c.keyword().upper(): c for c in arm_classes if c.keyword()}
    for t in item:
        arm_cls = kw_map.get(str(t).upper())
        if arm_cls is not None:
            return arm_cls
    return None


def construct_union_item(
    values, arm_classes: "tuple[type[Item], ...]", context: "RowContext | None" = None
) -> "Item | None":
    """Build an Item from a flat user-supplied positional tuple for a union
    arm, e.g. ``(0, "STATUS", "ACTIVE")`` for LAK's Status.

    Dispatches to the right arm by keyword token, same as dispatch_union_item,
    then drops that token and builds the rest positionally via from_values
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
    return arm_cls.from_values(values, context)


def parse_union_items(
    items: list,
    arm_classes: "tuple[type[Item], ...]",
    *,
    words: tuple[str, ...] = (),
    context: RowContext | None = None,
    load_child: Callable[[attrs.Attribute, str], Any] | None = None,
) -> list | None:
    """Parse raw token items into Item instances, dispatching each by
    keyword (see dispatch_union_item), or into ``words`` (PRP's ``ALL``);
    unmatched items are skipped. ``load_child`` loads a child column's
    component (see from_tokens)."""
    if not items:
        return None
    result: list = []
    for item in items:
        if not item:
            continue
        if len(item) == 1 and (word := str(item[0]).upper()) in words:
            result.append(word)
            continue
        arm_cls = dispatch_union_item(item, arm_classes)
        if arm_cls is None:
            continue
        result.append(arm_cls.from_tokens(item, context, load_child=load_child))
    return result or None
