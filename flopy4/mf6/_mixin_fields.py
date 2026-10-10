"""Find fields the mixins read that the generated classes don't have.

The mixins (see ``MIXINS`` in ``utils.codegen.make``) are written against
the development DFNs. Synced to other DFNs, a class can lack a field a
mixin method reads, which would only show when that method is called. So
sync scans each mixin's methods for the attributes they read from their
class, and looks each up on the classes it generated, before swapping
them in.

The scan follows attribute chains starting at the class: ``self.x`` and
``cls.x``; ``self.parent.x`` in a nested helper class; local names bound
to a chain, including loop variables; ``getattr(obj, "x")``; and keyword
arguments to a class (``cls(x=...)``, ``cls.Inner(y=...)``), including
those in a local dict with literal keys passed as ``cls(**kwargs)``. A chain is
followed through field types (a child component, a record, a list's
items) and inner classes, and stops at anything else, like a method.
``getattr`` with a default is a field the code does without, and isn't
followed. Names built at run time, or passed through ``**kwargs``, can't
be seen.
"""

import ast
import inspect
import textwrap
import typing
from collections.abc import Iterable
from functools import cache
from types import ModuleType
from typing import Any

import attrs


def _chain(node: ast.AST, names: dict[str, list[str]], nested: bool) -> list[str] | None:
    """The attributes an expression reads from the class, e.g.
    ``self.parent.oc.head_file`` in a nested helper gives ``["oc",
    "head_file"]``, or None if it doesn't start at the class."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute):
        if nested and isinstance(node.value, ast.Name) and node.value.id == "self":
            return [] if node.attr == "parent" else None
        base = _chain(node.value, names, nested)
        return None if base is None else [*base, node.attr]
    if isinstance(node, ast.BoolOp):  # `self.x or []`
        return _chain(node.values[0], names, nested)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        base = _chain(node.args[0], names, nested)
        return None if base is None else [*base, node.args[1].value]
    return None


def _bindings(func: ast.FunctionDef) -> list[tuple[str, ast.expr]]:
    """Local names and what they're bound to: assignments, and loop
    variables to what they iterate over."""
    found: list[tuple[str, ast.expr]] = []
    for n in ast.walk(func):
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            target, value = n.targets[0], n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            target, value = n.target, n.value
        elif isinstance(n, (ast.For, ast.comprehension)):
            target, value = n.target, n.iter
        else:
            continue
        if isinstance(target, ast.Name):
            found.append((target.id, value))
    return found


def _functions(mixin: type) -> list[tuple[str, ast.FunctionDef, bool]]:
    """A mixin's methods, by qualified name, and whether each is in a
    nested helper class (where the class is ``self.parent``)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(mixin)))
    (node,) = tree.body
    assert isinstance(node, ast.ClassDef)
    found = []
    for item in node.body:
        if isinstance(item, ast.FunctionDef):
            found.append((f"{node.name}.{item.name}", item, False))
        elif isinstance(item, ast.ClassDef):
            found += [
                (f"{node.name}.{item.name}.{f.name}", f, True)
                for f in item.body
                if isinstance(f, ast.FunctionDef)
            ]
    return found


def _dict_keys(func: ast.FunctionDef) -> dict[str, set[str]]:
    """Local dicts' literal keys: from ``d = {"x": ...}`` or
    ``d = dict(x=...)``, and ``d["x"] = ...``."""
    keys: dict[str, set[str]] = {}
    for n in ast.walk(func):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        target, value = n.targets[0], n.value
        if isinstance(target, ast.Name):
            if isinstance(value, ast.Dict):
                keys.setdefault(target.id, set()).update(
                    k.value
                    for k in value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                )
            elif isinstance(value, ast.Call) and getattr(value.func, "id", None) == "dict":
                keys.setdefault(target.id, set()).update(k.arg for k in value.keywords if k.arg)
        elif (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and isinstance(target.slice, ast.Constant)
            and isinstance(target.slice.value, str)
        ):
            keys.setdefault(target.value.id, set()).add(target.slice.value)
    return keys


@cache
def mixin_chains(mixin: type) -> dict[str, list[list[str]]]:
    """The attribute chains each of a mixin's methods reads from its
    class, by method."""
    chains: dict[str, list[list[str]]] = {}
    for qualname, func, nested in _functions(mixin):
        names: dict[str, list[str]] = {} if nested else {"self": [], "cls": []}
        bindings = _bindings(func)
        # Bindings can refer to each other in any order (a comprehension's
        # variable is bound after its element), so repeat until settled.
        for _ in range(len(bindings)):
            changed = False
            for name, value in bindings:
                if name not in names and (chain := _chain(value, names, nested)) is not None:
                    names[name] = chain
                    changed = True
            if not changed:
                break
        dicts = _dict_keys(func)
        found = chains.setdefault(qualname, [])
        for n in ast.walk(func):
            if (chain := _chain(n, names, nested)) is not None and chain:
                found.append(chain)
            if isinstance(n, ast.Call) and (chain := _chain(n.func, names, nested)) is not None:
                for k in n.keywords:
                    if k.arg:
                        found.append([*chain, k.arg])
                    elif isinstance(k.value, ast.Name):  # **kwargs
                        found += [[*chain, key] for key in sorted(dicts.get(k.value.id, ()))]
    return chains


def _classes(tp: Any) -> set[type]:
    """The attrs classes a type annotation can hold, through Optional,
    unions and containers."""
    if isinstance(tp, type) and attrs.has(tp):
        return {tp}
    return {c for arg in typing.get_args(tp) for c in _classes(arg)}


@cache
def _field_types(cls: type) -> dict[str, Any]:
    """An attrs class's fields, by name and by ``__init__`` alias, with
    their types. Unresolvable annotations are left as they are."""
    try:
        hints = typing.get_type_hints(cls, localns={cls.__name__: cls})
    except Exception:
        hints = {}
    types = {}
    for f in attrs.fields(cls):
        tp = hints.get(f.name, f.type)
        types[f.name] = tp
        if f.alias:
            types[f.alias] = tp
    return types


def _missing(cls: type, chain: list[str]) -> list[str]:
    """Where a chain read from ``cls`` hits an attribute that isn't there,
    as ``Class.attr``."""
    missing = []
    at = {cls}
    for attr in chain:
        following: set[type] = set()
        for c in at:
            fields = _field_types(c) if attrs.has(c) else {}
            if attr in fields:
                following |= _classes(fields[attr])
            elif hasattr(c, attr):
                value = getattr(c, attr)
                if isinstance(value, type) and attrs.has(value):
                    following.add(value)
            else:
                missing.append(f"{c.__qualname__}.{attr}")
        at = following
    return missing


def mixin_gaps(cls: type, mixin: type) -> list[str]:
    """What ``mixin``'s methods read that ``cls`` lacks, one line per
    method, e.g. ``DisMethods.to_grid: no Dis.crs``."""
    gaps = []
    for method, chains in mixin_chains(mixin).items():
        missing = sorted({m for chain in chains for m in _missing(cls, chain)})
        if missing:
            gaps.append(f"{method}: no {', '.join(missing)}")
    return gaps


def find_mixin_gaps(modules: Iterable[ModuleType], mixins: Iterable[type]) -> list[str]:
    """What the mixins' methods read that the classes in ``modules`` that
    use them lack, as ``module.Class: Mixin.method: no Class.attr``
    lines."""
    mixins = tuple(mixins)
    gaps = []
    for module in modules:
        for cls in vars(module).values():
            if not (isinstance(cls, type) and cls.__module__ == module.__name__):
                continue
            for mixin in (m for m in cls.__mro__ if m in mixins):
                gaps += [f"{module.__name__}.{cls.__name__}: {g}" for g in mixin_gaps(cls, mixin)]
    return gaps
