"""
Generate Python source files from MODFLOW 6 DFN files.

All template context is pre-computed in Python (see filters.py) so that
Jinja templates stay thin and logic is easy to test and debug.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn, Field

from . import filters
from .filters import ColumnSpec, _dq, python_repr, row_class, schema_class
from .overrides import (
    always_emit_blocks,
    apply_to_child,
    block_dim_override,
    extra_list_blocks,
    extra_period_fields,
    extra_record_children,
    replace_list_blocks,
    replace_list_fields,
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

    Produced by build_component_spec from v1 DFN data. Drives block_schemas
    and the Optional[np.recarray] FieldSpec emitted per block in extra_specs.
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


# Context builders


def _build_field_spec(f: Field, *, has_maxbound: bool = False) -> FieldSpec:
    generatable = filters.is_generatable(f)
    # Strip 'record' suffix from file record names for a cleaner API
    # (e.g. head_filerecord → head_file, budget_filerecord → budget_file).
    # Compound records get the same treatment via _strip_record_words in
    # build_component_spec; this keeps the two paths consistent.
    if filters.is_file_record(f):
        py_name = filters.safe_name("_".join(_strip_record_words(f["name"])))
    else:
        py_name = filters.safe_name(f["name"])
    if generatable:
        spec_call_str = filters.field_call(f, has_maxbound=has_maxbound)
    else:
        spec_call_str = ""
    return FieldSpec(
        dfn_name=f["name"],
        py_name=py_name,
        type_annotation=(filters.py_type(f) if generatable else "Any"),
        spec_call=spec_call_str,
        generatable=generatable,
        skip_reason=filters.skip_reason(f),
    )


_FIELD_KNOWN_KEYS = frozenset(
    {
        "name",
        "type",
        "block",
        "default",
        "longname",
        "description",
        "children",
        "optional",
        "developmode",
        "shape",
        "valid",
        "netcdf",
        "tagged",
    }
)


def _child_to_field(child_dict: dict) -> Field:
    """Convert a record child dict to a Field object."""
    return Field(**{k: v for k, v in child_dict.items() if k in _FIELD_KNOWN_KEYS})


def _expand_record_field(
    f: Field, *, has_maxbound: bool = False
) -> tuple[list[FieldSpec], list[Field]]:
    """Expand a compound record into FieldSpecs for its generatable children.

    Returns (field_specs, generatable_child_fields).  field_specs contains one
    entry per expandable child plus an optional partial-TODO for any optional
    children that can't be generated standalone.  generatable_child_fields is
    the corresponding list of Field objects used for import computation.
    """
    children = f.get("children", None) or {}
    expandable: list[Field] = []
    unexpandable_optional: list[str] = []

    for child_dict in children.values():
        if filters._is_expandable_child(child_dict):
            expandable.append(_child_to_field(child_dict))
        elif child_dict.get("optional", False):
            unexpandable_optional.append(child_dict["name"])
        # required unexpandable children were already blocked by can_expand_record

    specs: list[FieldSpec] = []
    gen_fields: list[Field] = []
    for child_field in expandable:
        spec = _build_field_spec(child_field, has_maxbound=has_maxbound)
        specs.append(spec)
        if spec.generatable:
            gen_fields.append(child_field)

    if unexpandable_optional:
        specs.append(
            FieldSpec(
                dfn_name=f["name"],
                py_name=filters.safe_name(f["name"]),
                type_annotation="Any",
                spec_call="",
                generatable=False,
                skip_reason=(
                    f"positional sub-fields not yet supported: {', '.join(unexpandable_optional)}"
                ),
            )
        )

    return specs, gen_fields


def _build_period_schema_from_array_fields(fields: list[Field]) -> list[dict]:
    """Build __period_schema__ from individual period array fields (v1-style DFNs).

    Standard stress packages (DRN, WEL, CHD, etc.) store period data as
    individual array fields in the DFN rather than a list-type field. The
    cellid column is always first (implicit — not a top-level DFN field);
    aux columns are skipped here and appended dynamically in __attrs_post_init__.

    Keyword-only period blocks (e.g. STO TRANSIENT/STEADY-STATE) have no
    cellid and use a single keystring column to hold the state token.
    """
    # Keyword-only period block: all fields are keyword type with no associated value.
    if fields and all(f["type"] == "keyword" for f in fields):
        return [{"name": "storagestate", "dfn_type": "keyword", "role": "keystring"}]

    schema: list[dict] = [
        {
            "name": "cellid",
            "dfn_type": "integer",
            "role": "cellid",
            "shape": "ncelldim",
            "optional": False,
        }
    ]
    for f in fields:
        name = f["name"]
        if name == "aux":
            continue  # appended dynamically in __attrs_post_init__
        entry = {
            "name": name,
            "dfn_type": f["type"],
            "optional": bool(f.get("optional", False)),
        }
        if name == "boundname":
            entry["role"] = "boundname"
            entry["dtype"] = "np.object_"
        else:
            entry["role"] = "value"
            if f.get("time_series"):
                entry["time_series"] = True
                entry["dtype"] = "np.object_"
        schema.append(entry)
    return schema


def _build_schema_from_list_field(f: Field) -> list[dict]:
    """Build a block schema list from a list-type Field (e.g. TDIS perioddata).

    Used by the new codegen path to convert list fields to recarray block
    schemas instead of per-column array() expansions.
    """
    schema = []
    for col in filters.list_columns(f):
        col_type = col.get("type", "string")
        entry: dict = {"name": col.get("name", ""), "dfn_type": col_type}
        if col.get("cellid", False) or col.get("numeric_index", False):
            entry["role"] = "feature_id"
        elif col.get("name") == "boundname":
            entry["role"] = "boundname"
        elif col_type == "string":
            entry["role"] = "value"
            entry["dtype"] = "np.object_"
        else:
            entry["role"] = "value"
        schema.append(entry)
    return schema


def _build_block_schema(bp: BlockPropertySpec) -> list[dict]:
    """Build __*_schema__ for a static (non-period) list block.

    Parallels _build_period_schema_from_array_fields but reads from
    BlockPropertySpec column descriptors rather than raw Field objects.
    aux columns are excluded — they are appended dynamically in __attrs_post_init__.

    is_prefix columns (non-optional tagged keywords, e.g. FILEIN, SPC6) are
    accumulated and attached as a 'prefix' key on the next value column so the
    codec can emit the fixed token(s) before the value.

    is_row_keyword columns (optional keywords, e.g. MIXED) get role
    'inline_keyword' so the codec knows to emit/parse them conditionally.
    """
    schema = []
    pending_prefix: list[str] = []
    for col in bp.columns:
        if col.is_prefix:
            pending_prefix.append(col.name.upper())
            continue
        if col.name == "aux":
            pending_prefix = []
            continue
        entry: dict = {"name": col.name, "dfn_type": col.type}
        if col.is_cellid:
            entry["role"] = "cellid"
        elif col.numeric_index:
            entry["role"] = "feature_id"
        elif col.name == "boundname":
            entry["role"] = "boundname"
        elif col.is_row_keyword:
            entry["role"] = "inline_keyword"
            entry["optional"] = True
        elif col.type == "string":
            entry["role"] = "value"
            entry["dtype"] = "np.object_"
        else:
            entry["role"] = "value"
        if pending_prefix:
            entry["prefix"] = " ".join(pending_prefix)
            pending_prefix = []
        schema.append(entry)
    return schema


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
    metadata dict — codegen-v2 fields are plain attrs fields, so they go
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


def _expand_oc_record_field(f: Field, dfn_name: str) -> list[FieldSpec]:
    """Expand saverecord/printrecord into per-rtype period fields."""
    rtypes = filters._OC_RTYPES.get(dfn_name, [])
    action = "save" if f["name"] == "saverecord" else "print"
    specs: list[FieldSpec] = []
    for rtype in rtypes:
        py_name = f"{action}_{rtype}"
        spec_call = _ml_field(
            metadata={
                "block": "period",
                "oc_action": action,
                "oc_rtype": rtype,
            }
        )
        type_annotation = "Optional[dict[int, list[str]]]"
        specs.append(
            FieldSpec(
                dfn_name=f"{f['name']}_{rtype}",
                py_name=py_name,
                type_annotation=type_annotation,
                spec_call=spec_call,
                generatable=True,
            )
        )
    return specs


def _strip_record_words(name: str) -> list[str]:
    """Split a DFN field name and strip any trailing 'record' component.

    Works for both underscore-separated suffixes ('rewet_record' → ['rewet'])
    and concatenated suffixes ('rcloserecord' → ['rclose']).
    Returns a list of words suitable for joining as a field name or title-casing
    into a class name.
    """
    words = name.split("_")
    if words:
        last = words[-1].lower()
        if last == "record":
            words = words[:-1]
        elif last.endswith("record"):
            words[-1] = words[-1][: -len("record")]
    return [w for w in words if w]


def _build_inner_class_spec(f: Field, dfn_name: str) -> InnerClassSpec:
    """Build an InnerClassSpec for a mixed-type compound record field.

    When the first child is a keyword type it becomes the trigger token
    (``_keyword``) and is not emitted as a data field.  When the first child
    is a tagged scalar there is no leading keyword token (``_keyword = ""``)
    and all children become data fields.

    Required keyword children after the trigger are treated as fixed tokens
    (always emitted, not user-facing fields) stored in ``_extra_tokens``.
    Optional keyword children become Optional[bool] fields.

    Extra children from ``dfn_overrides.toml`` (used to flatten nested
    sub-records lost in v2 TOML conversion) are appended after the direct
    children.  All fields are sorted required-first to satisfy attrs.
    """
    children = list((f.get("children", None) or {}).values())
    first = children[0]
    if first.get("type") == "keyword":
        keyword = first["name"]
        data_children = children[1:]
    else:
        keyword = ""
        data_children = children

    extra_tokens: list[str] = []
    inner_fields: list[InnerClassFieldSpec] = []

    def _process_child(child_dict: dict) -> None:
        child_dict = apply_to_child(dfn_name, child_dict)
        child_type = child_dict.get("type", "string")
        child_name = child_dict["name"]
        is_optional = child_dict.get("optional", False)
        tagged = child_dict.get("tagged", False)

        if child_type == "keyword":
            if not is_optional:
                # Required keyword: always emitted as a fixed syntax token.
                extra_tokens.append(child_name.upper())
            else:
                # Optional keyword: user chooses whether to set it.
                inner_fields.append(
                    InnerClassFieldSpec(
                        py_name=filters.safe_name(child_name),
                        type_annotation="Optional[bool]",
                        tagged=tagged,
                        optional=True,
                    )
                )
        else:
            base_type = filters._SCALAR_PY_TYPES.get(child_type, "Any")
            type_annotation = f"Optional[{base_type}]" if is_optional else base_type
            inner_fields.append(
                InnerClassFieldSpec(
                    py_name=filters.safe_name(child_name),
                    type_annotation=type_annotation,
                    tagged=tagged,
                    optional=is_optional,
                )
            )

    for child_dict in data_children:
        _process_child(child_dict)

    for child_dict in extra_record_children(dfn_name, f["name"]):
        _process_child(child_dict)

    # attrs requires fields with defaults to follow fields without defaults.
    inner_fields.sort(key=lambda field: str(field.optional))

    words = _strip_record_words(f["name"])
    class_name = "".join(w.capitalize() for w in words)
    extra_tokens_repr = (
        "(" + ", ".join(f'"{t}"' for t in extra_tokens) + ",)" if extra_tokens else ""
    )
    return InnerClassSpec(
        class_name=class_name,
        keyword=keyword,
        extra_tokens=extra_tokens,
        extra_tokens_repr=extra_tokens_repr,
        fields=inner_fields,
    )


def _build_block_property_specs(
    dfn: Dfn,
    v1_dfn: Dfn,
    *,
    extra_blocks: set[str],
    replace_blocks: set[str],
) -> tuple[list[BlockPropertySpec], set[str]]:
    """Compute BlockPropertySpec for all static list blocks in a DFN.

    Uses v1 DFN column schemas (which dfn2toml drops) to build the
    block property API for each recarray block.  Returns (specs, block_names)
    where block_names is used as a skip-set in the main field loop.
    """
    dfn_dims = set((dfn.get("blocks") or {}).get("dimensions", {}).keys())
    dfn_dims_ordered = list((dfn.get("blocks") or {}).get("dimensions", {}).keys())

    # Collect v2 list blocks, excluding those handled by TOML overrides.
    list_fields_map: dict[str, Field | None] = {
        f["block"]: f
        for f in filters.flat_fields(dfn)
        if filters.is_list_field(f)
        and f["block"] not in extra_blocks
        and f["block"] not in replace_blocks
        and "period" not in f["block"]
    }
    # Add recarray blocks present in v1 DFN but dropped by dfn2toml (e.g. SSM sources/fileinput).
    for v1_block in filters.v1_list_block_names(v1_dfn):
        if v1_block in list_fields_map or v1_block in replace_blocks or "period" in v1_block:
            continue
        list_fields_map[v1_block] = None

    v1_schemas = {block: filters.block_schema(v1_dfn, block) for block in list_fields_map}
    # Period field bare names: static columns sharing a name with a period field
    # must take the block-prefixed attr name so the period field keeps the bare name.
    bare_period_names = frozenset(pf["keyword"].lower() for pf in extra_period_fields(dfn["name"]))
    collisions = filters.collision_names(v1_schemas, reserved=bare_period_names)

    # Resolve which DFN dimension scalar each block maps to.
    dim_resolutions: dict[str, tuple[str, bool]] = {}
    claimed_dims: set[str] = set()
    maxbound_blocks: list[str] = []

    for block_name, lf in list_fields_map.items():
        if lf is None:
            dim_resolutions[block_name] = (f"n{block_name}", False)
            continue
        dfn_dim = filters.list_col_dim(lf, dfn)
        if dfn_dim and dfn_dim in dfn_dims:
            dim_resolutions[block_name] = (dfn_dim, True)
            claimed_dims.add(dfn_dim)
        elif lf.get("shape", None) and "maxbound" in str(lf.get("shape", None)) and dfn_dims:
            maxbound_blocks.append(block_name)
        else:
            override = block_dim_override(dfn["name"], block_name)
            dim_resolutions[block_name] = (override or f"n{block_name}", False)

    unclaimed = [d for d in dfn_dims_ordered if d not in claimed_dims]
    for block_name in maxbound_blocks:
        dim_resolutions[block_name] = (
            (unclaimed.pop(0), True) if unclaimed else (f"n{block_name}", False)
        )

    specs: list[BlockPropertySpec] = []
    block_names: set[str] = set()
    for block_name, v1_cols in v1_schemas.items():
        dim_attr_raw, dim_is_dfn_declared = dim_resolutions[block_name]
        attr_name_map = {
            col.name: (
                filters.safe_name(f"{block_name}_{col.name}")
                if col.name in collisions
                else filters.safe_name(col.name)
            )
            for col in v1_cols
            if not col.is_prefix
        }
        specs.append(
            BlockPropertySpec(
                block_name=block_name,
                dim_attr=filters.safe_name(dim_attr_raw),
                dim_is_dfn_declared=dim_is_dfn_declared,
                columns=v1_cols,
                attr_name_map=attr_name_map,
            )
        )
        block_names.add(block_name)

    return specs, block_names


def _new_codegen_imports(
    generatable_fields: list[Field],
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
        and f.get("block")
        != "griddata"  # griddata fields → Int/FloatArrayLike, not NDArray[np.xxx]
        for f in generatable_fields
    )
    has_file_records = any(filters.is_file_record(f) for f in generatable_fields)
    has_optional = (
        any(
            (f.get("optional") and f.get("type") != "keyword") or filters.is_period_array(f)
            for f in generatable_fields
        )
        or has_inner_classes
        or has_period_schema
        or has_readarray_period
        or has_injected_paths  # injected path fields are always Optional[Path]
    )
    has_classvar = multi or slntype or has_inner_classes or has_period_schema
    # Union[float, str] is used by row_class() for time_series and np.object_ columns.
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
    # become Path fields via path() in row_class(), not Union[float, str].
    _row_path_cols = [col for col in _all_schema_cols if col.get("prefix")]
    has_row_path_cols = bool(_row_path_cols)
    has_optional_row_path_cols = any(col.get("optional") for col in _row_path_cols)

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
    if has_array or has_period_schema:
        third_party.append("import numpy as np")
    if has_array:
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
        flopy4.append("from flopy4.mf6.schema import Column, Schema")
    _spec_parts: list[str] = []
    if has_field_call:
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


def _base_class(dfn: Dfn) -> str:
    """Determine the Python base class for a component."""
    if dfn["name"].split("-")[0] == _SLN_PREFIX:
        return "Solution"
    return "Package"


def _slntype(dfn: Dfn) -> str | None:
    """Return the slntype string for solution DFNs, or None."""
    if dfn["name"].split("-")[0] == _SLN_PREFIX:
        return dfn["name"].split("-")[1]
    return None


def build_component_spec(
    dfn: Dfn,
    *,
    root: Path,
    developmode: bool = False,
    v1_dfn: Dfn | None = None,
) -> ComponentSpec:
    """Build all template context for a DFN component."""
    all_fields = filters.flat_fields(dfn, developmode=developmode)

    has_maxbound = filters.has_dimensions_block(dfn)

    # Fields are collected into four ordered buckets so the generated class has
    # fields in DFN block order without hard-coding block names in any sort key.
    # Stable sort in blocks_dict (with devtools block_sort_key) then preserves
    # DFN order naturally for all existing and future block names.
    #
    #   prefix_specs  — options + dimensions (from DFN)
    #   extra_specs   — injected list blocks / path replacements (from dfn_overrides)
    #   data_specs    — remaining DFN data blocks (e.g. outlets)
    #   period_specs  — period fields from DFN + embedded keystring fields
    #
    # extra_specs come before data_specs because injected blocks replace blocks that
    # dfn2toml dropped; those blocks always precede any surviving DFN data blocks
    # (like outlets) in the v1 DFN canonical order.
    prefix_specs: list[FieldSpec] = []
    extra_specs: list[FieldSpec] = []
    data_specs: list[FieldSpec] = []
    period_specs: list[FieldSpec] = []

    inner_class_specs: list[InnerClassSpec] = []
    generatable_field_objects: list[Field] = []
    block_schemas: dict[str, list[dict]] = {}
    _replace_blocks = replace_list_blocks(dfn["name"])
    _extra_blocks = {lb["block"] for lb in extra_list_blocks(dfn["name"])}

    # BlockPropertySpec for static list blocks — must precede the main field loop
    # since _bp_block_names is used there as a skip-set.
    block_properties: list[BlockPropertySpec] = []
    _bp_block_names: set[str] = set()
    if v1_dfn is not None:
        block_properties, _bp_block_names = _build_block_property_specs(
            dfn,
            v1_dfn,
            extra_blocks=_extra_blocks,
            replace_blocks=_replace_blocks,
        )

    period_schema: list[dict] = []
    _period_array_fields: list[Field] = []  # list-based period fields (CHD, DRN, WEL …)
    _readarray_period_fields: list[Field] = []  # READARRAY period fields (CHDG, DRNG …)
    for f in all_fields:
        if filters.is_list_field(f) and f["block"] in (_replace_blocks | _extra_blocks):
            # List field replaced by explicit path fields or injected via extra_list_blocks.
            continue
        if filters.is_list_field(f) and f["block"] in _bp_block_names:
            # List field covered by BlockPropertySpec; column attrs generated below.
            continue

        # New codegen: collect period array fields.
        # G-variant packages (CHDG, DRNG, WELG, RCHA …) use reader=readarray →
        # individual Optional[Int|FloatArrayLike] fields.
        # Standard stress packages (DRN, WEL, CHD …) use list-based recarray.
        if "period" in f["block"] and filters.is_period_array(f):
            if f.get("reader") == "readarray":
                _readarray_period_fields.append(f)
            else:
                _period_array_fields.append(f)
            continue

        if f["block"] in ("options", "dimensions"):
            target = prefix_specs
        elif "period" in f["block"]:
            target = period_specs
        else:
            target = data_specs

        if filters.is_list_field(f):
            block_name = f["block"]
            schema = _build_schema_from_list_field(f)
            if schema:
                block_schemas[block_name] = schema
                meta = {"block": block_name, "schema": f"__{block_name}_schema__"}
                target.append(
                    FieldSpec(
                        dfn_name=f["name"],
                        py_name=filters.safe_name(block_name),
                        type_annotation="Optional[np.recarray]",
                        spec_call=_ml_field(metadata=meta),
                        generatable=True,
                    )
                )
        elif filters.is_oc_record(f, dfn["name"]):
            expanded = _expand_oc_record_field(f, dfn["name"])
            target.extend(expanded)
        elif filters.can_generate_record_class(f):
            record_spec = _build_inner_class_spec(f, dfn["name"])
            inner_class_specs.append(record_spec)
            clean_name = filters.safe_name("_".join(_strip_record_words(f["name"])))
            block = f["block"]
            inner_spec_call = _ml_field(metadata={"block": block})
            target.append(
                FieldSpec(
                    dfn_name=f["name"],
                    py_name=clean_name,
                    type_annotation=f"Optional[{record_spec.class_name}]",
                    spec_call=inner_spec_call,
                    generatable=True,
                )
            )
            generatable_field_objects.append(f)
        elif filters.can_expand_record(f):
            specs, gen_fields = _expand_record_field(f, has_maxbound=has_maxbound)
            target.extend(specs)
            generatable_field_objects.extend(gen_fields)
        else:
            spec = _build_field_spec(f, has_maxbound=has_maxbound)
            target.append(spec)
            if spec.generatable:
                generatable_field_objects.append(f)

    # Inject path fields that replace heterogeneous list blocks (e.g. prt-fmi packagedata).
    has_injected_paths = False
    for entry in replace_list_fields(dfn["name"]):
        has_injected_paths = True
        ln = entry.get("longname", "")
        block = entry["block"]
        inout = entry["inout"]
        _path_meta: dict = {
            "block": block,
            "optional": True,
            "inout": inout,
        }
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

    # Inject extra list blocks from dfn_overrides.toml (_package_extras section).
    # These are list blocks entirely missing from v2 TOML conversion (e.g. SSM sources).
    # Each block contributes: one dim() field (in __dim__ sentinel block, never written)
    # and one array() field per column (in the declared block).
    # Entries must be listed in dfn_overrides.toml in v1 DFN block order so that
    # stable sort on key 3 in block_sort_key produces the correct write sequence.
    _dfn_dim_names = set((dfn.get("blocks", {}) or {}).get("dimensions", {}).keys())
    for lb in extra_list_blocks(dfn["name"]):
        block_name = lb["block"]
        dim_name = lb["dim"]
        # Only add the dim field when it is not already declared in the DFN's
        # dimensions block (e.g. ntables for LAK is already there; nconn is not).
        if dim_name not in _dfn_dim_names:
            extra_specs.append(
                FieldSpec(
                    dfn_name=dim_name,
                    py_name=filters.safe_name(dim_name),
                    type_annotation="Optional[int]",
                    spec_call='dim(block="__dim__", coord=False, default=None)',
                    generatable=True,
                )
            )
        v1_block = (v1_dfn.get("blocks", {}) or {}).get(block_name, {}) if v1_dfn else {}
        for col in lb.get("columns", []):
            col_name = col["name"]
            col_py_name = filters.safe_name(col.get("py_name", col_name))
            col_type = col.get("type", "string")
            col_longname = col.get("longname", "")
            col_prefix = col.get("prefix", None)
            v1_field = v1_block.get(col_name)
            col_cellid = col.get("cellid", False) or getattr(v1_field, "numeric_index", False)
            is_keyword = col_type == "keyword"
            dtype = filters.ARRAY_NUMPY_DTYPES.get(col_type, "np.object_")
            args = [
                f'block="{block_name}"',
                f'dims=("{dim_name}",)',
                "default=None",
            ]
            if not is_keyword:
                args.append(
                    "converter=Converter(structure_array, takes_self=True, takes_field=True)"
                )
            if col_longname:
                args.append(f"longname={repr(col_longname)}")
            if col_prefix:
                args.append(f"prefix={tuple(col_prefix)!r}")
            if is_keyword:
                args.append(f"row_keyword={col_name.upper()!r}")
            if col_cellid:
                args.append("cellid=True")
            extra_specs.append(
                FieldSpec(
                    dfn_name=col_name,
                    py_name=col_py_name,
                    type_annotation=f"Optional[NDArray[{dtype}]]",
                    spec_call=f"array({', '.join(args)})",
                    generatable=True,
                )
            )

    # Inject embedded-keystring period fields (e.g. LAK STATUS/STAGE/RAINFALL).
    # These use embedded_keystring() rather than array(), as the period block for
    # advanced packages emits rows of the form: ``feature_num KEYWORD value``.
    has_period_keystring = False
    # Period fields always use the bare keyword name. Static block columns that
    # share a name with a period field take the block-prefixed attr name instead
    # (see _bare_period_names + collision_names(reserved=...)).
    for pf in extra_period_fields(dfn["name"]):
        # New codegen consolidates keystring period entries into a single
        # (number, keyword, value) recarray; skip per-keyword field emission.
        has_period_keystring = True

    # BlockPropertySpec-driven fields: one Optional[np.recarray] per block plus
    # a __*_schema__ ClassVar.
    _always_emit_set = set(always_emit_blocks(dfn["name"]))
    for bp in block_properties:
        if not bp.columns:
            continue
        schema = _build_block_schema(bp)
        block_schemas[bp.block_name] = schema
        _meta: dict = {
            "block": bp.block_name,
            "schema": f"__{bp.block_name}_schema__",
        }
        if bp.dim_is_dfn_declared:
            _meta["auto_from"] = bp.block_name
        if bp.block_name in _always_emit_set:
            _meta["always_emit"] = True
        extra_specs.append(
            FieldSpec(
                dfn_name=bp.block_name,
                py_name=bp.block_name,
                type_annotation="Optional[np.recarray]",
                spec_call=_ml_field(metadata=_meta),
                generatable=True,
            )
        )

    # Consolidate period fields into one stress_period_data field.
    # Keystring packages (LAK, SFR, MAW, UZF) use a fixed (number, keyword, value)
    # schema; standard stress packages (DRN, WEL, CHD) use per-column schema.
    if has_period_keystring:
        # Keystring period: schema is approximated as (number, keyword, value).
        # The DFN defines a discriminated union (laksetting/sfrsetting/mawsetting)
        # where the keyword determines the value type and arity.  A proper typed
        # representation requires a sealed class hierarchy or tagged variant type
        # and is deferred pending upstream devtools schema work.  Current limitations:
        # (1) Single-value keywords (STAGE, RAINFALL, STATUS, etc.) work correctly.
        # (2) AUXILIARY (two values: auxname + auxval) must be passed as a tuple in
        #     the value field: Row(number=0, keyword="AUXILIARY", value=("conc", 5.0)).
        #     There is no typed Row.aux field for keystring packages (unlike standard
        #     stress packages) because the value arity is determined by the keyword.
        # (3) Compound sub-records (diversionrecord, flowing_wellrecord, etc.) are
        #     not representable in the current schema.
        # See docs/dev/dask1.gaps.md G3 (keystring aux) and G5 (union type).
        # _period_array_fields contains the leading index column (e.g. "number").
        # feature_id role: user passes 0-based Python index; codec emits 1-based for MF6.
        period_schema = [
            {
                "name": f["name"] if _period_array_fields else "number",
                "dfn_type": "integer",
                "role": "feature_id",
            }
            for f in (_period_array_fields or [{"name": "number"}])
        ] + [
            {"name": "keyword", "dfn_type": "string", "role": "keystring"},
            {"name": "value", "dfn_type": "object", "role": "keystring_value"},
        ]
    if has_period_keystring or _period_array_fields:
        if not has_period_keystring:
            period_schema = _build_period_schema_from_array_fields(_period_array_fields)
        _spd_meta = {
            "block": "period",
            "schema": "__period_schema__",
            "fill_forward": True,
        }
        period_specs.append(
            FieldSpec(
                dfn_name="_stress_period_data",
                py_name="_stress_period_data",
                type_annotation="Optional[dict[int, np.recarray]]",
                spec_call=_ml_field(
                    alias="stress_period_data",
                    repr_=False,
                    metadata=_spd_meta,
                ),
                generatable=True,
            )
        )

    # New codegen: READARRAY period fields → individual Optional[Int|FloatArrayLike]
    # attrs fields. G-variant packages (CHDG, DRNG, WELG, RCHA …) declare each period
    # array separately with reader=readarray. Each field is a full-grid array passed
    # directly by the user; the egress dispatches to _unstructure_readarray_period.
    if _readarray_period_fields:
        for _ra_f in _readarray_period_fields:
            _ra_meta = {
                "block": "period",
                "reader": "readarray",
                "layered": _ra_f.get("layered", False),
            }
            _ra_base = "IntArrayLike" if _ra_f.get("type") == "integer" else "FloatArrayLike"
            period_specs.append(
                FieldSpec(
                    dfn_name=_ra_f["name"],
                    py_name=filters.safe_name(_ra_f["name"]),
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

    base = _base_class(dfn)
    multi = bool(dfn.get("multi", False))
    slntype = _slntype(dfn)
    has_inner_classes = bool(inner_class_specs)

    _has_griddata = any(
        f.get("block") == "griddata" and filters.is_array(f) for f in generatable_field_objects
    )
    _arraylike_types = {
        f["type"] for f in generatable_field_objects if f.get("block") == "griddata"
    } | {f.get("type", "double") for f in _readarray_period_fields}
    _needs_int_arraylike = "integer" in _arraylike_types
    _needs_float_arraylike = bool(_arraylike_types - {"integer"})
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
            any(filters.is_file_record(f) for f in generatable_field_objects) or has_injected_paths
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
        dfn_name=dfn["name"],
        class_name=filters.class_name(dfn["name"]),
        base_class=base,
        multi=multi,
        slntype=slntype,
        imports=imports,
        fields=field_specs,
        inner_classes=inner_class_specs,
        outpath=filters.output_path(dfn["name"], root),
        block_properties=block_properties,
        period_schema=period_schema,
        block_schemas=block_schemas,
        has_maxbound=has_maxbound,
        has_keystring_period=has_period_keystring,
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
    env.filters["row_class"] = row_class
    env.filters["schema_class"] = schema_class
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
    dfns: dict[str, "Dfn"],
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
        Pre-loaded DFN dict, e.g. from a registry's spec() call.
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
    for name, dfn in dfns.items():
        if name in skip:
            continue
        spec = build_component_spec(
            dfn,
            root=outdir,
            developmode=developmode,
            v1_dfn=dfn,
        )
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
