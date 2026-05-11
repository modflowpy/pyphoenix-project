"""
Python-side filters for MF6 code generation.

Converts modflow_devtools.dfns Dfn/Field dataclasses to the context
dicts consumed by Jinja templates. Keeping computation here (rather
than in Jinja macros) makes edge-case handling easier to test and debug.
"""

import builtins
import keyword
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modflow_devtools.dfns import Dfn
from modflow_devtools.dfns.schema.field import Field

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
    return "period" in (dfn.blocks or {})


def has_dimensions_block(dfn: Dfn) -> bool:
    """True if the DFN has a dimensions block with a 'maxbound' field.

    Only packages with a field literally named 'maxbound' use the
    auto-computed pattern (init=False, on_setattr=update_maxbound).
    Packages like MVR/BUY/VSC have user-specified dimension scalars
    (maxmvr, maxpackages, nrhospecies) that must NOT be init=False.
    """
    dim_block = (dfn.blocks or {}).get("dimensions", {})
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
    if f.children:
        return "filein" in f.children or "fileout" in f.children
    # v1 DFN fields encode subfields in the type string, e.g.
    # "record ts6 filein ts6_filename" — check there instead.
    return " filein " in f.type or " fileout " in f.type


def _has_file_child_of(f: Field, kind: str) -> bool:
    """True if the record has a child of the given kind ('filein' or 'fileout')."""
    if f.children:
        return kind in f.children
    return f" {kind} " in f.type


def _file_record_subfield_names(f: Field) -> frozenset[str]:
    """Return the subfield names encoded in a v1 DFN record type string."""
    if f.children:
        return frozenset(f.children)
    # type string format: "record name1 name2 ..."
    parts = f.type.split()
    return frozenset(parts[1:]) if len(parts) > 1 else frozenset()


def _resolve_alt_grid(shape: str) -> str:
    """Replace known alternative-grid tokens with their canonical names."""
    for token, canonical in _ALT_DIM_TOKENS.items():
        shape = shape.replace(token, canonical)
    return shape


def _has_complex_shape(f: Field) -> bool:
    """True for shapes with unsupported alternative-grid or arithmetic notation."""
    if not f.shape:
        return False
    resolved = _resolve_alt_grid(f.shape)
    return "*" in resolved or ";" in resolved


def is_scalar(f: Field) -> bool:
    """True for simple scalar fields (no shape)."""
    return f.type in _SCALAR_TYPES and not f.shape


def is_array(f: Field) -> bool:
    """True for array fields (numeric or string type with a shape).

    Excludes auxiliary variable lists, which are handled by is_aux_list_field.
    """
    return (
        f.type in _ARRAY_BASE_TYPES
        and bool(f.shape)
        and not _has_complex_shape(f)
        and not is_aux_list_field(f)
    )


def is_keyword_array(f: Field) -> bool:
    """True for boolean-array fields (keyword type with shape)."""
    return f.type == "keyword" and bool(f.shape) and not _has_complex_shape(f)


def is_file_record(f: Field) -> bool:
    """True for record fields whose children include filein or fileout."""
    return f.type.startswith("record") and _has_file_child(f)


def is_aux_list_field(f: Field) -> bool:
    """True for auxiliary variable name lists (options block, shape naux).

    These are generated as ``Optional[list[str]]`` with no dims and no
    structure_array converter, matching the hand-written pattern.
    """
    return f.type == "string" and f.block == "options" and bool(f.shape) and "naux" in f.shape


def is_period_array(f: Field) -> bool:
    """True for array fields in the period block."""
    return f.block == "period" and (is_array(f) or is_keyword_array(f))


def is_dimensions_scalar(f: Field) -> bool:
    """True for scalar fields in the dimensions block (computed, init=False)."""
    return f.block == "dimensions" and is_scalar(f)


def is_boundname_field(f: Field) -> bool:
    """True for the boundname string array in the period block."""
    return f.block == "period" and f.name == "boundname"


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
        f.block == "period"
        and f.type.startswith("record")
        and f.name in ("saverecord", "printrecord")
        and dfn_name in _OC_RTYPES
    )


def is_list_field(f: Field) -> bool:
    """True for list-type sub-table fields (packagedata, perioddata, etc.)."""
    return f.type == "list"


def list_columns(f: Field) -> list[dict]:
    """Return the leaf column dicts of a list-type sub-table.

    Children in the v2 TOML schema are stored as plain dicts, not Field
    objects.  The list field has a single record child dict; the column
    entries are that record's ``children`` mapping.
    """
    if not f.children:
        return []
    record_child = next(iter(f.children.values()))
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
    dim_block = (dfn.blocks or {}).get("dimensions", {})
    if f.shape:
        inner = f.shape.strip().strip("()")
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

    Keywords are safe regardless of tagged — they're self-naming tokens.
    Scalar data fields require tagged=True so they carry their own keyword prefix.
    """
    return child["type"] == "keyword" or (
        child["type"] in _SCALAR_TYPES and child.get("tagged", False)
    )


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
    if is_file_record(f) or not f.children:
        return False
    children = list(f.children.values())
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
    if is_file_record(f) or not f.children:
        return False
    for child in f.children.values():
        if not child.get("optional", False) and not _is_expandable_child(child):
            return False
    return True


def skip_reason(f: Field) -> str | None:
    """Return a human-readable reason why a field is skipped, or None."""
    if is_generatable(f):
        return None
    if is_list_field(f):
        return None  # handled by _expand_list_field in make.py
    if can_expand_record(f):
        return None  # handled by _expand_record_field in make.py
    if _has_complex_shape(f):
        return f"complex shape '{f.shape}' not yet supported"
    if f.type in ("record", "recarray", "keystring"):
        return f"complex type '{f.type}' not yet supported"
    return f"type '{f.type}' not yet supported"


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
    for block in (dfn.blocks or {}).values():
        for f in block.values():
            if is_file_record(f):
                subfield_names.update(_file_record_subfield_names(f))

    result = []
    for block in (dfn.blocks or {}).values():
        for f in block.values():
            f = apply_override(dfn.name, f)
            if f.developmode and not developmode:
                continue
            if f.name in subfield_names:
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
        # boundname uses a fixed-width string dtype, not generic object
        base = "NDArray[np.str_]"
    elif is_keyword_array(f):
        base = "NDArray[np.bool_]"
    elif is_array(f):
        dtype = ARRAY_NUMPY_DTYPES.get(f.type, "np.object_")
        base = f"NDArray[{dtype}]"
    elif is_dimensions_scalar(f):
        # dimensions fields are computed (init=False) and always nullable
        base = _SCALAR_PY_TYPES.get(f.type, "Any")
        return f"Optional[{base}]"
    elif is_scalar(f):
        # Keywords are always bool (not Optional[bool]) regardless of optional flag.
        if f.type == "keyword":
            return "bool"
        base = _SCALAR_PY_TYPES.get(f.type, "Any")
    else:
        base = "Any"

    # Period-block arrays can be absent for a given stress period, so they're
    # implicitly nullable at the Python level even when the DFN marks them required.
    is_nullable = f.optional or is_period_array(f)
    return f"Optional[{base}]" if is_nullable else base


# Python name sanitisation


def safe_name(name: str) -> str:
    """Return a safe Python identifier for a DFN field name."""
    name = name.replace("-", "_")
    if keyword.iskeyword(name) or name in dir(builtins):
        return f"{name}_"
    return name


# spec() call strings


def _dims_tuple(shape: str) -> str:
    """Convert a DFN shape string to a Python dims tuple literal.

    Applies _ALT_DIM_TOKENS, then _DIM_ALIASES to normalise dimension names.

    Examples
    --------
    "(ncol)"                    -> '("ncol",)'
    "(nper, nnodes)"            -> '("nper", "nodes")'
    "(nper, ncol*nrow; ncpl)"   -> '("nper", "ncpl")'
    """
    resolved = _resolve_alt_grid(shape)
    inner = resolved.strip().strip("()")
    raw = [_DIM_ALIASES.get(p.strip(), p.strip()) for p in inner.split(",") if p.strip()]
    parts = [p for p in raw if p not in _DROP_DIMS]
    quoted = ", ".join(f'"{p}"' for p in parts)
    suffix = "," if len(parts) == 1 else ""
    return f"({quoted}{suffix})"


def _longname_repr(longname: str | None) -> str | None:
    if not longname:
        return None
    return repr(longname)


def _default_repr(f: Field) -> str:
    """Return the Python repr of a field's default value."""
    if f.default is None:
        # Scalar keywords default to False (absent == not set).
        # Arrays (including keyword arrays) default to None.
        if f.type == "keyword" and not f.shape:
            return "False"
        return "None"
    if isinstance(f.default, str):
        return repr(f.default)
    return repr(f.default)


def _array_args(f: Field, *, has_maxbound: bool = False) -> list[str]:
    """Build the argument list for an array() spec call.

    Shared by both is_array and is_keyword_array branches. The only
    difference between them is that is_array may prepend a dtype for
    the boundname field; everything else (dims, netcdf, converter,
    on_setattr, longname) is identical.
    """
    dims = _dims_tuple(f.shape) if f.shape else '("nodes",)'
    args = [
        f'block="{f.block}"',
        f"dims={dims}",
        f"default={_default_repr(f)}",
    ]
    if f.netcdf:
        args.append("netcdf=True")
    args.append("converter=Converter(structure_array, takes_self=True, takes_field=True)")
    if is_period_array(f) and has_maxbound:
        args.append("on_setattr=update_maxbound")
    if is_boundname_field(f):
        args.insert(0, 'dtype=f"<U{LENBOUNDNAME}"')
    if ln := _longname_repr(f.longname):
        args.append(f"longname={ln}")
    return args


def spec_call(f: Field, *, has_maxbound: bool = False) -> str:
    """Return the spec function call string for a field.

    Parameters
    ----------
    f :
        The DFN field.
    has_maxbound :
        True when the containing package has a dimensions block with maxbound.
        Enables ``on_setattr=update_maxbound`` on period block arrays.

    The call is intentionally kept as a single line so that ruff
    can reformat it to the project's style.
    """
    if is_aux_list_field(f):
        args = [f'block="{f.block}"', f"default={_default_repr(f)}"]
        if ln := _longname_repr(f.longname):
            args.append(f"longname={ln}")
        return f"array({', '.join(args)})"

    if is_file_record(f):
        inout = "filein" if _has_file_child_of(f, "filein") else "fileout"
        args = [
            f'block="{f.block}"',
            f"default={_default_repr(f)}",
            "converter=to_path",
            f'inout="{inout}"',
        ]
        return f"path({', '.join(args)})"

    if is_keyword_array(f) or is_array(f):
        return f"array({', '.join(_array_args(f, has_maxbound=has_maxbound))})"

    # scalar field
    if is_dimensions_scalar(f):
        if has_maxbound and f.name == "maxbound":
            # Only maxbound itself is auto-computed from data, so init=False.
            # Other dimension scalars in the same block (e.g. nseg in EVT) are
            # user-specified and must remain in __init__.
            args = [f'block="{f.block}"', f"default={_default_repr(f)}", "init=False"]
            if f.longname:
                args.append(f"longname={repr(f.longname)}")
            return f"field({', '.join(args)})"
        else:
            # User-specified dims (nseg, nrhospecies, maxmvr, maxpackages, …):
            # use dim(coord=False) so xattree includes the value in its
            # dimension resolution when expanding array fields.
            args = [f'block="{f.block}"', "coord=False", f"default={_default_repr(f)}"]
            if f.longname:
                args.append(f"longname={repr(f.longname)}")
            return f"dim({', '.join(args)})"
    # Required scalar with no DFN default: omit default= entirely so the field is
    # positional-required at construction.  Matches MF6 semantics (the user MUST
    # supply a value) and avoids the float/int annotation contradicting default=None.
    if is_scalar(f) and not f.optional and f.default is None and f.type != "keyword":
        args = [f'block="{f.block}"']
        if ln := _longname_repr(f.longname):
            args.append(f"longname={ln}")
        return f"field({', '.join(args)})"
    args = [f'block="{f.block}"', f"default={_default_repr(f)}"]
    if ln := _longname_repr(f.longname):
        args.append(f"longname={ln}")
    return f"field({', '.join(args)})"


# Import computation


def needed_imports(
    generatable_fields: list[Field],
    *,
    base_class: str = "Package",
    multi: bool = False,
    slntype: bool = False,
    has_maxbound: bool = False,
    has_list_cols: bool = False,
    has_inner_classes: bool = False,
    has_oc_fields: bool = False,
    has_extra_dims: bool = False,
    has_injected_paths: bool = False,
    has_period_keystring: bool = False,
    has_block_properties: bool = False,
) -> dict[str, list[str]]:
    """Compute the import lines needed for a generated module.

    Returns a dict with keys 'stdlib', 'third_party', 'flopy4'.
    """
    has_array = (
        any(is_array(f) or is_keyword_array(f) for f in generatable_fields)
        or has_list_cols
        or has_oc_fields
    )
    has_aux_list = any(is_aux_list_field(f) for f in generatable_fields)
    has_path = any(is_file_record(f) for f in generatable_fields) or has_injected_paths
    has_optional = any(
        (f.optional or is_period_array(f)) and f.type != "keyword" for f in generatable_fields
    )
    has_dimensions = any(is_dimensions_scalar(f) for f in generatable_fields)
    has_stress_arrays = any(is_period_array(f) for f in generatable_fields)
    has_boundname = any(is_boundname_field(f) for f in generatable_fields)
    has_classvar = multi or slntype or has_inner_classes or has_block_properties

    # dimensions, aux list, list-expansion columns, inner class parents,
    # and injected paths are always Optional
    if has_dimensions or has_aux_list or has_list_cols or has_inner_classes or has_injected_paths:
        has_optional = True

    stdlib: list[str] = []
    if has_path:
        stdlib.append("from pathlib import Path")
    typing_parts: list[str] = []
    if has_classvar:
        typing_parts.append("ClassVar")
    if has_optional:
        typing_parts.append("Optional")
    if typing_parts:
        stdlib.append(f"from typing import {', '.join(sorted(typing_parts))}")

    third_party: list[str] = []
    if has_inner_classes or has_block_properties:
        third_party.append("import attrs")
    if has_array:
        third_party.append("import numpy as np")
        third_party.append("from attrs import Converter")
        third_party.append("from numpy.typing import NDArray")
    third_party.append("from xattree import xattree")

    _base_imports = {
        "Package": "from flopy4.mf6.package import Package",
        "Solution": "from flopy4.mf6.solution import Solution",
        "Context": "from flopy4.mf6.context import Context",
    }

    has_user_dims = (
        any(is_dimensions_scalar(f) and f.name != "maxbound" for f in generatable_fields)
        or has_extra_dims
    )

    spec_funcs: list[str] = ["field"]
    if has_array or has_aux_list:
        spec_funcs.append("array")
    if has_period_keystring:
        spec_funcs.append("embedded_keystring")
    if has_oc_fields:
        spec_funcs.append("keystring")
    if has_path:
        spec_funcs.append("path")
    if has_user_dims:
        spec_funcs.append("dim")
    spec_funcs = sorted(set(spec_funcs))

    flopy4: list[str] = []
    if has_boundname:
        flopy4.append("from flopy4.mf6.constants import LENBOUNDNAME")
    if has_array:
        flopy4.append("from flopy4.mf6.converter import structure_array")
    flopy4.append(_base_imports.get(base_class, _base_imports["Package"]))
    if has_inner_classes:
        flopy4.append("from flopy4.mf6.record import Record")
    flopy4.append(f"from flopy4.mf6.spec import {', '.join(spec_funcs)}")
    if has_path:
        flopy4.append("from flopy4.utils import to_path")
    if has_stress_arrays and has_maxbound:
        flopy4.append("from flopy4.mf6.utils.grid import update_maxbound")

    return {"stdlib": stdlib, "third_party": third_party, "flopy4": flopy4}


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

    Skips the recarray header field (in_record=False). Returns one
    ColumnSpec per in_record=True field in DFN order.
    """
    v1_block = (v1_dfn.blocks or {}).get(block_name) or {}
    result = []
    for name, f in v1_block.items():
        if not getattr(f, "in_record", False):
            continue
        ftype = getattr(f, "type", "") or ""
        optional = _as_bool(getattr(f, "optional", False))
        tagged = _as_bool(getattr(f, "tagged", False))
        shape = str(getattr(f, "shape", "") or "")
        is_keyword = ftype.lower() == "keyword"
        result.append(
            ColumnSpec(
                name=name,
                type=ftype,
                longname=getattr(f, "longname", "") or "",
                is_cellid="(ncelldim)" in shape,
                is_prefix=is_keyword and tagged and not optional,
                is_row_keyword=is_keyword and optional,
                numeric_index=bool(getattr(f, "numeric_index", False)),
            )
        )
    return result


def list_block_names(dfn: Dfn) -> list[str]:
    """Return block names that contain list-type (recarray) fields, in DFN order."""
    seen: set[str] = set()
    result = []
    for f in flat_fields(dfn):
        if is_list_field(f) and f.block not in seen:
            seen.add(f.block)
            result.append(f.block)
    return result


def v1_list_block_names(v1_dfn: Dfn) -> list[str]:
    """Return recarray block names from a v1 DFN, in order.

    A block is a recarray when it contains a header field whose ``type``
    starts with ``"recarray"``.  This is more precise than checking
    ``in_record=True``, which also matches sub-fields of compound records
    (filerecord entries) inside scalar options blocks.
    Used to discover blocks that dfn2toml dropped from the v2 TOML.
    """
    seen: set[str] = set()
    result = []
    for block_name, block in (v1_dfn.blocks or {}).items():
        if block_name in seen:
            continue
        if any(
            str(getattr(f, "type", "") or "").lower().startswith("recarray") for f in block.values()
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
