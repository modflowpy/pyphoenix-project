"""
Generate Python source files from MODFLOW 6 DFN files.

All template context is pre-computed in Python (see filters.py) so that
Jinja templates stay thin and logic is easy to test and debug.
"""

import logging
import subprocess
import sys
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns import Dfn, load_flat
from modflow_devtools.dfns.schema.field import Field as DfnField

from . import filters
from .overrides import apply_to_child, extra_record_children

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
    template: str = "package.py.jinja"


# Context builders


def _build_field_spec(f: DfnField, *, has_maxbound: bool = False) -> FieldSpec:
    generatable = filters.is_generatable(f)
    # Strip 'record' suffix from file record names for a cleaner API
    # (e.g. head_filerecord → head_file, budget_filerecord → budget_file).
    # Compound records get the same treatment via _strip_record_words in
    # build_component_spec; this keeps the two paths consistent.
    if filters.is_file_record(f):
        py_name = filters.safe_name("_".join(_strip_record_words(f.name)))
    else:
        py_name = filters.safe_name(f.name)
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


def _child_to_field(child_dict: dict) -> DfnField:
    """Convert a record child dict to a Field object."""
    return DfnField(**{k: v for k, v in child_dict.items() if k in _FIELD_KNOWN_KEYS})


def _expand_record_field(
    f: DfnField, *, has_maxbound: bool = False
) -> tuple[list[FieldSpec], list[DfnField]]:
    """Expand a compound record into FieldSpecs for its generatable children.

    Returns (field_specs, generatable_child_fields).  field_specs contains one
    entry per expandable child plus an optional partial-TODO for any optional
    children that can't be generated standalone.  generatable_child_fields is
    the corresponding list of Field objects used for import computation.
    """
    children = f.children or {}
    expandable: list[DfnField] = []
    unexpandable_optional: list[str] = []

    for child_dict in children.values():
        if filters._is_expandable_child(child_dict):
            expandable.append(_child_to_field(child_dict))
        elif child_dict.get("optional", False):
            unexpandable_optional.append(child_dict["name"])
        # required unexpandable children were already blocked by can_expand_record

    specs: list[FieldSpec] = []
    gen_fields: list[DfnField] = []
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
                    f"positional sub-fields not yet supported: "
                    f"{', '.join(unexpandable_optional)}"
                ),
            )
        )

    return specs, gen_fields


def _expand_list_field(f: DfnField, dfn: Dfn) -> list[FieldSpec]:
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


def _expand_oc_record_field(f: DfnField, dfn_name: str) -> list[FieldSpec]:
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
            "array("
            "dtype=np.dtypes.StringDType(), "
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


def _build_inner_class_spec(f: DfnField, dfn_name: str) -> InnerClassSpec:
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
) -> ComponentSpec:
    """Build all template context for a DFN component."""
    all_fields = filters.flat_fields(dfn, developmode=developmode)

    has_maxbound = filters.has_dimensions_block(dfn)

    field_specs: list[FieldSpec] = []
    inner_class_specs: list[InnerClassSpec] = []
    generatable_field_objects: list[DfnField] = []
    has_list_cols = False
    has_oc_fields = False
    for f in all_fields:
        if filters.is_list_field(f):
            expanded = _expand_list_field(f, dfn)
            field_specs.extend(expanded)
            has_list_cols = has_list_cols or any(fs.generatable for fs in expanded)
        elif filters.is_oc_record(f, dfn.name):
            expanded = _expand_oc_record_field(f, dfn.name)
            field_specs.extend(expanded)
            has_oc_fields = has_oc_fields or any(fs.generatable for fs in expanded)
        elif filters.can_generate_record_class(f):
            record_spec = _build_inner_class_spec(f, dfn.name)
            inner_class_specs.append(record_spec)
            clean_name = filters.safe_name("_".join(_strip_record_words(f.name)))
            field_specs.append(
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
            field_specs.extend(specs)
            generatable_field_objects.extend(gen_fields)
        else:
            spec = _build_field_spec(f, has_maxbound=has_maxbound)
            field_specs.append(spec)
            if spec.generatable:
                generatable_field_objects.append(f)

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
        has_list_cols=has_list_cols,
        has_inner_classes=has_inner_classes,
        has_oc_fields=has_oc_fields,
    )

    template = "package.py.jinja"

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
        template=template,
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
    spec.outpath.write_text(rendered)
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

    Returns
    -------
    list[ComponentSpec]
        Specs for all components that were generated.
    """
    dfndir = Path(dfndir)
    outdir = Path(outdir)
    skip = skip or set()
    env = _get_env()
    dfns = load_flat(dfndir)
    specs = []
    for name, dfn in dfns.items():
        if name in skip:
            continue
        spec = build_component_spec(dfn, root=outdir, developmode=developmode)
        if existing_only and not spec.outpath.exists():
            logger.info(f"{spec.outpath} does not exist — skipping {name} (existing_only)")
            continue
        if makedirs:
            spec.outpath.parent.mkdir(parents=True, exist_ok=True)
        make_component(spec, env, fmt=fmt)
        specs.append(spec)
    return specs
