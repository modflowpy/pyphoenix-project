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
    return env


def _compute_block_metadata(blocks):
    """Pre-compute block metadata for template rendering."""
    blocks_list = []
    for block_name, block_fields in blocks.items():
        period_groups = filters.group_period_fields(block_fields)
        has_index = block_name == "period"

        # Build recarrays list
        recarrays = []
        grouped_field_names = set()
        if period_groups:
            for field_names in period_groups.values():
                recarray_name = filters.get_recarray_name(block_name)
                recarrays.append({"name": recarray_name, "fields": field_names})
                grouped_field_names.update(field_names)

        # Get standalone fields (not in any recarray)
        all_field_names = list(block_fields.keys())
        standalone_fields = [f for f in all_field_names if f not in grouped_field_names]

        blocks_list.append(
            {
                "name": block_name,
                "has_index": has_index,
                "standalone_fields": standalone_fields,
                "recarrays": recarrays,
            }
        )

    return blocks_list


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn.name}.lark"

    # Pre-compute block metadata
    blocks_list = _compute_block_metadata(dfn.blocks)

    with open(target_path, "w") as f:
        name = dfn.name
        f.write(template.render(name=name, blocks=blocks_list, fields=dfn.fields))


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
