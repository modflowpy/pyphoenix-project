"""
Generate Python source files from MODFLOW 6 DFN files.

All template context is pre-computed in Python (see filters.py) so that
Jinja templates stay thin and logic is easy to test and debug.
"""

import logging
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field as dc_field
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn, Field

from . import filters
from .filters import ColumnSpec
from .overrides import (
    apply_to_child,
    block_dim_override,
    extra_list_blocks,
    extra_period_fields,
    extra_record_children,
    replace_list_blocks,
    replace_list_fields,
)

logger = logging.getLogger(__name__)

_RUFF_CONFIG = Path(__file__).parents[4] / "pyproject.toml"


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

    Produced by build_component_spec from v1 DFN data. Stored on
    ComponentSpec.block_properties for use by the Phase 3 template.
    The template is currently unchanged — this field is computed but
    not yet emitted.
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
    template: str = "package.py.jinja"
    has_aux: bool = False
    period_col_map: dict[str, str] = dc_field(default_factory=dict)


# Context builders


def _build_field_spec(f: Field, *, has_maxbound: bool = False) -> FieldSpec:
    generatable = filters.is_generatable(f)
    # Strip 'record' suffix from file record names for a cleaner API
    # (e.g. head_filerecord → head_file, budget_filerecord → budget_file).
    # Compound records get the same treatment via _strip_record_words in
    # build_component_spec; this keeps the two paths consistent.
    if filters.is_file_record(f):
        py_name = filters.safe_name("_".join(_strip_record_words(f.name)))
    else:
        py_name = filters.safe_name(f["name"])
    return FieldSpec(
        dfn_name=f.name,
        py_name=py_name,
        type_annotation=filters.py_type(f) if generatable else "Any",
        spec_call=filters.spec_call(f, has_maxbound=has_maxbound) if generatable else "",
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
    children = f.children or {}
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


def _expand_list_field(f: Field, dfn: Dfn) -> list[FieldSpec]:
    """Expand a list-type sub-table field into one FieldSpec per column.

    Each column becomes an array() field with the list block's block name
    and the list field's dimension.  Matches the hand-written Tdis pattern
    of exploding perioddata columns into separate named arrays.
    """
    cols = filters.list_columns(f)
    dim = filters.list_col_dim(f, dfn)
    if not cols or dim is None:
        return [
            FieldSpec(
                dfn_name=f.name,
                py_name=filters.safe_name(f.name),
                type_annotation="Any",
                spec_call="",
                generatable=False,
                skip_reason="could not determine list column dimension",
            )
        ]

    specs = []
    for col in cols:
        col = apply_to_child(dfn.name, col)
        col_name = col["name"]
        col_type = col.get("type", "string")
        col_longname = col.get("longname", "")
        dtype = filters.ARRAY_NUMPY_DTYPES.get(col_type, "np.object_")
        base = f"NDArray[{dtype}]"
        annotation = f"Optional[{base}]"  # expanded columns always default to None
        args = [
            f'block="{f.block}"',
            f'dims=("{dim}",)',
            "default=None",
            "converter=Converter(structure_array, takes_self=True, takes_field=True)",
        ]
        if col_longname:
            args.append(f"longname={repr(col_longname)}")
        specs.append(
            FieldSpec(
                dfn_name=col_name,
                py_name=filters.safe_name(col_name),
                type_annotation=annotation,
                spec_call=f"array({', '.join(args)})",
                generatable=True,
            )
        )
    return specs


def _expand_oc_record_field(f: Field, dfn_name: str) -> list[FieldSpec]:
    """Expand saverecord/printrecord into per-rtype NDArray[np.str_] fields.

    Generates one array field per rtype (e.g. save_concentration, save_budget)
    using StringDType so the egress writer can produce ``SAVE CONCENTRATION all``
    by splitting on ``_`` → replacing with space.
    """
    rtypes = filters._OC_RTYPES.get(dfn_name, [])
    action = "save" if f.name == "saverecord" else "print"
    specs: list[FieldSpec] = []
    for rtype in rtypes:
        py_name = f"{action}_{rtype}"
        spec_call = (
            "keystring("
            'block="period", '
            'dims=("nper",), '
            "default=None, "
            "converter=Converter(structure_array, takes_self=True, takes_field=True)"
            ")"
        )
        specs.append(
            FieldSpec(
                dfn_name=f"{f.name}_{rtype}",
                py_name=py_name,
                type_annotation="Optional[NDArray[np.str_]]",
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


_SCALAR_PY_TYPES_INNER: dict[str, str] = {
    "keyword": "bool",
    "integer": "int",
    "double precision": "float",
    "double": "float",
    "string": "str",
}


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
    children = list((f.children or {}).values())
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
            base_type = _SCALAR_PY_TYPES_INNER.get(child_type, "Any")
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

    for child_dict in extra_record_children(dfn_name, f.name):
        _process_child(child_dict)

    # attrs requires fields with defaults to follow fields without defaults.
    inner_fields.sort(key=lambda field: field.optional)

    words = _strip_record_words(f.name)
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
    dfn_dims = set((dfn.blocks or {}).get("dimensions", {}).keys())
    dfn_dims_ordered = list((dfn.blocks or {}).get("dimensions", {}).keys())

    # Collect v2 list blocks, excluding those handled by TOML overrides.
    list_fields_map: dict[str, Field | None] = {
        f.block: f
        for f in filters.flat_fields(dfn)
        if filters.is_list_field(f)
        and f.block not in extra_blocks
        and f.block not in replace_blocks
        and "period" not in f.block
    }
    # Add recarray blocks present in v1 DFN but dropped by dfn2toml (e.g. SSM sources/fileinput).
    for v1_block in filters.v1_list_block_names(v1_dfn):
        if v1_block in list_fields_map or v1_block in replace_blocks or "period" in v1_block:
            continue
        list_fields_map[v1_block] = None

    v1_schemas = {block: filters.block_schema(v1_dfn, block) for block in list_fields_map}
    # Period field bare names: static columns sharing a name with a period field
    # must take the block-prefixed attr name so the period field keeps the bare name.
    bare_period_names = frozenset(pf["keyword"].lower() for pf in extra_period_fields(dfn.name))
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
        elif lf.shape and "maxbound" in str(lf.shape) and dfn_dims:
            maxbound_blocks.append(block_name)
        else:
            override = block_dim_override(dfn.name, block_name)
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


_SLN_PREFIX = "sln"


def _base_class(dfn: Dfn) -> str:
    """Determine the Python base class for a component."""
    if dfn.name.split("-")[0] == _SLN_PREFIX:
        return "Solution"
    return "Package"


def _slntype(dfn: Dfn) -> str | None:
    """Return the slntype string for solution DFNs, or None."""
    if dfn.name.split("-")[0] == _SLN_PREFIX:
        return dfn.name.split("-")[1]
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
    _replace_blocks = replace_list_blocks(dfn.name)
    _extra_blocks = {lb["block"] for lb in extra_list_blocks(dfn.name)}

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

    has_list_cols = False
    has_oc_fields = False
    for f in all_fields:
        if filters.is_list_field(f) and f.block in (_replace_blocks | _extra_blocks):
            # List field replaced by explicit path fields or injected via extra_list_blocks.
            continue
        if filters.is_list_field(f) and f.block in _bp_block_names:
            # List field covered by BlockPropertySpec; column attrs generated below.
            continue

        if f.block in ("options", "dimensions"):
            target = prefix_specs
        elif "period" in f.block:
            target = period_specs
        else:
            target = data_specs

        if filters.is_list_field(f):
            expanded = _expand_list_field(f, dfn)
            target.extend(expanded)
            has_list_cols = has_list_cols or any(fs.generatable for fs in expanded)
        elif filters.is_oc_record(f, dfn.name):
            expanded = _expand_oc_record_field(f, dfn.name)
            target.extend(expanded)
            has_oc_fields = has_oc_fields or any(fs.generatable for fs in expanded)
        elif filters.can_generate_record_class(f):
            record_spec = _build_inner_class_spec(f, dfn.name)
            inner_class_specs.append(record_spec)
            clean_name = filters.safe_name("_".join(_strip_record_words(f.name)))
            target.append(
                FieldSpec(
                    dfn_name=f.name,
                    py_name=clean_name,
                    type_annotation=f"Optional[{record_spec.class_name}]",
                    spec_call=f'field(block="{f.block}", default=None)',
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
    # Each injected entry becomes an Optional[Path] field using the path() spec.
    has_injected_paths = False
    for entry in replace_list_fields(dfn.name):
        has_injected_paths = True
        ln = entry.get("longname", "")
        args = [
            f'block="{entry["block"]}"',
            "default=None",
            "converter=to_path",
            f'inout="{entry["inout"]}"',
        ]
        if ln:
            args.append(f"longname={repr(ln)}")
        extra_specs.append(
            FieldSpec(
                dfn_name=entry["name"],
                py_name=filters.safe_name(entry["name"]),
                type_annotation="Optional[Path]",
                spec_call=f"path({', '.join(args)})",
                generatable=True,
            )
        )

    # Inject extra list blocks from dfn_overrides.toml (_package_extras section).
    # These are list blocks entirely missing from v2 TOML conversion (e.g. SSM sources).
    # Each block contributes: one dim() field (in __dim__ sentinel block, never written)
    # and one array() field per column (in the declared block).
    # Entries must be listed in dfn_overrides.toml in v1 DFN block order so that
    # stable sort on key 3 in block_sort_key produces the correct write sequence.
    has_extra_dims = False
    _dfn_dim_names = set((dfn.blocks or {}).get("dimensions", {}).keys())
    for lb in extra_list_blocks(dfn.name):
        block_name = lb["block"]
        dim_name = lb["dim"]
        # Only add the dim field when it is not already declared in the DFN's
        # dimensions block (e.g. ntables for LAK is already there; nconn is not).
        if dim_name not in _dfn_dim_names:
            has_extra_dims = True
            extra_specs.append(
                FieldSpec(
                    dfn_name=dim_name,
                    py_name=filters.safe_name(dim_name),
                    type_annotation="Optional[int]",
                    spec_call='dim(block="__dim__", coord=False, default=None)',
                    generatable=True,
                )
            )
        v1_block = (v1_dfn.blocks or {}).get(block_name, {}) if v1_dfn else {}
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
        has_list_cols = True

    # Inject embedded-keystring period fields (e.g. LAK STATUS/STAGE/RAINFALL).
    # These use embedded_keystring() rather than array(), as the period block for
    # advanced packages emits rows of the form: ``feature_num KEYWORD value``.
    has_period_keystring = False
    # Period fields always use the bare keyword name. Static block columns that
    # share a name with a period field take the block-prefixed attr name instead
    # (see _bare_period_names + collision_names(reserved=...)).
    for pf in extra_period_fields(dfn.name):
        kw = pf["keyword"]
        feat_dim = pf["feature_dim"]
        py_name = filters.safe_name(kw.lower())
        dtype_str = pf.get("dtype", "double precision")
        numpy_dtype = filters.ARRAY_NUMPY_DTYPES.get(dtype_str, "np.object_")
        is_str = numpy_dtype == "np.object_"
        args = [
            f'"{kw}"',
            f'"{feat_dim}"',
        ]
        if is_str:
            args.append(f"dtype={numpy_dtype}")
        args += [
            'block="period"',
            "default=None",
            "converter=Converter(structure_array, takes_self=True, takes_field=True)",
        ]
        period_specs.append(
            FieldSpec(
                dfn_name=kw.lower(),
                py_name=py_name,
                type_annotation=f"Optional[NDArray[{numpy_dtype}]]",
                spec_call=f"embedded_keystring({', '.join(args)})",
                generatable=True,
            )
        )
        has_period_keystring = True

    # BlockPropertySpec-driven column fields.
    # Each block gets: private init-only dict field, optional synthetic dim, column arrays.
    # _bp_emitted_dims prevents emitting the same synthetic dim twice when two blocks
    # share a dimension (e.g. connectiondata and tables both using nconnectiondata).
    _bp_emitted_dims: set[str] = set()
    _naux_emitted = False  # emit naux dim at most once per package
    for bp in block_properties:
        if not bp.columns:
            continue
        extra_specs.append(
            FieldSpec(
                dfn_name=f"_{bp.block_name}",
                py_name=f"_{bp.block_name}",
                type_annotation="Optional[dict]",
                spec_call=f'attrs.field(alias="{bp.block_name}", default=None, repr=False)',
                generatable=True,
            )
        )
        if not bp.dim_is_dfn_declared and bp.dim_attr not in _bp_emitted_dims:
            has_extra_dims = True
            _bp_emitted_dims.add(bp.dim_attr)
            extra_specs.append(
                FieldSpec(
                    dfn_name=bp.dim_attr,
                    py_name=bp.dim_attr,
                    type_annotation="Optional[int]",
                    spec_call='dim(block="__dim__", coord=False, default=None)',
                    generatable=True,
                )
            )
        # Emit naux synthetic dim once when this block carries an aux column
        _bp_has_aux = "aux" in bp.attr_name_map
        if _bp_has_aux and not _naux_emitted:
            _naux_emitted = True
            has_extra_dims = True
            extra_specs.append(
                FieldSpec(
                    dfn_name="naux",
                    py_name="naux",
                    type_annotation="Optional[int]",
                    spec_call='dim(block="__dim__", coord=False, default=None)',
                    generatable=True,
                )
            )
        _pending_prefixes: list[str] = []
        for col in bp.columns:
            if col.is_prefix:
                _pending_prefixes.append(col.name.upper())
                continue
            attr_name = bp.attr_name_map[col.name]
            dtype = (
                "np.object_"
                if col.is_cellid
                else filters.ARRAY_NUMPY_DTYPES.get(col.type, "np.object_")
            )
            args = [
                f'block="{bp.block_name}"',
                # aux carries a second dimension for the number of auxiliary variables
                (
                    f'dims=("{bp.dim_attr}", "naux")'
                    if col.name == "aux"
                    else f'dims=("{bp.dim_attr}",)'
                ),
                "default=None",
            ]
            if not col.is_row_keyword:
                args.append(
                    "converter=Converter(structure_array, takes_self=True, takes_field=True)"
                )
            if col.longname:
                args.append(f"longname={repr(col.longname)}")
            if _pending_prefixes:
                args.append(f"prefix={tuple(_pending_prefixes)!r}")
                _pending_prefixes = []
            if col.is_row_keyword:
                args.append(f"row_keyword={col.name.upper()!r}")
            if col.is_cellid or col.numeric_index:
                args.append("cellid=True")
            extra_specs.append(
                FieldSpec(
                    dfn_name=col.name,
                    py_name=attr_name,
                    type_annotation=f"Optional[NDArray[{dtype}]]",
                    spec_call=f"array({', '.join(args)})",
                    generatable=True,
                )
            )
        has_list_cols = True

    # Emit naux synthetic dim when any period field carries aux.
    # List-based packages (CHD/WEL/etc.) have "naux" in the DFN shape.
    # G/A variants (CHDG/WELG/RCHA/EVTA) use per-variable readarray blocks so
    # naux is absent from the DFN shape; detect them by field name instead.
    if not _naux_emitted:
        for _f in all_fields:
            if (
                _f.block == "period"
                and filters.is_array(_f)
                and _f.shape
                and ("naux" in _f.shape or _f.name == "aux")
            ):
                _naux_emitted = True
                has_extra_dims = True
                extra_specs.append(
                    FieldSpec(
                        dfn_name="naux",
                        py_name="naux",
                        type_annotation="Optional[int]",
                        spec_call='dim(block="__dim__", coord=False, default=None)',
                        generatable=True,
                    )
                )
                break

    field_specs = prefix_specs + extra_specs + data_specs + period_specs

    # Build period_col_map: value columns in the period block (cellid/aux/boundname excluded).
    # Only packages with a standard stress-period list format produce a non-empty map.
    # Advanced packages (LAK/MAW/UZF) use embedded_keystring rows and will have no
    # is_period_array fields with scalar type, so their map stays empty.
    period_col_map: dict[str, str] = {}
    for _f in all_fields:
        # Only node-based floating/integer list columns: excludes keyword period arrays
        # (STO steady-state/transient flags) and non-list period blocks.
        if not (_f.block == "period" and filters.is_array(_f)):
            continue
        if _f.name in ("boundname", "aux"):
            continue
        if _f.shape and "naux" in _f.shape:
            continue
        # Require node dimension (nnodes/nodes in shape) — excludes OC and period-level scalars
        if not _f.shape or ("nnodes" not in _f.shape and "nodes" not in _f.shape):
            continue
        period_col_map[_f.name] = filters.safe_name(_f.name)

    base = _base_class(dfn)
    multi = bool(dfn.multi)
    slntype = _slntype(dfn)
    has_inner_classes = bool(inner_class_specs)

    imports = filters.needed_imports(
        generatable_field_objects,
        base_class=base,
        multi=multi,
        slntype=slntype is not None,
        has_maxbound=has_maxbound,
        has_list_cols=has_list_cols or has_period_keystring,
        has_inner_classes=has_inner_classes,
        has_oc_fields=has_oc_fields,
        has_extra_dims=has_extra_dims,
        has_injected_paths=has_injected_paths,
        has_period_keystring=has_period_keystring,
        has_block_properties=bool(block_properties),
        has_period_col_map=bool(period_col_map),
    )

    return ComponentSpec(
        dfn_name=dfn.name,
        class_name=filters.class_name(dfn.name),
        base_class=base,
        multi=multi,
        slntype=slntype,
        imports=imports,
        fields=field_specs,
        inner_classes=inner_class_specs,
        outpath=filters.output_path(dfn.name, root),
        block_properties=block_properties,
        has_aux=_naux_emitted,
        period_col_map=period_col_map,
    )


# Template environment


def _get_env() -> jinja2.Environment:
    loader = jinja2.PackageLoader("flopy4", "mf6/utils/codegen/templates")
    return jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )


# File generation


def _format(path: Path) -> None:
    config = ["--config", str(_RUFF_CONFIG)] if _RUFF_CONFIG.exists() else []
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", *config, str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", *config, str(path)],
        check=True,
        capture_output=True,
    )


def make_component(
    spec: ComponentSpec,
    env: jinja2.Environment,
    *,
    fmt: bool = True,
) -> None:
    """Render and write a single component file."""
    template = env.get_template(spec.template)
    rendered = template.render(spec=spec)
    spec.outpath.write_text(rendered, newline="\n")
    logger.info(f"Wrote {spec.outpath}")
    if fmt:
        try:
            _format(spec.outpath)
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to format {spec.outpath}: {e.stderr.decode().strip()}")


def make_all(
    *,
    dfndir: PathLike,
    outdir: PathLike,
    developmode: bool = False,
    fmt: bool = True,
    skip: set[str] | None = None,
    makedirs: bool = False,
    existing_only: bool = False,
    v1dfndir: PathLike | None = None,
) -> list[ComponentSpec]:
    """Generate Python source files for all DFNs in dfndir.

    Parameters
    ----------
    dfndir :
        Directory containing v2 TOML DFN files.
    outdir :
        Root output directory for generated Python files.
    developmode :
        If True, include developmode fields.
    fmt :
        If True, run ruff format/check on generated files.
    skip :
        Set of DFN names to skip.
    makedirs :
        If True, create output subdirectories as needed.
    existing_only :
        If True, only (re)generate files that already exist on disk.
    v1dfndir :
        Optional directory containing v1 DFN files (.dfn). When provided,
        numeric_index is read from the v1 DFN to auto-detect cellid columns
        in extra_list_blocks without requiring explicit ``cellid=true`` in
        dfn_overrides.toml.

    Returns
    -------
    list[ComponentSpec]
        Specs for all components that were generated.
    """
    dfndir = Path(dfndir)
    outdir = Path(outdir)
    skip = skip or set()
    env = _get_env()
    dfns = Dfn.load_all(dfndir)
    v1_dfns = Dfn.load_all(v1dfndir) if v1dfndir else {}
    specs = []
    for name, dfn in dfns.items():
        if name in skip:
            continue
        spec = build_component_spec(
            dfn, root=outdir, developmode=developmode, v1_dfn=v1_dfns.get(name)
        )
        if existing_only and not spec.outpath.exists():
            logger.info(f"{spec.outpath} does not exist — skipping {name} (existing_only)")
            continue
        if makedirs:
            spec.outpath.parent.mkdir(parents=True, exist_ok=True)
        make_component(spec, env, fmt=fmt)
        specs.append(spec)
    return specs
