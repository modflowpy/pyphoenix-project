from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns.schema import Array, Component, List, Union

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


def _get_template_data(blocks) -> tuple[list[dict], dict[str, object], dict[str, str]]:
    """Build per-block, per-field jinja context from a Component's blocks.

    A block's ``List`` field (at most one) is the only special case: a
    ``List(item=Record)`` (e.g. WEL's ``stress_period_data``) becomes a
    generic ``record+`` recarray rule; a ``List(item=Union)`` (OC's
    ``output``, PRP's ``perioddata``) has no recarray indirection -- its
    arms are spliced into the block's own field list directly. An Array arm
    there (PRP's ``steps``) needs its type precomputed as ``field_type``
    would otherwise use full griddata-array syntax instead of "N trailing
    values". Every field also passes through ``filters.valid_as_union``.
    """
    all_blocks = []
    all_fields = {}
    field_type_overrides: dict[str, str] = {}

    for block_name, block in blocks.items():
        has_index = block.header is not None
        recarrays = []
        standalone_fields = []

        for field_name, field in block.fields.items():
            field = filters.valid_as_union(field)
            if isinstance(field, List):
                if isinstance(field.item, Union):
                    for arm_name, arm in field.item.arms.items():
                        all_fields[arm_name] = arm
                        standalone_fields.append(arm_name)
                        if isinstance(arm, Array):
                            field_type_overrides[arm_name] = f"{arm.dtype}+"
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

    return all_blocks, all_fields, field_type_overrides


def make_grammar(component: Component, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{component.name}.lark"
    blocks, fields, field_type_overrides = _get_template_data(component.blocks or {})
    with open(target_path, "w") as f:
        f.write(
            template.render(
                name=component.name,
                blocks=blocks,
                fields=fields,
                field_type_overrides=field_type_overrides,
            )
        )


def make_grammars(dfns: dict[str, Component], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for component in dfns.values():
        make_grammar(component, outdir)
