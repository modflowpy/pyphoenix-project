"""
Python-side filters for MF6 code generation.

Converts modflow_devtools.dfns (pydantic, schema 2.0.0.dev3) Component/Block/
Field objects to the context dicts consumed by Jinja templates. Keeping
computation here (rather than in Jinja macros) makes edge-case handling
easier to test and debug.

Sources from the pydantic-native dev3 schema (Scalar | Array | Record | Union
| List, discriminated by `.type`) rather than the legacy flat TypedDict schema
(modflow_devtools.dfn). See namefile-load-plan.md, Phase 0.6a+0.6b, for the
migration history and the reasoning behind specific choices below.
"""

import builtins
import keyword
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modflow_devtools.dfns.schema import (
    Array,
    Component,
    Double,
    File,
    Integer,
    Keyword as KeywordField,
    List as ListField,
    Record,
    String,
    Union as UnionField,
)

from .overrides import apply as apply_override

FieldV3 = KeywordField | Integer | Double | String | Array | Record | UnionField | ListField | File

# DFN-level routing helpers

# Components whose model prefix maps to the flopy4/mf6/ root (no subdir).
_ROOT_PREFIXES = {"sim", "sln"}


def model_abbr(dfn_name: str) -> str | None:
    """Return the model prefix of a DFN name, or None for top-level components.

    Examples
    --------
    "gwf-ic"  -> "gwf"
    "sln-ims" -> None
    "sim-nam" -> None
    """
    prefix = dfn_name.split("-")[0]
    return None if prefix in _ROOT_PREFIXES else prefix


def pkg_abbr(dfn_name: str) -> str:
    """Return the package suffix of a DFN name.

    Examples
    --------
    "gwf-ic"  -> "ic"
    "sln-ims" -> "ims"
    """
    return dfn_name.split("-")[-1]


def class_name(dfn_name: str) -> str:
    """Return the Python class name for a DFN.

    Examples
    --------
    "gwf-ic"  -> "Ic"
    "sln-ims" -> "Ims"
    """
    return pkg_abbr(dfn_name).capitalize()


def module_name(dfn_name: str) -> str:
    """Return the Python module (file) name for a DFN.

    Examples
    --------
    "gwf-ic"  -> "ic"
    """
    return pkg_abbr(dfn_name)


def output_path(dfn_name: str, root: Path) -> Path:
    """Compute the output file path for a DFN's generated module."""
    abbr = model_abbr(dfn_name)
    mod = module_name(dfn_name)
    if abbr is None:
        return root / f"{mod}.py"
    return root / abbr / f"{mod}.py"


# Component/Block-level helpers


def has_period_block(component: Component) -> bool:
    """True if the component defines a period block (stress package)."""
    return "period" in (component.blocks or {})


def has_dimensions_block(component: Component) -> bool:
    """True if the component has a dimensions block with a 'maxbound' field.

    Only packages with a field literally named 'maxbound' use the
    auto-computed pattern (init=False, on_setattr=update_maxbound).
    Packages like MVR/BUY/VSC have user-specified dimension scalars
    (maxmvr, maxpackages, nrhospecies) that must NOT be init=False.
    """
    block = (component.blocks or {}).get("dimensions")
    return block is not None and "maxbound" in block.fields


# Field classification
#
# dev3's Field union is a real discriminated union -- isinstance dispatch
# replaces the legacy schema's string-set membership checks directly. No
# equivalent of the legacy _has_complex_shape/_ALT_DIM_TOKENS/_DIM_ALIASES is
# needed: verified against a broad corpus slice (gwf-npf, gwf-disu, gwf-evta,
# gwf-rcha, gwf-dis) that dev3 shapes are already canonicalized (e.g.
# ['ncpl'] uniformly for DIS/DISV cell-count dims, never 'ncol*nrow' or a
# ';'-joined alternative-grid expression) -- the workaround those three
# helpers existed for is gone at the source.

ARRAY_NUMPY_DTYPES: dict[str, str] = {
    "double": "np.float64",
    "integer": "np.int64",
    "string": "np.object_",
    "keyword": "np.bool_",
}


def is_scalar(f: FieldV3) -> bool:
    """True for simple scalar fields (no shape)."""
    return isinstance(f, (KeywordField, Integer, Double, String))


def is_array(f: FieldV3) -> bool:
    """True for array fields (numeric or string type with a shape).

    Excludes auxiliary variable name lists (shape == [], see is_aux_list_field)
    and other unshaped arrays (variadic-count fields with no static dim --
    see devtools/todo.md 2026-08-18 entry on Array.repeat).
    """
    return isinstance(f, Array) and bool(f.shape) and f.dtype != "keyword"


def is_keyword_array(f: FieldV3) -> bool:
    """True for boolean-array fields (keyword type with shape)."""
    return isinstance(f, Array) and f.dtype == "keyword" and bool(f.shape)


def is_file_record(f: FieldV3) -> bool:
    """True for record fields whose children include a File field.

    The MF6 ``KEYWORD FILEIN <path>``/``KEYWORD FILEOUT <path>`` pattern
    (e.g. options-block ``ts_filerecord``): a Record wrapping a trigger
    Keyword and a File child. Distinct from is_bare_file (below) -- a File
    field can also appear directly in a block with no wrapping Record (e.g.
    prt-fmi.packagedata's gwfhead/gwfbudget/gwfgrid).
    """
    return isinstance(f, Record) and any(isinstance(c, File) for c in f.fields.values())


def is_bare_file(f: FieldV3) -> bool:
    """True for a File field with no wrapping Record (no fixed keyword token
    precedes it -- just ``<path>`` directly, e.g. prt-fmi's packagedata File
    fields). See is_file_record for the wrapped-in-a-Record case."""
    return isinstance(f, File)


def file_child(f: Record) -> File | None:
    """Return the File child of a file record, or None."""
    return next((c for c in f.fields.values() if isinstance(c, File)), None)


def is_aux_list_field(f: FieldV3) -> bool:
    """True for auxiliary variable name lists (options block, shape []).

    dev3 represents this as Array(dtype="string", shape=[], name="auxiliary")
    -- an unshaped string array. (Legacy encoded this as a shaped field with
    a self-referential dim "naux"; dev3 drops the fake dimension entirely
    since the count *is* len() of the list itself, nothing to declare.)
    """
    return isinstance(f, Array) and f.dtype == "string" and f.shape == [] and f.name == "auxiliary"


def is_period_array(f: FieldV3, block_name: str) -> bool:
    """True for array fields in the period block (G-variant packages)."""
    return block_name == "period" and (is_array(f) or is_keyword_array(f))


def is_dimensions_scalar(f: FieldV3, block_name: str) -> bool:
    """True for scalar fields in the dimensions block (computed, init=False)."""
    return block_name == "dimensions" and is_scalar(f)


def is_boundname_field(f: FieldV3, block_name: str) -> bool:
    """True for the boundname string field in the period block."""
    return block_name == "period" and f.name == "boundname"


def is_list_field(f: FieldV3) -> bool:
    """True for list-type sub-table fields (packagedata, perioddata, etc.)."""
    return isinstance(f, ListField)


def is_generatable(f: FieldV3) -> bool:
    """True if this field can be handled in the current generation pass."""
    return (
        is_scalar(f)
        or is_array(f)
        or is_keyword_array(f)
        or is_file_record(f)
        or is_bare_file(f)
        or is_aux_list_field(f)
    )


_RECORD_CLASS_SCALAR_TYPES = (Integer, Double, String)


def _is_expandable_child(child: FieldV3) -> bool:
    """True if a record child can be generated as a standalone field.

    Only keyword-type children are expandable: they're self-naming tokens that
    map cleanly to individual bool fields. Scalar data fields (even tagged ones)
    are positional components of a compound construct and must stay grouped.
    """
    return isinstance(child, KeywordField)


def can_generate_record_class(f: FieldV3) -> bool:
    """True when a compound record should be rendered as an inner attrs class.

    All non-file records whose children are entirely scalars and/or keywords
    become inner attrs classes. The first keyword child (if any) is the
    trigger token (``_keyword``); remaining keyword children become
    ``Optional[bool]`` fields so related options stay grouped.

    All-keyword records with only one child (a lone flag keyword) are left to
    :func:`can_expand_record` -- a bare bool field is cleaner there than an
    empty inner class. Records with unsupported child types (list, union)
    fall back to TODO comments. A child that is itself a Record is supported
    one level deep, provided *its* children are all scalar/keyword too (the
    `head/temperature/concentration/qoutflow/cim` printrecord family: outer
    record wraps `formatrecord: Record{columns, width, digits, format}`) --
    its fields are flattened into the same inner class (see
    make.py._build_inner_class_spec). Deeper nesting falls back to TODO.
    """
    if not isinstance(f, Record) or is_file_record(f) or not f.fields:
        return False
    children = list(f.fields.values())

    def _supported(c: FieldV3) -> bool:
        if isinstance(c, _RECORD_CLASS_SCALAR_TYPES + (KeywordField,)):
            return True
        if isinstance(c, Record) and c.fields:
            return all(
                isinstance(gc, _RECORD_CLASS_SCALAR_TYPES + (KeywordField,))
                for gc in c.fields.values()
            )
        return False

    all_supported = all(_supported(c) for c in children)
    if not all_supported:
        return False
    has_scalar = any(isinstance(c, _RECORD_CLASS_SCALAR_TYPES) for c in children)
    # All-keyword records need at least 2 children (trigger + modifier) to
    # justify a class; a single lone keyword expands more cleanly to a bool.
    if not has_scalar:
        return len(children) >= 2
    return True


def can_expand_record(f: FieldV3) -> bool:
    """True if a non-file compound record can be at least partially expanded.

    A record can be expanded when all its required (non-optional) children are
    individually generatable as standalone fields. Optional children that
    can't be generated standalone are noted in a TODO comment but don't
    block expansion.
    """
    if not isinstance(f, Record) or is_file_record(f) or not f.fields:
        return False
    for child in f.fields.values():
        if not child.optional and not _is_expandable_child(child):
            return False
    return True


def skip_reason(f: FieldV3) -> str | None:
    """Return a human-readable reason why a field is skipped, or None."""
    if is_generatable(f):
        return None
    if is_list_field(f):
        return None  # handled as recarray block in build_component_spec
    if can_expand_record(f):
        return None  # handled by _expand_record_field in make.py
    if isinstance(f, Array) and not f.shape:
        return "unshaped (variadic-count) array not yet supported"
    return f"type '{f.type}' not yet supported"


# Field iteration


def flat_fields(
    component: Component, *, developmode: bool = False
) -> list[tuple[str, FieldV3]]:
    """Return an ordered flat list of (block_name, field) for all blocks.

    Unlike the legacy schema, dev3 fields don't carry their own block name --
    block membership is structural (Block.fields), so callers need the block
    name alongside the field. Subfields of file records and record children
    are NOT included (records are walked separately where needed); this
    mirrors the legacy flat_fields, which also excluded file-record subfields.

    Parameters
    ----------
    component :
        The component definition.
    developmode :
        If False (default), fields marked developmode are excluded.
    """
    result: list[tuple[str, FieldV3]] = []
    for block_name, block in (component.blocks or {}).items():
        for f in block.fields.values():
            f = apply_override(component.name, f)
            if f.developmode and not developmode:
                continue
            result.append((block_name, f))
    return result


# Python type annotations

_SCALAR_PY_TYPES: dict[type, str] = {
    KeywordField: "bool",
    Integer: "int",
    Double: "float",
    String: "str",
}


def py_type(f: FieldV3, block_name: str) -> str:
    """Return the Python type annotation string for a field."""
    if is_aux_list_field(f):
        return "Optional[list[str]]"
    if is_file_record(f) or is_bare_file(f):
        base = "Path"
    elif is_boundname_field(f, block_name):
        base = "NDArray[np.str_]"
    elif is_keyword_array(f):
        base = "NDArray[np.bool_]"
    elif is_array(f):
        assert isinstance(f, Array)
        if block_name == "griddata":
            base = "IntArrayLike" if f.dtype == "integer" else "FloatArrayLike"
        else:
            dtype = ARRAY_NUMPY_DTYPES.get(f.dtype, "np.object_")
            base = f"NDArray[{dtype}]"
    elif is_dimensions_scalar(f, block_name):
        # dimensions fields are computed (init=False) and always nullable
        base = _SCALAR_PY_TYPES.get(type(f), "Any")
        return f"Optional[{base}]"
    elif is_scalar(f):
        # Keywords are always bool (not Optional[bool]) regardless of optional flag.
        if isinstance(f, KeywordField):
            return "bool"
        base = _SCALAR_PY_TYPES.get(type(f), "Any")
    else:
        base = "Any"

    # Period-block arrays can be absent for a given stress period, so they're
    # implicitly nullable at the Python level even when the DFN marks them required.
    is_nullable = f.optional or is_period_array(f, block_name)
    return f"Optional[{base}]" if is_nullable else base


# Python name sanitisation


def safe_name(name: str) -> str:
    """Return a safe Python identifier for a DFN field name."""
    name = name.replace("-", "_")
    if keyword.iskeyword(name) or name in dir(builtins):
        return f"{name}_"
    return name


# spec() call strings


def _default_repr(f: FieldV3) -> str:
    """Return the Python repr of a field's default value."""
    default = f.default
    if default is None:
        # Scalar keywords default to False (absent == not set).
        # Arrays (including keyword arrays) default to None.
        if isinstance(f, KeywordField) and not getattr(f, "shape", None):
            return "False"
        return "None"
    if isinstance(default, str):
        if isinstance(f, Integer):
            try:
                return repr(int(default))
            except (ValueError, TypeError):
                pass
        elif isinstance(f, Double):
            try:
                return repr(float(default))
            except (ValueError, TypeError):
                pass
        return _dq(default)
    return repr(default)


# New-codegen field call strings


def field_metadata(f: FieldV3, block_name: str, *, has_maxbound: bool = False) -> dict:
    """Build the ``field()``/``path()`` spec-call kwargs for a field (new codegen path).

    Codegen-v2 packages are plain attrs classes (not ``@xattree``-decorated), so
    these calls carry passive metadata read by the codec and conversion methods
    at call time rather than real xattree array/dim/coord structure.
    """
    kw: dict = {"block": block_name}
    if shape := getattr(f, "shape", None):
        kw["shape"] = tuple(shape)
    if getattr(f, "netcdf", False):
        kw["netcdf"] = True
    if getattr(f, "time_series", False):
        kw["time_series"] = True
    if f.optional:
        kw["optional"] = True
    if block_name == "dimensions" and f.name == "maxbound" and has_maxbound:
        kw["auto_from"] = "stress_period_data"
    if is_file_record(f):
        child = file_child(f)
        kw["inout"] = "filein" if child.direction == "in" else "fileout"
    elif is_bare_file(f):
        kw["inout"] = "filein" if f.direction == "in" else "fileout"
    return kw


def _dq(v) -> str:
    """Format a scalar value as a Python literal using double-quoted strings.

    Used when emitting metadata dicts and schema ClassVars into generated source
    so all string literals use double quotes for consistency with ruff output.
    """
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, tuple):
        inner = ", ".join(f'"{s}"' if isinstance(s, str) else repr(s) for s in v)
        trailing = "," if len(v) == 1 else ""
        return f"({inner}{trailing})"
    return repr(v)


def field_call(f: FieldV3, block_name: str, *, has_maxbound: bool = False) -> str:
    """Return the field()/path() spec call string for a field.

    Emits a multi-line call to comply with the 100-char line-length limit.
    Continuation lines are pre-indented for class body (8-space args,
    4-space closing paren).
    """
    kw = field_metadata(f, block_name, has_maxbound=has_maxbound)
    # maxbound is auto-computed from stress_period_data at write time; default 0.
    if block_name == "dimensions" and f.name == "maxbound":
        default = "0"
    else:
        default = _default_repr(f)
    # String-encoded numeric defaults (e.g. '1.e-5', '1000.') are valid at
    # runtime but mypy can't verify they satisfy Optional[float/int].
    # Scalar defaults (int, float, str) on Int/FloatArrayLike fields have the same issue.
    _str_default = default.startswith("'")
    _numeric_field = isinstance(f, (Double, Integer))
    type_ignore = ""
    if (is_array(f) and default != "None") or (_str_default and _numeric_field):
        type_ignore = "  # type: ignore[assignment]"
    fn = "path" if (is_file_record(f) or is_bare_file(f)) else "field"
    lines = [f"{fn}(", f"        default={default},"]
    if is_file_record(f) or is_bare_file(f):
        lines.append("        converter=_optional_path,")
    for k, v in kw.items():
        lines.append(f"        {k}={_dq(v)},")
    lines.append(f"    ){type_ignore}")
    return "\n".join(lines)


def python_repr(v) -> str:
    """Format a list[dict] schema as multi-line Python for class-body assignment.

    Registered as the ``python_repr`` Jinja filter. Produces 8-space item
    indent, 12-space key indent, 4-space closing bracket so the result renders
    correctly after ``    __name__: ClassVar[...] = ``.
    """
    if not isinstance(v, list):
        return repr(v)
    lines = ["["]
    for item in v:
        if isinstance(item, dict):
            lines.append("        {")
            for k, val in item.items():
                lines.append(f'            "{k}": {_dq(val)},')
            lines.append("        },")
        else:
            lines.append(f"        {_dq(item)},")
    lines.append("    ]")
    return "\n".join(lines)


def row_class(
    schema_list: list[dict], class_name: str, is_period: bool = False, has_aux: bool = False
) -> str:
    """Render a Row subclass (flopy4.mf6.row.Row) for list block construction.

    Called as::

        {{ spec.period_schema | row_class("Row", True) }}
        {{ block_schema | row_class("PackagedataRow") }}

    Produces a 4-space-indented ``@attrs.define`` class whose fields carry
    real metadata (``pk=``/``fk=``/``cellid=``/``time_series=``/``prefix=``/
    ``tagged=``, via ``field()``) -- the class itself is the schema;
    structure.py/unstructure.py introspect it directly (see flopy4.mf6.row).
    No separate Schema/Column description is emitted.

    Required fields (no default) are declared before optional fields to
    satisfy attrs ordering constraints.

    ``is_period=True`` injects ``aux: tuple = ()`` between required value
    columns and optional columns, for packages that accept positional AUXILIARY
    columns in their stress period rows. Static list blocks (packagedata,
    connectiondata, etc.) have fixed DFN schemas and never carry dynamic aux
    columns, so ``is_period`` should be False (the default) for those.
    """
    if not schema_list:
        return ""

    _DFN_PY: dict[str, str] = {
        "double": "float",
        "double precision": "float",
        "integer": "int",
        "string": "str",
        "keyword": "str",
        "object": "object",
    }

    def _py_type(col: dict) -> str:
        role = col["role"]
        if role == "cellid":
            return "tuple"
        if role == "feature_id":
            return "int"
        if role in ("keystring", "inline_keyword"):
            return "str"
        if role == "keystring_value":
            return "object"
        if role == "boundname":
            return "str"
        if col.get("time_series") or col.get("dtype") == "np.object_":
            return "Union[float, str]"
        return _DFN_PY.get(col.get("dfn_type", "double"), "float")

    def _is_optional(col: dict) -> bool:
        # keystring_value is always optional: some keystring arms are bare
        # keywords with no payload at all (e.g. PRT-PRP's FIRST/LAST/ALL --
        # confirmed via the v1 DFN, no feature-id/value field), so a
        # required "value" would fail to parse those rows from file tokens.
        return bool(col.get("optional")) or col["role"] in (
            "boundname",
            "inline_keyword",
            "keystring_value",
        )

    def _prefix_inout(col: dict) -> str:
        """MF6 inout direction implied by a row column's prefix tokens."""
        return "fileout" if "FILEOUT" in (col.get("prefix") or "").upper().split() else "filein"

    def _prefix_tokens(col: dict) -> tuple:
        """Fixed literal prefix token(s) preceding FILEIN/FILEOUT itself (e.g.
        SSM fileinput's "SPC6", LAK tables' "TAB6") -- the FILEIN/FILEOUT
        keyword is handled separately via inout=, not part of this tuple."""
        parts = (col.get("prefix") or "").split()
        return tuple(p for p in parts if p not in ("FILEIN", "FILEOUT"))

    def _field_meta(col: dict) -> dict:
        role = col["role"]
        meta: dict = {}
        if role == "cellid":
            meta["cellid"] = True
        elif role == "feature_id":
            if col.get("fk"):
                meta["fk"] = col["fk"]
            else:
                meta["pk"] = True
        elif role == "inline_keyword":
            meta["tagged"] = True
        if col.get("time_series"):
            meta["time_series"] = True
        if _is_optional(col):
            # Needed even for time_series fields: _n_fixed_tokens() (row.py)
            # uses this to tell "always present" fixed columns apart from
            # trailing columns that may be entirely absent from a given row
            # (e.g. EVT's pxdp/petm/petm0, only written when
            # surf_rate_specified) when inferring a variable-width cellid's
            # element count from raw token counts.
            meta["optional"] = True
        return meta

    def _field_line(col: dict, *, optional: bool) -> str:
        # File-reference columns (a fixed MF6 token or two before a filename,
        # e.g. LAK tables' "TAB6 FILEIN <file>") are Path fields built via the
        # same path() convention used for Package-level file fields, not the
        # generic dtype-based Union[float, str] fallback below.
        if col.get("prefix"):
            inout = _prefix_inout(col)
            fixed = _prefix_tokens(col)
            prefix_kw = f", prefix={_dq(fixed)}" if fixed else ""
            if optional:
                return (
                    f"        {col['name']}: Optional[Path] = path(\n"
                    f'            default=None, converter=_optional_path, inout="{inout}"{prefix_kw}\n'
                    f"        )"
                )
            return f'        {col["name"]}: Path = path(converter=Path, inout="{inout}"{prefix_kw})'
        py_type = _py_type(col)
        meta = _field_meta(col)
        margs = ", ".join(f"{k}={_dq(v)}" for k, v in meta.items())
        if optional:
            if meta:
                return f"        {col['name']}: Optional[{py_type}] = field(default=None, {margs})"
            return f"        {col['name']}: Optional[{py_type}] = None"
        if meta:
            return f"        {col['name']}: {py_type} = field({margs})"
        return f"        {col['name']}: {py_type}"

    required = [col for col in schema_list if not _is_optional(col)]
    optional = [col for col in schema_list if _is_optional(col)]
    # Aux injection: period blocks (standard stress packages CHD, WEL, DRN,
    # … carry aux as positional trailing columns whose count equals
    # len(package.auxiliary); keystring period packages (LAK, SFR) embed
    # AUXILIARY as a named keyword arm instead -- no positional aux there)
    # and packagedata blocks specifically (has_aux=True, passed by the
    # template only for block_name == "packagedata" -- the one static list
    # block MF6 allows per-row aux values on; connectiondata/tables/outlets
    # etc. have fixed schemas and never carry dynamic aux columns).
    has_positional_aux = has_aux or (
        is_period and not any(col["role"] == "keystring" for col in schema_list)
    )

    # aux sits between other optional columns and boundname in the real DFN
    # token order (e.g. EVT: ..., pxdp, petm, petm0, aux, boundname) -- not
    # necessarily right after the required columns (some packages, like EVT,
    # have their own optional value columns before aux).
    optional_non_boundname = [col for col in optional if col["role"] != "boundname"]
    boundname_cols = [col for col in optional if col["role"] == "boundname"]

    lines = ["    @attrs.define"]
    lines.append(f"    class {class_name}(Row):")
    for col in required:
        lines.append(_field_line(col, optional=False))
    for col in optional_non_boundname:
        lines.append(_field_line(col, optional=True))
    if has_positional_aux:
        lines.append("        aux: tuple = ()")
    for col in boundname_cols:
        lines.append(_field_line(col, optional=True))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# List-block column schema utilities
# ---------------------------------------------------------------------------
# These functions derive recarray block column schemas directly from dev3
# List/Record/Array fields. Used by make.py to auto-detect list blocks and
# build BlockPropertySpec. Replaces the legacy schema's v1-DFN-sourced
# ColumnSpec/block_schema (which needed v1 DFN data because dfn2toml dropped
# column-level detail, and used the bespoke `numeric_index` flag) -- dev3
# carries real pk/fk and real column structure natively, no v1 fallback needed.
# ---------------------------------------------------------------------------


@dataclass
class ColumnSpec:
    """Schema for one column in a dev3 List[Record] block."""

    name: str
    field: FieldV3  # the underlying dev3 field, for shape/dtype/time_series/fk access
    is_cellid: bool  # shape=["ncelldim"] -- stored as object-dtype tuple attr
    is_prefix: bool  # tagged non-optional keyword -- write-side token only, no attr
    is_row_keyword: bool  # optional keyword -- stored as bool attr
    is_index: bool  # pk or fk column: 0-based index written as 1-based (+1 at write time)


def find_keystring_union(list_field: ListField) -> UnionField | None:
    """Find the discriminating Union in a List field's per-row shape, if any.

    Two real shapes seen in the corpus:
    - OC-style: ``item`` is a Union directly (no Record wrapper) -- saverecord/
      printrecord.
    - LAK-style: ``item`` is a Record with exactly one field, itself a Union
      (no separate index column -- each arm carries its own fk index, e.g.
      LAK's ``lakeno``/``outletno``).
    - LKE/LKT/SFR-style: ``item`` is a Record with an index column *and* a
      sibling Union field (e.g. gwe-lke's ``{lakeno: Integer, laksetting:
      Union}`` -- the index is a plain field here, not embedded per-arm).

    Returns None for ordinary (non-keystring) list blocks -- packagedata,
    connectiondata, standard period blocks (CHD/WEL/DRN-style) -- where
    ``item`` is a Record with no Union field anywhere among its top-level
    fields.
    """
    item = list_field.item
    if isinstance(item, UnionField):
        return item
    if isinstance(item, Record):
        for f in item.fields.values():
            if isinstance(f, UnionField):
                return f
    return None


def list_columns(f: ListField, component_name: str = "") -> list[ColumnSpec]:
    """Return the leaf column specs of a dev3 List[Record] field, in order.

    Returns [] for keystring-shaped lists (see find_keystring_union) -- those
    are handled separately (see make.py's keystring period handling).

    ``component_name`` applies dfn_overrides.toml patches to list columns --
    unlike top-level block fields (patched in flat_fields), columns nested
    inside a List's item Record aren't reached by that walk, so this is the
    only place a list-column override (e.g. a temporary pk=True stopgap for
    a numeric_index field devtools hasn't backfilled yet) takes effect.
    """
    if find_keystring_union(f) is not None:
        return []
    item = f.item
    if not isinstance(item, Record):
        return []
    result = []
    for col_name, raw_col in item.fields.items():
        col = apply_override(component_name, raw_col) if component_name else raw_col
        is_keyword = isinstance(col, KeywordField)
        is_optional = col.optional
        result.append(
            ColumnSpec(
                name=col_name,
                field=col,
                is_cellid=isinstance(col, Array) and list(col.shape or []) == ["ncelldim"],
                is_prefix=is_keyword and not is_optional,
                is_row_keyword=is_keyword and is_optional,
                # role="feature_id" implies MF6's numeric 0-based-Python/1-based-
                # file conversion (structure.py: int(...) - 1) -- only sound for
                # integer indices. String pk/fk (e.g. MVR's `pname`, a package
                # *name* reference, not a numeric one) must stay role="value".
                is_index=isinstance(col, Integer)
                and bool(getattr(col, "pk", False) or getattr(col, "fk", None)),
            )
        )
    return result


def is_keystring_list(f: ListField) -> bool:
    """True if a List field's per-row shape has a discriminating Union
    (keystring period style)."""
    return find_keystring_union(f) is not None


def list_col_dim(f: ListField, component: Component) -> str | None:
    """Return the dimension name for list column arrays.

    Uses the last entry of the list field's explicit shape when present,
    preferring the actual dimensions-block field name when the shape entry
    differs (e.g. shape uses 'npackages' but field is 'maxpackages').
    Falls back to the single entry in the component's dimensions block.
    Returns None when the dimension cannot be determined unambiguously.
    """
    dim_block = (component.blocks or {}).get("dimensions")
    dim_names = list(dim_block.fields.keys()) if dim_block is not None else []
    if shape := (f.shape or []):
        shape_dim = shape[-1]
        if shape_dim in dim_names:
            return shape_dim
        # Shape dim may use a different prefix than the actual field name
        # (e.g., shape "npackages" vs dimensions field "maxpackages"). Try
        # suffix matching: strip leading "n" and find a field that ends with
        # the remainder.
        suffix = shape_dim.lstrip("n")
        if suffix:
            for fname in dim_names:
                if fname.endswith(suffix):
                    return fname
    if len(dim_names) == 1:
        return dim_names[0]
    return None


def list_block_names(component: Component) -> list[str]:
    """Return block names that contain list-type fields, in component order."""
    seen: set[str] = set()
    result = []
    for block_name, f in flat_fields(component):
        if is_list_field(f) and block_name not in seen:
            seen.add(block_name)
            result.append(block_name)
    return result


def collision_names(
    block_schemas: dict[str, list[ColumnSpec]],
    reserved: frozenset[str] = frozenset(),
) -> set[str]:
    """Column names that require block-prefixed Python attr names.

    A name is a collision when it appears in more than one static list block,
    OR when it appears in any block AND is reserved by a period field. The
    latter ensures that static block attrs never shadow bare period field names.
    Prefix columns are excluded since they produce no attr.
    """
    names = [col.name for cols in block_schemas.values() for col in cols if not col.is_prefix]
    counts = Counter(names)
    return {name for name, count in counts.items() if count > 1 or name in reserved}
