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
that may ``allow_zero`` is None (0 in the file) for no row (LAK's
``lakeout``), as a cellid's no cell. An index array column's fk applies to each element (SFR's
``ic``), a signed index's to its magnitude.

An fk may have a ``rule`` instead of a scope (see modflow-devtools'
``RULES``); unknown rules are skipped:

- ``exchange_models``: one of the binding exchange's models.
- ``flow_model``: checked in the flow model paired with this transport
  model by an exchange; unchecked if there is none.
- ``ssm_package``: checked in the flow package the parent's binding row
  names, unless an advanced transport package (LKT, SFT, ...) is paired
  with it, when MF6 ignores the SPC file (tsp-ssm.f90:195, tsp-apt.f90:343).

An integer fk may name a ``key`` role instead of a path, checked in the
component its scope or rule picks, at that component's ``key_sets`` path
(``block.column``, or ``<=dim`` for a row position). The component must
play the role, and for a mover role have ``mover`` on; if a rule picks a
component without the role, the check is skipped.

A key in a union column's arm (SFR's period ``diversion`` ``idv``) is
checked among that arm's rows, and its scope may name a column of the
enclosing row (``ifno``).

Some keys are unique across lists, which a pk can't say (see
modflow-devtools' dfnspec.md, "Consumer checks"): SSM names a flow package
once in ``sources`` and ``fileinput`` together (tsp-ssm.f90:814-821,
912-919)."""

from types import SimpleNamespace
from typing import Any, Iterable, Optional

import attrs

from flopy4.mf6.item import item_list_type
from flopy4.mf6.item_table import ItemTable
from flopy4.spec import reference_names

# Roles that need the component's ``mover`` option on.
_MOVER_ROLES = ("mover_provider", "mover_receiver")

# Lists whose keys are unique across them, by DFN: (list, column) pairs.
_SHARED_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "gwt-ssm": (("sources", "pname"), ("fileinput", "pname")),
    "gwe-ssm": (("sources", "pname"), ("fileinput", "pname")),
}


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
    return errors + _shared_key_errors(pkg)


def _shared_key_errors(pkg) -> list[str]:
    """Keys given in more than one of the lists in `_SHARED_KEYS`."""
    lists = _SHARED_KEYS.get(getattr(type(pkg), "dfn_name", ""), ())
    seen: dict[Any, str] = {}
    errors = []
    for list_name, column in lists:
        rows = getattr(pkg, list_name, None)
        for value in [] if rows is None else _values(rows, column):
            if value is None:
                continue
            key = _norm((value,))
            if key in seen and seen[key] != list_name:
                errors.append(
                    f"{type(pkg).__name__}.{list_name}: {column} {value!r} is also in {seen[key]}"
                )
            seen.setdefault(key, list_name)
    return errors


def _row_errors(pkg, where: str, cls, rows) -> list[str]:
    columns = {col.name: col for col in cls.fields()}
    errors = _column_errors(pkg, where, columns, rows)
    for col in columns.values():
        if col.metadata.get("type") == "union" and not col.metadata.get("union"):
            errors += _arm_errors(pkg, where, columns, rows, col.name)
    return errors


def _arm_errors(pkg, where: str, columns: dict, rows, name: str) -> list[str]:
    """Keys in the arms of the union column ``name``: each arm's rows, with
    the enclosing row's columns there for a scope to name (SFR's period
    ``diversion`` ``idv``, within the row's ``ifno``)."""
    by_arm: dict[type, list] = {}
    for row, value in zip(_dicts(rows, columns), _values(rows, name)):
        if attrs.has(type(value)):
            arm_values = {f.name: getattr(value, f.name) for f in attrs.fields(type(value))}
            by_arm.setdefault(type(value), []).append(SimpleNamespace(**{**row, **arm_values}))
    errors = []
    for arm, arm_rows in by_arm.items():
        arm_columns = {c.name: c for c in arm.fields()}
        visible = {**columns, **arm_columns}
        errors += _column_errors(pkg, where, visible, arm_rows, check=arm_columns)
    return errors


def _column_errors(pkg, where: str, columns: dict, rows, check: dict | None = None) -> list[str]:
    """Keys of the columns ``check`` (default: all ``columns``) that aren't
    unique or name no row; a scope may name any of ``columns``."""
    errors = []
    for col in (columns if check is None else check).values():
        meta = col.metadata
        if meta.get("type") not in ("string", "integer", "array"):
            continue
        if meta.get("key"):
            errors += _role_errors(pkg, where, columns, rows, col.name)
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
        if meta.get("pk"):
            errors += _duplicates(where, col.name, scope, keys)
        if fk := meta.get("fk"):
            scope_fk = columns[scope].metadata.get("fk") if scope else None
            rule = meta.get("rule")
            dangling = _dangling(pkg, where, col.name, scope, scope_fk, fk, keys, rule)
            errors += dangling
            if rule == "exchange_models" and not dangling:
                errors += _unbound(pkg, where, col.name, [k[1] for k in keys])
    return errors


def _unbound(pkg, where: str, name: str, values: list) -> list[str]:
    """Names that aren't models of the nearest ancestor with model
    references (`flopy4.spec.reference`). Unchecked if there's none."""
    component = pkg._parent
    while component is not None and not component._reference_fields():
        component = component._parent
    if component is None:
        return []
    names = {
        n.lower()
        for f in component._reference_fields()
        for n in _flat(reference_names(getattr(component, f.name)))
        if n is not None
    }
    return [
        f"{where}: {name} {v!r} isn't a model of {_label(component)} ({', '.join(sorted(names))})"
        for v in values
        if v is not None and v.lower() not in names
    ]


def _role_errors(pkg, where: str, columns: dict, rows, name: str) -> list[str]:
    """Keys of the role column ``name`` naming no row of the component its
    scope or rule picks. Rows with no component are skipped."""
    meta = columns[name].metadata
    role, scope, rule = meta["key"], meta.get("scope"), meta.get("rule")
    if scope is None and rule != "ssm_package":
        return []
    bound = _ssm_package(pkg) if scope is None else None
    errors = []
    found: dict[int, tuple[Any, str]] = {}  # by component
    for row in _dicts(rows, columns):
        value = row.get(name)
        instance = bound if scope is None else _instance(pkg, columns, row, scope)
        if value is None or instance is None:
            continue
        what = _describe(name, None, (None, value))
        if id(instance) not in found:
            path = getattr(type(instance), "key_sets", {}).get(role)
            found[id(instance)] = (None, "") if path is None else _role_keys(instance, path)
            if path is not None and role in _MOVER_ROLES and not instance.mover:
                errors.append(f"{where}: {what} is in {_label(instance)}, which hasn't mover on")
        keys, missing = found[id(instance)]
        if keys is None and scope is None:
            continue
        if keys is None:
            role_ = role.replace("_", " ")
            errors.append(f"{where}: {what} is in {_label(instance)}, which isn't a {role_}")
        elif int(value) not in keys:
            errors.append(f"{where}: {what} isn't {missing}")
    return errors


def _role_keys(component, path: str) -> tuple[set | range, str]:
    """The component's keys at ``path``, and where they are. ``<=dim`` is
    row positions below ``dim``, or below the longest list if unset."""
    if path.startswith("<="):
        dim = path[2:]
        # its own (LAK's derived nlakeconn), or a provider's
        n = getattr(component, dim, None)
        if not isinstance(n, int):
            n = component.resolve_dims(dim).get(dim)
        if not isinstance(n, int):
            n = _longest(component)
        return range(n), f"below the {dim} of {_label(component)} ({n})"
    block, column = path.split(".")
    return {k[1] for k in _keys(component, block, column)}, f"in {block} of {_label(component)}"


def _longest(component) -> int:
    """The most rows in any of the component's lists, in any period."""
    most = 0
    for f in attrs.fields(type(component)):
        if item_list_type(f.type) is not None:
            for _, rows in _groups(getattr(component, f.name)):
                most = max(most, len(rows))
    return most


def _instance(pkg, columns: dict, row: dict, name: str) -> Any:
    """The component the row's column ``name`` names, following its fk,
    possibly through the package's own rows. None if it names none."""
    value = row.get(name)
    meta = columns[name].metadata
    fk, scope = meta.get("fk"), meta.get("scope")
    if value is None or not fk:
        return None
    *component, block, column = fk.split(".")
    if component:
        if meta.get("rule") == "flow_model":
            owner = _flow_model(pkg, component[0])
        elif scope is None or row.get(scope) is None:
            owner = _context(pkg, component[0])
        else:
            owner = _row(pkg, columns[scope].metadata.get("fk"), row[scope])
        return None if owner is None else _rows(owner, block).get(str(value).lower())
    key = _norm((row.get(scope) if scope else None, value))
    for f in attrs.fields(type(pkg)):
        item = item_list_type(f.type)
        if f.metadata.get("block") != block or item is None or isinstance(item, tuple):
            continue
        cols = {c.name: c for c in item.fields()}
        target_scope = cols[column].metadata.get("scope")
        for _, rows in _groups(getattr(pkg, f.name)):
            for target in _dicts(rows, cols):
                ours = (target.get(target_scope) if target_scope else None, target[column])
                if _norm(ours) == key:
                    return _instance(pkg, cols, target, column)
    return None


def _flow_model(pkg, dfn_name: str) -> Any:
    """The model of DFN ``dfn_name`` an exchange pairs with the package's
    model, or None if there's none or several."""
    model = pkg._parent
    while model is not None and not _rows(model, "packages"):
        model = model._parent
    sim = _context(pkg, "sim-nam")
    if model is None or sim is None or not model.name:
        return None
    models = _rows(sim, "models")
    found = []
    for exchange in _rows(sim, "exchanges").values():
        names = [
            n.lower()
            for f in exchange._reference_fields()
            for n in _flat(reference_names(getattr(exchange, f.name)))
            if n is not None
        ]
        if model.name.lower() not in names:
            continue
        found += [
            m
            for n in names
            if (m := models.get(n)) is not None and getattr(type(m), "dfn_name", None) == dfn_name
        ]
    return found[0] if len(found) == 1 else None


def _ssm_package(pkg) -> Any:
    """The package named by the parent's row holding this package, or None,
    also if an advanced transport package in the parent's model is paired
    with it (by ``flow_package_name``, else the same name), since MF6 then
    ignores this package."""
    package = _binding_package(pkg)
    model = getattr(pkg._parent, "_parent", None)
    if package is None or model is None or not package.name:
        return package
    for sibling in model._children.values():
        if "flow_package_name" not in attrs.fields_dict(type(sibling)):
            continue
        paired = sibling.flow_package_name or sibling.name
        if paired and paired.lower() == package.name.lower():
            return None
    return package


def _binding_package(pkg) -> Any:
    """The package named by the parent's row holding this package, or None."""
    parent = pkg._parent
    if parent is None:
        return None
    for f in attrs.fields(type(parent)):
        item = item_list_type(f.type)
        if item is None or isinstance(item, tuple):
            continue
        cols = {c.name: c for c in item.fields()}
        for _, rows in _groups(getattr(parent, f.name)):
            for row in _dicts(rows, cols):
                if not any(v is pkg for v in row.values()):
                    continue
                for name, col in cols.items():
                    if col.metadata.get("fk") and col.metadata.get("type") == "string":
                        return _instance(parent, cols, row, name)
    return None


def _dicts(rows, columns: dict) -> list[dict]:
    """The rows as dicts of their columns' values."""
    values = {name: _values(rows, name) for name in columns}
    return [{name: values[name][i] for name in columns} for i in range(len(rows))]


def _flat(value) -> list:
    return value if isinstance(value, list) else [value]


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


def _dangling(pkg, where, name, scope, scope_fk, fk, keys, rule=None) -> list[str]:
    """Keys naming no row of the list the path ``fk`` names. In the
    package's own list, a key is matched with its scope; in another
    component's, the scope (``scope_fk`` the list it's a row of) or the
    ``flow_model`` rule picks the component, and a key whose scope names
    none is skipped: the scope's own check reports it. So is a key whose
    component isn't there, which the component's own checks would
    report."""
    *component, block, column = fk.split(".")
    errors = []
    targets: dict[int, set[tuple]] = {}  # by owner, built once each
    flow_model = _flow_model(pkg, component[0]) if component and rule == "flow_model" else None
    for key in keys:
        if key[1] is None:
            continue
        if not component:
            owner, found = pkg, _norm(key)
        else:
            if rule == "flow_model":
                owner = flow_model
            elif key[0] is None:
                owner = _context(pkg, component[0])
            else:
                owner = _row(pkg, scope_fk, key[0])
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
