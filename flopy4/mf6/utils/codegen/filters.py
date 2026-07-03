"""
Python-side filters for MF6 code generation.

Converts modflow_devtools.dfn.Dfn/Field dataclasses to the context
dicts consumed by Jinja templates. Keeping computation here (rather
than in Jinja macros) makes edge-case handling easier to test and debug.
"""

import builtins
import keyword
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modflow_devtools.dfn import Dfn, Field

from .overrides import apply as apply_override

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


# DFN block-level helpers


def has_period_block(dfn: Dfn) -> bool:
    """True if the DFN defines a period block (stress package)."""
    return "period" in (dfn.get("blocks") or {})


def has_dimensions_block(dfn: Dfn) -> bool:
    """True if the DFN has a dimensions block with a 'maxbound' field.

    Only packages with a field literally named 'maxbound' use the
    auto-computed pattern (init=False, on_setattr=update_maxbound).
    Packages like MVR/BUY/VSC have user-specified dimension scalars
    (maxmvr, maxpackages, nrhospecies) that must NOT be init=False.
    """
    dim_block = (dfn.get("blocks", {}) or {}).get("dimensions", {})
    return "maxbound" in dim_block


# Field classification

# v2 TOML uses "double" for what v1 called "double precision"
_SCALAR_TYPES = {"keyword", "integer", "double precision", "double", "string"}
_ARRAY_BASE_TYPES = {"double precision", "double", "integer", "string"}

# DFN dimension name → flopy4 canonical dimension name.
# Applied when converting DFN shape strings to dims tuples.
_DIM_ALIASES: dict[str, str] = {
    "nnodes": "nodes",
}

# Alternative-grid shape tokens: each key is a raw DFN token that appears in
# shape strings and contains * or ; (making it look "complex"), but maps to a
# single well-known flopy4 dimension. Substituted before complexity checks.
# "ncol*nrow; ncpl": cells per layer — ncol*nrow for DIS, ncpl for DISV.
_ALT_DIM_TOKENS: dict[str, str] = {
    "ncol*nrow; ncpl": "ncpl",
}

# DFN dimension names that are dropped from dims tuples entirely.
# naux: auxiliary variable count is not tracked as an xattree dim —
# auxiliary data is stored flattened into the primary node dimension.
# nseg-1: number of ET segment values per row (EVT list-based input);
# repeated columns per row like naux, not a separate array dimension.
_DROP_DIMS: frozenset[str] = frozenset({"naux", "nseg-1"})


def _has_file_child(f: Field) -> bool:
    if f.get("children", None):
        return "filein" in f["children"] or "fileout" in f["children"]
    # v1 DFN fields encode subfields in the type string, e.g.
    # "record ts6 filein ts6_filename" — check there instead.
    return " filein " in f["type"] or " fileout " in f["type"]


def _has_file_child_of(f: Field, kind: str) -> bool:
    """True if the record has a child of the given kind ('filein' or 'fileout')."""
    if f.get("children", None):
        return kind in f["children"]
    return f" {kind} " in f["type"]


def _file_record_subfield_names(f: Field) -> frozenset[str]:
    """Return the subfield names encoded in a v1 DFN record type string."""
    if f.get("children", None):
        return frozenset(f["children"])
    # type string format: "record name1 name2 ..."
    parts = f["type"].split()
    return frozenset(parts[1:]) if len(parts) > 1 else frozenset()


def _resolve_alt_grid(shape: str) -> str:
    """Replace known alternative-grid tokens with their canonical names."""
    for token, canonical in _ALT_DIM_TOKENS.items():
        shape = shape.replace(token, canonical)
    return shape


def _has_complex_shape(f: Field) -> bool:
    """True for shapes with unsupported alternative-grid or arithmetic notation."""
    if not f.get("shape", None):
        return False
    resolved = _resolve_alt_grid(f["shape"])
    return "*" in resolved or ";" in resolved


def is_scalar(f: Field) -> bool:
    """True for simple scalar fields (no shape)."""
    return f["type"] in _SCALAR_TYPES and not f.get("shape", None)


_STRING_LENGTH_DIMS = frozenset({"lenbigline", "linelength"})


def is_array(f: Field) -> bool:
    """True for array fields (numeric or string type with a shape).

    Excludes auxiliary variable lists, which are handled by is_aux_list_field.
    """
    # TODO: emit string fields shaped only by lenbigline/linelength as field(Optional[str]);
    # for now exclude so they fall to scalar handling (see ncf.py Ncf.wkt for the pattern).
    if (
        f["type"] == "string"
        and f.get("shape", None)
        and all(s in _STRING_LENGTH_DIMS for s in f.get("shape", None))
    ):
        return False
    return (
        f["type"] in _ARRAY_BASE_TYPES
        and bool(f.get("shape", None))
        and not _has_complex_shape(f)
        and not is_aux_list_field(f)
    )


def is_keyword_array(f: Field) -> bool:
    """True for boolean-array fields (keyword type with shape)."""
    return f["type"] == "keyword" and bool(f.get("shape", None)) and not _has_complex_shape(f)


def is_file_record(f: Field) -> bool:
    """True for record fields whose children include filein or fileout."""
    return f["type"].startswith("record") and _has_file_child(f)


def is_aux_list_field(f: Field) -> bool:
    """True for auxiliary variable name lists (options block, shape naux).

    These are generated as ``Optional[list[str]]`` with no dims and no
    structure_array converter, matching the hand-written pattern.
    """
    return (
        f["type"] == "string"
        and f["block"] == "options"
        and bool(f.get("shape", None))
        and "naux" in f.get("shape", None)
    )


def is_period_array(f: Field) -> bool:
    """True for array fields in the period block."""
    return f["block"] == "period" and (is_array(f) or is_keyword_array(f))


def is_dimensions_scalar(f: Field) -> bool:
    """True for scalar fields in the dimensions block (computed, init=False)."""
    return f["block"] == "dimensions" and is_scalar(f)


def is_boundname_field(f: Field) -> bool:
    """True for the boundname string array in the period block."""
    return f["block"] == "period" and f["name"] == "boundname"


# Per-package OC record types.  Each entry maps a DFN name to the list of
# rtype strings that are valid for its SAVE/PRINT period records.
_OC_RTYPES: dict[str, list[str]] = {
    "gwf-oc": ["head", "budget"],
    "gwt-oc": ["concentration", "budget"],
    "gwe-oc": ["temperature", "budget"],
    "prt-oc": ["budget"],
}


def is_oc_record(f: Field, dfn_name: str) -> bool:
    """True for saverecord/printrecord in OC-style period blocks.

    These records take the form ``SAVE|PRINT RTYPE OCSETTING`` and are
    expanded by codegen into per-rtype NDArray[np.str_] fields rather than
    being emitted as inner classes or TODO comments.
    """
    return (
        f["block"] == "period"
        and f["type"].startswith("record")
        and f["name"] in ("saverecord", "printrecord")
        and dfn_name in _OC_RTYPES
    )


def is_list_field(f: Field) -> bool:
    """True for list-type sub-table fields (packagedata, perioddata, etc.)."""
    return f["type"] == "list"


def list_columns(f: Field) -> list[dict]:
    """Return the leaf column dicts of a list-type sub-table.

    Children in the v2 TOML schema are stored as plain dicts, not Field
    objects.  The list field has a single record child dict; the column
    entries are that record's ``children`` mapping.
    """
    if not f.get("children", None):
        return []
    record_child = next(iter(f["children"].values()))
    if not isinstance(record_child, dict):
        return []
    return list(record_child.get("children", {}).values())


def list_col_dim(f: Field, dfn: Dfn) -> str | None:
    """Return the dimension name for list column arrays.

    Uses the last token from the list field's explicit shape when present,
    preferring the actual dimensions-block field name when the shape token
    differs (e.g. shape uses 'npackages' but field is 'maxpackages').
    Falls back to the single entry in the DFN's dimensions block.
    Returns None when the dimension cannot be determined unambiguously.
    """
    dim_block = (dfn.get("blocks") or {}).get("dimensions", {})
    if shape := f.get("shape", None):
        inner = shape.strip().strip("()")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        if parts:
            shape_dim = _DIM_ALIASES.get(parts[-1], parts[-1])
            if shape_dim in dim_block:
                return shape_dim
            # Shape dim may use a different prefix than the actual field name
            # (e.g., shape "npackages" vs dimensions field "maxpackages").
            # Try suffix matching: strip leading "n" and find a field that ends
            # with the remainder.
            suffix = shape_dim.lstrip("n")
            if suffix:
                for fname in dim_block:
                    if fname.endswith(suffix):
                        return fname
    if len(dim_block) == 1:
        name = next(iter(dim_block))
        return _DIM_ALIASES.get(name, name)
    return None


def is_generatable(f: Field) -> bool:
    """True if this field can be handled in the current generation pass."""
    if _has_complex_shape(f):
        return False
    return (
        is_scalar(f)
        or is_array(f)
        or is_keyword_array(f)
        or is_file_record(f)
        or is_aux_list_field(f)
    )


def _is_expandable_child(child: dict) -> bool:
    """True if a record child dict can be generated as a standalone field.

    Only keyword-type children are expandable: they're self-naming tokens that
    map cleanly to individual bool fields.  Scalar data fields (even tagged ones)
    are positional components of a compound construct and must stay grouped.
    """
    return child["type"] == "keyword"


_RECORD_CLASS_SCALAR_TYPES = frozenset({"integer", "double precision", "double", "string"})


def can_generate_record_class(f: Field) -> bool:
    """True when a compound record should be rendered as an inner attrs class.

    All non-file records whose children are entirely scalars and/or keywords
    become inner attrs classes.  The first keyword child (if any) is the
    trigger token (``_keyword``); remaining keyword children become
    ``Optional[bool]`` fields so related options stay grouped.

    All-keyword records with only one child (a lone flag keyword) are left to
    :func:`can_expand_record` — a bare bool field is cleaner there than an
    empty inner class.  Records with unsupported child types (recarray, union,
    complex shapes) fall back to TODO comments.
    """
    if is_file_record(f) or not f.get("children", None):
        return False
    children = list(f["children"].values())
    _supported = _RECORD_CLASS_SCALAR_TYPES | {"keyword"}
    all_supported = all(c.get("type") in _supported for c in children)
    if not all_supported:
        return False
    has_scalar = any(c.get("type") in _RECORD_CLASS_SCALAR_TYPES for c in children)
    # All-keyword records need at least 2 children (trigger + modifier) to
    # justify a class; a single lone keyword expands more cleanly to a bool.
    if not has_scalar:
        return len(children) >= 2
    return True


def can_expand_record(f: Field) -> bool:
    """True if a non-file compound record can be at least partially expanded.

    A record can be expanded when all its required (non-optional) children are
    individually generatable as standalone fields.  Optional children that
    can't be generated standalone are noted in a TODO comment but don't
    block expansion.
    """
    if is_file_record(f) or not f.get("children", None):
        return False
    for child in f["children"].values():
        if not child.get("optional", False) and not _is_expandable_child(child):
            return False
    return True


def skip_reason(f: Field) -> str | None:
    """Return a human-readable reason why a field is skipped, or None."""
    if is_generatable(f):
        return None
    if is_list_field(f):
        return None  # handled as recarray block in build_component_spec
    if can_expand_record(f):
        return None  # handled by _expand_record_field in make.py
    if _has_complex_shape(f):
        return f"complex shape '{f.get('shape', None)}' not yet supported"
    if f["type"] in ("record", "recarray", "keystring"):
        return f"complex type '{f['type']}' not yet supported"
    return f"type '{f['type']}' not yet supported"


# Field iteration


def flat_fields(dfn: Dfn, *, developmode: bool = False) -> list[Field]:
    """Return an ordered flat list of all fields from all blocks.

    Parameters
    ----------
    dfn :
        The component definition.
    developmode :
        If False (default), fields marked developmode are excluded.
    """
    # Collect subfield names from file records so they can be suppressed.
    subfield_names: set[str] = set()
    for block in (dfn.get("blocks", {}) or {}).values():
        for f in block.values():
            if is_file_record(f):
                subfield_names.update(_file_record_subfield_names(f))

    result = []
    for block in (dfn.get("blocks", {}) or {}).values():
        for f in block.values():
            f = apply_override(dfn["name"], f)
            if f.get("developmode", False) and not developmode:
                continue
            if f["name"] in subfield_names:
                continue
            result.append(f)
    return result


# Python type annotations

_SCALAR_PY_TYPES: dict[str, str] = {
    "keyword": "bool",
    "integer": "int",
    "double precision": "float",
    "double": "float",
    "string": "str",
}

ARRAY_NUMPY_DTYPES: dict[str, str] = {
    "double precision": "np.float64",
    "double": "np.float64",
    "integer": "np.int64",
    "string": "np.object_",
    "keyword": "np.bool_",
}


def py_type(f: Field) -> str:
    """Return the Python type annotation string for a field."""
    if is_aux_list_field(f):
        return "Optional[list[str]]"
    if is_file_record(f):
        base = "Path"
    elif is_boundname_field(f):
        base = "NDArray[np.str_]"
    elif is_keyword_array(f):
        base = "NDArray[np.bool_]"
    elif is_array(f):
        if f.get("block") == "griddata":
            base = "IntArrayLike" if f["type"] == "integer" else "FloatArrayLike"
        else:
            dtype = ARRAY_NUMPY_DTYPES.get(f["type"], "np.object_")
            base = f"NDArray[{dtype}]"
    elif is_dimensions_scalar(f):
        # dimensions fields are computed (init=False) and always nullable
        base = _SCALAR_PY_TYPES.get(f["type"], "Any")
        return f"Optional[{base}]"
    elif is_scalar(f):
        # Keywords are always bool (not Optional[bool]) regardless of optional flag.
        if f["type"] == "keyword":
            return "bool"
        base = _SCALAR_PY_TYPES.get(f["type"], "Any")
    else:
        base = "Any"

    # Period-block arrays can be absent for a given stress period, so they're
    # implicitly nullable at the Python level even when the DFN marks them required.
    is_nullable = f.get("optional", None) or is_period_array(f)
    return f"Optional[{base}]" if is_nullable else base


# Python name sanitisation


def safe_name(name: str) -> str:
    """Return a safe Python identifier for a DFN field name."""
    name = name.replace("-", "_")
    if keyword.iskeyword(name) or name in dir(builtins):
        return f"{name}_"
    return name


# spec() call strings


def _dims_tuple_val(shape: str, *, keep: frozenset[str] | None = None) -> tuple:
    """Like _dims_tuple but returns an actual tuple instead of a string literal."""
    resolved = _resolve_alt_grid(shape)
    inner = resolved.strip().strip("()")
    raw = [_DIM_ALIASES.get(p.strip(), p.strip()) for p in inner.split(",") if p.strip()]
    drop = _DROP_DIMS - (keep or frozenset())
    return tuple(p for p in raw if p not in drop)


def _default_repr(f: Field) -> str:
    """Return the Python repr of a field's default value."""
    default = f.get("default", None)
    if default is None:
        # Scalar keywords default to False (absent == not set).
        # Arrays (including keyword arrays) default to None.
        if f["type"] == "keyword" and not f.get("shape", None):
            return "False"
        return "None"
    if isinstance(default, str):
        dfn_type = f.get("type", "")
        if dfn_type == "integer":
            try:
                return repr(int(default))
            except (ValueError, TypeError):
                pass
        elif dfn_type in ("double", "double precision"):
            try:
                return repr(float(default))
            except (ValueError, TypeError):
                pass
        return _dq(default)
    return repr(default)


# New-codegen field call strings


def field_metadata(f: Field, *, has_maxbound: bool = False) -> dict:
    """Build the ``field()``/``path()`` spec-call kwargs for a field (new codegen path).

    Codegen-v2 packages are plain attrs classes (not ``@xattree``-decorated), so
    these calls carry passive metadata read by the codec and conversion methods
    at call time rather than real xattree array/dim/coord structure.
    """
    kw: dict = {"block": f["block"]}
    if shape := f.get("shape"):
        kw["shape"] = _dims_tuple_val(shape)
    if f.get("layered"):
        kw["layered"] = True
    if f.get("netcdf"):
        kw["netcdf"] = True
    if f.get("time_series"):
        kw["time_series"] = True
    if f.get("optional"):
        kw["optional"] = True
    if f["block"] == "dimensions" and f["name"] == "maxbound" and has_maxbound:
        kw["auto_from"] = "stress_period_data"
    if is_file_record(f):
        kw["inout"] = "filein" if _has_file_child_of(f, "filein") else "fileout"
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


def field_call(f: Field, *, has_maxbound: bool = False) -> str:
    """Return the field()/path() spec call string for a field.

    Emits a multi-line call to comply with the 100-char line-length limit.
    Continuation lines are pre-indented for class body (8-space args,
    4-space closing paren).
    """
    kw = field_metadata(f, has_maxbound=has_maxbound)
    # maxbound is auto-computed from stress_period_data at write time; default 0.
    if f["block"] == "dimensions" and f["name"] == "maxbound":
        default = "0"
    else:
        default = _default_repr(f)
    # String-encoded numeric defaults (e.g. '1.e-5', '1000.') are valid at
    # runtime but mypy can't verify they satisfy Optional[float/int].
    # Scalar defaults (int, float, str) on Int/FloatArrayLike fields have the same issue.
    _str_default = default.startswith("'")
    _numeric_field = f.get("type", "") in ("double", "double precision", "integer")
    type_ignore = ""
    if (is_array(f) and default != "None") or (_str_default and _numeric_field):
        type_ignore = "  # type: ignore[assignment]"
    fn = "path" if is_file_record(f) else "field"
    lines = [f"{fn}(", f"        default={default},"]
    if is_file_record(f):
        lines.append("        converter=_optional_path,")
    for k, v in kw.items():
        lines.append(f"        {k}={_dq(v)},")
    lines.append(f"    ){type_ignore}")
    return "\n".join(lines)


def python_repr(v) -> str:
    """Format a list[dict] schema as multi-line Python for class-body assignment.

    Registered as the ``python_repr`` Jinja filter.  Produces 8-space item
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


def row_class(schema_list: list[dict], class_name: str, is_period: bool = False) -> str:
    """Render an @attrs.define Row nested class for list block construction.

    Called as::

        {{ spec.period_schema | row_class("Row", True) }}
        {{ block_schema | row_class("PackagedataRow") }}

    Produces a 4-space-indented ``@attrs.define`` class with typed fields and
    an ``__iter__`` method that yields column values in schema column order.
    Row instances can be passed anywhere nested lists are accepted — they are
    coerced to np.recarray in ``__attrs_post_init__`` exactly like nested lists.

    Required fields (no default) are declared before optional fields to
    satisfy attrs ordering constraints.  ``__iter__`` follows schema column
    order so coercion produces the correct recarray layout.

    ``is_period=True`` injects ``aux: tuple = ()`` between required value
    columns and optional columns, for packages that accept positional AUXILIARY
    columns in their stress period recarray.  Static list blocks (packagedata,
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
        return bool(col.get("optional")) or col["role"] in ("boundname", "inline_keyword")

    required = [col for col in schema_list if not _is_optional(col)]
    optional = [col for col in schema_list if _is_optional(col)]
    # Aux injection: only for period blocks.  Standard stress packages (CHD,
    # WEL, DRN, …) carry aux as positional trailing columns in the recarray
    # whose count equals len(package.auxiliary).  Keystring period packages
    # (LAK, SFR) embed AUXILIARY as a named keyword record — no positional aux.
    # Static list blocks (packagedata, connectiondata, etc.) have fixed schemas
    # and never carry dynamic aux columns regardless of package options.
    has_positional_aux = is_period and not any(col["role"] == "keystring" for col in schema_list)

    lines = ["    @attrs.define"]
    lines.append(f"    class {class_name}:")
    for col in required:
        lines.append(f"        {col['name']}: {_py_type(col)}")
    if has_positional_aux:
        lines.append("        aux: tuple = ()")
    for col in optional:
        lines.append(f"        {col['name']}: Optional[{_py_type(col)}] = None")
    lines.append("")
    lines.append("        def __iter__(self):")
    for col in required:
        lines.append(f"            yield self.{col['name']}")
    if has_positional_aux:
        lines.append("            yield from self.aux")
    for col in optional:
        lines.append(f"            yield self.{col['name']}")
    return "\n".join(lines)


def schema_class(schema_list: list[dict], class_name: str) -> str:
    """Render a Schema subclass body for a list[dict] column schema.

    Registered as the ``schema_class`` Jinja filter.  Called as::

        {{ spec.period_schema | schema_class("_PeriodSchema") }}

    Produces a 4-space-indented class definition (suitable for class-body
    emission in generated files) with one Column(...) attribute per column.
    Long Column() calls are wrapped to keep lines under the 100-character
    ruff limit.
    """
    if not schema_list:
        return ""
    lines = [f"    class {class_name}(Schema):"]
    for col in schema_list:
        name = col["name"]
        args = [f'"{name}"', f'role="{col["role"]}"', f'dfn_type="{col.get("dfn_type", "double")}"']
        if col.get("shape"):
            args.append(f'shape="{col["shape"]}"')
        if col.get("optional"):
            args.append("optional=True")
        if col.get("time_series"):
            args.append("time_series=True")
        if col.get("dtype"):
            args.append(f'dtype="{col["dtype"]}"')
        if col.get("prefix"):
            args.append(f'prefix="{col["prefix"]}"')
        single = f"        {name} = Column({', '.join(args)})"
        if len(single) <= 100:
            lines.append(single)
        else:
            # Wrap: each arg on its own line at 12-space indent.
            lines.append(f"        {name} = Column(")
            for arg in args:
                lines.append(f"            {arg},")
            lines.append("        )")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# v1 DFN block schema utilities
# ---------------------------------------------------------------------------
# These functions derive recarray block column schemas from v1 DFN data.
# Used by make.py to auto-detect list blocks and build BlockPropertySpec.
# ---------------------------------------------------------------------------


def _as_bool(val) -> bool:
    """Normalize a v1 DFN attribute that may be bool or string 'true'/'false'."""
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"


@dataclass
class ColumnSpec:
    """Schema for one column in a v1 DFN recarray block."""

    name: str
    type: str
    longname: str
    is_cellid: bool  # shape=(ncelldim) — stored as object-dtype tuple attr
    is_prefix: bool  # tagged non-optional keyword — write-side token only, no attr
    is_row_keyword: bool  # optional keyword — stored as bool attr
    numeric_index: bool  # 0-based index written as 1-based (+1 at write time)


def block_schema(v1_dfn: Dfn, block_name: str) -> list[ColumnSpec]:
    """Derive column schema for a recarray block from a v1 DFN.

    Finds the list-type header field in the block and reads columns from
    its nested children (built by the v2.0.0.dev1 migration). Returns one
    ColumnSpec per column in DFN order.
    """
    v1_block = (v1_dfn.get("blocks") or {}).get(block_name) or {}
    list_field = next((f for f in v1_block.values() if f.get("type") == "list"), None)
    if list_field is None:
        return []
    result = []
    for col in list_columns(list_field):
        ftype = col.get("type", "") or ""
        optional_val = col.get("optional")
        optional = _as_bool(optional_val or False)
        shape = str(col.get("shape", "") or "")
        is_keyword = ftype.lower() == "keyword"
        result.append(
            ColumnSpec(
                name=col.get("name", ""),
                type=ftype,
                longname=col.get("longname", "") or "",
                is_cellid="(ncelldim)" in shape,
                is_prefix=is_keyword and (optional_val is False),
                is_row_keyword=is_keyword and optional,
                numeric_index=bool(col.get("numeric_index", False)),
            )
        )
    return result


def list_block_names(dfn: Dfn) -> list[str]:
    """Return block names that contain list-type (recarray) fields, in DFN order."""
    seen: set[str] = set()
    result = []
    for f in flat_fields(dfn):
        if is_list_field(f) and f["block"] not in seen:
            seen.add(f["block"])
            result.append(f["block"])
    return result


def v1_list_block_names(v1_dfn: Dfn) -> list[str]:
    """Return recarray block names from a v1 DFN, in order.

    A block is a recarray when it contains a header field whose ``type``
    is ``"list"`` (v2.0.0.dev1) or starts with ``"recarray"`` (v1).
    Used to discover blocks that dfn2toml dropped from the v2 TOML.
    """
    seen: set[str] = set()
    result = []
    for block_name, block in (v1_dfn.get("blocks") or {}).items():
        if block_name in seen:
            continue
        if any(
            (f.get("type", "") or "").lower() == "list"
            or (f.get("type", "") or "").lower().startswith("recarray")
            for f in block.values()
        ):
            result.append(block_name)
            seen.add(block_name)
    return result


def collision_names(
    block_schemas: dict[str, list[ColumnSpec]],
    reserved: frozenset[str] = frozenset(),
) -> set[str]:
    """Column names that require block-prefixed Python attr names.

    A name is a collision when it appears in more than one static list block,
    OR when it appears in any block AND is reserved by a period field.  The
    latter ensures that static block attrs never shadow bare period field names.
    Prefix columns are excluded since they produce no attr.
    """
    names = [col.name for cols in block_schemas.values() for col in cols if not col.is_prefix]
    counts = Counter(names)
    return {name for name, count in counts.items() if count > 1 or name in reserved}
