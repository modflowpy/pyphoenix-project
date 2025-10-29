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
    env.filters["group_period_fields"] = filters.group_period_fields
    env.filters["get_recarray_name"] = filters.get_recarray_name
    env.filters["get_all_grouped_field_names"] = filters.get_all_grouped_field_names
    return env


def _compute_block_metadata(blocks):
    """Pre-compute block metadata for template rendering."""
    block_metadata = {}
    for block_name, block_fields in blocks.items():
        period_groups = filters.group_period_fields(block_fields)
        recarray_name = filters.get_recarray_name(block_name) if period_groups else None
        has_index = block_name == "period"

        block_metadata[block_name] = {
            "fields": block_fields,
            "period_groups": period_groups,
            "recarray_name": recarray_name,
            "has_index": has_index,
        }
    return block_metadata


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn.name}.lark"

    # Pre-compute block metadata
    block_metadata = _compute_block_metadata(dfn.blocks)

    with open(target_path, "w") as f:
        name = dfn.name
        f.write(
            template.render(
                name=name, blocks=dfn.blocks, fields=dfn.fields, block_metadata=block_metadata
            )
        )


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
