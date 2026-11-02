"""Checking a package's keys when it's written (see `flopy4.mf6.spec.string`
and `flopy4.mf6.spec.integer`): a ``pk`` is unique within its ``scope``,
and an ``fk`` names a row that exists. An fk's path is
``[component.]block.column``: a list of the package's own (MVR's ``pname1``,
a ``packages`` row; LAK's ``lakeout``, a ``packagedata`` row), or of
another component's: the nearest ancestor of that DFN (``sim-nam``, the
simulation), the one package of it in the nearest ancestor (CHF CDB's
``idcxs``, the model's CXS), or the row the key's scope names (MVR's
``pname`` and ``mname``, a package of the model ``mname`` names). A name
file's lists are its children, each row's key its name. String comparison
is case-insensitive, as MF6's.

Integer keys are 0-based indices in memory, as everywhere in flopy4. An fk
that may ``allow_zero`` is -1 (0 in the file) for no row (LAK's
``lakeout``). An index array column's fk applies to each element (SFR's
``ic``), a signed index's to its magnitude."""

from typing import Any, Iterable, Optional

import attrs

from flopy4.mf6.item import item_list_type
from flopy4.mf6.item_table import ItemTable


def key_errors(pkg: Any) -> list[str]:
    """What's wrong with the package's keys."""
    errors: list[str] = []
    for f in attrs.fields(type(pkg)):
        item = item_list_type(f.type)
        if item is None:
            continue
        arms = item if isinstance(item, tuple) else (item,)
        for kper, rows in _groups(getattr(pkg, f.name)):
            where = f"{type(pkg).__name__}.{f.name.lstrip('_')}"
            if kper is not None:
                where += f": period {kper}"
            for cls in arms:
                if len(arms) > 1:
                    # a list of unions: each arm's rows (LAK's STATUS, RATE)
                    rows_ = [r for r in rows if isinstance(r, cls)]
                else:
                    rows_ = rows
                errors += _row_errors(pkg, where, cls, rows_)
    return errors


def _row_errors(pkg, where: str, cls, rows) -> list[str]:
    columns = {col.name: col for col in cls.fields()}
    errors = []
    for col in columns.values():
        meta = col.metadata
        if meta.get("type") not in ("string", "integer", "array"):
            continue
        if not (meta.get("pk") or meta.get("fk")):
            continue
        scope = meta.get("scope")
        values = _values(rows, col.name)
        if meta.get("type") == "array":
            values = [_element(v, meta) for row in values for v in row or ()]
            scopes: list = [None] * len(values)
        else:
            scopes = _values(rows, scope)
        keys = list(zip(scopes, values))
        if meta.get("allow_zero"):
            keys = [k for k in keys if k[1] != -1]
        if meta.get("pk"):
            errors += _duplicates(where, col.name, scope, keys)
        if fk := meta.get("fk"):
            scope_fk = columns[scope].metadata.get("fk") if scope else None
            errors += _dangling(pkg, where, col.name, scope, scope_fk, fk, keys)
    return errors


def _element(value, meta: dict):
    """An index array's element's index: a signed one's magnitude (SFR's
    ``ic``, as (index, sign) pairs)."""
    if meta.get("index") == "signed" and isinstance(value, tuple):
        return value[0]
    return value


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
    scope's own check reports it. So is a key whose component isn't
    there, which the component's own checks would report."""
    *component, block, column = fk.split(".")
    errors = []
    targets: dict[int, set[tuple]] = {}  # by owner, built once each
    for key in keys:
        if key[1] is None:
            continue
        if not component:
            owner, found = pkg, _norm(key)
        else:
            owner = _context(pkg, component[0]) if key[0] is None else _row(pkg, scope_fk, key[0])
            found = (None, _norm(key)[1])
        if owner is None:
            continue
        if id(owner) not in targets:
            targets[id(owner)] = _keys(owner, block, column)
        if found not in targets[id(owner)]:
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
    owner = _context(pkg, component[0]) if component else pkg
    return None if owner is None else _rows(owner, block).get(key.lower())


def _context(component, dfn_name: str) -> Any:
    """The component of the DFN an fk's path names, in the component's
    context: its nearest ancestor of the DFN (``sim-nam``, the
    simulation), or the only child of the DFN of its nearest ancestor
    that has one (a CHF model's CXS); None if there's none, or several."""
    component = component._parent
    while component is not None:
        if getattr(type(component), "dfn_name", None) == dfn_name:
            return component
        found = [
            c
            for c in component._children.values()
            if getattr(type(c), "dfn_name", None) == dfn_name
        ]
        if found:
            return found[0] if len(found) == 1 else None
        component = component._parent
    return None


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
    return tuple(k.lower() if isinstance(k, str) else int(k) if _is_int(k) else k for k in key)


def _is_int(value) -> bool:
    try:
        return int(value) == value and not isinstance(value, bool)
    except (TypeError, ValueError):
        return False


def _describe(name: str, scope: Optional[str], key: tuple) -> str:
    key = tuple(int(k) if _is_int(k) else k for k in key)
    if scope is None or key[0] is None:
        return f"{name} {key[1]!r}"
    return f"{name} {key[1]!r} ({scope} {key[0]!r})"
