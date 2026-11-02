"""Checking a package's string keys when it's written (see
`flopy4.mf6.spec.string`): a ``pk`` is unique within its ``scope``, and an
``fk`` names a row that exists. An fk's path is ``[component.]block.column``:
a list of the package's own (MVR's ``pname1``, a ``packages`` row), or of
another component's, the nearest ancestor of that DFN (``sim-nam``, the
simulation) or the row the key's scope names (MVR's ``pname`` and
``mname``, a package of the model ``mname`` names). A name file's lists
are its children, each row's key its name. Comparison is
case-insensitive, as MF6's.

Integer keys aren't checked yet: some take 0 for none (LAK's ``lakeout``,
UZF's ``ivertcon``)."""

from typing import Any, Iterable, Optional

import attrs

from flopy4.mf6.item import item_list_type
from flopy4.mf6.item_table import ItemTable


def key_errors(pkg: Any) -> list[str]:
    """What's wrong with the package's string keys."""
    errors: list[str] = []
    for f in attrs.fields(type(pkg)):
        item = item_list_type(f.type)
        if item is None or isinstance(item, tuple):
            continue
        columns = {col.name: col for col in item.fields()}
        for kper, rows in _groups(getattr(pkg, f.name)):
            where = f"{type(pkg).__name__}.{f.name.lstrip('_')}"
            if kper is not None:
                where += f": period {kper}"
            for col in columns.values():
                if col.metadata.get("type") != "string":
                    continue
                scope = col.metadata.get("scope")
                keys = list(zip(_values(rows, scope), _values(rows, col.name)))
                if col.metadata.get("pk"):
                    errors += _duplicates(where, col.name, scope, keys)
                if fk := col.metadata.get("fk"):
                    scope_fk = columns[scope].metadata.get("fk") if scope else None
                    errors += _dangling(pkg, where, col.name, scope, scope_fk, fk, keys)
    return errors


def _duplicates(where, name, scope, keys) -> list[str]:
    seen: set = set()
    errors = []
    for key in keys:
        if (k := _norm(key)) in seen:
            errors.append(f"{where}: {_describe(name, scope, key)} is listed more than once")
        seen.add(k)
    return errors


def _dangling(pkg, where, name, scope, scope_fk, fk, keys) -> list[str]:
    """Keys naming no row of the list the path ``fk`` names. In the
    package's own list, a key is matched with its scope; in another
    component's, the scope picks the component (``scope_fk`` the list
    it's a row of), and a key whose scope names none is skipped: the
    scope's own check reports it."""
    *component, block, column = fk.split(".")
    errors = []
    for key in keys:
        if key[1] is None:
            continue
        if not component:
            owner, found = pkg, _norm(key)
        else:
            owner = _ancestor(pkg, component[0]) if key[0] is None else _row(pkg, scope_fk, key[0])
            found = (None, key[1].lower())
        if owner is not None and found not in _keys(owner, block, column):
            missing = block if owner is pkg else f"{block} of {_label(owner)}"
            errors.append(f"{where}: {_describe(name, scope, key)} isn't in {missing}")
    return errors


def _keys(owner, block: str, column: str) -> set[tuple]:
    """The keys of the component's ``block`` rows, by ``column``, with
    their scope."""
    keys = {(None, n) for n in _rows(owner, block)}
    for f in attrs.fields(type(owner)):
        item = item_list_type(f.type)
        if f.metadata.get("block") != block or item is None or isinstance(item, tuple):
            continue
        pk = next(g for g in item.fields() if g.name == column)
        scope = pk.metadata.get("scope")
        for _, rows in _groups(getattr(owner, f.name)):
            keys |= {_norm(k) for k in zip(_values(rows, scope), _values(rows, column))}
    return keys


def _rows(owner, block: str) -> dict[str, Any]:
    """The component's name-file ``block`` rows, its children there, by
    lowercase name (a row's pk)."""
    rows = {}
    for f in attrs.fields(type(owner)):
        if f.metadata.get("block") == block and f.metadata.get("row"):
            value = getattr(owner, f.name)
            for c in value if isinstance(value, list) else [] if value is None else [value]:
                rows[c.name.lower()] = c
    return rows


def _row(pkg, fk: Optional[str], key: str) -> Any:
    """The child the key names in the name-file list the path ``fk``
    names (MVR's ``mname``, a model), or None."""
    if fk is None:
        return None
    *component, block, _ = fk.split(".")
    owner = _ancestor(pkg, component[0]) if component else pkg
    return None if owner is None else _rows(owner, block).get(key.lower())


def _ancestor(component, dfn_name: str) -> Any:
    """The component's nearest ancestor of the DFN, or None."""
    component = component._parent
    while component is not None and getattr(type(component), "dfn_name", None) != dfn_name:
        component = component._parent
    return component


def _label(component) -> str:
    kind = type(component).__name__.lower()
    return f"{kind} {component.name!r}" if component.name else f"the {kind}"


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
