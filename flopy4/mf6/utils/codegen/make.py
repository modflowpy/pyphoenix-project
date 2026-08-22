"""
Generate Python source files from MODFLOW 6 DFN files.

All template context is pre-computed in Python (see filters.py) so that
Jinja templates stay thin and logic is easy to test and debug.

Sources from modflow_devtools.dfns (pydantic, schema 2.0.0.dev3) Component/
Block/Field objects. See namefile-load-plan.md, Phase 0.6a+0.6b, for the
migration history from the legacy modflow_devtools.dfn (flat TypedDict)
schema this replaces.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns.schema import (
    Component,
    Double,
    Integer,
    Record,
    String,
)
from modflow_devtools.dfns.schema import (
    Keyword as KeywordField,
)
from modflow_devtools.dfns.schema import (
    Union as UnionField,
)

from . import filters
from .filters import ColumnSpec, FieldV3, _dq, item_class, pascal_name, python_repr
from .overrides import (
    always_emit_blocks,
    block_dim_override,
    extra_record_children,
    replace_list_blocks,
    replace_list_fields,
)
from .overrides import (
    apply as apply_override,
)

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


@dataclass
class InnerClassSpec:
    """Pre-computed context for a generated inner attrs class."""

    class_name: str
    keyword: str
    extra_tokens: list[str]
    extra_tokens_repr: str  # pre-formatted Python tuple literal, e.g. '("PRINT_FORMAT",)'
    fields: list[InnerClassFieldSpec]


@dataclass
class BlockPropertySpec:
    """Pre-computed schema for one list (recarray) block property.

    Produced by build_component_spec from dev3 List/Record fields. Drives
    block_schemas and the Optional[np.recarray] FieldSpec emitted per block
    in extra_specs.
    """

    block_name: str
    dim_attr: str  # Python name of the dim field
    dim_is_dfn_declared: bool  # False → synthetic (__dim__), not written to file
    columns: list[ColumnSpec]
    attr_name_map: dict[str, str]  # col_name → Python attr name (bare or block-prefixed)


@dataclass
class ComponentSpec:
    """Pre-computed context for a generated component class."""

    dfn_name: str
    class_name: str
    base_class: str
    multi: bool
    slntype: str | None
    imports: dict[str, list[str]]
    fields: list[FieldSpec]
    inner_classes: list[InnerClassSpec]
    outpath: Path
    block_properties: list[BlockPropertySpec] = dc_field(default_factory=list)
    period_schema: list[dict] = dc_field(default_factory=list)
    block_schemas: dict[str, list[dict]] = dc_field(default_factory=dict)
    has_maxbound: bool = False
    has_keystring_period: bool = False
    has_griddata: bool = False
    has_readarray_period: bool = False


# Column-schema-dict builders
#
# Both static list blocks and standard (non-keystring) period blocks are
# List[Record] under dev3 -- including a real cellid Array field for period
# blocks, which the legacy schema had to synthesize. One function builds the
# list[dict] "schema" (the intermediate format item_class/schema_class render)
# for both cases; only the surrounding FieldSpec (type annotation, block=
# vs fill_forward= metadata) differs between them.


def _schema_dict_from_columns(columns: list[ColumnSpec]) -> list[dict]:
    """Build a __*_schema__ list[dict] from ColumnSpecs.

    is_prefix columns (non-optional tagged keywords, e.g. FILEIN, SPC6) are
    accumulated and attached as a 'prefix' key on the next value column so the
    codec can emit the fixed token(s) before the value. is_row_keyword columns
    (optional keywords, e.g. MIXED) get role 'inline_keyword'. aux columns are
    excluded -- appended dynamically in __attrs_post_init__.
    """
    schema = []
    pending_prefix: list[str] = []
    for col in columns:
        if col.is_prefix:
            pending_prefix.append(col.name.upper())
            continue
        if col.name == "aux":
            pending_prefix = []
            continue
        f = col.field
        entry: dict = {"name": col.name, "dfn_type": _dfn_type_str(f)}
        if f.optional:
            entry["optional"] = True
        if col.is_cellid:
            entry["role"] = "cellid"
            if shape := getattr(f, "shape", None):
                entry["shape"] = ",".join(shape)
        elif col.is_index:
            entry["role"] = "feature_id"
            if getattr(f, "fk", None):
                entry["fk"] = f.fk
            elif getattr(f, "pk", False):
                entry["pk"] = True
        elif col.name == "boundname":
            entry["role"] = "boundname"
            entry["dtype"] = "np.object_"
        elif col.is_row_keyword:
            entry["role"] = "inline_keyword"
            entry["optional"] = True
        elif isinstance(f, String):
            entry["role"] = "value"
            entry["dtype"] = "np.object_"
        else:
            entry["role"] = "value"
        if getattr(f, "time_series", False):
            entry["time_series"] = True
            entry["dtype"] = "np.object_"
        if pending_prefix:
            entry["prefix"] = " ".join(pending_prefix)
            pending_prefix = []
        schema.append(entry)
    return schema


def _dfn_type_str(f: FieldV3) -> str:
    """DFN-type string for a leaf field, as used in the schema-dict format."""
    if isinstance(f, Integer):
        return "integer"
    if isinstance(f, Double):
        return "double"
    if isinstance(f, String):
        return "string"
    if isinstance(f, KeywordField):
        return "keyword"
    return getattr(f, "dtype", "double")  # Array


# Context builders


def _build_field_spec(f: FieldV3, block_name: str, *, has_maxbound: bool = False) -> FieldSpec:
    generatable = filters.is_generatable(f)
    # Strip 'record' suffix from file record names for a cleaner API
    # (e.g. head_filerecord → head_file, budget_filerecord → budget_file).
    # Compound records get the same treatment via _strip_record_words in
    # build_component_spec; this keeps the two paths consistent.
    if filters.is_file_record(f):
        py_name = filters.safe_name("_".join(_strip_record_words(f.name)))
    else:
        py_name = filters.safe_name(f.name)
    if generatable:
        spec_call_str = filters.field_call(f, block_name, has_maxbound=has_maxbound)
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


def _expand_record_field(
    f: Record, block_name: str, *, has_maxbound: bool = False
) -> tuple[list[FieldSpec], list[FieldV3]]:
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
        spec = _build_field_spec(child, block_name, has_maxbound=has_maxbound)
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
    ``path()`` kwargs (block, schema, oc_action, ...), not a raw attrs
    metadata dict -- codegen-v2 fields are plain attrs fields, so they go
    through the same passive-metadata constructors hand-written xattree
    classes use for their scalar fields.
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


# OC-family period record expansion: List[Union[saverecord, printrecord]],
# each arm a Record with a real `rtype` field whose `.valid` gives the
# rtype vocabulary natively -- replaces the legacy hardcoded _OC_RTYPES table.


def _is_oc_style_union(item: FieldV3) -> bool:
    """True for a List whose (unwrapped) item is a Union of rtype-bearing
    Records -- the gwf/gwt/gwe/prt-oc saverecord/printrecord shape."""
    return (
        isinstance(item, UnionField)
        and bool(item.arms)
        and all(isinstance(arm, Record) and "rtype" in arm.fields for arm in item.arms.values())
    )


def _is_index(f: FieldV3) -> bool:
    # dev3's `index` attribute is the direct, authoritative signal for
    # "needs the 0-based/1-based conversion 'feature_id' implies" -- split
    # out of the old overloaded pk/fk semantics (modflow-devtools 41dca93).
    # A string pk/fk (e.g. a name reference) is never `index`.
    return bool(getattr(f, "index", False))


def _keystring_has_index(list_field: FieldV3, union: UnionField) -> bool:
    """True if a keystring-shaped period list has a per-row feature index.

    Two shapes carry one: an outer sibling index field next to the union
    (LKE/LKT/SFR-style: item Record = {lakeno: Integer(fk=...), setting:
    Union}), or a pk/fk field embedded in every arm (LAK-style: item Record
    wraps the union alone, each arm starts with its own lakeno/outletno).
    PRP's `releasesetting` (ALL/FIRST/LAST/FREQUENCY/STEPS) has neither --
    confirmed via the v1 DFN, which declares it a bare `recarray
    releasesetting` with no index field at all, matching MF6IO syntax with
    no leading row number. Emitting a fabricated "number" column there would
    be wrong, not just redundant.
    """
    item = list_field.item
    if isinstance(item, Record):
        if any(f is not union and _is_index(f) for f in item.fields.values()):
            return True
    return any(
        isinstance(arm, Record) and any(_is_index(f) for f in arm.fields.values())
        for arm in union.arms.values()
    )


def _oc_rtypes(item: UnionField) -> list[str]:
    """Valid rtype strings for an OC-style union, read from the schema."""
    rtypes: list[str] = []
    for arm in item.arms.values():
        for v in arm.fields["rtype"].valid or []:
            if v not in rtypes:
                rtypes.append(v)
    return rtypes


def _oc_action(item: UnionField, arm_name: str) -> str:
    """'save' or 'print', from the arm's leading trigger keyword."""
    arm = item.arms[arm_name]
    trigger = next(iter(arm.fields.values()))
    return "save" if isinstance(trigger, KeywordField) and trigger.name == "save" else "print"


def _expand_oc_record_field(list_field: FieldV3) -> list[FieldSpec]:
    """Expand an OC-style period list field into per-rtype period fields."""
    item = filters.find_keystring_union(list_field)
    assert item is not None  # caller already confirmed this is an OC-style union field
    rtypes = _oc_rtypes(item)
    specs: list[FieldSpec] = []
    for arm_name in item.arms:
        action = _oc_action(item, arm_name)
        for rtype in rtypes:
            py_name = f"{action}_{rtype.lower()}"
            spec_call = _ml_field(
                metadata={"block": "period", "oc_action": action, "oc_rtype": rtype.lower()}
            )
            specs.append(
                FieldSpec(
                    dfn_name=f"{arm_name}_{rtype.lower()}",
                    py_name=py_name,
                    type_annotation="Optional[dict[int, list[str]]]",
                    spec_call=spec_call,
                    generatable=True,
                )
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


def _build_inner_class_spec(f: Record, dfn_name: str) -> InnerClassSpec:
    """Build an InnerClassSpec for a mixed-type compound record field.

    When the first child is a keyword type it becomes the trigger token
    (``_keyword``) and is not emitted as a data field. When the first child
    is a tagged scalar there is no leading keyword token (``_keyword = ""``)
    and all children become data fields.

    Required keyword children after the trigger are treated as fixed tokens
    (always emitted, not user-facing fields) stored in ``_extra_tokens``.
    Optional keyword children become Optional[bool] fields.

    Extra children from ``dfn_overrides.toml`` (used to inject fields not yet
    representable, e.g. positional sub-record fields) are appended after the
    direct children. All fields are sorted required-first to satisfy attrs.
    """
    children = list(f.fields.values())
    first = children[0]
    if isinstance(first, KeywordField):
        kw = first.name
        data_children = children[1:]
    else:
        kw = ""
        data_children = children

    extra_tokens: list[str] = []
    inner_fields: list[InnerClassFieldSpec] = []

    def _process_child(child: FieldV3) -> None:
        child = apply_override(dfn_name, child)
        is_optional = child.optional
        tagged = getattr(child, "tagged", False)

        if isinstance(child, Record):
            # One level of nesting (the head/temperature/concentration/
            # qoutflow/cim printrecord family: formatrecord wraps columns/
            # width/digits/format) -- flatten the nested record's own fields
            # into this same inner class rather than emitting a second class.
            # can_generate_record_class already confirmed all grandchildren
            # are scalar/keyword-only.
            for nested in child.fields.values():
                _process_child(nested)
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

    for child_dict in extra_record_children(dfn_name, f.name):
        # Extra children are still plain dicts in dfn_overrides.toml (not
        # pydantic fields) -- handled directly rather than routed through
        # _process_child, which expects a real Field object.
        is_optional = child_dict.get("optional", False)
        child_type = child_dict.get("type", "string")
        if child_type == "keyword":
            if not is_optional:
                extra_tokens.append(child_dict["name"].upper())
            else:
                inner_fields.append(
                    InnerClassFieldSpec(
                        py_name=filters.safe_name(child_dict["name"]),
                        type_annotation="Optional[bool]",
                        tagged=child_dict.get("tagged", False),
                        optional=True,
                    )
                )
        else:
            _type_map = {
                "integer": "int",
                "double": "float",
                "double precision": "float",
                "string": "str",
            }
            base_type = _type_map.get(child_type, "Any")
            type_annotation = f"Optional[{base_type}]" if is_optional else base_type
            inner_fields.append(
                InnerClassFieldSpec(
                    py_name=filters.safe_name(child_dict["name"]),
                    type_annotation=type_annotation,
                    tagged=child_dict.get("tagged", False),
                    optional=is_optional,
                )
            )

    # attrs requires fields with defaults to follow fields without defaults.
    inner_fields.sort(key=lambda field: str(field.optional))

    words = _strip_record_words(f.name)
    class_name = "".join(w.capitalize() for w in words)
    extra_tokens_repr = (
        "(" + ", ".join(f'"{t}"' for t in extra_tokens) + ",)" if extra_tokens else ""
    )
    return InnerClassSpec(
        class_name=class_name,
        keyword=kw,
        extra_tokens=extra_tokens,
        extra_tokens_repr=extra_tokens_repr,
        fields=inner_fields,
    )


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
    period = (component.blocks or {}).get("period")
    if period is None:
        return frozenset()
    for f in period.fields.values():
        if filters.is_list_field(f):
            union = filters.find_keystring_union(f)
            if union is not None:
                return frozenset(name.lower() for name in union.arms)
    return frozenset()


def _build_block_property_specs(
    component: Component,
    *,
    extra_blocks: set[str],
    replace_blocks: set[str],
    reserved_names: frozenset[str] = frozenset(),
) -> tuple[list[BlockPropertySpec], set[str]]:
    """Compute BlockPropertySpec for all static (non-period) list blocks.

    Returns (specs, block_names) where block_names is used as a skip-set in
    the main field loop.
    """
    dim_block = (component.blocks or {}).get("dimensions")
    dfn_dims_ordered = list(dim_block.fields.keys()) if dim_block is not None else []
    dfn_dims = set(dfn_dims_ordered)

    list_fields_map: dict[str, FieldV3] = {}
    for block_name, block in (component.blocks or {}).items():
        if block_name == "period" or block_name in extra_blocks or block_name in replace_blocks:
            continue
        for f in block.fields.values():
            if filters.is_list_field(f) and not filters.is_keystring_list(f):
                list_fields_map[block_name] = f
                break

    col_schemas = {
        block: filters.list_columns(f, component.name) for block, f in list_fields_map.items()
    }
    collisions = filters.collision_names(col_schemas, reserved=reserved_names)

    # Resolve which DFN dimension scalar each block maps to.
    dim_resolutions: dict[str, tuple[str, bool]] = {}
    claimed_dims: set[str] = set()
    maxbound_blocks: list[str] = []

    for block_name, lf in list_fields_map.items():
        dfn_dim = filters.list_col_dim(lf, component)
        if dfn_dim and dfn_dim in dfn_dims:
            dim_resolutions[block_name] = (dfn_dim, True)
            claimed_dims.add(dfn_dim)
        elif lf.shape and "maxbound" in lf.shape and dfn_dims:
            maxbound_blocks.append(block_name)
        else:
            override = block_dim_override(component.name, block_name)
            dim_resolutions[block_name] = (override or f"n{block_name}", False)

    unclaimed = [d for d in dfn_dims_ordered if d not in claimed_dims]
    for block_name in maxbound_blocks:
        dim_resolutions[block_name] = (
            (unclaimed.pop(0), True) if unclaimed else (f"n{block_name}", False)
        )

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
            )
        )
        block_names.add(block_name)

    return specs, block_names


def _new_codegen_imports(
    generatable_fields: list[tuple[str, FieldV3]],
    *,
    base_class: str = "Package",
    multi: bool = False,
    slntype: bool = False,
    has_inner_classes: bool = False,
    has_period_schema: bool = False,
    has_path: bool = False,
    has_readarray_period: bool = False,
    needs_int_arraylike: bool = False,
    needs_float_arraylike: bool = False,
    has_injected_paths: bool = False,
    has_field_call: bool = False,
    has_path_call: bool = False,
    period_schema: list[dict] | None = None,
    block_schemas: dict[str, list[dict]] | None = None,
) -> dict[str, list[str]]:
    """Compute import lines for new-codegen packages (no xattree, no spec calls)."""
    has_array = any(
        (filters.is_array(f) or filters.is_keyword_array(f))
        and block_name != "griddata"  # griddata fields → Int/FloatArrayLike, not NDArray[np.xxx]
        for block_name, f in generatable_fields
    )
    has_file_records = any(filters.is_file_record(f) for _, f in generatable_fields)
    has_optional = (
        any(
            (f.optional and not isinstance(f, KeywordField)) or filters.is_period_array(f, bn)
            for bn, f in generatable_fields
        )
        or has_inner_classes
        or has_period_schema
        or bool(block_schemas)
        or has_readarray_period
        or has_injected_paths  # injected path fields are always Optional[Path]
    )
    # dfn_name is always emitted as a ClassVar (see package.py.jinja), so
    # ClassVar is always needed regardless of multi/slntype/inner classes.
    has_classvar = True
    # Union[float, str] is used by item_class() for time_series and np.object_ columns.
    # Check both the period schema and all static block schemas.
    _all_schema_cols = list(period_schema or []) + [
        col for cols in (block_schemas or {}).values() for col in cols
    ]
    has_union = any(
        col.get("time_series") or col.get("dtype") == "np.object_"
        for col in _all_schema_cols
        if col.get("role") not in ("keystring_value", "boundname") and not col.get("prefix")
    )
    # prefix= row columns (file references, e.g. LAK tables' TAB6 FILEIN)
    # become Path fields via path() in item_class(), not Union[float, str].
    _row_path_cols = [col for col in _all_schema_cols if col.get("prefix")]
    has_row_path_cols = bool(_row_path_cols)
    has_optional_row_path_cols = any(col.get("optional") for col in _row_path_cols)
    # Row class fields with cellid=/pk=/fk=/tagged=/time_series= metadata use
    # field(), same as any other codegen-v2 field -- checked separately from
    # has_field_call since these live inside item_class()'s rendered text, not
    # in the package's own top-level field_specs.
    _row_has_field_call = any(
        col.get("role") in ("cellid", "feature_id", "inline_keyword") or col.get("time_series")
        for col in _all_schema_cols
        if not col.get("prefix")
    )

    stdlib: list[str] = []
    if has_path or has_injected_paths or has_file_records or has_row_path_cols:
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
    }
    flopy4: list[str] = [_base_imports.get(base_class, _base_imports["Package"])]
    if has_inner_classes:
        flopy4.append("from flopy4.mf6.record import Record")
    if has_period_schema:
        flopy4.append("from flopy4.mf6.item import Item")
    _spec_parts: list[str] = []
    if has_field_call or _row_has_field_call:
        _spec_parts.append("field")
    if has_path_call or has_row_path_cols:
        _spec_parts.append("path")
    if _spec_parts:
        flopy4.append(f"from flopy4.mf6.spec import {', '.join(sorted(_spec_parts))}")
    _types_parts: list[str] = []
    if needs_int_arraylike:
        _types_parts.append("IntArrayLike")
    if needs_float_arraylike:
        _types_parts.append("FloatArrayLike")
    if has_file_records or has_injected_paths or has_optional_row_path_cols:
        _types_parts.append("_optional_path")
    if _types_parts:
        flopy4.append(f"from flopy4.mf6._types import {', '.join(sorted(_types_parts))}")
    flopy4.sort()

    return {"stdlib": stdlib, "third_party": third_party, "flopy4": flopy4}


_SLN_PREFIX = "sln"


def _base_class(component: Component) -> str:
    """Determine the Python base class for a component."""
    if component.name.split("-")[0] == _SLN_PREFIX:
        return "Solution"
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
) -> ComponentSpec:
    """Build all template context for a DFN component."""
    all_fields = filters.flat_fields(component, developmode=developmode)

    has_maxbound = filters.has_dimensions_block(component)

    # Fields are collected into four ordered buckets so the generated class has
    # fields in DFN block order without hard-coding block names in any sort key.
    #
    #   prefix_specs  — options + dimensions (from DFN)
    #   extra_specs   — injected list blocks / path replacements (from dfn_overrides)
    #   data_specs    — remaining DFN data blocks (e.g. outlets)
    #   period_specs  — period fields
    prefix_specs: list[FieldSpec] = []
    extra_specs: list[FieldSpec] = []
    data_specs: list[FieldSpec] = []
    period_specs: list[FieldSpec] = []

    inner_class_specs: list[InnerClassSpec] = []
    generatable_field_objects: list[tuple[str, FieldV3]] = []
    block_schemas: dict[str, list[dict]] = {}
    _replace_blocks = replace_list_blocks(component.name)
    _extra_blocks: set[str] = set()  # extra_list_blocks mechanism no longer needed (see below)

    # BlockPropertySpec for static list blocks — must precede the main field loop
    # since _bp_block_names is used there as a skip-set.
    block_properties, _bp_block_names = _build_block_property_specs(
        component,
        extra_blocks=_extra_blocks,
        replace_blocks=_replace_blocks,
        reserved_names=_period_keystring_names(component),
    )

    period_schema: list[dict] = []
    has_period_keystring = False
    has_oc_period = False
    _readarray_period_fields: list[FieldV3] = []  # READARRAY period fields (CHDG, DRNG …)
    _standard_period_list: FieldV3 | None = None  # standard (non-keystring) period List field

    for block_name, f in all_fields:
        if filters.is_list_field(f) and block_name in (_replace_blocks | _extra_blocks):
            continue
        if filters.is_list_field(f) and block_name in _bp_block_names:
            continue  # covered by BlockPropertySpec; column attrs generated below

        if block_name == "period" and filters.is_list_field(f):
            union = filters.find_keystring_union(f)
            if union is not None and _is_oc_style_union(union):
                has_oc_period = True
                extra_specs.extend(_expand_oc_record_field(f))
            elif union is not None:
                has_period_keystring = True
                # Reproduces the current runtime-compatible shape: a generic
                # (index, keyword, value) approximation. Union.arms carries
                # real per-arm fk/type info now, but structure.py/unstructure.py
                # only understand the flat Column/Schema role vocabulary today
                # (see namefile-load-plan.md, Phase 0.6a+0.6b course
                # correction, 2026-08-18) -- a faithful typed-union
                # representation is a follow-up once Phase 0.6's Row
                # migration lands, not this pass.
                period_schema = []
                if _keystring_has_index(f, union):
                    period_schema.append(
                        {"name": "number", "dfn_type": "integer", "role": "feature_id"}
                    )
                period_schema.extend(
                    [
                        {"name": "keyword", "dfn_type": "string", "role": "keystring"},
                        {"name": "value", "dfn_type": "object", "role": "keystring_value"},
                    ]
                )
            else:
                _standard_period_list = f
            continue

        # G-variant packages (CHDG, DRNG, WELG, RCHA …) declare period arrays
        # directly (not wrapped in a List) with reader=readarray.
        if block_name == "period" and filters.is_period_array(f, block_name):
            _readarray_period_fields.append(f)
            continue

        # STO-family (chf/gwf/olf-sto): a bare scalar directly in the period
        # block ("storage", valid=["steady-state","transient"]) -- not a List,
        # but still needs the same per-period, fill-forward dict[int, ...]
        # treatment as any other period field (the whole point of a period
        # block is that its contents can differ/repeat across BEGIN PERIOD
        # blocks). Same runtime-compatible single-column keystring shape as
        # the LAK-style case above, just with exactly one column since there's
        # nothing else in the block to key against.
        if block_name == "period" and filters.is_scalar(f):
            has_period_keystring = True
            period_schema = [{"name": f.name, "dfn_type": "keyword", "role": "keystring"}]
            continue

        if block_name in ("options", "dimensions"):
            target = prefix_specs
        elif block_name == "period":
            target = period_specs
        else:
            target = data_specs

        if filters.can_generate_record_class(f):
            record_spec = _build_inner_class_spec(f, component.name)
            inner_class_specs.append(record_spec)
            clean_name = filters.safe_name("_".join(_strip_record_words(f.name)))
            inner_spec_call = _ml_field(metadata={"block": block_name})
            target.append(
                FieldSpec(
                    dfn_name=f.name,
                    py_name=clean_name,
                    type_annotation=f"Optional[{record_spec.class_name}]",
                    spec_call=inner_spec_call,
                    generatable=True,
                )
            )
            generatable_field_objects.append((block_name, f))
        elif filters.can_expand_record(f):
            specs, gen_fields = _expand_record_field(f, block_name, has_maxbound=has_maxbound)
            target.extend(specs)
            generatable_field_objects.extend((block_name, gf) for gf in gen_fields)
        else:
            spec = _build_field_spec(f, block_name, has_maxbound=has_maxbound)
            target.append(spec)
            if spec.generatable:
                generatable_field_objects.append((block_name, f))

    # Standard (non-keystring) period list block: same column-schema-building
    # as a static list block (dev3 already carries a real cellid field), just
    # wrapped as a repeating dict[int, ...] field instead of a flat one.
    if _standard_period_list is not None:
        cols = filters.list_columns(_standard_period_list, component.name)
        period_schema = _schema_dict_from_columns(cols)

    # Inject path fields that replace heterogeneous list blocks (e.g. prt-fmi packagedata).
    has_injected_paths = False
    for entry in replace_list_fields(component.name):
        has_injected_paths = True
        block = entry["block"]
        inout = entry["inout"]
        _path_meta: dict = {"block": block, "optional": True, "inout": inout}
        spec_call_str = _ml_field(metadata=_path_meta, converter="_optional_path", fn="path")
        extra_specs.append(
            FieldSpec(
                dfn_name=entry["name"],
                py_name=filters.safe_name(entry["name"]),
                type_annotation="Optional[Path]",
                spec_call=spec_call_str,
                generatable=True,
            )
        )

    # BlockPropertySpec-driven fields: one Optional[list[ItemClass]] per block.
    # The Item class's own fields are the schema -- see item_class() -- no
    # separate __*_schema__ ClassVar needed.
    _always_emit_set = set(always_emit_blocks(component.name))
    for bp in block_properties:
        if not bp.columns:
            continue
        schema = _schema_dict_from_columns(bp.columns)
        if not schema:
            continue
        block_schemas[bp.block_name] = schema
        _meta: dict = {"block": bp.block_name}
        if bp.dim_is_dfn_declared:
            _meta["auto_from"] = bp.block_name
        if bp.block_name in _always_emit_set:
            _meta["always_emit"] = True
        _item_cls_name = pascal_name(bp.block_name)
        extra_specs.append(
            FieldSpec(
                dfn_name=bp.block_name,
                py_name=bp.block_name,
                type_annotation=f"Optional[list[{_item_cls_name}]]",
                spec_call=_ml_field(metadata=_meta),
                generatable=True,
            )
        )

    # Consolidate period fields into one stress_period_data field.
    if period_schema:
        _spd_meta = {"block": "period", "fill_forward": True}
        period_specs.append(
            FieldSpec(
                dfn_name="_stress_period_data",
                py_name="_stress_period_data",
                type_annotation="Optional[dict[int, list[StressPeriodData]]]",
                spec_call=_ml_field(alias="stress_period_data", repr_=False, metadata=_spd_meta),
                generatable=True,
            )
        )

    # READARRAY period fields → individual Optional[Int|FloatArrayLike] attrs
    # fields. G-variant packages (CHDG, DRNG, WELG, RCHA …) declare each period
    # array separately with reader=readarray. Each field is a full-grid array
    # passed directly by the user; the egress dispatches to
    # _unstructure_readarray_period.
    if _readarray_period_fields:
        for _ra_f in _readarray_period_fields:
            _ra_meta = {
                "block": "period",
                "reader": "readarray",
                "layered": getattr(_ra_f, "layered", False),
            }
            _ra_base = (
                "IntArrayLike" if getattr(_ra_f, "dtype", "") == "integer" else "FloatArrayLike"
            )
            period_specs.append(
                FieldSpec(
                    dfn_name=_ra_f.name,
                    py_name=filters.safe_name(_ra_f.name),
                    type_annotation=f"Optional[{_ra_base}]",
                    spec_call=_ml_field(metadata=_ra_meta),
                    generatable=True,
                )
            )

    _seen_py_names: set[str] = set()
    _deduped: list[FieldSpec] = []
    for _fs in prefix_specs + extra_specs + data_specs + period_specs:
        if _fs.py_name not in _seen_py_names:
            _seen_py_names.add(_fs.py_name)
            _deduped.append(_fs)
    field_specs = _deduped

    base = _base_class(component)
    multi = bool(component.multi) if hasattr(component, "multi") else False
    slntype = _slntype(component)
    has_inner_classes = bool(inner_class_specs)

    _has_griddata = any(
        bn == "griddata" and filters.is_array(f) for bn, f in generatable_field_objects
    )
    _arraylike_types = {
        getattr(f, "dtype", None) for bn, f in generatable_field_objects if bn == "griddata"
    } | {getattr(f, "dtype", "double") for f in _readarray_period_fields}
    _needs_int_arraylike = "integer" in _arraylike_types
    _needs_float_arraylike = bool(_arraylike_types - {"integer", None})
    _has_field_call = any(
        fs.generatable and fs.spec_call.startswith("field(") for fs in field_specs
    )
    _has_path_call = any(fs.generatable and fs.spec_call.startswith("path(") for fs in field_specs)
    imports = _new_codegen_imports(
        generatable_field_objects,
        base_class=base,
        multi=multi,
        slntype=slntype is not None,
        has_inner_classes=has_inner_classes,
        has_period_schema=bool(period_schema) or bool(block_schemas),
        has_path=(
            any(filters.is_file_record(f) for _, f in generatable_field_objects)
            or has_injected_paths
        ),
        needs_int_arraylike=_needs_int_arraylike,
        needs_float_arraylike=_needs_float_arraylike,
        has_injected_paths=has_injected_paths,
        has_field_call=_has_field_call,
        has_path_call=_has_path_call,
        has_readarray_period=bool(_readarray_period_fields),
        period_schema=period_schema,
        block_schemas=block_schemas,
    )

    return ComponentSpec(
        dfn_name=component.name,
        class_name=filters.class_name(component.name),
        base_class=base,
        multi=multi,
        slntype=slntype,
        imports=imports,
        fields=field_specs,
        inner_classes=inner_class_specs,
        outpath=filters.output_path(component.name, root),
        block_properties=block_properties,
        period_schema=period_schema,
        block_schemas=block_schemas,
        has_maxbound=has_maxbound,
        has_keystring_period=has_period_keystring or has_oc_period,
        has_griddata=_has_griddata,
        has_readarray_period=bool(_readarray_period_fields),
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
    env.filters["item_class"] = item_class
    env.filters["pascal_name"] = pascal_name
    return env


def make_module(spec: ComponentSpec, env: jinja2.Environment, verbose: bool = False) -> None:
    """Generate a single component module."""
    import shutil
    import subprocess

    template = env.get_template(_TEMPLATE_NAME)
    rendered = template.render(spec=spec).rstrip() + "\n"
    spec.outpath.write_text(rendered, newline="\n")
    ruff = shutil.which("ruff")
    if ruff:
        subprocess.run([ruff, "format", str(spec.outpath)], check=False, capture_output=True)
    if verbose:
        print(f"Wrote {spec.outpath}")


def make_modules(
    *,
    dfns: dict[str, Component],
    outdir: PathLike,
    developmode: bool = False,
    skip: set[str] | None = None,
    makedirs: bool = False,
    existing_only: bool = False,
    verbose: bool = False,
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
        spec = build_component_spec(component, root=outdir, developmode=developmode)
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
        if makedirs:
            spec.outpath.parent.mkdir(parents=True, exist_ok=True)
        make_module(spec, env)
        specs.append(spec)
    return specs
