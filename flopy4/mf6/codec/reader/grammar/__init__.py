from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn

from .filters import get_block_variables, get_blocks, get_variables, is_recarray_block


def _get_template_env():
    loader = jinja2.FileSystemLoader(Path(__file__).parent / "templates")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["is_recarray_block"] = is_recarray_block
    env.filters["get_block_variables"] = get_block_variables
    return env


_TEMPLATE_ENV = _get_template_env()


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    template = _TEMPLATE_ENV.get_template("component.lark.j2")
    blocks = get_blocks(dfn)
    variables = get_variables(dfn)
    target_path = outdir / f"{dfn['name'].replace('-', '')}.lark"
    with open(target_path, "w") as f:
        f.write(template.render(component=dfn["name"], blocks=blocks, variables=variables))


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
