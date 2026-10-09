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

import ast
import builtins
import keyword
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from modflow_devtools.dfns.schema import (
    Array,
    Cellid,
    Component,
    Double,
    File,
    Integer,
    Record,
    String,
    split_bound,
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

FieldV3: TypeAlias = (
    KeywordField | Integer | Double | String | Array | Record | UnionField | ListField | File
)

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


# Components not named by their suffix.
_NAMES = {"sim-nam": "simulation"}


def is_model_nam(dfn_name: str) -> bool:
    """Whether a DFN is a model's name file, which becomes the model class
    in its subpackage's ``__init__.py`` (gwf-nam -> flopy4.mf6.gwf.Gwf)."""
    prefix, _, suffix = dfn_name.partition("-")
    return suffix == "nam" and prefix not in _ROOT_PREFIXES


def pkg_abbr(dfn_name: str) -> str:
    """Return the package suffix of a DFN name.

    Examples
    --------
    "gwf-ic"  -> "ic"
    "sln-ims" -> "ims"
    "sim-nam" -> "simulation"
    "gwf-nam" -> "gwf"
    """
    if is_model_nam(dfn_name):
        return dfn_name.split("-")[0]
    return _NAMES.get(dfn_name, dfn_name.split("-")[-1])


def class_name(dfn_name: str) -> str:
    """Return the Python class name for a DFN.

    Examples
    --------
    "gwf-ic"  -> "Ic"
    "sln-ims" -> "Ims"
    "gwf-nam" -> "Gwf"
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
    if is_model_nam(dfn_name):
        return root / mod / "__init__.py"
    if abbr is None:
        return root / f"{mod}.py"
    return root / abbr / f"{mod}.py"


# Component/Block-level helpers


def fill_forward_blocks(component: Component) -> frozenset[str]:
    """Names of the component's repeating blocks whose header fills forward
    (a missing occurrence reuses the prior one's values) -- ``period``, per
    the DFN's own ``BlockHeader.fill_forward``, not assumed by name.
    """
    return frozenset(
        name
        for name, block in (component.blocks or {}).items()
        if block.header is not None and block.header.fill_forward
    )


def has_dimensions_block(component: Component) -> bool:
    """True if the component has a dimensions block with a 'maxbound' field.

    Combined with a real Item-list period field (see
    `build_component_spec`'s `_maxbound_is_computed`), drives emitting
    `maxbound` as a computed read-only property instead of a stored field.
    A G-variant package (CHDG, DRNG, …) also has 'maxbound', but its period
    data is a READARRAY grid, not a row list to count -- stays a plain field.
    """
    block = (component.blocks or {}).get("dimensions")
    return block is not None and "maxbound" in block.fields


# Field classification
#
# dev3's Field union is a real discriminated union -- isinstance dispatch
# replaces the legacy schema's string-set membership checks directly. No
# equivalent of the legacy _has_complex_shape/_ALT_DIM_TOKENS/_DIM_ALIASES is
# needed: dev3 shapes are lists of dimension names, never 'ncol*nrow' or a
# ';'-joined alternative-grid expression. The grid packages' structured
# griddata shapes (e.g. dis botm's ['ncol', 'nrow', 'nlay']) are flattened
# by canonical_shape.


def is_scalar(f: FieldV3) -> bool:
    return isinstance(f, (KeywordField, Integer, Double, String))


def is_readarray(f: FieldV3) -> bool:
    return isinstance(f, Array) and f.dtype not in ("keyword", "string")


def is_fixed_length_array(f: FieldV3) -> bool:
    return isinstance(f, Array) and bool(f.shape) and not any(split_bound(s)[0] for s in f.shape)


def is_keyword_array(f: FieldV3) -> bool:
    return isinstance(f, Array) and f.dtype == "keyword" and bool(f.shape)


def is_file_record(f: FieldV3) -> bool:
    """True for record fields whose children include a File field."""
    return isinstance(f, Record) and any(isinstance(c, File) for c in f.fields.values())


def file_child(f: Record) -> File | None:
    """Return the File child of a file record, or None."""
    return next((c for c in f.fields.values() if isinstance(c, File)), None)


def is_aux_list_field(f: FieldV3) -> bool:
    """True for auxiliary variable name arrays (options block).

    A standalone string array -- inline per the DFN spec, never the
    multi-line readarray form (see is_readarray). (Legacy encoded this as a
    shaped field with a self-referential dim "naux"; dev3 drops the fake
    dimension entirely since the count *is* len() of the list itself,
    nothing to declare.)
    """
    return isinstance(f, Array) and f.dtype == "string"


def is_any_array(f: FieldV3) -> bool:
    """True for numeric or keyword array fields."""
    return is_readarray(f) or is_keyword_array(f)


def is_dimensions_scalar(f: FieldV3, block_name: str) -> bool:
    return block_name == "dimensions" and is_scalar(f)


def is_list_field(f: FieldV3) -> bool:
    return isinstance(f, ListField)


def is_tagged_list(f: FieldV3) -> bool:
    return isinstance(f, ListField) and f.tagged


def is_file_list(f: FieldV3) -> bool:
    return is_tagged_list(f) and is_file_record(f.item)


def is_generatable(f: FieldV3) -> bool:
    """True if this field can be handled in the current generation pass."""
    return (
        is_scalar(f)
        or is_readarray(f)
        or is_keyword_array(f)
        or is_file_record(f)
        or is_aux_list_field(f)
        or is_file_list(f)
    )


_RECORD_CLASS_SCALAR_TYPES = (Integer, Double, String)


def _is_expandable_child(child: FieldV3) -> bool:
    """True if a record child can be generated as a standalone field.

    Only keyword-type children are expandable: they're self-naming tokens that
    map cleanly to individual bool fields. Scalar data fields (even tagged ones)
    are positional components of a compound construct and must stay grouped.
    """
    return isinstance(child, KeywordField)


def is_record_list_field(c: FieldV3) -> bool:
    """True for a non-keyword array nested in a record.

    Per the DFN spec, an array nested in a record is always inline: it
    consumes whatever tokens remain on the line, regardless of any declared
    shape (e.g. sfacval's shape == ["time_series_name"], a sibling-field
    reference rather than a resolvable extent). See record.py's
    from_tokens/to_tokens.
    """
    return isinstance(c, Array) and c.dtype != "keyword"


def _record_child_supported(c: FieldV3) -> bool:
    """True if a record child is a scalar/keyword, a nested inline array
    (is_record_list_field), or a Record of supported children (recursive).
    Recarray-typed Lists and unions still fall back to TODO."""
    if isinstance(c, _RECORD_CLASS_SCALAR_TYPES + (KeywordField,)):
        return True
    if is_record_list_field(c):
        return True
    if isinstance(c, Record) and c.fields:
        return all(_record_child_supported(gc) for gc in c.fields.values())
    return False


def can_generate_record_class(f: FieldV3) -> bool:
    """True when a compound record should be rendered as an inner attrs class.

    All non-file records whose children are entirely scalars, keywords,
    nested inline arrays, and/or nested records (see
    _record_child_supported) become inner attrs classes. The first keyword
    child (if any) is the trigger token (``_keyword``); remaining keyword
    children become ``Optional[bool]`` fields. A child that is itself a
    Record becomes its own composed class rather than being flattened in.

    All-keyword records with only one child are left to
    :func:`can_expand_record` instead. Records with unsupported child types
    (recarray list, union) fall back to TODO comments.
    """
    if not isinstance(f, Record) or is_file_record(f) or not f.fields:
        return False
    children = list(f.fields.values())
    if not all(_record_child_supported(c) for c in children):
        return False
    has_data = any(
        isinstance(c, _RECORD_CLASS_SCALAR_TYPES) or is_record_list_field(c) for c in children
    )
    # All-keyword records need at least 2 children (trigger + modifier) to
    # justify a class; a single lone keyword expands more cleanly to a bool.
    if not has_data:
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


def flat_fields(component: Component, *, developmode: bool = False) -> list[tuple[str, FieldV3]]:
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

    Fields marked `removed` are always excluded -- MF6 no longer parses
    that syntax at all (unlike `deprecated`, which still parses and stays
    generated). See InputFieldBase.removed's docstring.
    """
    result: list[tuple[str, FieldV3]] = []
    for block_name, block in (component.blocks or {}).items():
        for f in block.fields.values():
            if f.developmode and not developmode:
                continue
            if getattr(f, "removed", None):
                continue
            result.append((block_name, f))
    return result


def dynamically_named_array(f) -> tuple[Array, str] | None:
    """For a list of dynamically named arrays (RCHA's period aux: an auxiliary name, then
    its array), the array and the name's fk ("options.auxiliary"); None for
    any other field."""
    if not isinstance(f, ListField) or not isinstance(f.item, Record):
        return None
    match list(f.item.fields.values()):
        case [String(fk=str(fk)), Array(shape=[_, *_]) as arr]:
            return arr, fk
    return None


# A function call in a dimension expression, as in LAK's sum(...)
_DIM_CALL = re.compile(r"\w\s*\(")


def derived_dims(component: Component) -> dict[str, str]:
    """A component's arithmetic derived dimensions, name -> expression, e.g.
    gwf-dis's ``{"ncpl": "nrow * ncol", "nodes": "nlay * nrow * ncol",
    "ncelldim": "3"}``. Other expressions (LAK's ``sum(...)``, ``len(...)``)
    are left out."""
    dims = {}
    for name, dim in (component.dims or {}).items():
        if dim.value == name or _DIM_CALL.search(dim.value):
            continue
        dims[name] = dim.value
    return dims


def shared_dims(component: Component) -> tuple[str, ...]:
    """The dimensions a component shares beyond itself, by the DFN's dim
    scopes: gwf-dis's model dimensions, sim-tdis's ``nper``. A component
    with any is a dimension provider."""
    return tuple(name for name, dim in (component.dims or {}).items() if dim.scope != "component")


def _product_names(expr: str) -> list[str] | None:
    """The names multiplied in a pure product expression ("nlay * ncpl"),
    else None."""

    def _names(node: ast.expr) -> list[str] | None:
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            left, right = _names(node.left), _names(node.right)
            return None if left is None or right is None else left + right
        return None

    return _names(ast.parse(expr, mode="eval").body)


def canonical_shape(f: FieldV3, derived: dict[str, str]) -> FieldV3:
    """Replace an array's structured shape with the derived dimension it
    spans: ``(ncol, nrow)`` -> ``(ncpl,)``, ``(ncol, nrow, nlay)`` or
    ``(ncpl, nlay)`` -> ``(nodes,)``.

    flopy4 stores griddata flat, as MF6 does and as every other package's
    DFN shapes it (NPF ``k`` is ``(nodes,)``); only the grid packages' DFNs
    give the structured shape (in Fortran order). The match is on the
    multiset of names, so order doesn't matter. Where several dimensions
    match (olf-dis2d's ``ncpl`` and ``nodes`` are both ``nrow * ncol``),
    the first declared wins.
    """
    shape = getattr(f, "shape", None)
    if not isinstance(f, Array) or not shape or len(shape) < 2:
        return f
    names = Counter(shape)
    for name, expr in derived.items():
        if (factors := _product_names(expr)) and Counter(factors) == names:
            return f.model_copy(update={"shape": [name]})
    raise ValueError(f"{f.name}: shape {shape} matches no derived dimension in {derived}")


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
        return "Optional[NDArray[np.str_]]"
    if is_file_list(f):
        return "Optional[list[Path]]"
    if is_file_record(f):
        base = "Path"
    elif is_keyword_array(f):
        base = "NDArray[np.bool_]"
    elif is_readarray(f):
        assert isinstance(f, Array)
        base = "IntArrayLike" if f.dtype == "integer" else "FloatArrayLike"
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

    return f"Optional[{base}]" if f.optional else base


def converter(type_str: str) -> str | None:
    """The attrs converter for a generated type annotation, built from the
    type: ``Optional[X]`` -> ``attrs.converters.optional(<X>)``, ``list[X]``
    -> ``to_list(<X>)``, ``Path`` -> ``Path``, and an inline (string) array
    ``NDArray[np.str_]`` -> ``to_array(np.str_)``. Other types need none
    (numeric arrays take constants, layers or xarray; see is_readarray).
    """
    if m := re.fullmatch(r"Optional\[(.+)\]", type_str):
        inner = converter(m[1])
        return f"attrs.converters.optional({inner})" if inner else None
    if m := re.fullmatch(r"list\[(.+)\]", type_str):
        inner = converter(m[1])
        return f"to_list({inner})" if inner else None
    if type_str == "NDArray[np.str_]":
        return "to_array(np.str_)"
    if type_str == "Path":
        return "Path"
    return None


def field_converter(f: FieldV3, block_name: str) -> str | None:
    """A generated field's converter (see converter). A field defaulting to
    None accepts None whatever its annotation says."""
    type_str = py_type(f, block_name)
    if _default_repr(f) == "None" and not type_str.startswith("Optional["):
        type_str = f"Optional[{type_str}]"
    return converter(type_str)


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


# Field call strings


def field_metadata(f: FieldV3, block_name: str) -> dict:
    """Build the ``field()``/``path()`` spec-call kwargs for a field.

    These calls carry passive metadata (shape, block, etc.) read by the
    codec and conversion methods at call time, rather than any structure
    resolved up front at class-definition time.
    """
    kw: dict = {"block": block_name}
    if shape := getattr(f, "shape", None):
        kw["shape"] = tuple(shape)
    if getattr(f, "layered", False):
        kw["layered"] = True
    if getattr(f, "netcdf", False):
        kw["netcdf"] = True
    if getattr(f, "time_series", False):
        kw["time_series"] = True
    if isinstance(f, Array) and f.index:
        # 0-based, written as 1-based, as for item columns
        kw["index"] = True
    if f.optional:
        kw["optional"] = True
    if is_file_record(f):
        child = file_child(f)
        assert child is not None  # is_file_record() already confirmed a File child exists
        kw["direction"] = child.direction
        # The record's trigger keyword (e.g. "ts6" in "TS6 FILEIN <file>")
        # isn't recoverable from the py name (ts_filerecord → ts_file), so
        # carry it explicitly -- stored as _keyword metadata, the same
        # convention as a Record class's own _keyword (see spec.path).
        keywords = [c.name for c in f.fields.values() if isinstance(c, KeywordField)]
        if len(keywords) != 1:
            raise ValueError(f"file record {f.name!r}: expected one keyword, got {keywords}")
        kw["keyword"] = keywords[0].lower()
    if longname := getattr(f, "longname", None):
        # DFN longname text escapes underscores for LaTeX rendering (e.g.
        # AUTO\_FLOW\_REDUCE); harmless in the .dfn but `\_` isn't a valid
        # Python string escape, so strip it before embedding as a literal.
        kw["longname"] = longname.replace("\\_", "_")
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


def _wrap_kwarg_line(k: str, v, indent: int = 8) -> str:
    """Render one field()/path() kwarg line, wrapping long string values across
    adjacent literals (standard Python string concatenation) so the line
    respects the 100-char limit -- ruff/black can't split a string literal
    on their own, so long DFN longname text needs this done explicitly.
    """
    pad = " " * indent
    line = f"{pad}{k}={_dq(v)},"
    if len(line) <= 100 or not isinstance(v, str):
        return line
    inner_pad = " " * (indent + 4)
    max_width = 96 - len(inner_pad)
    words = v.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_width:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    body = "\n".join(
        f'{inner_pad}"{c} "' if i < len(chunks) - 1 else f'{inner_pad}"{c}"'
        for i, c in enumerate(chunks)
    )
    return f"{pad}{k}=(\n{body}\n{pad}),"


def field_call(f: FieldV3, block_name: str, linked_dim: bool = False) -> str:
    """Return the field()/path() spec call string for a field.

    Emits a multi-line call to comply with the 100-char line-length limit.
    Continuation lines are pre-indented for class body (8-space args,
    4-space closing paren).

    A `linked_dim` (a dimension counting a list's rows, e.g. TDIS's nper)
    defaults to None, so an explicit value equal to the DFN default still
    counts as given. With no explicit value it's set from the row count.
    """
    if is_file_list(f):
        # Same metadata as a single file record (keyword, direction).
        item_kw = field_metadata(f.item, block_name)
        kw = {"block": item_kw.pop("block")}
        if f.optional:
            kw["optional"] = True
        kw |= item_kw
        conv = field_converter(f, block_name)
        lines = ["path(", "        default=None,", f"        converter={conv},"]
        lines += [_wrap_kwarg_line(k, v) for k, v in kw.items()]
        lines.append("    )")
        return "\n".join(lines)
    kw = field_metadata(f, block_name)
    # A plain (non-computed) required maxbound defaults to 0, like the
    # computed one. An optional one (READARRAYGRID packages: CHDG, WELG, ...)
    # keeps the DFN default (None) so it's omitted unless set -- MF6 then
    # sizes it to the grid, and rejects an explicit MAXBOUND <= 0.
    if block_name == "dimensions" and f.name == "maxbound" and not f.optional:
        default = "0"
    else:
        default = _default_repr(f)
    if linked_dim:
        default = "None"
    # String-encoded numeric defaults (e.g. '1.e-5', '1000.') are valid at
    # runtime but mypy can't verify they satisfy Optional[float/int].
    # Scalar defaults (int, float, str) on Int/FloatArrayLike fields have the same issue.
    _str_default = default.startswith("'")
    _numeric_field = isinstance(f, (Double, Integer))
    type_ignore = ""
    if (is_readarray(f) and default != "None") or (_str_default and _numeric_field):
        type_ignore = "  # type: ignore[assignment]"
    fn = "path" if is_file_record(f) else "field"
    lines = [f"{fn}(", f"        default={default},"]
    if conv := field_converter(f, block_name):
        lines.append(f"        converter={conv},")
        if "to_array(" in conv:
            # inline arrays have no shape for field() to key on
            lines.append("        eq=ARRAY_EQ,")
    for k, v in kw.items():
        lines.append(_wrap_kwarg_line(k, v))
    lines.append(f"    ){type_ignore}")
    return "\n".join(lines)


def tuple_repr(v: tuple) -> str:
    """A tuple of strings (or of such tuples) as Python, double-quoted like
    ruff would, so the output doesn't depend on running it."""
    return repr(v).replace("'", '"')


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


def pascal_name(name: str) -> str:
    """snake_case, hyphenated, or a plain lowercase word -> PascalCase, e.g.
    ``stress_period_data`` -> ``StressPeriodData``, ``packagedata`` ->
    ``Packagedata``, ``ext-inflow`` (a real MF6 keystring keyword, LKT/LKE)
    -> ``ExtInflow``. Only "_"/"-" split words -- the wire keyword itself
    (unlike the class name) keeps its original separator, since a hyphen is
    fine inside a Python string but not an identifier."""
    return "".join(part.capitalize() for part in re.split(r"[_-]", name))


# An untagged union column's Python type, by arm kind (see make._arm_kind).
_UNION_ARM_PY = {
    "cellid": "tuple[int, ...]",
    "index": "int",
    "integer": "int",
    "double": "float",
    "string": "str",
}


_DFN_PY: dict[str, str] = {
    "double": "float",
    "double precision": "float",
    "integer": "int",
    "string": "str",
    "keyword": "str",
    "object": "object",
}


@dataclass
class ItemColumn:
    """One rendered column of a generated Item class.

    Built by the per-kind functions below (``value_column``, ``feature_id_column``,
    ...), each of which decides a column's whole rendering -- annotation,
    right-hand side, optionality -- in one place. ``item_class`` only orders
    and emits them.

    ``annotation`` and ``rhs`` render as ``name: annotation = rhs``. A
    nested-union column sets ``arm_classes`` instead of ``annotation``, as
    its forward-reference union needs the package class name.
    """

    name: str
    annotation: str
    rhs: str
    optional: bool = False  # declared after the required columns
    arm_classes: tuple[str, ...] = ()

    @property
    def uses_path(self) -> bool:
        """Whether the module needs ``Path`` and ``path`` imported."""
        return "path(" in self.rhs

    @property
    def uses_union(self) -> bool:
        """Whether the module needs ``Union`` imported."""
        return "Union[" in self.annotation

    @property
    def uses_child(self) -> bool:
        return "child(" in self.rhs

    @property
    def uses_field(self) -> bool:
        """Whether the module needs ``field`` imported."""
        return "field(" in self.rhs

    def line(self, package_class_name: str = "") -> str:
        annotation = self.annotation
        if self.arm_classes:
            arms = " | ".join(f"{package_class_name}.{c}" for c in self.arm_classes)
            annotation = f'"{arms}"'
        return f"        {self.name}: {annotation} = {self.rhs}"


def _margs(meta: dict) -> str:
    return ", ".join(f"{k}={_dq(v)}" for k, v in meta.items())


def attr_column(
    name: str,
    py_type: str,
    meta: dict,
    *,
    optional: bool,
    time_series: bool = False,
    default: str = "None",
    **kwargs,
) -> ItemColumn:
    """The generic rendering: ``name: T = field(meta)``, or, when optional,
    ``Optional[T]`` with a ``None`` default (or ``T`` with ``default``)."""
    meta = dict(meta)
    if time_series:
        meta["time_series"] = True
    if optional:
        # Needed even for time_series fields: _n_fixed_tokens() (item.py)
        # uses this to tell "always present" fixed columns apart from
        # trailing columns that may be entirely absent from a given row
        # (e.g. EVT's pxdp/petm/petm0, only written when
        # surf_rate_specified) when inferring a variable-width cellid's
        # element count from raw token counts.
        meta["optional"] = True
    margs = _margs(meta)
    if optional:
        annotation = py_type if default != "None" else f"Optional[{py_type}]"
        rhs = f"field(default={default}, {margs})" if meta else default
    else:
        annotation = py_type
        # A bare annotation here is equivalent to field() at runtime (both
        # mean "no default") -- but mypy's attrs plugin doesn't recognize
        # field() (a flopy4.mf6.spec wrapper, not attrs.field itself) as a
        # field specifier, so it can't tell field()-declared columns above
        # (e.g. pk=/cellid=) don't actually have a default either. Left
        # bare, that misreading makes mypy treat *this* column as a
        # "non-default attribute after a default attribute". Always going
        # through field() keeps every column's mypy-visible shape
        # consistent and side-steps the false positive.
        rhs = f"field({margs})"
    return ItemColumn(
        name=name,
        annotation=annotation,
        rhs=rhs,
        optional=optional,
        **kwargs,
    )


def value_column(
    name: str,
    dfn_type: str = "double",
    *,
    optional: bool = False,
    time_series: bool = False,
    object_dtype: bool = False,
) -> ItemColumn:
    """A plain scalar. A time series or object-dtype value may be a string."""
    object_dtype = object_dtype or time_series
    py_type = "Union[float, str]" if object_dtype else _DFN_PY.get(dfn_type, "float")
    return attr_column(
        name,
        py_type,
        {},
        optional=optional,
        time_series=time_series,
    )


def feature_id_column(
    name: str,
    *,
    fk: str | None = None,
    pk: bool = False,
    optional: bool = False,
    time_series: bool = False,
) -> ItemColumn:
    meta: dict = {"index": True}
    if fk:
        meta["fk"] = fk
    elif pk:
        meta["pk"] = True
    return attr_column(
        name,
        "int",
        meta,
        optional=optional,
        time_series=time_series,
    )


def union_column(
    name: str, arms: tuple[str, ...], *, optional: bool = False, time_series: bool = False
) -> ItemColumn:
    """One column that is any of several arm kinds (OBS's id: a cellid, an
    index or a boundname), told apart when read."""
    types = dict.fromkeys(_UNION_ARM_PY[arm] for arm in arms)
    return attr_column(
        name,
        f"Union[{', '.join(types)}]",
        {"union": arms},
        optional=optional,
        time_series=time_series,
    )


def array_column(
    name: str,
    shape: str | None,
    dfn_type: str = "double",
    *,
    cellid: Cellid = False,
    index: bool = False,
    signed: bool = False,
    optional: bool = False,
    time_series: bool = False,
) -> ItemColumn:
    """An inline array with as many values as the shape expression ``shape``
    gives (``nseg-1``, ``auxiliary``, ``packagedata.ncon(ifno)``), emitted
    as-is for the runtime to evaluate. Empty when omitted.

    Without a ``shape`` it consumes all remaining tokens -- a keyword-plus-
    trailing-values setting whose arity isn't fixed (PRP's Steps.steps/
    Fraction's leaf field), typed when the DFN says (STEPS are integers).
    """
    if shape is None:
        elem = _DFN_PY[dfn_type] if dfn_type in ("integer", "double") else None
        return ItemColumn(
            name=name,
            annotation=f"tuple[{elem}, ...]" if elem else "tuple",
            rhs="field(default=(), array=True)",
            optional=True,
        )
    if cellid:
        py_type = "tuple[tuple[int, ...], ...]"
    elif signed:
        py_type = "tuple[tuple[int, int], ...]"
    elif time_series:
        py_type = "tuple[Union[float, str], ...]"
    else:
        py_type = f"tuple[{_DFN_PY.get(dfn_type, 'float')}, ...]"
    meta: dict = {"array": True}
    if cellid:
        meta["cellid"] = cellid
    if index:
        meta["index"] = True
    meta["shape"] = (shape,)
    if signed:
        meta["signed"] = True
    return attr_column(
        name, py_type, meta, optional=optional, time_series=time_series, default="()"
    )


def file_column(
    name: str, direction: str, keyword: str | None = None, *, optional: bool = False
) -> ItemColumn:
    """A path() field (e.g. LAK tables' "TAB6 FILEIN <file>")."""
    keyword_kw = f", keyword={_dq(keyword)}" if keyword else ""
    if optional:
        return ItemColumn(
            name=name,
            annotation="Optional[Path]",
            rhs=(
                "path(\n"
                f"            default=None, converter={converter('Optional[Path]')}, "
                f'direction="{direction}"{keyword_kw}\n'
                "        )"
            ),
            optional=True,
        )
    return ItemColumn(
        name=name,
        annotation="Path",
        rhs=f'path(converter=Path, direction="{direction}"{keyword_kw})',
    )


def child_column(
    name: str,
    classes: list[str],
    direction: str,
    keyword: str | None = None,
    *,
    optional: bool = False,
) -> ItemColumn:
    """A file column naming components holds the component itself (LAK's
    "TAB6 FILEIN <file>" holds a utl-laktab)."""
    cls = classes[0] if len(classes) == 1 else f"Union[{', '.join(classes)}]"
    args = f'direction="{direction}"'
    if keyword:
        args = f"keyword={_dq(keyword)}, {args}"
    if optional:
        return ItemColumn(
            name=name,
            annotation=f"Optional[{cls}]",
            rhs=f"child({args})",
            optional=True,
        )
    return ItemColumn(
        name=name,
        annotation=cls,
        rhs=f"child({args}, default=attrs.NOTHING)",
    )


def nested_union_column(
    name: str, arm_classes: list[str], *, optional: bool = False, time_series: bool = False
) -> ItemColumn:
    """A union nested inside this arm (OC's ocsetting), arms already built as
    sibling classes (see make.py's _build_arm_specs_from_union)."""
    return ItemColumn(
        name=name,
        annotation="",
        rhs="field()",
        optional=optional,
        arm_classes=tuple(arm_classes),
    )


def item_class(
    schema_list: list[ItemColumn],
    class_name: str,
    keyword: str = "",
    package_class_name: str = "",
) -> str:
    """Render an Item subclass (flopy4.mf6.item.Item) for list block construction.

    Called as::

        {{ spec.period_schema | item_class("StressPeriodData", True) }}
        {{ block_schema | item_class("Packagedata") }}
        {{ arm_schema | item_class("Status", keyword="STATUS") }}

    ``package_class_name`` (e.g. ``"Oc"``) is only needed for a nested-union
    column -- it qualifies that field's forward-reference union annotation
    (``"Oc.All | Oc.First | ..."``).

    Produces a 4-space-indented ``@attrs.define`` class whose fields carry
    real metadata (``index=``/``pk=``/``fk=``/``cellid=``/``time_series=``/
    ``tagged=``, via ``field()``; ``direction=``/``keyword=`` for a file
    column, via ``path()``) -- the class itself is the schema.

    Required fields (no default) are declared before optional fields to
    satisfy attrs ordering constraints.

    ``keyword``, when given, is one arm of a keystring-union period field
    (e.g. LAK's STAGE/RATE/STATUS settings, OC's SAVE/PRINT records) --
    emitted as ``_keyword`` so flopy4.mf6.item.dispatch_union_item can pick
    the right arm class for a raw row by its leading token. An arm can be a
    bare keyword with no data of its own (e.g. PRP's releasesetting ALL/
    FIRST/LAST) -- schema_list is then empty, but the class itself (just
    _keyword) is still real and must still be emitted.
    """
    if not schema_list and not keyword:
        return ""

    required = [col for col in schema_list if not col.optional]
    optional = [col for col in schema_list if col.optional]
    # Optional columns keep DFN order (e.g. EVT: ..., pxdp, petm, petm0, aux,
    # boundname).

    lines = ["    @attrs.define"]
    lines.append(f"    class {class_name}(Item):")
    if keyword:
        lines.append(f'        _keyword: ClassVar[str] = "{keyword}"')
    # Declaring required columns first reorders a row whose optional
    # columns come before required ones (MVR's mname1 pname1 ...).
    columns = [col.name for col in schema_list]
    if columns != [col.name for col in required + optional]:
        names = ", ".join(f'"{c}"' for c in columns)
        lines.append(f"        _columns: ClassVar[tuple[str, ...]] = ({names},)")
    for col in required + optional:
        lines.append(col.line(package_class_name))
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
    is_cellid: bool  # dev3 Array.cellid -- stored as object-dtype tuple attr
    cellid: Cellid  # its value: True, or "1"/"2" for an exchange's models
    is_prefix: bool  # tagged non-optional keyword -- write-side token only, no attr
    is_row_keyword: bool  # optional keyword -- stored as bool attr
    is_index: bool  # dev3 Integer.index -- 0-based, written as 1-based (+1 at write time)


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
            # An untagged union (OBS's id) is one column, not a keystring.
            if isinstance(f, UnionField) and f.tagged:
                return f
    return None


def _fields_to_columns(fields: "list[tuple[str, FieldV3]]") -> list[ColumnSpec]:
    """Build ColumnSpecs from an ordered (name, field) sequence -- the shared
    core of list_columns (a List[Record]'s own item fields) and
    make.py's keystring-union arm processing (a Union arm's fields, once its
    own leading keyword, if any, is split off as the arm's _keyword).

    ``safe_name`` sanitizes the column name (e.g. LKT/LKE's hyphenated
    "ext-inflow" arm -> "ext_inflow") since it becomes a Python attribute
    name here -- unlike a class's own _keyword string, which keeps its
    original spelling (it's compared against a raw wire token, not used as
    an identifier).
    """
    result = []
    for col_name, col in fields:
        is_keyword = isinstance(col, KeywordField)
        is_optional = col.optional
        result.append(
            ColumnSpec(
                name=safe_name(col_name),
                field=col,
                is_cellid=isinstance(col, Array) and bool(col.cellid),
                cellid=col.cellid if isinstance(col, Array) else False,
                is_prefix=is_keyword and not is_optional,
                is_row_keyword=is_keyword and is_optional,
                # a feature id implies MF6's numeric 0-based-Python/1-based-
                # file conversion (structure.py: int(...) - 1). dev3's `index`
                # attribute (split out of the old overloaded pk/fk semantics,
                # modflow-devtools 41dca93) is now the direct, authoritative
                # signal for this -- no longer inferred from pk/fk-ness (a
                # string pk/fk, e.g. MVR's `pname`, a package *name* reference
                # not a numeric one, is never `index`, so the old
                # isinstance(col, Integer)-guarded pk-or-fk heuristic this
                # replaced is no longer needed either).
                is_index=bool(getattr(col, "index", False)),
            )
        )
    return result


def list_columns(f: ListField) -> list[ColumnSpec]:
    """Return the leaf column specs of a dev3 List[Record] field, in order.

    Returns [] for keystring-shaped lists (see find_keystring_union) -- those
    are handled separately (see make.py's keystring period handling).
    """
    if find_keystring_union(f) is not None:
        return []
    item = f.item
    if not isinstance(item, Record):
        return []
    return _fields_to_columns(list(item.fields.items()))


def list_col_dim(f: ListField, component: Component) -> str | None:
    """Return the DIMENSIONS field that counts a list's rows, or None.

    Only an explicit shape links a list to a dimension: its single entry,
    minus any bound operator (``"<=maxbound"`` -> ``maxbound``), when that
    names a field in the component's dimensions block.
    """
    dim_block = (component.blocks or {}).get("dimensions")
    dim_names = list(dim_block.fields.keys()) if dim_block is not None else []
    shape = f.shape or []
    if len(shape) != 1:
        return None
    _, shape_dim = split_bound(shape[0])
    return shape_dim if shape_dim in dim_names else None


def list_dim_bound(f: ListField) -> str | None:
    """Return a list shape's bound operator (``"<="`` for ``"<=maxbound"``),
    or None when the shape is exact (or absent)."""
    shape = f.shape or []
    return split_bound(shape[0])[0] if len(shape) == 1 else None


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
