from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns import Dfn

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
    env.filters["to_rule_name"] = filters.to_rule_name
    env.filters["get_list_columns"] = filters.get_list_columns
    env.filters["list_child_type"] = filters.list_child_type
    return env


def _get_template_data(blocks) -> tuple[list[dict], dict[str, object]]:
    all_blocks: list[dict] = []
    all_fields: dict[str, object] = {}

    if blocks is None:
        return all_blocks, all_fields

    for block_name, block_fields in blocks.items():
        period_groups = filters.group_period_fields(block_fields)
        has_index = block_name in ("period", "solutiongroup")

        recarrays = []
        grouped_field_names = set()
        if period_groups:
            for field_names in period_groups.values():
                recarray_name = filters.get_recarray_name(block_name)
                recarrays.append({"name": recarray_name, "fields": field_names})
                grouped_field_names.update(field_names)

        all_field_names = list(block_fields.keys())
        standalone_fields = [f for f in all_field_names if f not in grouped_field_names]

        all_fields.update(block_fields)
        all_blocks.append(
            {
                "name": block_name,
                "has_index": has_index,
                "standalone_fields": standalone_fields,
                "recarrays": recarrays,
            }
        )

    return all_blocks, all_fields


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn.name}.lark"
    blocks, fields = _get_template_data(dfn.blocks)
    with open(target_path, "w") as f:
        name = dfn.name
        f.write(template.render(name=name, blocks=blocks, fields=fields))


def make_all_grammars(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_grammar(dfn, outdir)
