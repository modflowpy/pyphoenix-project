from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn

from flopy4.mf6.codec.reader.grammar import filters


def _get_template_env():
    loader = jinja2.PackageLoader("flopy4", "mf6/codec/reader/grammar/templates/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["field_type"] = filters.field_type
    env.filters["record_child_type"] = filters.record_child_type
    env.filters["keystring_children"] = filters.keystring_children
    return env


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn.name}.lark"
    with open(target_path, "w") as f:
        name = dfn.name
        f.write(template.render(name=name, blocks=dfn.blocks, fields=dfn.fields))


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
