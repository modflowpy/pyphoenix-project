from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns.schema import Block, Component, List, Union

from flopy4.mf6.codec.reader.grammar import filters


def _get_env():
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
    return env


def _to_context(blocks: dict[str, Block]) -> tuple[list[dict], dict[str, object]]:
    """Build block and field context"""
    all_blocks = []
    all_fields = {}

    for block_name, block in blocks.items():
        has_index = block.header is not None
        recarrays = []
        standalone_fields = []

        for field_name, field in block.fields.items():
            if field.removed:
                continue
            field = filters.valid_as_union(field)
            if isinstance(field, List):
                if isinstance(field.item, Union):
                    for arm_name, arm in field.item.arms.items():
                        if arm.removed:
                            continue
                        all_fields[arm_name] = arm
                        standalone_fields.append(arm_name)
                else:
                    recarray_name = filters.get_recarray_name(block_name)
                    recarrays.append({"name": recarray_name})
                    all_fields[field_name] = field
                continue
            all_fields[field_name] = field
            standalone_fields.append(field_name)

        all_blocks.append(
            {
                "name": block_name,
                "has_index": has_index,
                "standalone_fields": standalone_fields,
                "recarrays": recarrays,
            }
        )

    return all_blocks, all_fields


def make_grammar(component: Component, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{component.name}.lark"
    blocks, fields = _to_context(component.blocks or {})
    with open(target_path, "w") as f:
        f.write(
            template.render(
                name=component.name,
                blocks=blocks,
                fields=fields,
            )
        )


def make_grammars(dfns: dict[str, Component], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for component in dfns.values():
        make_grammar(component, outdir)
