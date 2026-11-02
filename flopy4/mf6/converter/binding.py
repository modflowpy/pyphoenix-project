"""Binding rows: the rows naming a component's children in its name file
(a simulation's ``GWF6 model.nam model``, a model's ``CHD6 model.chd-1.chd
chd-1``). A child field's ``row`` (see `flopy4.mf6.spec.child`), generated
from the DFN, names the child attribute each column holds: ``ftype``,
``filename``, ``name``, or a reference field."""

from typing import Any

import attrs

from flopy4.mf6.component import Component
from flopy4.spec import is_reference, resolve


def write_row(child: Component, columns: tuple[str, ...]) -> tuple[str, ...]:
    """The child's row: its columns' values, with the filename in POSIX
    form and references as names (see `Component._row_value`). A list's
    values are spread out. Trailing empty values (an unnamed package's
    name) are left off."""
    terms: list = []
    for attr in columns:
        if attr == "ftype":
            value: Any = child.ftype
        elif attr == "filename":
            value = child.filename.as_posix()  # type: ignore[attr-defined]
        else:
            value = child._row_value(attr)
        terms += value if isinstance(value, list) else [value]
    while terms and not terms[-1]:
        terms.pop()
    return tuple(terms)


def read_row(row: list, columns: tuple[str, ...], cls: type, models: list) -> dict[str, Any]:
    """The values a row gives a child of class `cls`, by the attribute
    each column holds. A list reference takes the rest of the row.
    References are resolved among `models` (those loaded so far)
    case-insensitively, as MF6 looks them up; unknown names stay. An empty
    name is none."""
    fields = attrs.fields_dict(cls)
    values: dict[str, Any] = {}
    terms = list(row)
    for attr in columns:
        if not terms:
            break
        f = fields.get(attr)
        if f is not None and is_reference(f):
            if f.metadata["many"]:
                names, terms = [str(t) for t in terms], []
                values[attr] = resolve(names, models)
            else:
                values[attr], terms = resolve(str(terms[0]), models), terms[1:]
        else:
            values[attr], terms = terms[0], terms[1:]
    if "name" in values:
        values["name"] = str(values["name"]) or None
    return values
