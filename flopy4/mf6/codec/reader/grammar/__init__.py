from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns.schema import (
    Array,
    Block,
    Component,
    Double,
    InputField,
    Keyword,
    List,
    Record,
    Union,
)

from flopy4.mf6.codec.reader.grammar import filters
from flopy4.mf6.codec.reader.grammar.names import rule_name, to_rule_name


def _get_env():
    loader = jinja2.PackageLoader("flopy4", "mf6/codec/reader/grammar/templates/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["field_type"] = filters.field_type
    env.tests["dynamically_named_array"] = filters.is_dynamically_named_array
    env.filters["keyword_literal"] = filters.keyword_literal
    env.filters["record_child_type"] = filters.record_child_type
    env.filters["to_rule_name"] = to_rule_name
    env.globals["rule"] = lambda *path, tags=(): rule_name(*path, tags=tuple(tags))
    env.globals["part_tag"] = filters.part_tag
    return env


def _field_tag(field: InputField) -> str:
    """The kind tag of a block field's rule (see grammar.names)."""
    if filters.is_dynamically_named_array(field):
        return "val"
    if isinstance(field, Record) and field.children is not None:
        return "rec"
    if isinstance(field, Union) and field.children is not None:
        return "union"
    if isinstance(field, Keyword):
        return "kw"
    return "val"


def _to_context(blocks: dict[str, Block]) -> tuple[list[dict], dict[str, object]]:
    """Build block and field context"""
    all_blocks = []
    all_fields = {}

    for block_name, block in blocks.items():
        header = block.header.field if block.header is not None else None
        has_index = header is not None and not isinstance(header, Record)
        if isinstance(header, Record):
            all_fields[header.name] = header
        recarrays = []
        standalone_fields = []
        # a list's element lines, each read into the list (see names.py)
        elements = set()

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
                        elements.add(arm_name)
                elif field.tagged:
                    all_fields[field_name] = field.item
                    standalone_fields.append(field_name)
                    elements.add(field_name)
                else:
                    recarray_name = filters.get_recarray_name(block_name)
                    recarrays.append({"name": recarray_name})
                    all_fields[field_name] = field
                continue
            all_fields[field_name] = field
            standalone_fields.append(field_name)

        bare_array = any(
            isinstance(all_fields[n], Array) and not all_fields[n].tagged for n in standalone_fields
        )
        rules = {
            name: rule_name(
                name,
                tags=(_field_tag(all_fields[name]), *(("elem",) if name in elements else ())),
            )
            for name in standalone_fields
        }
        all_blocks.append(
            {
                "name": block_name,
                "has_index": has_index,
                # utl-tas's TIME block is indexed by a time, not a number
                "index_rule": "double_index" if isinstance(header, Double) else "block_index",
                "header": header.name if isinstance(header, Record) else None,
                "standalone_fields": standalone_fields,
                "rules": rules,
                "recarrays": recarrays,
                "redirect": not bare_array,
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
    text = template.render(name=component.name, blocks=blocks, fields=fields)
    # one trailing newline, however the template's last rule ends
    target_path.write_text(text.rstrip("\n") + "\n")


def make_grammars(dfns: dict[str, Component], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for component in dfns.values():
        make_grammar(component, outdir)
