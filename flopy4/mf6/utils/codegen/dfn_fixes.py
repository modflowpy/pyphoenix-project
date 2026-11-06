"""Corrections for where MF6 accepts input its DFNs say it doesn't.

Classes and grammars are generated from whichever release's DFNs ``flopy4 mf6
sync`` reads, so a correction has to be made during generation to survive a
sync. One should be removed when no supported release's DFNs need it.
"""

from typing import Any

from modflow_devtools.dfns.schema import Component, Record

# Record parts MF6 doesn't require but the DFNs mark `optional false`.
#
# formatrecord's format: MF6's `print_format` (src/Utilities/InputOutput.f90)
# reads whatever words follow DIGITS, and without any keeps the caller's edit
# descriptor. mf6/test/test060_gms_ets relies on this.
_OPTIONAL_PARTS: dict[str, frozenset[str]] = {"formatrecord": frozenset({"format"})}


def _fix_field(field: Any) -> Any:
    if not isinstance(field, Record):
        return field
    optional = _OPTIONAL_PARTS.get(field.name, frozenset())
    fixed = {}
    for name, part in field.fields.items():
        part = _fix_field(part)
        fixed[name] = part.model_copy(update={"optional": True}) if name in optional else part
    return field.model_copy(update={"fields": fixed})


def fix_component(component: Component) -> Component:
    """A copy of the component, with the DFN corrections applied."""
    blocks = {
        name: block.model_copy(
            update={"fields": {k: _fix_field(f) for k, f in block.fields.items()}}
        )
        for name, block in (component.blocks or {}).items()
    }
    return component.model_copy(update={"blocks": blocks or component.blocks})
