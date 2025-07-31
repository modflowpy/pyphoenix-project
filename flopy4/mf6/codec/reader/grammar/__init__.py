from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfn import Dfn, get_blocks, get_fields

from flopy4.mf6.codec.reader.grammar.filters import field_type, record_child_type


def _get_template_env():
    loader = jinja2.PackageLoader("flopy4", "mf6/codec/reader/grammar/templates/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["field_type"] = field_type
    env.filters["record_child_type"] = record_child_type
    return env


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn['name']}.lark"
    with open(target_path, "w") as f:
        name = dfn["name"]
        blocks = get_blocks(dfn)
        fields = get_fields(dfn)
        f.write(template.render(name=name, blocks=blocks, fields=fields))


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
