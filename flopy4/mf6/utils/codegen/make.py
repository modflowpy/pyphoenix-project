"""
Generate Python source files from MODFLOW 6 DFN files.

All template context is pre-computed in Python (see filters.py) so that
Jinja templates stay thin and logic is easy to test and debug.

Sources from modflow_devtools.dfns (pydantic, schema 2.0.0.dev3) Component/
Block/Field objects. See namefile-load-plan.md, Phase 0.6a+0.6b, for the
migration history from the legacy modflow_devtools.dfn (flat TypedDict)
schema this replaces.
"""

import importlib.util
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dc_field
from os import PathLike
from pathlib import Path
from typing import Any

import jinja2
from modflow_devtools.dfns import dim_input, split_bound
from modflow_devtools.dfns.schema import (
    Array,
    Component,
    Double,
    File,
    Integer,
    Record,
    String,
    admits,
)
from modflow_devtools.dfns.schema import (
    Keyword as KeywordField,
)
from modflow_devtools.dfns.schema import (
    List as ListField,
)
from modflow_devtools.dfns.schema import (
    Union as UnionField,
)

from . import filters
from .filters import ColumnSpec, FieldV3, ItemColumn, _dq, item_class, pascal_name, python_repr

# Pre-computed context dataclasses


@dataclass
class FieldSpec:
    """Pre-computed context for a single DFN field."""

    dfn_name: str
    py_name: str
    type_annotation: str
    spec_call: str
    generatable: bool
    skip_reason: str | None = None


@dataclass
class InnerClassFieldSpec:
    """Pre-computed context for one field of an inner attrs class."""

    py_name: str
    type_annotation: str
    tagged: bool
    optional: bool
    nested: bool = False  # composes another generated Record class, see below


@dataclass
class InnerClassSpec:
    """Pre-computed context for a generated inner attrs class."""

    class_name: str
    keyword: str
    extra_tokens: list[str]
    extra_tokens_repr: str  # pre-formatted Python tuple literal, e.g. '("PRINT_FORMAT",)'
    fields: list[InnerClassFieldSpec]
    aliases_repr: str = ""  # the keyword's other spellings, formatted likewise


@dataclass
class BlockPropertySpec:
    """Pre-computed schema for one list (recarray) block property.

    Produced by build_component_spec for each block whose only field is an
    untagged list. Drives the Optional[list[ItemClass]] FieldSpec emitted
    per block in extra_specs.
    """

    block_name: str
    dim_attr: str  # Python name of the dim field
    dim_is_dfn_declared: bool  # False → synthetic (__dim__), not written to file
    columns: list[ColumnSpec]
    attr_name_map: dict[str, str]  # col_name → Python attr name (bare or block-prefixed)
    dim_bound: str | None = None  # shape's bound operator ("<="), None → exact


@dataclass
class ItemClassSpec:
    """Pre-computed context for one generated Item class: the element type
    of a list field, in any block (see _build_list_item_specs) -- a plain
    row (CHD's StressPeriodData, LAK's Packagedata), a keyword-led row (a
    tagged list's record), or one arm of a union (LAK's Stage/Rate/Status,
    OC's Saverecord/Printrecord).

    ``top_level`` is False for an arm built by recursing into another
    arm's own union-typed field (e.g. OC's ocsetting) -- still emitted as
    a flat sibling class, but excluded from the outer union alias.
    """

    class_name: str
    keyword: str  # lowercase, matches Record's _keyword convention; "" if none
    schema: list[ItemColumn]
    top_level: bool = True


@dataclass
class ItemUnionSpec:
    """A union list's element type alias (e.g. ``_StressPeriodDataItem =
    Stage | Rate | ...``), keeping the field annotation short."""

    alias: str
    members: list[str]


@dataclass
class BlockClassSpec:
    """A repeating block whose header is a record (OBS's ``CONTINUOUS
    FILEOUT <file> [BINARY]``), as a class holding the header record and
    the block's list: one instance per occurrence of the block."""

    class_name: str
    header: str  # the header record's field name
    header_class: str
    list_name: str
    list_elem: str


@dataclass
class ComputedFieldSpec:
    """Pre-computed context for a read-only computed property, replacing a
    stored attrs field entirely -- e.g. ``maxbound``, derived live from
    ``stress_period_data``'s row counts rather than stored and kept in
    sync by hand (see ``build_component_spec``'s ``_maxbound_is_computed``
    for when this applies)."""

    py_name: str
    source_field: str


@dataclass
class ComponentSpec:
    """Pre-computed context for a generated component class."""

    dfn_name: str
    class_name: str
    base_class: str
    mixins: list[str]
    multi: bool
    slntype: str | None
    imports: dict[str, list[str]]
    fields: list[FieldSpec]
    inner_classes: list[InnerClassSpec]
    outpath: Path
    block_properties: list[BlockPropertySpec] = dc_field(default_factory=list)
    item_classes: list[ItemClassSpec] = dc_field(default_factory=list)
    item_unions: list[ItemUnionSpec] = dc_field(default_factory=list)
    computed_fields: list[ComputedFieldSpec] = dc_field(default_factory=list)
    block_classes: list[BlockClassSpec] = dc_field(default_factory=list)
    # Derived dimensions that aren't fields, name -> DFN expression (DerivedDim)
    derived_dims: dict[str, str] = dc_field(default_factory=dict)
    # Dims counting item columns that aren't fields, name -> DFN expression
    # Observation types the component's OBS file takes, name -> id forms
    observations: dict[str, tuple[tuple[str, ...], ...]] = dc_field(default_factory=dict)
    has_griddata: bool = False
    has_readarray_period: bool = False
    # A model subpackage's __all__: the model and its packages
    exports: list[str] = dc_field(default_factory=list)


# Column-schema-dict builders
#
# Both static list blocks and standard (non-keystring) period blocks are
# List[Record] under dev3 -- including a real cellid Array field for period
# blocks, which the legacy schema had to synthesize. One function builds the
# list[dict] "schema" (the intermediate format item_class/schema_class render)
# for both cases; only the surrounding FieldSpec (type annotation, block=
# vs fill_forward= metadata) differs between them.


def _item_columns(
    columns: list[ColumnSpec],
    nested_arm_classes: "dict[str, list[str]] | None" = None,
    children: "Mapping[str, list[str]] | None" = None,
) -> list[ItemColumn]:
    """Build the rendered columns of an Item class from ColumnSpecs.

    File columns become path() fields; a preceding is_prefix column (e.g.
    SPC6) becomes its keyword. A file column ``children`` maps to the
    components it names (LAK's TAB6 file, a utl-laktab) holds them.
    is_row_keyword columns (optional keywords,
    e.g. MIXED) are tagged strings. An array column's shape expression is
    emitted as-is, for the runtime to evaluate.

    ``nested_arm_classes``, when given, maps a column name to sibling arm
    class names already built for it (see ``_build_arm_specs_from_union``)
    -- such a column is a nested union instead of the generic untyped-union
    array below.
    """
    nested_arm_classes = nested_arm_classes or {}
    children = children or {}
    items: list[ItemColumn] = []
    pending_prefix: list[str] = []
    names = {col.name for col in columns}
    # Each array column's count column, if the count is one of the row's
    # (cell2d's ncvert, for icvert): optional, and filled in from the
    # array's length when omitted.
    counted_by = {
        col.name: solved[0]
        for col in columns
        if (expr := _array_shape(col)) is not None
        and (solved := dim_input(expr, length=0)) is not None
        and solved[0] in names
    }
    counts = set(counted_by.values())
    for col in columns:
        if col.is_prefix:
            pending_prefix.append(col.name.upper())
            continue
        f = col.field
        name = col.name
        dfn_type = _dfn_type_str(f)
        optional = bool(f.optional) or name in counts
        ts = bool(getattr(f, "time_series", False))
        if isinstance(f, File):
            if len(pending_prefix) > 1:
                raise ValueError(
                    f"file column {name!r}: expected one keyword, got {pending_prefix}"
                )
            keyword = pending_prefix.pop().lower() if pending_prefix else None
            if targets := children.get(name):
                item = filters.child_column(
                    filters.module_name(targets[0]),
                    [filters.class_name(t) for t in targets],
                    f.direction,
                    keyword,
                    optional=optional,
                )
            else:
                item = filters.file_column(name, f.direction, keyword, optional=optional)
        elif pending_prefix:
            raise ValueError(f"fixed keyword(s) {pending_prefix} before non-file column {name!r}")
        elif (count := _array_shape(col)) is not None:
            item = filters.array_column(
                name,
                count,
                dfn_type,
                cellid=col.cellid,
                index=col.is_index and not col.is_cellid,
                signed=f.index == "signed",
                optional=optional or name in counted_by,
                time_series=ts,
            )
        elif col.is_cellid:
            item = filters.attr_column(
                name, "tuple", {"cellid": col.cellid}, optional=optional, time_series=ts
            )
        elif col.is_index:
            fk = getattr(f, "fk", None)
            pk = not fk and bool(getattr(f, "pk", False))
            item = filters.feature_id_column(name, fk=fk, pk=pk, optional=optional, time_series=ts)
        elif name == "boundname":
            item = filters.attr_column(name, "str", {}, optional=True)
        elif col.is_row_keyword:
            item = filters.attr_column(name, "str", {"tagged": True}, optional=True, time_series=ts)
        elif isinstance(f, UnionField) and not f.tagged:
            # One column, any of the arms (OBS's id: a cellid, an index or
            # a boundname), told apart when read (see Item.from_tokens).
            item = filters.union_column(
                name,
                tuple(_arm_kind(arm) for arm in f.arms.values()),
                optional=optional,
                time_series=ts,
            )
        elif isinstance(f, UnionField) and name in nested_arm_classes:
            item = filters.nested_union_column(name, nested_arm_classes[name], optional=optional)
        elif isinstance(f, UnionField) or (
            isinstance(f, Array) and not filters.is_fixed_length_array(f)
        ):
            item = filters.array_column(name, None, dfn_type)
        else:
            item = filters.value_column(
                name,
                dfn_type,
                optional=optional,
                time_series=ts,
                object_dtype=isinstance(f, String),
            )
        items.append(item)
    return items


def _arm_kind(arm: FieldV3) -> str:
    """An untagged union arm's kind: "cellid", "index", or its DFN type."""
    if isinstance(arm, Array) and arm.cellid:
        return "cellid"
    if getattr(arm, "index", False):
        return "index"
    kind = _dfn_type_str(arm)
    if kind not in ("integer", "double", "string"):
        raise ValueError(f"unsupported union arm {arm.name!r}: {type(arm).__name__}")
    return kind


def _obs_forms(f: FieldV3) -> list[tuple[str, ...]]:
    """The forms an observation type's ids take, each the kinds of the
    utl-obs columns it fills (see _arm_kind): UZF's water-content is
    ``[("index", "double"), ("string", "double")]``."""
    if isinstance(f, UnionField):
        return [form for arm in f.arms.values() for form in _obs_forms(arm)]
    if isinstance(f, Record):
        forms: list[tuple[str, ...]] = [()]
        for sub in (f.fields or {}).values():
            forms = [a + b for a in forms for b in _obs_forms(sub)]
        return forms
    return [(_arm_kind(f),)]


def _array_shape(col: ColumnSpec) -> str | None:
    """The shape expression counting an inline array column's values, or None
    for a column that isn't one (a cellid's first axis is ncelldim)."""
    f = col.field
    if not isinstance(f, Array):
        return None
    shape = f.shape or []
    counts = shape[1:] if col.is_cellid else shape
    return counts[0] if len(counts) == 1 and split_bound(counts[0])[0] is None else None


def _dfn_type_str(f: FieldV3) -> str:
    """DFN-type string for a leaf field, as used in the schema-dict format."""
    if isinstance(f, Integer):
        return "integer"
    if isinstance(f, Double):
        return "double"
    if isinstance(f, (String, File)):
        return "string"
    if isinstance(f, KeywordField):
        return "keyword"
    if isinstance(f, UnionField):
        # Unused for a nested-union column, which never consults dfn_type.
        return "object"
    return getattr(f, "dtype", "double")  # Array


# Context builders


# Fields named for their keyword rather than their DFN name: the model name
# files' NetCDF records (NETCDF_MESH2D FILEOUT <file>, NETCDF FILEIN <file>).
_PY_NAMES = {
    "nc_mesh2d_filerecord": "netcdf_mesh2d_file",
    "nc_structured_filerecord": "netcdf_structured_file",
    "nc_filerecord": "netcdf_input_file",
}


def _build_field_spec(
    f: FieldV3, block_name: str, linked_dims: frozenset[str] | set[str] = frozenset()
) -> FieldSpec:
    generatable = filters.is_generatable(f)
    # Strip 'record' suffix from file record names for a cleaner API
    # (e.g. head_filerecord → head_file, budget_filerecord → budget_file).
    # Compound records get the same treatment via _strip_record_words in
    # build_component_spec; this keeps the two paths consistent.
    if f.name in _PY_NAMES:
        py_name = _PY_NAMES[f.name]
    elif filters.is_file_record(f) or filters.is_file_list(f):
        py_name = filters.safe_name("_".join(_strip_record_words(f.name)))
    else:
        py_name = filters.safe_name(f.name)
    if generatable:
        spec_call_str = filters.field_call(f, block_name, linked_dim=py_name in linked_dims)
    else:
        spec_call_str = ""
    return FieldSpec(
        dfn_name=f.name,
        py_name=py_name,
        type_annotation=(filters.py_type(f, block_name) if generatable else "Any"),
        spec_call=spec_call_str,
        generatable=generatable,
        skip_reason=filters.skip_reason(f),
    )


def _expand_record_field(f: Record, block_name: str) -> tuple[list[FieldSpec], list[FieldV3]]:
    """Expand a compound record into FieldSpecs for its generatable children.

    Returns (field_specs, generatable_child_fields). field_specs contains one
    entry per expandable child plus an optional partial-TODO for any optional
    children that can't be generated standalone. generatable_child_fields is
    the corresponding list of Field objects used for import computation.
    """
    expandable: list[FieldV3] = []
    unexpandable_optional: list[str] = []

    for child in f.fields.values():
        if filters._is_expandable_child(child):
            expandable.append(child)
        elif child.optional:
            unexpandable_optional.append(child.name)
        # required unexpandable children were already blocked by can_expand_record

    specs: list[FieldSpec] = []
    gen_fields: list[FieldV3] = []
    for child in expandable:
        spec = _build_field_spec(child, block_name)
        specs.append(spec)
        if spec.generatable:
            gen_fields.append(child)

    if unexpandable_optional:
        specs.append(
            FieldSpec(
                dfn_name=f.name,
                py_name=filters.safe_name(f.name),
                type_annotation="Any",
                spec_call="",
                generatable=False,
                skip_reason=(
                    f"positional sub-fields not yet supported: {', '.join(unexpandable_optional)}"
                ),
            )
        )

    return specs, gen_fields


def _ml_field(
    default: str = "None",
    metadata: dict | None = None,
    *,
    fn: str = "field",
    alias: str | None = None,
    converter: str | None = None,
    repr_: bool = True,
    type_ignore: str | None = None,
) -> str:
    """Multi-line field()/path() spec-call string for class-body spec_calls.

    Produces continuation lines pre-indented at 8 spaces (args) and 4 spaces
    (closing paren) so the Jinja template can render it verbatim after
    ``    {name}: {type} = ``. ``metadata`` here is the set of ``field()``/
    ``path()`` kwargs (block, schema, fill_forward, ...), not a raw attrs
    metadata dict -- generated fields are plain attrs fields, so they go
    through the same passive-metadata constructors hand-written classes
    use for their scalar fields.
    """
    lines = [f"{fn}("]
    if alias is not None:
        lines.append(f'        alias="{alias}",')
    lines.append(f"        default={default},")
    if converter is not None:
        lines.append(f"        converter={converter},")
    if not repr_:
        lines.append("        repr=False,")
    if metadata is not None:
        for k, v in metadata.items():
            lines.append(f"        {k}={_dq(v)},")
    suffix = f"  {type_ignore}" if type_ignore else ""
    lines.append(f"    ){suffix}")
    return "\n".join(lines)


def _build_list_item_specs(
    list_field: ListField,
    class_name: str,
    used_names: set[str],
    children: "Mapping[str, list[str]] | None" = None,
) -> tuple[list[ItemClassSpec], str, ItemUnionSpec | None]:
    """Build the Item class(es) for a list's elements, wherever the list is
    (any block, repeating or not). Returns (classes, element type, union
    alias or None):

    - a union item (OC's output, LAK's period settings): one class per arm,
      dispatched by keyword, and a ``_<class_name>Item`` alias for the union
    - a tagged (keyword-led) record item: one class whose leading keyword is
      its ``_keyword``, built like a union arm
    - an untagged record item (packagedata, CHD's stress_period_data): one
      class of positional columns

    ``children`` maps the rows' child columns, by name, to the components
    they name (see _item_columns).
    """
    union = filters.find_keystring_union(list_field)
    if union is not None:
        item = list_field.item
        shared_cols: list[tuple[str, FieldV3]] = (
            [(n, f) for n, f in item.fields.items() if f is not union]
            if isinstance(item, Record)
            else []
        )
        specs = _build_arm_specs_from_union(
            union, used_names, {}, shared_cols, name_hint=list_field.name, children=children
        )
        alias = f"_{class_name}Item"
        members = [s.class_name for s in specs if s.top_level]
        return specs, alias, ItemUnionSpec(alias=alias, members=members)
    if list_field.tagged:
        specs = _build_arm_spec(
            list_field.name,
            list_field.item,
            used_names,
            {},
            [],
            class_name=class_name,
        )
        return specs, specs[-1].class_name, None
    schema = _item_columns(filters.list_columns(list_field), children=children)
    used_names.add(class_name)
    spec = ItemClassSpec(class_name=class_name, keyword="", schema=schema)
    return [spec], class_name, None


def _build_arm_specs_from_union(
    union: UnionField,
    used_names: set[str],
    nested_union_cache: "dict[tuple[str, ...], list[ItemClassSpec]]",
    shared_cols: "list[tuple[str, FieldV3]]" = [],
    *,
    name_hint: str = "",
    top_level: bool = True,
    children: "Mapping[str, list[str]] | None" = None,
) -> list[ItemClassSpec]:
    """Build one ItemClassSpec per arm of `union` (see _build_arm_spec).

    Handles all three index shapes seen in the corpus generically, via a
    shared prefix of columns prepended to every arm:
    - OC-style: the List's item IS the union directly (no index at all).
    - LAK-style: each arm embeds its own fk index (lakeno/outletno) as one
      of its own fields -- no shared prefix needed, it falls out of the
      arm's own fields.
    - SFR/MAW-style: the union is a sibling of an outer index field (item
      Record = {ifno, ...setting: Union}) -- shared by every arm.

    `nested_union_cache` (shared across the whole call tree) is keyed by a
    nested union's arm-name set, since DFN parsing builds each Record
    arm's fields independently -- OC's `saverecord.ocsetting` and
    `printrecord.ocsetting` are distinct `Union` objects with identical
    arms, and without the cache the second occurrence would rebuild and
    rename a duplicate set of classes instead of reusing the first's.
    """
    specs: list[ItemClassSpec] = []
    for arm_name, arm in union.arms.items():
        specs.extend(
            _build_arm_spec(
                arm_name,
                arm,
                used_names,
                nested_union_cache,
                shared_cols,
                name_hint=name_hint,
                top_level=top_level,
                children=children,
            )
        )
    return specs


def _build_arm_spec(
    arm_name: str,
    arm: FieldV3,
    used_names: set[str],
    nested_union_cache: "dict[tuple[str, ...], list[ItemClassSpec]]",
    shared_cols: "list[tuple[str, FieldV3]]",
    *,
    name_hint: str = "",
    top_level: bool = True,
    class_name: str = "",
    children: "Mapping[str, list[str]] | None" = None,
) -> list[ItemClassSpec]:
    """Build the keyword-led Item class for one union arm, or for a tagged
    list's record item -- each line starts with (or, LAK-style, contains)
    a keyword naming it. Returns any classes built for unions nested in it
    (OC's ocsetting, recursively exploded into its own typed sub-arms with
    `top_level=False` -- the DFN schema doesn't cap union nesting depth),
    then this one.
    """
    specs: list[ItemClassSpec] = []
    if isinstance(arm, Record):
        # The discriminating keyword isn't always the arm's first field --
        # LAK's auxiliaryrecord is (lakeno, auxiliary(kw), auxname, auxval),
        # its own per-arm index leading the keyword. Find the first
        # KeywordField anywhere; everything else (including any leading
        # index) is a real column. A second required keyword later (e.g.
        # SFR's cross_sectionrecord: cross_section(kw), tab6(kw), ...) is
        # left in `rest` and becomes its file column's keyword=, not _keyword.
        arm_fields = list(arm.fields.items())
        kw_idx = next(
            (i for i, (_, fld) in enumerate(arm_fields) if isinstance(fld, KeywordField)), None
        )
        if kw_idx is not None:
            keyword = arm_fields[kw_idx][0]
            rest = arm_fields[:kw_idx] + arm_fields[kw_idx + 1 :]
        else:
            keyword = "_".join(_strip_record_words(arm_name))
            rest = arm_fields
    elif isinstance(arm, KeywordField):
        # A bare keyword arm carries no data of its own (PRP's
        # releasesetting ALL/FIRST/LAST) -- the keyword IS the entire row.
        keyword = "_".join(_strip_record_words(arm_name))
        rest = []
    else:
        keyword = "_".join(_strip_record_words(arm_name))
        rest = [(arm_name, arm)]

    nested_arm_classes: dict[str, list[str]] = {}
    for field_name, fld in rest:
        if not isinstance(fld, UnionField):
            continue
        cache_key = tuple(sorted(fld.arms.keys()))
        cached = nested_union_cache.get(cache_key)
        if cached is None:
            cached = _build_arm_specs_from_union(
                fld,
                used_names,
                nested_union_cache,
                name_hint=field_name,
                top_level=False,
            )
            nested_union_cache[cache_key] = cached
            specs.extend(cached)
        nested_arm_classes[field_name] = [s.class_name for s in cached]

    cols = filters._fields_to_columns(list(shared_cols) + rest)
    schema = _item_columns(cols, nested_arm_classes, children)
    if not class_name:
        class_name = pascal_name("_".join(_strip_record_words(arm_name)))
        if class_name in used_names:
            class_name = pascal_name("_".join(_strip_record_words(name_hint))) + class_name
    used_names.add(class_name)
    specs.append(
        ItemClassSpec(class_name=class_name, keyword=keyword, schema=schema, top_level=top_level)
    )
    return specs


def _strip_record_words(name: str) -> list[str]:
    """Split a DFN field name and strip any trailing 'record' component.

    Works for both underscore-separated suffixes ('rewet_record' → ['rewet'])
    and concatenated suffixes ('rcloserecord' → ['rclose']). Returns a list of
    words suitable for joining as a field name or title-casing into a class name.
    """
    words = name.split("_")
    if words:
        last = words[-1].lower()
        if last == "record":
            words = words[:-1]
        elif last.endswith("record"):
            words[-1] = words[-1][: -len("record")]
    return [w for w in words if w]


_RECORD_LIST_CHILD_PY_TYPES: dict[str, str] = {"string": "str", "double": "float", "integer": "int"}


def _build_record_class_specs(
    f: Record, dfn_name: str, used_names: set[str], *, parent_hint: str = ""
) -> list[InnerClassSpec]:
    """Build InnerClassSpecs for a compound record field and any nested
    Record children, in dependency order (nested classes first, so a later
    class can reference an earlier one).

    When the first child is a keyword type it becomes the trigger token
    (``_keyword``) and is not emitted as a data field. When the first child
    is a required tagged scalar (IMS ``INNER_RCLOSE <value> ...``), its tag
    is the trigger token: it becomes ``_keyword`` and the child an untagged
    data field, so the record is found by its leading token like any other.
    Otherwise there is no trigger token (``_keyword = ""``) and all children
    become data fields.

    Required keyword children after the trigger are treated as fixed tokens
    (always emitted, not user-facing fields) stored in ``_extra_tokens``.
    Optional keyword children become Optional[bool] fields.

    A child that's itself a Record composes as its own class (recursing
    here) rather than flattening its fields into this one: the field gets a
    forward-reference string type annotation (qualified with the enclosing
    package class name, e.g. ``"Oc.Format"``, so mypy's scope analysis can
    resolve it too), since generated inner classes render as flat siblings
    inside the package class regardless of DFN nesting depth, and Python
    class bodies can't see sibling names at class-body-execution time.
    record.py's Record.from_tokens infers which fields are composed from
    that annotation directly (via _nested_class) -- no declared flag needed.
    `used_names` disambiguates two different fields whose nested child
    happens to share a name (e.g. two unrelated "formatrecord" wrappers) by
    prefixing the second with `parent_hint`.
    """
    children = list(f.fields.values())
    first = children[0]
    if isinstance(first, KeywordField):
        kw = first.name
        aliases = first.aliases
        data_children = children[1:]
    elif getattr(first, "tagged", False) and not first.optional:
        kw = first.name
        aliases = getattr(first, "aliases", None) or []
        data_children = children
    else:
        kw = ""
        aliases = []
        data_children = children

    extra_tokens: list[str] = []
    inner_fields: list[InnerClassFieldSpec] = []
    nested_specs: list[InnerClassSpec] = []

    def _process_child(child: FieldV3) -> None:
        is_optional = child.optional
        # a child whose tag is the trigger token is written after it, untagged
        tagged = getattr(child, "tagged", False) and child.name != kw

        if isinstance(child, Record):
            child_specs = _build_record_class_specs(child, dfn_name, used_names, parent_hint=f.name)
            nested_specs.extend(child_specs)
            inner_fields.append(
                InnerClassFieldSpec(
                    py_name=filters.safe_name(child.name),
                    type_annotation=child_specs[-1].class_name,  # bare; template qualifies it
                    tagged=False,
                    optional=is_optional,
                    nested=True,
                )
            )
        elif isinstance(child, KeywordField):
            if not is_optional:
                # Required keyword: always emitted as a fixed syntax token.
                extra_tokens.append(child.name.upper())
            else:
                # Optional keyword: user chooses whether to set it.
                inner_fields.append(
                    InnerClassFieldSpec(
                        py_name=filters.safe_name(child.name),
                        type_annotation="Optional[bool]",
                        tagged=tagged,
                        optional=True,
                    )
                )
        elif isinstance(child, Array):
            # Array nested in a record is always inline -- see is_record_list_field.
            elem_type = _RECORD_LIST_CHILD_PY_TYPES.get(child.dtype, "str")
            base_type = f"list[{elem_type}]"
            type_annotation = f"Optional[{base_type}]" if is_optional else base_type
            inner_fields.append(
                InnerClassFieldSpec(
                    py_name=filters.safe_name(child.name),
                    type_annotation=type_annotation,
                    tagged=tagged,
                    optional=is_optional,
                )
            )
        else:
            base_type = filters._SCALAR_PY_TYPES.get(type(child), "Any")
            type_annotation = f"Optional[{base_type}]" if is_optional else base_type
            inner_fields.append(
                InnerClassFieldSpec(
                    py_name=filters.safe_name(child.name),
                    type_annotation=type_annotation,
                    tagged=tagged,
                    optional=is_optional,
                )
            )

    for child in data_children:
        _process_child(child)

    # attrs requires fields with defaults to follow fields without defaults.
    inner_fields.sort(key=lambda field: str(field.optional))

    words = _strip_record_words(f.name)
    class_name = "".join(w.capitalize() for w in words) or "Record"
    if class_name in used_names and parent_hint:
        class_name = "".join(w.capitalize() for w in _strip_record_words(parent_hint)) + class_name
    used_names.add(class_name)
    extra_tokens_repr = (
        "(" + ", ".join(f'"{t}"' for t in extra_tokens) + ",)" if extra_tokens else ""
    )
    this_spec = InnerClassSpec(
        class_name=class_name,
        keyword=kw,
        extra_tokens=extra_tokens,
        extra_tokens_repr=extra_tokens_repr,
        fields=inner_fields,
        aliases_repr="(" + ", ".join(f'"{a}"' for a in aliases) + ",)" if aliases else "",
    )
    return nested_specs + [this_spec]


def _period_keystring_names(component: Component) -> frozenset[str]:
    """Names reserved by the period block's keystring keywords, if any.

    LAK-style keystring period settings (STATUS, STAGE, RATE, INVERT, ...)
    are consolidated into a single generic _stress_period_data field (see
    build_component_spec) -- no Python attribute is literally named e.g.
    "invert" for period data. But the same word is also a real static-block
    column name in some packages (LAK's outlets.invert), and a bare "invert"
    attr there would read ambiguously against the period keyword string of
    the same name. Static columns colliding with a period keystring keyword
    take a block-prefixed attr name instead (collision_names' `reserved`
    param) -- reproduces the legacy behavior, now sourced from the real
    Union.arms names instead of the extra_period_fields TOML override table
    (removed: no longer needed now that arms are schema-native).
    """
    for block_name in filters.fill_forward_blocks(component):
        for f in component.blocks[block_name].fields.values():
            if filters.is_list_field(f):
                union = filters.find_keystring_union(f)
                if union is not None:
                    return frozenset(name.lower() for name in union.arms)
    return frozenset()


def _build_block_property_specs(
    component: Component,
    *,
    reserved_names: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> tuple[list[BlockPropertySpec], set[str]]:
    """Compute BlockPropertySpec for all static (non-period) list blocks.

    Returns (specs, block_names) where block_names is used as a skip-set in
    the main field loop.
    """
    fill_forward_blocks = filters.fill_forward_blocks(component)
    list_fields_map: dict[str, FieldV3] = {}
    for block_name, block in (component.blocks or {}).items():
        if block_name in fill_forward_blocks:
            continue
        # An untagged list must be alone in its block, so it's the block's
        # only field; a tagged list is one field among the block's others
        # (see is_tagged_list).
        for f in block.fields.values():
            if f.name in skip:
                continue
            if filters.is_list_field(f) and not filters.is_tagged_list(f):
                list_fields_map[block_name] = f
                break

    col_schemas = {block: filters.list_columns(f) for block, f in list_fields_map.items()}
    collisions = filters.collision_names(col_schemas, reserved=reserved_names)

    # Resolve which DFN dimension scalar each block maps to: only through the
    # list's explicit shape (see filters.list_col_dim).
    dim_resolutions: dict[str, tuple[str, bool]] = {}
    for block_name, lf in list_fields_map.items():
        if dfn_dim := filters.list_col_dim(lf, component):
            dim_resolutions[block_name] = (dfn_dim, True)
        else:
            dim_resolutions[block_name] = (f"n{block_name}", False)

    specs: list[BlockPropertySpec] = []
    block_names: set[str] = set()
    for block_name, cols in col_schemas.items():
        dim_attr_raw, dim_is_dfn_declared = dim_resolutions[block_name]
        attr_name_map = {
            col.name: (
                filters.safe_name(f"{block_name}_{col.name}")
                if col.name in collisions
                else filters.safe_name(col.name)
            )
            for col in cols
            if not col.is_prefix
        }
        specs.append(
            BlockPropertySpec(
                block_name=block_name,
                dim_attr=filters.safe_name(dim_attr_raw),
                dim_is_dfn_declared=dim_is_dfn_declared,
                columns=cols,
                attr_name_map=attr_name_map,
                dim_bound=filters.list_dim_bound(list_fields_map[block_name]),
            )
        )
        block_names.add(block_name)

    return specs, block_names


def _generated_imports(
    generatable_fields: list[tuple[str, FieldV3]],
    *,
    base_class: str = "Package",
    mixins: list[str] | None = None,
    multi: bool = False,
    slntype: bool = False,
    has_inner_classes: bool = False,
    has_readarray_period: bool = False,
    needs_int_arraylike: bool = False,
    needs_float_arraylike: bool = False,
    has_field_call: bool = False,
    has_path_call: bool = False,
    has_child_call: bool = False,
    item_classes: "list[ItemClassSpec] | None" = None,
    has_derived_dims: bool = False,
    has_optional_child: bool = False,
    has_union_child: bool = False,
    extra_imports: list[str] | None = None,
) -> dict[str, list[str]]:
    """Compute import lines for generated packages."""
    # numeric arrays → Int/FloatArrayLike, not NDArray[np.xxx]
    has_array = any(
        filters.is_keyword_array(f) or filters.is_aux_list_field(f) for _, f in generatable_fields
    )
    has_file_records = any(filters.is_file_record(f) for _, f in generatable_fields)
    has_file_lists = any(filters.is_file_list(f) for _, f in generatable_fields)
    has_optional = (
        any(f.optional and not isinstance(f, KeywordField) for _, f in generatable_fields)
        or has_inner_classes
        or bool(item_classes)
        or has_readarray_period
        or has_optional_child
    )
    # dfn_name is always emitted as a ClassVar (see package.py.jinja), so
    # ClassVar is always needed regardless of multi/slntype/inner classes.
    has_classvar = True
    # Union[float, str] is used by item_class() for time_series and np.object_ columns.
    # Check every generated Item class's columns.
    _all_schema_cols = [col for ic in (item_classes or []) for col in ic.schema]
    has_union = has_union_child or any(col.uses_union for col in _all_schema_cols)
    # File row columns become Path fields, not Union[float, str].
    has_row_path_cols = any(col.uses_path for col in _all_schema_cols)
    # Row class fields with cellid=/pk=/fk=/tagged=/time_series= metadata use
    # field(), same as any other generated field -- checked separately from
    # has_field_call since these live inside item_class()'s rendered text, not
    # in the package's own top-level field_specs.
    _row_has_field_call = any(col.uses_field for col in _all_schema_cols)

    stdlib: list[str] = []
    if has_file_records or has_file_lists or has_row_path_cols:
        stdlib.append("from pathlib import Path")
    typing_parts: list[str] = []
    if has_classvar:
        typing_parts.append("ClassVar")
    if has_optional:
        typing_parts.append("Optional")
    if has_union:
        typing_parts.append("Union")
    if typing_parts:
        stdlib.append(f"from typing import {', '.join(sorted(typing_parts))}")

    third_party: list[str] = ["import attrs"]
    if has_array:
        third_party.append("import numpy as np")
        third_party.append("from numpy.typing import NDArray")

    _base_imports = {
        "Package": "from flopy4.mf6.package import Package",
        "Solution": "from flopy4.mf6.solution import Solution",
        "Context": "from flopy4.mf6.context import Context",
        "Exchange": "from flopy4.mf6.exchange import Exchange",
        "Model": "from flopy4.mf6.model import Model",
    }
    flopy4: list[str] = [_base_imports.get(base_class, _base_imports["Package"])]
    for mixin in mixins or []:
        module, name = mixin.split(":")
        flopy4.append(f"from {module} import {name}")
    if has_derived_dims:
        flopy4.append("from flopy4.dimensions import DerivedDim")
    flopy4.extend(extra_imports or [])
    if has_inner_classes:
        flopy4.append("from flopy4.mf6.record import Record")
    if item_classes:
        flopy4.append("from flopy4.mf6.item import Item")
    _spec_parts: list[str] = []
    if has_field_call or _row_has_field_call:
        _spec_parts.append("field")
    if has_path_call or has_row_path_cols:
        _spec_parts.append("path")
    if has_child_call or any(col.uses_child for col in _all_schema_cols):
        _spec_parts.append("child")
    if _spec_parts:
        flopy4.append(f"from flopy4.mf6.spec import {', '.join(sorted(_spec_parts))}")
    _types_parts: list[str] = []
    if needs_int_arraylike:
        _types_parts.append("IntArrayLike")
    if needs_float_arraylike:
        _types_parts.append("FloatArrayLike")
    _converters = " ".join(c for b, f in generatable_fields if (c := filters.field_converter(f, b)))
    _types_parts += [fn for fn in ("to_array", "to_list") if f"{fn}(" in _converters]
    if "to_array(" in _converters:
        _types_parts.append("ARRAY_EQ")
    if _types_parts:
        flopy4.append(f"from flopy4.mf6._types import {', '.join(sorted(_types_parts))}")
    # merge lines importing from the same module
    names: dict[str, list[str]] = {}
    for line in flopy4:
        module, _, imported = line.removeprefix("from ").partition(" import ")
        names.setdefault(module, []).extend(n for n in imported.split(", ") if n)
    flopy4 = sorted(
        f"from {m} import {', '.join(sorted(set(ns), key=lambda n: (n[0].islower(), n)))}"
        for m, ns in names.items()
    )

    return {"stdlib": stdlib, "third_party": third_party, "flopy4": flopy4}


_SLN_PREFIX = "sln"

# flopy API methods (factories, conversions to and from flopy types) for
# generated classes, as "module:Class" method-only mixins. Mixins declare no
# fields; those come from the DFN only.
_GRID_DIMS = ["flopy4.mf6.grid_dims_methods:GridDimsMethods"]
_DIS = ["flopy4.mf6.dis_methods:DisMethods", *_GRID_DIMS]
_DISV = ["flopy4.mf6.disv_methods:DisvMethods", *_GRID_DIMS]
_DISU = ["flopy4.mf6.disu_methods:DisuMethods", *_GRID_DIMS]
_MODEL = ["flopy4.mf6.model_methods:ModelMethods"]
MIXINS: dict[str, list[str]] = {
    "sim-nam": ["flopy4.mf6.simulation_methods:SimulationMethods"],
    "gwf-nam": ["flopy4.mf6.gwf_methods:GwfMethods", *_MODEL],
    "gwt-nam": _MODEL,
    "gwe-nam": _MODEL,
    "prt-nam": _MODEL,
    "sim-tdis": ["flopy4.mf6.tdis_methods:TdisMethods"],
    "utl-ncf": ["flopy4.mf6.utl.ncf_methods:NcfMethods"],
    # Grid packages provide the model's dimensions. Which components do
    # can't be told from the DFN (maxbound and friends are model-scoped too).
    "gwf-dis": _DIS,
    "gwf-disv": _DISV,
    "gwf-disu": _DISU,
    "gwt-dis": _DIS,
    "gwt-disv": _DISV,
    "gwt-disu": _DISU,
    "gwe-dis": _DIS,
    "gwe-disv": _DISV,
    "gwe-disu": _DISU,
    "prt-dis": _DIS,
    "prt-disv": _DISV,
    "chf-disv1d": _GRID_DIMS,
    "olf-dis2d": _GRID_DIMS,
    "olf-disv1d": _GRID_DIMS,
    "olf-disv2d": _GRID_DIMS,
}


def check_mixins(dfns: Mapping[str, Component]) -> None:
    """Raise if a `MIXINS` key names no DFN component."""
    if unknown := sorted(set(MIXINS) - set(dfns)):
        raise ValueError(f"MIXINS keys match no DFN component: {unknown}")


def _find_link(f: FieldV3) -> tuple[str, File, bool] | None:
    """The first linked file in a top-level field (itself, a record's member
    or a list's column), its path, and whether the rest of its record or row
    is just the file's keyword."""
    members: dict[str, FieldV3] = {f.name: f}
    record = f.item if isinstance(f, ListField) else f
    if isinstance(record, Record):
        members |= {f"{f.name}.{n}": m for n, m in (record.fields or {}).items()}
    for path, m in members.items():
        if isinstance(m, File) and m.component:
            rest = [o for o in members.values() if o is not m and o is not f]
            return path, m, all(isinstance(o, KeywordField) for o in rest)
    return None


def _is_child_of(child: Component, parent: Component) -> bool:
    """Whether a component may sit under another: its ``parent`` selector
    names the other, or its type (``model``, ``package``) or subtype."""
    return admits(child.parent, parent)


def resolve_link(
    component: Component,
    path: str,
    link: File,
    dfns: Mapping[str, Component] | None,
    by_content: bool = False,
) -> list[str]:
    """The concrete components a link can target. Several need a
    component_ftype to pick one, unless the file's content does
    (``by_content``: SSM's SPC6 file is a utl-spca if it reads arrays)."""
    assert link.component is not None
    selectors = [link.component] if isinstance(link.component, str) else link.component
    found: list[str] = []
    for sel in selectors:
        if "-" in sel:  # a concrete name; utilities' DFN parents aren't reliable
            found.append(sel)
            continue
        if dfns is None:
            raise ValueError(f"{component.name}.{path}: resolving {sel!r} needs the DFNs")
        found += [
            n
            for n, c in dfns.items()
            if sel in (c.type, getattr(c, "subtype", None)) and _is_child_of(c, component)
        ]
    if not found:
        raise ValueError(f"{component.name}.{path}: {link.component!r} matches no component")
    if len(found) > 1 and link.component_ftype is None and not by_content:
        raise ValueError(
            f"{component.name}.{path}: {link.component!r} matches {found}, "
            "but there is no component_ftype to choose between them"
        )
    return found


def _has_class(target: str, link: File, dfns: Mapping[str, Component] | None) -> bool:
    """Whether flopy4 has a class for a link's target: a hand-written base
    for a family picked per row, otherwise a generated module."""
    if link.component_ftype is not None:
        c = dfns[target] if dfns is not None else None
        return c is not None and bool({c.type, getattr(c, "subtype", None)} & set(_CHILD_BASES))
    return _has_module(target)


def _has_module(target: str) -> bool:
    """Whether a component's generated module exists."""
    try:
        return importlib.util.find_spec(_component_module(target)) is not None
    except ModuleNotFoundError:  # no subpackage either (chf-dis)
        return False


def _child_link(
    component: Component, f: FieldV3, dfns: Mapping[str, Component] | None
) -> tuple[File, list[str]] | None:
    """The link a top-level field becomes a child for, and its targets, or
    None to keep the field as is. Links flopy4 can't load yet stay paths:
    those to targets without a class, and files sharing a row with other data
    but no column picking the target's type (LAK/SFR tables, SSM sources)."""
    if (found := _find_link(f)) is None:
        return None
    path, link, file_only = found
    if not file_only and link.component_ftype is None:
        return None
    targets = resolve_link(component, path, link, dfns)
    if filters.is_model_nam(component.name) and link.component_ftype is not None:
        return link, targets  # a field per package type, see _model_package_specs
    if not all(_has_class(t, link, dfns) for t in targets):
        return None
    return link, targets


def _column_children(
    component: Component, f: FieldV3, dfns: Mapping[str, Component] | None
) -> dict[str, list[str]]:
    """A list's file column naming a component flopy4 has a class for, with
    the components it can name (LAK's ``ifno TAB6 FILEIN <file>``, a
    utl-laktab; SSM's SPC6 file, a utl-spc or utl-spca; SFR's period
    ``CROSS_SECTION TAB6 FILEIN <file>``, a utl-sfrtab), or nothing."""
    if not isinstance(f, ListField):
        return {}
    if (union := filters.find_keystring_union(f)) is not None:
        return _arm_column_children(component, f, union, dfns)
    if (found := _find_link(f)) is None:
        return {}
    path, link, file_only = found
    if file_only or link.component_ftype is not None or "." not in path:
        return {}  # the list itself is the child (see _child_link)
    targets = resolve_link(component, path, link, dfns, by_content=True)
    if not all(_has_class(t, link, dfns) for t in targets):
        return {}
    return {path.split(".", 1)[1]: targets}


def _arm_column_children(
    component: Component, f: ListField, union: UnionField, dfns: Mapping[str, Component] | None
) -> dict[str, list[str]]:
    """A keystring list's file columns naming components, from its arms."""
    children = {}
    for arm in union.arms.values():
        for name, m in (arm.fields or {}).items() if isinstance(arm, Record) else ():
            if not (isinstance(m, File) and m.component):
                continue
            targets = resolve_link(component, f"{f.name}.{name}", m, dfns, by_content=True)
            if all(_has_class(t, m, dfns) for t in targets):
                children[name] = targets
    return children


def _component_module(name: str) -> str:
    """The generated module for a component, e.g. utl-ncf -> flopy4.mf6.utl.ncf."""
    parts = filters.output_path(name, Path()).with_suffix("").parts
    return ".".join(("flopy4", "mf6", *(p for p in parts if p != "__init__")))


# flopy4 base classes of hand-written components, by DFN type or subtype.
_CHILD_BASES = {
    "model": "flopy4.mf6.model:Model",
    "exchange": "flopy4.mf6.exchange:Exchange",
    "solution": "flopy4.mf6.solution:Solution",
}


def _child_base(component: Component) -> str:
    for kind in (component.type, getattr(component, "subtype", None)):
        if kind in _CHILD_BASES:
            return _CHILD_BASES[kind]
    raise NotImplementedError(f"no flopy4 base class for {component.name}'s children")


def _child_field_spec(
    component: Component,
    f: FieldV3,
    block_name: str,
    link: File,
    targets: list[str],
    dfns: Mapping[str, Component] | None,
) -> tuple[FieldSpec, list[str]]:
    """The child field standing in for a linked field, and its imports."""
    if link.component_ftype is not None:
        if not filters.is_list_field(f):
            raise ValueError(f"{component.name}.{f.name}: component_ftype outside a list")
        assert dfns is not None  # resolve_link needed them
        bases = {_child_base(dfns[t]) for t in targets}
        if len(bases) != 1:
            raise NotImplementedError(f"{component.name}.{f.name}: children of {sorted(bases)}")
        module, base = bases.pop().split(":")
        return FieldSpec(
            dfn_name=f.name,
            py_name=filters.safe_name(f.name),
            type_annotation=f"dict[str, {base}]",
            spec_call=f'child(block="{block_name}", default=attrs.Factory(dict))',
            generatable=True,
        ), [f"from {module} import {base}"]
    (target,) = targets
    cls = filters.class_name(target)
    args = f'block="{block_name}"'
    record = f.item if isinstance(f, ListField) else f
    if isinstance(record, Record):  # KEYWORD FILEIN <file>, maybe repeated
        members = list((record.fields or {}).values())
        keyword = next(m.name for m in members if isinstance(m, KeywordField))
        direction = next(m.direction for m in members if isinstance(m, File))
        args += f', keyword="{keyword}", direction="{direction}"'
    elif isinstance(f, File) and not f.mode_keyword:  # KEYWORD <file>, e.g. TDIS6
        args += f', keyword="{f.name}"'
    if filters.is_list_field(f):
        annotation, call = f"list[{cls}]", f"child({args}, default=attrs.Factory(list))"
    elif f.optional:
        annotation, call = f"Optional[{cls}]", f"child({args})"
    else:
        annotation, call = cls, f"child({args}, default=attrs.Factory({cls}))"
    return FieldSpec(
        dfn_name=f.name,
        py_name=filters.module_name(target),
        type_annotation=annotation,
        spec_call=call,
        generatable=True,
    ), [f"from {_component_module(target)} import {cls}"]


# Package types sharing one model field: a model has one discretization.
_SLOTS = {"DIS6": "dis", "DISV6": "dis", "DISU6": "dis"}


def _model_package_specs(
    component: Component, block_name: str, targets: list[str], dfns: Mapping[str, Component]
) -> tuple[list[FieldSpec], list[str]]:
    """A model's package fields, one per package type in its name file's
    packages block, and their imports. Variants sharing a type (CHD and
    CHDG) share a field typed as their union; a type MF6 reads more than
    once (``multi``) is a list. Packages without a generated class are left
    out until they have one. The discretization comes first."""
    slots: dict[str, list[str]] = {}
    for t in targets:
        if not _has_module(t):
            continue
        # utl-obs may sit under any model, but only one with observation
        # types reads an OBS6 file (PRT has none yet)
        if t == "utl-obs" and not component.observations:
            continue
        ftype = dfns[t].ftype
        if ftype is None:
            raise ValueError(f"{component.name}: package {t} has no ftype")
        name = _SLOTS.get(ftype, ftype.lower().removesuffix("6"))
        slots.setdefault(name, []).append(t)
    if "dis" in slots:
        slots = {"dis": slots.pop("dis"), **slots}
    specs, imports = [], []
    for name, members in slots.items():
        if len({bool(dfns[t].multi) for t in members}) > 1:
            raise ValueError(f"{component.name}.{name}: {members} disagree on multi")
        classes = [filters.class_name(t) for t in members]
        imports += [f"from {_component_module(t)} import {c}" for t, c in zip(members, classes)]
        cls = classes[0] if len(classes) == 1 else f"Union[{', '.join(classes)}]"
        if dfns[members[0]].multi:
            annotation = f"list[{cls}]"
            call = f'child(block="{block_name}", default=attrs.Factory(list))'
        else:
            annotation, call = f"Optional[{cls}]", f'child(block="{block_name}")'
        specs.append(
            FieldSpec(
                dfn_name=name,
                py_name=filters.safe_name(name),
                type_annotation=annotation,
                spec_call=call,
                generatable=True,
            )
        )
    return specs, imports


def _base_class(component: Component) -> str:
    """Determine the Python base class for a component."""
    if component.type == "simulation":
        return "Context"
    if filters.is_model_nam(component.name):
        return "Model"
    if component.name.split("-")[0] == _SLN_PREFIX:
        return "Solution"
    if getattr(component, "subtype", None) == "exchange":
        return "Exchange"
    return "Package"


def _slntype(component: Component) -> str | None:
    """Return the slntype string for solution DFNs, or None."""
    if component.name.split("-")[0] == _SLN_PREFIX:
        return component.name.split("-")[1]
    return None


def build_component_spec(
    component: Component,
    *,
    root: Path,
    developmode: bool = False,
    dfns: Mapping[str, Component] | None = None,
) -> ComponentSpec:
    """Build all template context for a DFN component. `dfns`, all the
    components, resolves links to other components by type."""
    derived_dims = filters.derived_dims(component)
    all_fields = [
        (block_name, filters.canonical_shape(f, derived_dims))
        for block_name, f in filters.flat_fields(component, developmode=developmode)
    ]

    # Block names where Block.repeats is True (Block.header is not None),
    # mapped to their header field's Python key type (e.g. "float" for utl-tas's
    # "time" block, header type double; "int" for period/solutiongroup,
    # header type integer) -- read from the header field itself rather than
    # assumed, since different repeating blocks have different header types
    # (confirmed against the real DFN corpus: period/solutiongroup headers
    # are integer, utl-tas's time header is the only double one).
    _repeating_blocks: dict[str, str] = {
        name: filters._SCALAR_PY_TYPES[type(block.header.field)]
        for name, block in (component.blocks or {}).items()
        if block.header is not None and type(block.header.field) in filters._SCALAR_PY_TYPES
    }
    # Repeating blocks whose missing occurrences reuse the prior one's
    # values (period) -- see filters.fill_forward_blocks. Their contents
    # consolidate into one stress_period_data field (plus any READARRAY
    # fields), which assumes at most one such block per component.
    _fill_forward_blocks = filters.fill_forward_blocks(component)
    if len(_fill_forward_blocks) > 1:
        raise ValueError(
            f"{component.name}: expected at most one fill-forward block, "
            f"found {sorted(_fill_forward_blocks)}"
        )
    _ff_block = next(iter(_fill_forward_blocks), None)

    has_maxbound = filters.has_dimensions_block(component)
    # maxbound becomes a computed property only with a real Item-list period
    # field to derive it from (see has_dimensions_block's docstring).
    _has_list_period = any(
        block_name in _fill_forward_blocks
        and filters.is_list_field(f)
        and filters.dynamically_named_array(f) is None
        for block_name, f in all_fields
    )
    _maxbound_is_computed = has_maxbound and _has_list_period

    # Fields are collected into four ordered buckets so the generated class has
    # fields in DFN block order without hard-coding block names in any sort key.
    #
    #   prefix_specs  — options + dimensions (from DFN)
    #   extra_specs   — BlockPropertySpec-driven list fields (static list blocks)
    #   data_specs    — remaining DFN data blocks (e.g. outlets)
    #   period_specs  — period fields
    prefix_specs: list[FieldSpec] = []
    extra_specs: list[FieldSpec] = []
    data_specs: list[FieldSpec] = []
    period_specs: list[FieldSpec] = []

    inner_class_specs: list[InnerClassSpec] = []
    _inner_class_names: set[str] = set()
    generatable_field_objects: list[tuple[str, FieldV3]] = []
    # Every list's element classes (and union aliases), whatever its block --
    # see _build_list_item_specs.
    item_classes: list[ItemClassSpec] = []
    item_unions: list[ItemUnionSpec] = []
    block_classes: list[BlockClassSpec] = []

    # BlockPropertySpec for static list blocks — must precede the main field loop
    # since _bp_block_names is used there as a skip-set.
    # Linked fields, by name, each replaced by a child field.
    links = {f.name: found for _, f in all_fields if (found := _child_link(component, f, dfns))}
    child_fields = frozenset(links)
    block_properties, _bp_block_names = _build_block_property_specs(
        component,
        reserved_names=_period_keystring_names(component),
        skip=child_fields,
    )
    # DIMENSIONS fields counting a list's rows
    _linked_dims = {bp.dim_attr for bp in block_properties if bp.dim_is_dfn_declared}

    extra_imports: list[str] = []  # child fields' imports
    _period_item: str | None = None  # element type of the fill-forward block's list
    _readarray_period_fields: list[FieldV3] = []  # READARRAY period fields (CHDG, DRNG …)
    _dynamically_named_period_fields: list[tuple] = []  # (list, array, fk): RCHA's aux
    _repeating_array_fields: list[FieldV3] = []  # repeating block's own array field

    # Lists' file columns naming components, by list (LAK's tables).
    _column_links = {
        f.name: columns for _, f in all_fields if (columns := _column_children(component, f, dfns))
    }
    for columns in _column_links.values():
        for targets in columns.values():
            extra_imports.extend(
                f"from {_component_module(t)} import {filters.class_name(t)}" for t in targets
            )

    def _add_list_items(lf: ListField, class_name: str) -> str:
        specs, elem, union = _build_list_item_specs(
            lf, class_name, _inner_class_names, _column_links.get(lf.name)
        )
        item_classes.extend(specs)
        if union is not None:
            item_unions.append(union)
        return elem

    for block_name, f in all_fields:
        if f.name in child_fields:
            link, targets = links[f.name]
            if filters.is_model_nam(component.name) and link.component_ftype is not None:
                assert dfns is not None  # resolve_link needed them
                specs, child_imports = _model_package_specs(component, block_name, targets, dfns)
            else:
                spec, child_imports = _child_field_spec(
                    component, f, block_name, link, targets, dfns
                )
                specs = [spec]
            (prefix_specs if block_name in ("options", "dimensions") else data_specs).extend(specs)
            extra_imports.extend(child_imports)
            continue

        if filters.is_list_field(f) and block_name in _bp_block_names:
            continue  # covered by BlockPropertySpec; column attrs generated below

        # Lists of dynamically named arrays (RCHA's aux): one array per auxiliary name.
        if block_name in _fill_forward_blocks and (named := filters.dynamically_named_array(f)):
            _dynamically_named_period_fields.append((f, *named))
            continue

        if block_name in _fill_forward_blocks and filters.is_list_field(f):
            _period_item = _add_list_items(f, "StressPeriodData")
            continue

        # G-variant packages (CHDG, DRNG, WELG, RCHA …) declare period arrays
        # directly (not wrapped in a List).
        if block_name in _fill_forward_blocks and filters.is_any_array(f):
            _readarray_period_fields.append(f)
            continue

        # STO-family (chf/gwf/olf-sto): a bare scalar directly in the period
        # block ("storage", valid=["steady-state","transient"]) -- not a List,
        # but still needs the same per-period, fill-forward dict[int, ...]
        # treatment as any other period field (the whole point of a period
        # block is that its contents can differ/repeat across BEGIN PERIOD
        # blocks). Same single-column keystring shape as the LAK-style case
        # above, just with exactly one column since there's nothing else in
        # the block to key against.
        if block_name in _fill_forward_blocks and filters.is_scalar(f):
            item_classes.append(
                ItemClassSpec(
                    class_name="StressPeriodData",
                    keyword="",
                    schema=[filters.attr_column(f.name, "str", {}, optional=False)],
                )
            )
            _period_item = "StressPeriodData"
            continue

        # maxbound: emitted as a computed property (see computed_field_specs
        # below), not a stored field -- skip normal field-building entirely.
        if block_name == "dimensions" and f.name == "maxbound" and _maxbound_is_computed:
            continue

        # Array field whose own block repeats (e.g. utl-tas's "time" block,
        # the only current DFN example -- see _repeating_blocks). Header
        # value isn't a stored field -- carried by the dict's own keys, typed
        # per the block's own header type rather than assumed, since
        # different repeating blocks have different header types (period's
        # is integer, utl-tas's is double).
        if filters.is_readarray(f) and block_name in _repeating_blocks:
            _repeating_array_fields.append(f)
            _repeating_array_base = (
                "IntArrayLike" if getattr(f, "dtype", "") == "integer" else "FloatArrayLike"
            )
            _repeating_block_meta: dict[str, Any] = {"block": block_name}
            if getattr(f, "shape", None):
                _repeating_block_meta["shape"] = tuple(f.shape)
            if getattr(f, "tagged", True):
                # field()'s tagged kwarg only ever records True.
                _repeating_block_meta["tagged"] = True
            data_specs.append(
                FieldSpec(
                    dfn_name=f.name,
                    py_name=filters.safe_name(f.name),
                    type_annotation=(
                        f"Optional[dict[{_repeating_blocks[block_name]}, {_repeating_array_base}]]"
                    ),
                    spec_call=_ml_field(metadata=_repeating_block_meta),
                    generatable=True,
                )
            )
            generatable_field_objects.append((block_name, f))
            continue

        if block_name in ("options", "dimensions"):
            target = prefix_specs
        elif block_name in _fill_forward_blocks:
            target = period_specs
        else:
            target = data_specs

        # A tagged list among a block's other fields: one keyword-led line per
        # element. File records' elements are their paths (list[Path], see
        # _build_field_spec); any other item gets Item classes like any list.
        if filters.is_tagged_list(f) and not filters.is_file_list(f):
            py_words = _strip_record_words(f.name)
            elem = _add_list_items(f, pascal_name("_".join(py_words)))
            target.append(
                FieldSpec(
                    dfn_name=f.name,
                    py_name=filters.safe_name("_".join(py_words)),
                    type_annotation=f"Optional[list[{elem}]]",
                    spec_call=_ml_field(metadata={"block": block_name}),
                    generatable=True,
                )
            )
            generatable_field_objects.append((block_name, f))
            continue

        if filters.can_generate_record_class(f):
            record_specs = _build_record_class_specs(f, component.name, _inner_class_names)
            inner_class_specs.extend(record_specs)
            outer_spec = record_specs[-1]
            clean_name = filters.safe_name("_".join(_strip_record_words(f.name)))
            # a keyword and its options, all optional, can be given as a bool;
            # a keyword and one value, as the value
            flag = bool(outer_spec.keyword) and all(c.optional for c in outer_spec.fields)
            value = (
                bool(outer_spec.keyword)
                and not outer_spec.extra_tokens
                and len(outer_spec.fields) == 1
                and not outer_spec.fields[0].optional
                and not outer_spec.fields[0].nested
                and not outer_spec.fields[0].tagged
            )
            converter = "from_flag" if flag else "from_value" if value else None
            inner_spec_call = _ml_field(
                metadata={"block": block_name},
                converter=f"{outer_spec.class_name}.{converter}" if converter else None,
            )
            target.append(
                FieldSpec(
                    dfn_name=f.name,
                    py_name=clean_name,
                    type_annotation=f"Optional[{outer_spec.class_name}]",
                    spec_call=inner_spec_call,
                    generatable=True,
                )
            )
            generatable_field_objects.append((block_name, f))
        elif filters.can_expand_record(f):
            specs, gen_fields = _expand_record_field(f, block_name)
            target.extend(specs)
            generatable_field_objects.extend((block_name, gf) for gf in gen_fields)
        else:
            spec = _build_field_spec(f, block_name, _linked_dims)
            target.append(spec)
            if spec.generatable:
                generatable_field_objects.append((block_name, f))

    # Rendered before the other blocks' element classes.
    block_item_classes: list[ItemClassSpec] = []
    # BlockPropertySpec-driven fields: one Optional[list[ItemClass]] per block
    # whose only field is an untagged list. The Item class's own fields are
    # the schema -- see item_class() -- no separate __*_schema__ ClassVar.
    for bp in block_properties:
        _list_field = next(
            f for f in component.blocks[bp.block_name].fields.values() if filters.is_list_field(f)
        )
        _specs, _elem, _union = _build_list_item_specs(
            _list_field,
            pascal_name(bp.block_name),
            _inner_class_names,
            _column_links.get(_list_field.name),
        )
        if not any(spec.schema or spec.keyword for spec in _specs):
            continue
        block_item_classes.extend(_specs)
        if _union is not None:
            item_unions.append(_union)
        _meta: dict = {"block": bp.block_name}
        _header = component.blocks[bp.block_name].header
        if _header is not None and isinstance(_header.field, Record):
            # The block repeats under a record header: a list of block
            # classes, each holding its header and the block's list.
            _header_specs, _header_elem, _ = _build_list_item_specs(
                ListField(name=_header.field.name, item=_header.field),
                pascal_name(_header.field.name),
                _inner_class_names,
            )
            block_item_classes.extend(_header_specs)
            _block_cls = f"{pascal_name(bp.block_name)}Block"
            _inner_class_names.add(_block_cls)
            block_classes.append(
                BlockClassSpec(
                    class_name=_block_cls,
                    header=_header.field.name,
                    header_class=_header_elem,
                    list_name=_list_field.name,
                    list_elem=_elem,
                )
            )
            _elem = _block_cls
        # The DIMENSIONS field counting this block's rows, in the DFN's shape
        # syntax: exact ("nper") or a bound ("<=maxats").
        if bp.dim_is_dfn_declared:
            _meta["dim"] = f"{bp.dim_bound or ''}{bp.dim_attr}"
        # DFN default rows (TDIS's perioddata) are the field's real default.
        _default = repr(tuple(_list_field.default)) if _list_field.default else "None"
        # A block must still appear in the written file even with zero rows
        # if MF6 requires its header to be present regardless of row count
        # (e.g. SSM SOURCES) -- as opposed to a block that must be *omitted*
        # entirely when empty (e.g. LAK TABLES/OUTLETS, gated by ntables/
        # noutlets being nonzero; writing them out empty breaks parsing, per
        # test_gwf_lak_status: "Looking for BEGIN PERIOD iper. Found BEGIN
        # TABLES instead."). This is a real MF6 runtime fact that only the
        # Fortran source encodes -- Block.write_if_empty (modflow-devtools
        # PR #357) is the authoritative signal. No modflow6 DFN sets the
        # underlying tag directly yet, but devtools' migration now forces it
        # for gwt-ssm/gwe-ssm's SOURCES as a stopgap fixup (PR #358) -- so
        # this is genuinely live for those two, not just wired for later.
        # The `or` fallback (required + no real DIMENSIONS-declared row
        # count) covers everything else (gwt-lkt/gwe-lke packagedata, LAK
        # connectiondata) where write_if_empty isn't set anywhere yet; drop
        # it once modflow6 (or a devtools fixup) covers those too.
        _block = (component.blocks or {}).get(bp.block_name)
        if (
            _block is not None
            and _block.header is None
            and (_block.write_if_empty or (not _block.optional and not bp.dim_is_dfn_declared))
        ):
            _meta["write_if_empty"] = True
        extra_specs.append(
            FieldSpec(
                dfn_name=bp.block_name,
                py_name=bp.block_name,
                type_annotation=f"Optional[list[{_elem}]]",
                spec_call=_ml_field(
                    _default,
                    metadata=_meta,
                    type_ignore="# type: ignore[assignment]" if _list_field.default else None,
                ),
                generatable=True,
            )
        )

    item_classes = block_item_classes + item_classes

    # The fill-forward block's list (or STO-style scalar), one list of
    # elements per period: the same element classes a list in any other
    # block gets, in a dict keyed by period.
    if _period_item is not None:
        _spd_meta = {"block": _ff_block, "fill_forward": True}
        # The DIMENSIONS field bounding each period's rows, unless it's
        # computed (maxbound): HFB's "<=maxhfb".
        _ff_list = next(
            (
                f
                for b, f in all_fields
                if b == _ff_block
                and filters.is_list_field(f)
                and filters.dynamically_named_array(f) is None
            ),
            None,
        )
        if (
            _ff_list is not None
            and (_ff_dim := filters.list_col_dim(_ff_list, component))
            and not (_ff_dim == "maxbound" and _maxbound_is_computed)
        ):
            _spd_meta["dim"] = f"{filters.list_dim_bound(_ff_list) or ''}{_ff_dim}"
        period_specs.append(
            FieldSpec(
                dfn_name="_stress_period_data",
                py_name="_stress_period_data",
                type_annotation=f"Optional[dict[int, list[{_period_item}]]]",
                spec_call=_ml_field(alias="stress_period_data", repr_=False, metadata=_spd_meta),
                generatable=True,
            )
        )

    # READARRAY period fields → individual Optional[dict[int, Int|FloatArrayLike]]
    # attrs fields. G-variant packages (CHDG, DRNG, WELG, RCHA …) declare each
    # period array separately, keyed by the 0-based periods it's given in
    # (see flopy4.mf6.period_arrays).
    if _readarray_period_fields:
        # a grid package's period can be cleared, None (see period_arrays)
        _grid = any(f.name == "readarraygrid" for _, f in all_fields)
        for _ra_f in _readarray_period_fields:
            # shape/netcdf are the per-block DFN values, as for griddata;
            # shape is each period's array's.
            _ra_meta: dict = {"block": _ff_block}
            if shape := getattr(_ra_f, "shape", None):
                _ra_meta["shape"] = tuple(shape)
            _ra_meta["layered"] = getattr(_ra_f, "layered", False)
            if getattr(_ra_f, "index", False):
                _ra_meta["index"] = True
            if getattr(_ra_f, "netcdf", False):
                _ra_meta["netcdf"] = True
            _ra_meta["fill_forward"] = True
            _ra_base = (
                "IntArrayLike" if getattr(_ra_f, "dtype", "") == "integer" else "FloatArrayLike"
            )
            # a period's array can come from a time-array series, by name
            if getattr(_ra_f, "time_series", False):
                _ra_meta["time_series"] = True
                _ra_base += " | TimeArraySeriesRef"
                extra_imports.append("from flopy4.mf6._types import TimeArraySeriesRef")
            if _grid:
                _ra_base += " | None"
            period_specs.append(
                FieldSpec(
                    dfn_name=_ra_f.name,
                    py_name=filters.safe_name(_ra_f.name),
                    type_annotation=f"Optional[dict[int, {_ra_base}]]",
                    spec_call=_ml_field(metadata=_ra_meta),
                    generatable=True,
                )
            )

    # A dict of dynamically named arrays per list of them: RCHA's aux, keyed by
    # period, then by the auxiliary names (the fk), each array like a READARRAY
    # period field's.
    for _lf, _arr, _fk in _dynamically_named_period_fields:
        _na_meta: dict = {"block": _ff_block}
        if shape := getattr(_arr, "shape", None):
            _na_meta["shape"] = tuple(shape)
        _na_meta["layered"] = getattr(_arr, "layered", False)
        if getattr(_arr, "netcdf", False):
            _na_meta["netcdf"] = True
        _na_meta["fill_forward"] = True
        _na_meta["fk"] = _fk
        _na_base = "IntArrayLike" if getattr(_arr, "dtype", "") == "integer" else "FloatArrayLike"
        if getattr(_arr, "time_series", False) or getattr(_lf, "time_series", False):
            _na_meta["time_series"] = True
            _na_base += " | TimeArraySeriesRef"
            extra_imports.append("from flopy4.mf6._types import TimeArraySeriesRef")
        period_specs.append(
            FieldSpec(
                dfn_name=_lf.name,
                py_name=filters.safe_name(_lf.name),
                type_annotation=f"Optional[dict[int, dict[str, {_na_base}]]]",
                spec_call=_ml_field(metadata=_na_meta),
                generatable=True,
            )
        )

    _seen_py_names: set[str] = set()
    _deduped: list[FieldSpec] = []
    # list blocks and other data blocks interleave in DFN block order (DISU:
    # griddata, connectiondata, vertices, cell2d)
    _block_order = list(dict.fromkeys(bn for bn, _ in all_fields))
    _field_blocks = {f.name: bn for bn, f in all_fields}
    _extra = {id(fs) for fs in extra_specs}

    def _block_index(fs: FieldSpec) -> int:
        bn = fs.dfn_name if id(fs) in _extra else _field_blocks.get(fs.dfn_name)
        return _block_order.index(bn) if bn in _block_order else len(_block_order)

    _data = sorted(extra_specs + data_specs, key=_block_index)
    for _fs in prefix_specs + _data + period_specs:
        if _fs.py_name not in _seen_py_names:
            _seen_py_names.add(_fs.py_name)
            _deduped.append(_fs)
    field_specs = _deduped

    _derived_dims = {n: e for n, e in derived_dims.items() if n not in _seen_py_names}

    base = _base_class(component)
    mixins = MIXINS.get(component.name, [])
    multi = bool(component.multi) if hasattr(component, "multi") else False
    slntype = _slntype(component)
    has_inner_classes = bool(inner_class_specs)

    _has_griddata = any(
        bn == "griddata" and filters.is_readarray(f) for bn, f in generatable_field_objects
    )
    _arraylike_types = (
        {
            f.dtype
            for bn, f in generatable_field_objects
            if filters.is_readarray(f) and bn not in _repeating_blocks
        }
        | {getattr(f, "dtype", "double") for f in _readarray_period_fields}
        | {getattr(arr, "dtype", "double") for _, arr, _ in _dynamically_named_period_fields}
        | {getattr(f, "dtype", "double") for f in _repeating_array_fields}
    )
    _needs_int_arraylike = "integer" in _arraylike_types
    _needs_float_arraylike = bool(_arraylike_types - {"integer", None})
    _has_field_call = any(
        fs.generatable and fs.spec_call.startswith("field(") for fs in field_specs
    )
    _has_path_call = any(fs.generatable and fs.spec_call.startswith("path(") for fs in field_specs)
    _has_child_call = any(
        fs.generatable and fs.spec_call.startswith("child(") for fs in field_specs
    )
    imports = _generated_imports(
        generatable_field_objects,
        base_class=base,
        mixins=mixins,
        multi=multi,
        slntype=slntype is not None,
        has_inner_classes=has_inner_classes,
        needs_int_arraylike=_needs_int_arraylike,
        needs_float_arraylike=_needs_float_arraylike,
        has_field_call=_has_field_call,
        has_path_call=_has_path_call,
        has_child_call=_has_child_call,
        has_readarray_period=bool(_readarray_period_fields),
        item_classes=item_classes,
        has_derived_dims=bool(_derived_dims),
        has_optional_child=any(
            fs.generatable
            and fs.spec_call.startswith("child(")
            and "Optional[" in fs.type_annotation
            for fs in field_specs
        ),
        has_union_child=any(
            fs.spec_call.startswith("child(") and "Union[" in fs.type_annotation
            for fs in field_specs
        ),
        extra_imports=[
            *extra_imports,
            *(["from flopy4.mf6.block import Block"] if block_classes else []),
        ],
    )

    # a model's subpackage exports its packages
    _exports = (
        [
            filters.class_name(component.name),
            *sorted(
                line.rpartition(" import ")[2]
                for line in extra_imports
                if line.startswith(f"from flopy4.mf6.{filters.model_abbr(component.name)}.")
            ),
        ]
        if filters.is_model_nam(component.name)
        else []
    )

    computed_field_specs = (
        [ComputedFieldSpec(py_name="maxbound", source_field="stress_period_data")]
        if _maxbound_is_computed
        else []
    )

    return ComponentSpec(
        dfn_name=component.name,
        class_name=filters.class_name(component.name),
        base_class=base,
        mixins=[m.split(":")[1] for m in mixins],
        multi=multi,
        slntype=slntype,
        imports=imports,
        fields=field_specs,
        inner_classes=inner_class_specs,
        outpath=filters.output_path(component.name, root),
        block_properties=block_properties,
        item_classes=item_classes,
        item_unions=item_unions,
        block_classes=block_classes,
        computed_fields=computed_field_specs,
        derived_dims=_derived_dims,
        observations={
            name: tuple(_obs_forms(f)) for name, f in sorted((component.observations or {}).items())
        },
        has_griddata=_has_griddata,
        has_readarray_period=bool(_readarray_period_fields),
        exports=_exports,
    )


# Template environment

_TEMPLATE_NAME = "package.py.jinja"


def _get_env() -> jinja2.Environment:
    loader = jinja2.PackageLoader("flopy4", "mf6/utils/codegen/templates")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["python_repr"] = python_repr
    env.filters["tuple_repr"] = filters.tuple_repr
    env.filters["item_class"] = item_class
    env.filters["pascal_name"] = pascal_name
    return env


def make_module(
    spec: ComponentSpec,
    env: jinja2.Environment,
    verbose: bool = False,
    outpath: Path | None = None,
) -> None:
    """Generate a single component module, to ``outpath`` if given, else
    to ``spec.outpath``."""
    import shutil
    import subprocess

    outpath = outpath or spec.outpath
    template = env.get_template(_TEMPLATE_NAME)
    rendered = template.render(spec=spec).rstrip() + "\n"
    outpath.write_text(rendered, newline="\n")
    ruff = shutil.which("ruff")
    if ruff:
        subprocess.run([ruff, "format", str(outpath)], check=False, capture_output=True)
    if verbose:
        print(f"Wrote {outpath}")


def make_modules(
    *,
    dfns: dict[str, Component],
    outdir: PathLike,
    developmode: bool = False,
    skip: set[str] | None = None,
    makedirs: bool = False,
    existing_only: bool = False,
    verbose: bool = False,
    stage: PathLike | None = None,
) -> list[ComponentSpec]:
    """Generate Python modules for all components.

    Parameters
    ----------
    dfns :
        Pre-loaded {name: Component} dict, e.g. from a registry's
        ``.spec(schema_version="2.0.0.dev3").components``.
    outdir :
        Root output directory for generated Python files.
    developmode :
        If True, include developmode fields.
    skip :
        Set of DFN names to skip.
    makedirs :
        If True, create output subdirectories as needed.
    existing_only :
        If True, only (re)generate files that already exist on disk.
    verbose :
        Whether to show verbose output
    stage :
        If given, write each module here, at its path relative to
        ``outdir``, instead of into ``outdir``. Paths in the returned
        specs, and the ``existing_only`` checks, still refer to ``outdir``.

    Returns
    -------
    list[ComponentSpec]
        Specs for all components that were generated.
    """
    outdir = Path(outdir)
    skip = skip or set()
    env = _get_env()
    specs = []
    for name, component in dfns.items():
        if name in skip:
            continue
        spec = build_component_spec(component, root=outdir, developmode=developmode, dfns=dfns)
        if existing_only:
            if not spec.outpath.exists():
                if verbose:
                    print(f"{spec.outpath} does not exist — skipping {name}")
                continue
            first_line = spec.outpath.read_text().split("\n", 1)[0]
            if "autogenerated" not in first_line:
                if verbose:
                    print(f"{spec.outpath} is not autogenerated — skipping {name}")
                continue
        if stage is not None:
            outpath = Path(stage) / spec.outpath.relative_to(outdir)
            outpath.parent.mkdir(parents=True, exist_ok=True)
        else:
            outpath = spec.outpath
            if makedirs:
                outpath.parent.mkdir(parents=True, exist_ok=True)
        make_module(spec, env, outpath=outpath)
        specs.append(spec)
    return specs
