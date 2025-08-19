import inspect
import logging
import subprocess
import sys
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn, infer_tree

from .filters import Filters
from .jinja_tests import Tests

logger = logging.getLogger()


def _get_template_env():
    loader = jinja2.PackageLoader("codegen", "templates")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    env.filters.update(inspect.getmembers(Filters, predicate=inspect.isfunction))
    env.tests.update(inspect.getmembers(Tests, predicate=inspect.isfunction))

    return env


def _make_init(dfns: list[dict], *, env: jinja2.Environment, outdir: PathLike):
    """Generate a Python __init__.py file for the given input definitions.

    Parameters
    ----------
    dfns : list[dict]
        The list of DFN dictionaries to use for rendering the template.
    env : jinja2.Environment
        The Jinja2 environment to use for rendering templates.
    outdir : PathLike
        The output directory where the generated files will be saved.
    """
    outdir = Path(outdir).expanduser().absolute()

    target_name = "__init__.py"
    target_path = outdir / target_name
    template = env.get_template(f"{target_name}.jinja")
    with open(target_path, "w") as f:
        f.write(template.render(components=dfns))
    logger.info(f"Wrote {target_path}")


def _format_files(folder: PathLike):
    subprocess.run([sys.executable, "-m", "ruff", "format", folder], check=True, text=True)
    subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", folder], check=True, text=True)


def _make_targets(dfn, *, outdir: PathLike, env: jinja2.Environment):
    """Generate Python source file(s) from the given input definition."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    assert env.loader is not None
    all_templates = env.loader.list_templates()

    def _get_template_name(dfn) -> str:
        parent = dfn.get("parent", None)
        full_template_name = dfn["name"] + ".py.jinja"
        if full_template_name in all_templates:
            return full_template_name
        if parent == "sim" and "-" not in dfn["name"]:
            return "model.py.jinja"
        if dfn["name"].endswith("-dis"):
            return "dis.py.jinja"
        else:
            return "package.py.jinja"

    component_name = dfn["name"].replace("-", "")
    target_path = outdir / f"{component_name}.py"
    template = env.get_template(_get_template_name(dfn))
    with open(target_path, "w") as f:
        f.write(template.render(dfn=dfn))
    logger.info(f"Wrote {target_path}")


def make_all(
    *,
    dfndir: PathLike,
    outdir: PathLike,
    version: int = 1,
):
    """Generate Python source files from the DFN files in the given location."""
    dfndir = Path(dfndir).expanduser().resolve().absolute()
    loaded_dfns = Dfn.load_all(dfndir, version=version)
    dfns = list(loaded_dfns.values())

    env = _get_template_env()
    env.globals["dfn_tree"] = infer_tree(loaded_dfns)
    env.globals["line_width"] = 100

    _make_init(dfns, outdir=outdir, env=env)
    for dfn in dfns:
        _make_targets(dfn, outdir=outdir, env=env)
    _format_files(outdir)
