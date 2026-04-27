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
class ComponentSpec:
    """Pre-computed context for a generated component class."""

    dfn_name: str
    class_name: str
    base_class: str
    multi: bool
    imports: dict[str, list[str]]
    fields: list[FieldSpec]
    outpath: Path
    template: str = "package.py.jinja"


# Context builders


def _build_field_spec(f: DfnField, *, has_maxbound: bool = False) -> FieldSpec:
    generatable = filters.is_generatable(f)
    return FieldSpec(
        dfn_name=f.name,
        py_name=filters.safe_name(f.name),
        type_annotation=filters.py_type(f) if generatable else "Any",
        spec_call=filters.spec_call(f, has_maxbound=has_maxbound) if generatable else "",
        generatable=generatable,
        skip_reason=filters.skip_reason(f),
    )


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
        col_name = col["name"]
        col_type = col.get("type", "string")
        col_longname = col.get("longname", "")[:80]
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


def _base_class(dfn: Dfn) -> str:
    """Determine the Python base class for a component.

    Extended in later tiers to handle models, simulations, solutions.
    """
    return "Package"


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
    has_list_cols = False
    for f in all_fields:
        if filters.is_list_field(f):
            expanded = _expand_list_field(f, dfn)
            field_specs.extend(expanded)
            has_list_cols = has_list_cols or any(fs.generatable for fs in expanded)
        else:
            field_specs.append(_build_field_spec(f, has_maxbound=has_maxbound))

    base = _base_class(dfn)
    multi = bool(dfn.multi)

    generatable_fields = [f for f in all_fields if filters.is_generatable(f)]
    imports = filters.needed_imports(
        generatable_fields,
        base_class=base,
        multi=multi,
        has_maxbound=has_maxbound,
        has_list_cols=has_list_cols,
    )

    template = "package.py.jinja"

    return ComponentSpec(
        dfn_name=dfn.name,
        class_name=filters.class_name(dfn.name),
        base_class=base,
        multi=multi,
        imports=imports,
        fields=field_specs,
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
