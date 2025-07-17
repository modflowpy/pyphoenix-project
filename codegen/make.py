import subprocess
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn

from .filters import Filters


def _get_template_env():
    loader = jinja2.PackageLoader("codegen", "templates")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    env.filters["attrs"] = Filters.attrs
    env.filters["safe_name"] = Filters.safe_name
    env.filters["value"] = Filters.value
    env.filters["math"] = Filters.math
    env.filters["clean"] = Filters.clean
    env.filters["type_str"] = Filters.type_str
    env.filters["type_docstr"] = Filters.type_docstr
    env.filters["class_name"] = Filters.class_name
    env.filters["is_dis_or_tdis"] = Filters.is_dis_or_tdis

    return env


def _make_init(dfns: dict, *, outdir: PathLike, verbose: bool = False):
    """Generate a Python __init__.py file for the given input definitions."""
    env = _get_template_env()
    outdir = Path(outdir).expanduser().absolute()

    target_name = "__init__.py"
    target_path = outdir / target_name
    template = env.get_template(f"{target_name}.jinja")
    with open(target_path, "w") as f:
        f.write(template.render(components=dfns.values()))
        if verbose:
            print(f"Wrote {target_path}")


def _format_files(folder: PathLike):
    subprocess.run(["ruff", "format", folder], check=True, text=True)
    subprocess.run(["ruff", "check", "--fix", folder], check=True, text=True)


def _make_targets(dfn, *, outdir: PathLike, verbose: bool = False):
    """Generate Python source file(s) from the given input definition."""
    env = _get_template_env()
    outdir = Path(outdir).expanduser().resolve().absolute()

    def _get_template_name(dfn) -> str:
        parent = dfn.get("parent", None)
        if parent is None:
            return "simulation.py.jinja"
        elif parent == "sim" and "-" not in dfn["name"]:
            return "model.py.jinja"
        else:
            return "package.py.jinja"

    component_name = dfn["name"].replace("-", "")
    target_path = outdir / f"mf{component_name}.py"
    template = env.get_template(_get_template_name(dfn))
    with open(target_path, "w") as f:
        f.write(template.render(dfn=dfn))
        if verbose:
            print(f"Wrote {target_path}")


def make_all(
    *,
    dfndir: PathLike,
    outdir: PathLike,
    verbose: bool = False,
    version: int = 1,
):
    """Generate Python source files from the DFN files in the given location."""
    dfndir = Path(dfndir).expanduser().resolve().absolute()
    dfns = Dfn.load_all(dfndir, version=version)

    _make_init(dfns, outdir=outdir, verbose=verbose)
    for dfn in dfns.values():
        _make_targets(dfn, outdir=outdir, verbose=verbose)
    _format_files(outdir)
