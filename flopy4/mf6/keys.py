"""Checking a package's string keys when it's written (see
`flopy4.mf6.spec.string`): a ``pk`` is unique within its ``scope``, and an
``fk`` names a row that exists, in the same package (MVR's ``pname1``, a
``packages`` row) or in a name file (MVR's ``mname``, one of the
simulation's models; its ``pname``, a package of the model ``mname``
names). Comparison is case-insensitive, as MF6's.

Integer keys aren't checked yet: some take 0 for none (LAK's ``lakeout``,
UZF's ``ivertcon``)."""

from typing import Any, Iterable, Optional

import attrs

from flopy4.mf6.item import item_list_type
from flopy4.mf6.item_table import ItemTable


def key_errors(pkg: Any) -> list[str]:
    """What's wrong with the package's string keys."""
    fields = attrs.fields(type(pkg))
    errors: list[str] = []
    for f in fields:
        item = item_list_type(f.type)
        if item is None or isinstance(item, tuple):
            continue
        for kper, rows in _groups(getattr(pkg, f.name)):
            where = f"{type(pkg).__name__}.{f.name.lstrip('_')}"
            if kper is not None:
                where += f": period {kper}"
            for col in item.fields():
                if col.metadata.get("type") != "string":
                    continue
                scope = col.metadata.get("scope")
                keys = list(zip(_values(rows, scope), _values(rows, col.name)))
                if col.metadata.get("pk"):
                    errors += _duplicates(where, col.name, scope, keys)
                if fk := col.metadata.get("fk"):
                    errors += _dangling(pkg, fields, where, col.name, scope, fk, keys)
    return errors


def _duplicates(where, name, scope, keys) -> list[str]:
    seen: set = set()
    errors = []
    for key in keys:
        if (k := _norm(key)) in seen:
            errors.append(f"{where}: {_describe(name, scope, key)} is listed more than once")
        seen.add(k)
    return errors


def _dangling(pkg, fields, where, name, scope, fk, keys) -> list[str]:
    """Keys naming no row of the target the path ``fk`` names: a list of
    this package's (``packages.pname``) or a name file's
    (``sim-nam.models.mname``, ``gwf-nam.packages.pname``)."""
    errors = []
    *component, block, column = fk.split(".")
    if not component:
        target = next((g for g in fields if g.metadata.get("block") == block), None)
        item = item_list_type(target.type) if target else None
        if item is None or isinstance(item, tuple):
            return []
        pk = next(g for g in item.fields() if g.name == column)
        target_scope = pk.metadata.get("scope")
        allowed = {
            _norm(k)
            for _, rows in _groups(getattr(pkg, target.name))  # type: ignore[union-attr]
            for k in zip(_values(rows, target_scope), _values(rows, column))
        }
        for key in keys:
            if key[1] is not None and _norm(key) not in allowed:
                errors.append(f"{where}: {_describe(name, scope, key)} isn't in {block}")
        return errors
    names: dict = {}  # by model, as a model's packages are looked up once
    for key in keys:
        if key[1] is None:
            continue
        model = key[0].lower() if isinstance(key[0], str) else None
        if model not in names:
            names[model] = _names(pkg, component[0], model)
        if names[model] is not None and key[1].lower() not in names[model]:
            missing = _missing(pkg, component[0], key[0])
            errors.append(f"{where}: {_describe(name, scope, key)} {missing}")
    return errors


def _names(pkg, component: str, model: Optional[str]) -> Optional[set[str]]:
    """The names a name file's list holds, lowercase: the simulation's
    models (``sim-nam``) or a model's packages (``gwf-nam``), the model
    ``model`` names or else the package's own. None if not known, as
    for a package outside a simulation."""
    from flopy4.mf6.model import Model
    from flopy4.mf6.simulation import Simulation

    sim = _ancestor(pkg, Simulation)
    if component == "sim-nam":
        return None if sim is None else {m.name.lower() for m in sim.models}
    if not component.endswith("-nam"):
        return None
    if model is None:
        owner = _ancestor(pkg, Model)
    else:
        models = sim.models if sim is not None else []
        owner = next((m for m in models if m.name.lower() == model.lower()), None)
    return None if owner is None else {n.lower() for n in owner._children}


def _missing(pkg, component: str, model: Optional[str]) -> str:
    if component == "sim-nam":
        return "isn't a model in the simulation"
    from flopy4.mf6.model import Model

    owner = model or getattr(_ancestor(pkg, Model), "name", None)
    return f"isn't a package of model {owner!r}"


def _ancestor(component, cls) -> Any:
    while component is not None and not isinstance(component, cls):
        component = component._parent
    return component


def _groups(value) -> Iterable[tuple[Optional[int], Any]]:
    """A list field's rows, by period for a period list."""
    if isinstance(value, dict):
        return value.items()
    return [] if value is None else [(None, value)]


def _values(rows, name: Optional[str]) -> list:
    if name is None:
        return [None] * len(rows)
    if isinstance(rows, ItemTable):
        return rows.values(name)
    return [getattr(r, name) for r in rows]


def _norm(key: tuple) -> tuple:
    return tuple(k.lower() if isinstance(k, str) else k for k in key)


def _describe(name: str, scope: Optional[str], key: tuple) -> str:
    if scope is None or key[0] is None:
        return f"{name} {key[1]!r}"
    return f"{name} {key[1]!r} ({scope} {key[0]!r})"
