"""Item(Record): one row of a repeating tabular block (packagedata,
connectiondata, period data, ...).

Adds what Record doesn't need: index/pk/fk renumbering, cellid packing,
sized/boundname trailing columns, and external parse context (ncelldim/sizes/
boundnames -- facts about the surrounding list/package, not one row). A
sized column (``shape`` metadata, e.g. aux sized by the package's
``auxiliary``) holds as many values as the named package field has. A
tagged field here is always a bare presence flag (e.g. LAK tables' MIXED) --
unlike Record's tagged fields, which may carry a value.

An Item class MAY declare ``_keyword: ClassVar[str]`` for the
keystring-union-arm case (e.g. LAK/SFR/MAW/UZF period settings): several
Item subclasses share one field (a Union of their types), each identified
by its own leading keyword token (STATUS/STAGE/RATE/...).
"""

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Union, cast, get_args, get_origin

import attrs

from flopy4.mf6.record import Record, _coerce, _resolve_sibling_class


def _cellid_field(cls: type) -> attrs.Attribute | None:
    return next((f for f in cast(type[Record], cls).fields() if f.metadata.get("cellid")), None)


def _sized_field(cls: type) -> attrs.Attribute | None:
    """The column sized by a package field (its ``shape``, e.g. aux by
    ``auxiliary``), if any."""
    return next((f for f in cast(type[Record], cls).fields() if f.metadata.get("shape")), None)


def _size(cls: type, sizes: Mapping[str, int] | None) -> int:
    """How many tokens the class's sized column takes."""
    f = _sized_field(cls)
    return (sizes or {}).get(f.metadata["shape"][0], 0) if f is not None else 0


def sized_by(item_cls: "type[Item] | tuple[type[Item], ...]") -> set[str]:
    """Names of the package fields that size an item class's columns."""
    classes = item_cls if isinstance(item_cls, tuple) else (item_cls,)
    return {f.metadata["shape"][0] for c in classes if (f := _sized_field(c)) is not None}


def _counted_fields(cls: type) -> dict[str, attrs.Attribute]:
    """Count column name -> the array column it counts (cell2d's ncvert ->
    icvert)."""
    return {
        f.metadata["count"]: f for f in cast(type[Record], cls).fields() if f.metadata.get("count")
    }


def _dim_counted(cls: type, f: attrs.Attribute) -> bool:
    """An array column counted by a package dimension rather than another
    column (GNC's cellidsj, by numalphaj; EVT's pxdp, by nseg-1): fixed
    width, read in place."""
    count = f.metadata.get("count")
    if not isinstance(count, str) or not count:
        return False
    return count not in attrs.fields_dict(cls) and "(" not in count


def count_dim(count: str) -> tuple[str, int]:
    """Split a dimension count into the dimension and an offset:
    "nseg-1" -> ("nseg", -1)."""
    m = re.fullmatch(r"\s*(\w+)\s*(?:([+-])\s*(\d+))?\s*", count)
    if m is None:
        raise ValueError(f"invalid count: {count!r}")
    name, sign, k = m.groups()
    return name, (int(k) if sign == "+" else -int(k)) if k else 0


def _count(f: attrs.Attribute, sizes: Mapping[str, int] | None) -> int | None:
    """How many values a dimension-counted column takes, or None if the
    dimension isn't known."""
    name, offset = count_dim(f.metadata["count"])
    n = (sizes or {}).get(name)
    return None if n is None else n + offset


def _lookup(values: Mapping[str, Any], name: str) -> Any:
    """A field's value by name, at the top level or in a record (utl-ts's
    time_series_names, in its NAMES record)."""
    if (v := values.get(name)) is not None:
        return v
    for v in values.values():
        if isinstance(v, Record) and any(f.name == name for f in v.fields()):
            return getattr(v, name)
    return None


def resolve_dim(dim: str, exprs: Mapping[str, str], values: Mapping[str, Any]) -> int | None:
    """A counting dimension's value: the field of the same name, or as given
    in ``exprs`` (a component's ``count_dims``), e.g. utl-ts's
    "len(time_series_names)". None if the field isn't set."""
    expr = exprs.get(dim, dim)
    if m := re.fullmatch(r"len\((\w+)\)", expr):
        v = _lookup(values, m.group(1))
        return None if v is None else len(v)
    v = _lookup(values, expr)
    return None if v is None else int(v)


def dim_counted_fields(cls: type) -> list[attrs.Attribute]:
    """An item class's array columns counted by a package dimension."""
    return [f for f in cast(type[Record], cls).fields() if _dim_counted(cls, f)]


def counted_by(item_cls: "type[Item] | tuple[type[Item], ...]") -> set[str]:
    """Names of the package dimensions that count an item class's columns."""
    classes = item_cls if isinstance(item_cls, tuple) else (item_cls,)
    return {count_dim(f.metadata["count"])[0] for c in classes for f in dim_counted_fields(c)}


def _has_boundname_field(cls: type) -> bool:
    return any(f.name == "boundname" for f in cast(type[Record], cls).fields())


@lru_cache(maxsize=None)
def _nested_union_classes(cls: type, type_str: str) -> "tuple[type[Item], ...] | None":
    """If a field's raw type annotation is a `` | ``-joined forward
    reference to sibling Item classes (e.g. ``"Oc.All | Oc.First | ..."``,
    see make.py's _build_arm_specs_from_union), return the tuple of
    resolved classes; else None. Resolvability is itself the signal, same
    as record.py's _nested_class.

    Cached since to_tokens/from_tokens call this per field, often
    repeatedly while parsing many rows.
    """
    names = [part.strip().rsplit(".", 1)[-1] for part in type_str.split(" | ")]
    if len(names) < 2:
        return None
    resolved = [_resolve_sibling_class(cls, name) for name in names]
    if any(not (isinstance(r, type) and issubclass(r, Item)) for r in resolved):
        return None
    return tuple(cast("list[type[Item]]", resolved))


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


def construct_item(item_cls: type, values) -> "Item":
    """Build an Item from a flat positional tuple, e.g. ``(cellid, q, 35.0)``
    for one aux variable, or ``("HEAD", "FREQUENCY", 2)`` for OC's Save
    (rtype, ocsetting). Everything from the aux/array/nested-union field's
    position onward collects into that one field's value, except a
    trailing string when the class also has boundname (always declared
    last) -- a string there unambiguously isn't a numeric aux value.
    """
    fields = cast(type[Record], item_cls).fields()
    tuple_idx = next(
        (
            i
            for i, f in enumerate(fields)
            if f.metadata.get("shape")
            or (f.metadata.get("array") and not _dim_counted(item_cls, f))
            or (
                (t := _field_type_str(f)) is not None
                and _nested_union_classes(item_cls, t) is not None
            )
        ),
        None,
    )
    values = list(values)
    if tuple_idx is None:
        return cast("Item", item_cls(*values))
    nested_field = fields[tuple_idx]
    nested_field_type = _field_type_str(nested_field)
    arm_classes = (
        _nested_union_classes(item_cls, nested_field_type)
        if nested_field_type is not None
        else None
    )
    boundname_val = None
    if (
        fields
        and fields[-1].name == "boundname"
        and len(values) > tuple_idx
        and isinstance(values[-1], str)
        and arm_classes is None
    ):
        boundname_val = values[-1]
        values = values[:-1]
    before = values[:tuple_idx]
    trailing = values[tuple_idx:]
    if not trailing:
        # omitted optional columns before it, e.g. EVT's petm0 before aux
        return cast(
            "Item",
            item_cls(*before, boundname=boundname_val) if boundname_val else item_cls(*before),
        )
    if arm_classes is None and len(trailing) == 1 and isinstance(trailing[0], (list, tuple)):
        # The array given as one value, e.g. (0, 0.5, 0.5, 4, (0, 1, 4, 3)).
        trailing = list(trailing[0])
    tuple_vals = (
        construct_union_item(trailing, arm_classes) if arm_classes is not None else tuple(trailing)
    )
    if boundname_val is not None:
        return cast("Item", item_cls(*before, tuple_vals, boundname=boundname_val))
    return cast("Item", item_cls(*before, tuple_vals))


def _n_fixed_tokens(cls: type, sizes: Mapping[str, int] | None = None) -> tuple[int, int]:
    """Fixed (non-cellid/aux/boundname, non-optional) token slots, and the
    number of cellids -- used to infer a variable-width cellid's element
    count from total token length."""
    cls = cast(type[Record], cls)
    n = 1 if cls.keyword() else 0
    ncellids = 0
    for f in cls.fields():
        count = (_count(f, sizes) or 0) if _dim_counted(cls, f) else 1
        if f.metadata.get("cellid"):
            ncellids += count
            continue
        if f.metadata.get("shape") or f.name == "boundname":
            continue
        if f.metadata.get("optional"):
            continue
        n += count + (1 if f.metadata.get("_keyword") else 0)
        if f.metadata.get("direction"):
            n += 1
    return n, ncellids


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
    items: list[list],
    item_cls: "type[Item]",
    *,
    sizes: Mapping[str, int] | None = None,
    dims: "dict | None" = None,
) -> int:
    """Infer an Item class's cellid width, preferring grid dimensions
    (unambiguous) when available. Falls back to counting the first
    non-empty raw item's tokens -- total minus fixed columns minus sized
    minus a trailing boundname -- when `dims` isn't supplied or doesn't
    say; this heuristic overcounts if the row itself carries an extra
    trailing token the current Item class doesn't model (e.g. a field
    dropped from a newer DFN revision than the fixture predates)."""
    if _cellid_field(item_cls) is None:
        # A union column's cellid arm takes the grid's width, if known.
        return (ncelldim_from_dims(dims) or 0) if _union_fields(item_cls) else 0
    from_dims = ncelldim_from_dims(dims)
    if from_dims is not None:
        return from_dims
    first = next((r for r in items if r), None)
    if not first:
        return 0
    n_fixed, ncellids = _n_fixed_tokens(item_cls, sizes)
    last = first[-1]
    has_bn = isinstance(last, str) and not _token_fits(last, float)
    n_cell_tokens = len(first) - n_fixed - _size(item_cls, sizes) - (1 if has_bn else 0)
    return max(1, n_cell_tokens // max(1, ncellids))


def _float_or_str(token: Any) -> Any:
    """A numeric token as a float, else (a time series name) as is."""
    try:
        return float(token)
    except (ValueError, TypeError):
        return token


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


def _union_fields(cls: type) -> list[attrs.Attribute]:
    """Untagged union columns (OBS's id/id2), each holding any of its arms."""
    return [f for f in cast(type[Record], cls).fields() if f.metadata.get("union")]


def _integral(token: Any) -> bool:
    try:
        return float(str(token)).is_integer()
    except ValueError:
        return False


def _read_unions(
    fields: list[attrs.Attribute], tokens: list, ncelldim: int, prefer: str
) -> dict[str, Any]:
    """Read trailing untagged union columns, choosing each one's arm. A
    non-numeric token is a string arm (a boundname). Numbers could be a
    cellid or an index: take the reading that uses every token, preferring
    the ``prefer`` arm (the parent's: indexes for a package keyed by one,
    e.g. LAK's lake number, or an exchange; cellids otherwise), so a row
    unlike its parent's (CSUB's cellid observations) still reads by its
    width. A number no arm fits (UZF's water-content depth) is kept as is.
    Unknown grid width: any of 3, 2 or 1."""
    widths = (ncelldim,) if ncelldim else (3, 2, 1)

    def arms(f: attrs.Attribute, pos: int):
        """(value, width, cost) for each arm the tokens at pos can be."""
        tok = tokens[pos]
        numeric = _token_fits(tok, float)
        fits = False
        for kind in f.metadata["union"]:
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
        if numeric and not fits:
            yield _float_or_str(tok), 1, 10

    def solve(i: int, pos: int) -> "tuple[int, list] | None":
        if i == len(fields):
            return (0, []) if pos == len(tokens) else None
        if pos == len(tokens):
            # trailing optional columns may be absent
            return (0, [None] * (len(fields) - i)) if fields[i].metadata.get("optional") else None
        best = None
        for value, w, cost in arms(fields[i], pos):
            if (rest := solve(i + 1, pos + w)) is not None and (
                best is None or cost + rest[0] < best[0]
            ):
                best = (cost + rest[0], [value, *rest[1]])
        return best

    # Like MF6, ignore any tokens past what the columns take (a note after
    # a row, as in "1 1.0 (UZF CELL 1)").
    full = tokens
    for end in range(len(full), 0, -1):
        tokens = full[:end]
        if (solved := solve(0, 0)) is not None:
            return {f.name: v for f, v in zip(fields, solved[1]) if v is not None}
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
    return bool(f.metadata.get("pk") or f.metadata.get("fk") or f.metadata.get("cellid"))


class Item(Record):
    """Mixin for generated table-item types (plain items and keystring-union
    arms alike -- see module docstring)."""

    # Column order, when it differs from the field order (see from_tokens).
    _columns: ClassVar[tuple[str, ...]] = ()

    def __attrs_post_init__(self) -> None:
        """Fill each count column (cell2d's ncvert) from the array it counts,
        so an item compares equal whether it was built or loaded."""
        columns = attrs.fields_dict(type(self))  # type: ignore[arg-type]
        for count_name, array_field in _counted_fields(type(self)).items():
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

    def to_tokens(self) -> tuple:
        """index -> 1-based; cellid likewise per element. _keyword (if any)
        is emitted before the first non-row-key field. sized/boundname last.
        """
        cls = type(self)
        fields = cls.fields()
        if cls._columns:
            fields = _in_columns(cls, fields)
        sized = _sized_field(cls)
        keyword = cls.keyword()
        counted = _counted_fields(cls)
        row: list[Any] = []
        keyword_emitted = not keyword
        for f in fields:
            if f is sized or f.name == "boundname":
                continue
            val = getattr(self, f.name)
            if f.name in counted:
                n = len(getattr(self, counted[f.name].name))
                if val is not None and val != n:
                    raise ValueError(
                        f"{cls.__name__}.{f.name}={val} but {counted[f.name].name} has {n} values"
                    )
                val = n
            if val is None and not (f.metadata.get("cellid") and not f.metadata.get("array")):
                continue
            if not keyword_emitted and not _is_row_key(f):
                row.append(keyword.upper())
                keyword_emitted = True
            if f.metadata.get("cellid") and f.metadata.get("array"):
                row.extend(int(c) + 1 for cellid in val for c in cellid)
            elif f.metadata.get("cellid"):
                # see from_tokens' cellid()
                row.extend(["NONE"] if val is None else (int(c) + 1 for c in val))
            elif arms := f.metadata.get("union"):
                row.extend(_union_tokens(val, arms))
            elif f.metadata.get("array") and f.metadata.get("signed"):
                row.extend((int(i) + 1) * sign for i, sign in val)
            elif f.metadata.get("array") and f.metadata.get("index"):
                row.extend(int(v) + 1 for v in val)
            elif f.metadata.get("index"):
                row.append(int(val) + 1)
            elif f.metadata.get("array"):
                row.extend(val)
            elif f.metadata.get("tagged"):
                if val:
                    row.append(f.name.upper())
            elif isinstance(val, Record):
                # Nested keystring-union field (OC's ocsetting) -- val is
                # already the resolved arm instance and knows how to
                # serialize itself.
                row.extend(val.to_tokens())
            else:
                if file_kw := f.metadata.get("_keyword"):
                    row.append(file_kw.upper())
                if direction := f.metadata.get("direction"):
                    row.append("FILEOUT" if direction == "out" else "FILEIN")
                row.append(val.as_posix() if isinstance(val, Path) else val)
        if not keyword_emitted:
            row.append(keyword.upper())
        if sized is not None and (values := getattr(self, sized.name)):
            row.extend(values)
        boundname = getattr(self, "boundname", None)
        if boundname:
            row.append(boundname)
        return tuple(row)

    @classmethod
    def from_tokens(  # type: ignore[override]
        cls,
        tokens: list,
        *,
        ncelldim: int = 0,
        sizes: Mapping[str, int] | None = None,
        boundnames: bool = False,
        union_arm: str = "cellid",
    ) -> "Item":
        """Mirror of to_tokens. ``union_arm`` is the arm untagged union
        columns prefer for numbers (see _read_unions). Optional untagged columns (e.g. EVT's
        pxdp/petm/petm0) have no marker token -- MF6 writes a whole trailing
        group or none, gated by an unrelated OPTIONS flag -- so presence is
        inferred once from the token budget left after reserving sized/
        boundname, not per-field. Tagged optional fields self-identify by
        keyword and skip that budget.
        """
        fields = cls.fields()
        keyword = cls.keyword()
        keyword_skipped = not keyword
        has_boundname = _has_boundname_field(cls) and boundnames
        sized = _sized_field(cls)
        nsized = _size(cls, sizes)
        kwargs: dict[str, Any] = {}
        tok_idx = 0
        n = len(tokens)

        def cellid() -> tuple[int, ...] | None:
            nonlocal tok_idx
            # one NONE token, whatever ncelldim (e.g. an SFR reach with
            # no aquifer connection)
            if str(tokens[tok_idx]).upper() == "NONE":
                tok_idx += 1
                return None
            tok_idx += ncelldim
            return tuple(int(tokens[tok_idx - ncelldim + j]) - 1 for j in range(ncelldim))

        def consume(f: attrs.Attribute) -> None:
            nonlocal tok_idx, keyword_skipped
            if not keyword_skipped and not _is_row_key(f):
                tok_idx += 1
                keyword_skipped = True
            if _dim_counted(cls, f):
                count = _count(f, sizes)
                if count is None and not f.metadata.get("optional"):
                    raise ValueError(f"{cls.__name__}.{f.name}: {f.metadata['count']} unknown")
                if not count:
                    return
                if f.metadata.get("cellid"):
                    kwargs[f.name] = tuple(cellid() for _ in range(count))
                    return
                vals = tokens[tok_idx : tok_idx + count]
                tok_idx += count
                if f.metadata.get("index"):
                    kwargs[f.name] = tuple(int(float(str(v))) - 1 for v in vals)
                else:
                    kwargs[f.name] = tuple(_float_or_str(v) for v in vals)
                return
            if f.metadata.get("cellid"):
                kwargs[f.name] = cellid()
                return
            if f.metadata.get("index"):
                kwargs[f.name] = int(float(str(tokens[tok_idx]))) - 1
                tok_idx += 1
                return
            if f.metadata.get("_keyword"):
                tok_idx += 1
            if f.metadata.get("direction"):
                tok_idx += 1
            if tok_idx >= n:
                return
            kwargs[f.name] = _coerce(tokens[tok_idx], f)
            tok_idx += 1

        def width(f: attrs.Attribute) -> int:
            if _dim_counted(cls, f):
                return _count(f, sizes) or 0
            w = 1 + (1 if f.metadata.get("_keyword") else 0)
            if f.metadata.get("direction"):
                w += 1
            return w

        main_fields = [f for f in fields if f is not sized and f.name != "boundname"]
        nested_union_fields = [
            f
            for f in main_fields
            if (t := _field_type_str(f)) is not None
            # mypy false positive: type[Item] vs. Hashable (lru_cache arg)
            and _nested_union_classes(cls, t) is not None  # type: ignore[arg-type]
        ]
        main_fields = [f for f in main_fields if f not in nested_union_fields]
        union_fields = [f for f in main_fields if f.metadata.get("union")]
        main_fields = [f for f in main_fields if f not in union_fields]
        array_fields = [
            f for f in main_fields if f.metadata.get("array") and not _dim_counted(cls, f)
        ]
        main_fields = [f for f in main_fields if f not in array_fields]
        required_fields = [f for f in main_fields if not f.metadata.get("optional")]
        optional_fields = [f for f in main_fields if f.metadata.get("optional")]

        # An optional column before a required one (MVR's "mname1 pname1
        # id1 mname2 ...") means reading in column order, so the budget
        # comes from the required columns' widths instead. Those optional
        # columns come all together or not at all (MVR's MODELNAMES).
        columns = cls._columns
        if columns:
            optional_fields = _in_columns(cls, optional_fields)
            fixed = (0 if keyword_skipped else 1) + sum(
                ncelldim if f.metadata.get("cellid") else width(f) for f in required_fields
            )
        else:
            for f in required_fields:
                consume(f)
            fixed = tok_idx

        has_bn_token = False
        if has_boundname and n > fixed:
            last = tokens[-1]
            has_bn_token = isinstance(last, str) and not _token_fits(last, float)
        remaining = n - fixed - (1 if has_bn_token else 0) - nsized

        budget_fields = [f for f in optional_fields if not f.metadata.get("tagged")]
        n_opt_present = 0
        used = 0
        for f in budget_fields:
            w = width(f)
            if used + w > remaining:
                break
            used += w
            n_opt_present += 1
        if columns and n_opt_present < len(budget_fields):
            n_opt_present = 0

        budget_idx = 0
        ordered = (
            _in_columns(cls, required_fields + optional_fields) if columns else optional_fields
        )
        for f in ordered:
            if not f.metadata.get("optional"):
                consume(f)
                continue
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

        if union_fields:
            # The last columns, of varying width (see _read_unions).
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            end = n - (1 if has_bn_token else 0) - nsized
            kwargs.update(_read_unions(union_fields, tokens[tok_idx:end], ncelldim, union_arm))
            tok_idx = end
        elif array_fields:
            # Consumes everything left up to sized/boundname's own reserved
            # slots -- a keyword-plus-trailing-values setting (PRP's
            # Steps.steps/Fraction's leaf field: "n1 n2 ..."), coerced
            # numeric-or-string per token like aux (see below) since the
            # arity and type aren't fixed.
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            f = array_fields[0]
            end = n - (1 if has_bn_token else 0) - nsized
            if (count := kwargs.get(f.metadata.get("count", ""))) is not None:
                end = min(end, tok_idx + int(count))
            vals: list[Any] = []
            while tok_idx < end:
                tok = tokens[tok_idx]
                if f.metadata.get("signed"):
                    vals.append(int(float(str(tok))))  # see spec.to_signed_indexes
                elif f.metadata.get("index"):
                    vals.append(int(float(str(tok))) - 1)
                elif (elem := _array_elem_type(f)) is not None:
                    vals.append(elem(float(str(tok))))
                else:
                    try:
                        vals.append(float(tok))
                    except (ValueError, TypeError):
                        vals.append(tok)
                tok_idx += 1
            kwargs[f.name] = tuple(vals)
        elif nested_union_fields:
            # Nested keystring-union field (OC's ocsetting) -- same span
            # logic as array_fields above, but dispatches a typed arm
            # instance instead of collecting a raw tuple.
            if not keyword_skipped:
                tok_idx += 1
                keyword_skipped = True
            f = nested_union_fields[0]
            nested_field_type = _field_type_str(f)
            assert nested_field_type is not None
            arm_classes = _nested_union_classes(cls, nested_field_type)  # type: ignore[arg-type]
            assert arm_classes is not None
            end = n - (1 if has_bn_token else 0) - nsized
            nested_tokens = list(tokens[tok_idx:end])
            arm_cls = dispatch_union_item(nested_tokens, arm_classes)
            if arm_cls is None:
                raise ValueError(
                    f"{cls.__name__}.{f.name}: no matching arm in {arm_classes} "
                    f"for tokens {nested_tokens}"
                )
            kwargs[f.name] = arm_cls.from_tokens(nested_tokens)
            tok_idx = end
        elif not keyword_skipped:
            tok_idx += 1

        if sized is not None:
            sized_vals = []
            end = n - (1 if has_bn_token else 0)
            while tok_idx < end:
                tok = tokens[tok_idx]
                try:
                    sized_vals.append(float(tok))
                except (ValueError, TypeError):
                    sized_vals.append(tok)
                tok_idx += 1
            kwargs[sized.name] = tuple(sized_vals)

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
    items: list,
    arm_classes: "tuple[type[Item], ...]",
    *,
    sizes: Mapping[str, int] | None = None,
    boundnames: bool = False,
    dims: "dict | None" = None,
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
        ncelldim = infer_ncelldim([item], arm_cls, sizes=sizes, dims=dims)
        result.append(
            arm_cls.from_tokens(item, ncelldim=ncelldim, sizes=sizes, boundnames=boundnames)
        )
    return result or None
