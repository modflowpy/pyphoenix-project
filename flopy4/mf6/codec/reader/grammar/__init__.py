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

    A block's ``List`` field (at most one, enforced by the schema's own
    validator) is the only case needing special handling:

    - ``List(item=Record)`` (e.g. WEL/CHD's ``stress_period_data``) becomes a
      generic ``<recarray_name>: record+`` rule -- the untyped ``record``
      terminal from ``typed.lark`` already accepts any token-per-line row, so
      the item's own columns don't need individual grammar rules.
    - ``List(item=Union)`` (e.g. OC's ``output``, PRP's ``perioddata``) has no
      recarray indirection at all: each arm is spliced into the block's own
      field list and rendered exactly like any other top-level record/union
      field, matching the existing dispatch-by-leading-keyword grammar. A
      scalar/array arm (PRP's ``all``/``frequency``/``steps``, as opposed to
      OC's record-typed ``saverecord``/``printrecord``) needs its rendered
      type precomputed here rather than left to the generic ``field_type``
      filter: an ``Array`` arm here means "one or more trailing values on
      this line" (e.g. ``STEPS 1 3 5``), not a full griddata-style control
      block, which is what the generic filter would otherwise produce for
      any other ``Array`` field.

    Every field also passes through ``filters.valid_as_union`` first: a
    ``valid=``-restricted scalar (e.g. STO's ``storage``, one of
    ``STEADY-STATE``/``TRANSIENT``) is normalized into a synthetic keyword
    union so it renders (and, in ``TypedTransformer``, dispatches) exactly
    like any other keystring union.
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
