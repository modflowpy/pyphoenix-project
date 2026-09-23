"""
Pydantic prototype: the two mechanics `pydantic_dis_prototype.py` explicitly
left out of scope -- (1) `Component`'s full `MutableMapping` interface for a
*list*-kind child field (many packages of the same slot, e.g. a model's
`chd: list[Chd]`), not just the "only" (single-child, `Dis.ncf`) case that
prototype covered, and (2) `Package`'s Item-list coercion (raw
tuple/dict/instance stress-period-data -> `Item` instances), modeled on
`flopy4/mf6/gwf/chd.py`'s real shape.

Mined from:
- flopy4/mf6/component.py -- `__getitem__`/`__setitem__`/`__delitem__`/
  `__iter__`/`__len__`, `_find_child_field`, `_resolve_child_name`,
  `_attach_to_parent_field` (the "list" kind branches specifically).
- flopy4/mf6/package.py -- `_init_item_lists`, `_coerce_item_list`.
- flopy4/mf6/gwf/chd.py -- the real `Chd`/`Chd.StressPeriodData` shape being
  modeled (`_stress_period_data`, `alias=`, `block="period"`,
  `fill_forward=True`).
- flopy4/mf6/item.py -- `item_list_type()` (the field-type -> Item-class
  introspection this prototype's `_item_list_type()` adapts for pydantic's
  `SkipValidation`-wrapped annotation shape -- see the finding below).

Reuses `ComponentBase`/`PackageBase`/`_CFG`/`_DTYPE_MAP` from
`pydantic_dis_prototype.py` rather than redefining them.

KEY FINDING (the reason `SkipValidation` is needed at all): attrs applies
*zero* validation to `Chd._stress_period_data` at construction (no
validator/converter declared on that field) -- raw tuples/dicts pass
through attrs' `__init__` untouched, and `Package.__attrs_post_init__`
coerces them into real `Item` instances afterward. Pydantic does NOT default
to this behavior: a plain `Optional[dict[int, list[Row]]]`-typed field is
*eagerly, strictly* validated against that annotation at construction --
confirmed empirically that `Pkg(rows={0: [(1, 2.0)]})` raises
`ValidationError: Input should be an instance of Row` for a raw tuple,
before any post-init coercion hook ever runs. Wrapping the annotation in
`pydantic.SkipValidation[...]` fixes this (confirmed: identical raw input is
accepted, coercion runs in `__post_init__` exactly like the attrs version),
but costs two things pydantic_dis_prototype.py's array fields didn't need:
  1. `item_list_type()`'s `get_origin`/`get_args` walk must unwrap one extra
     `Annotated[..., SkipValidation()]` layer before it reaches
     `dict[int, list[Row]]` -- confirmed the real function's current logic
     does NOT do this and needs a small, mechanical addition (see
     `_item_list_type()` below).
  2. `SkipValidation` also skips `validate_assignment` re-validation on
     this field specifically -- confirmed `pkg.stress_period_data = "junk"`
     is silently accepted with `SkipValidation`, same as it would be on
     attrs today (no validator declared there either) -- a wash, not a
     regression, but worth naming since it's a per-field opt-out, not a
     global one.

Also confirms the `Item`/`Record` subsystem (`flopy4/mf6/item.py`,
`flopy4/mf6/record.py`) does NOT need to migrate to pydantic at all: with
`SkipValidation`, pydantic never inspects `Row`'s own fields, so `Row`
here is a genuine, unmodified `attrs.define` class -- exactly like the real
`Chd.StressPeriodData`. Mixed attrs/pydantic is fine for this boundary.

Run directly: `python docs/dev/prototypes/pydantic_chd_prototype.py`
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Annotated, Any, ClassVar, Optional, get_args, get_origin

import attrs
from pydantic import Field, SkipValidation
from pydantic.dataclasses import dataclass
from pydantic_dis_prototype import _CFG, ComponentBase, PackageBase

# ============================================================================
# Row type: stays a plain, unmodified attrs class -- see module docstring's
# "KEY FINDING" for why pydantic never needs to see inside it.
# ============================================================================


@attrs.define
class ChdRowProto:
    """Models `Chd.StressPeriodData` (flopy4/mf6/gwf/chd.py) -- a real
    attrs `Item` subclass in the actual codebase; simplified here to just
    the fields this prototype's coercion path exercises (the full
    `Item`/`Record` token round-trip machinery is out of scope -- see
    module docstring)."""

    cellid: tuple
    head: float
    boundname: Optional[str] = None


# ============================================================================
# item_list_type(): adapted from flopy4/mf6/item.py for pydantic's
# SkipValidation-wrapped annotation shape (see module docstring finding #1).
# ============================================================================


def _unwrap_skip_validation(t: Any) -> Any:
    """Strip one `Annotated[X, SkipValidation()]` layer, if present.

    NEW code this migration would need -- the real `item_list_type()` has
    no such step today because attrs field types are never wrapped this
    way. Confirmed necessary: `get_origin()` on the raw (unstripped)
    annotation returns `Annotated`, not `dict`, so the existing
    dict/list-unwrapping logic below would silently fail to find `Row`
    without this.
    """
    if get_origin(t) is Annotated:
        return get_args(t)[0]
    return t


def _item_list_type(field_type: Any) -> "type | None":
    """Adapted from `flopy4.mf6.item.item_list_type()`: for
    `Optional[SkipValidation[dict[int, list[C]]]]`, return `C`."""
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    inner = _unwrap_skip_validation(inner)
    origin = get_origin(inner)
    if origin is dict:
        _, val = get_args(inner)
        val = _unwrap_skip_validation(val)
        if get_origin(val) is list:
            (item_cls,) = get_args(val)
            return item_cls
    return None


# ============================================================================
# ListPackageBase: Package._init_item_lists/_coerce_item_list, adapted.
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class ListPackageBase(PackageBase):
    """Adds Item-list coercion on top of `PackageBase`'s griddata handling.
    A real generated package would get both by inheriting one shared base
    -- split here into two classes only so this file can import
    `PackageBase` from the Dis prototype unmodified."""

    def _init_item_lists(self) -> None:
        """Adapted from `Package._init_item_lists`/`_coerce_item_list`
        (non-union path only -- the keystring-union-arm case, e.g. LAK/SFR
        period settings, is a separate, still-unmeasured surface; see the
        plan doc)."""
        for fname, finfo in type(self)._pydantic_fields().items():
            meta = finfo.json_schema_extra or {}
            if not (isinstance(meta, dict) and meta.get("block")):
                continue
            item_cls = _item_list_type(finfo.annotation)
            if item_cls is None:
                continue
            raw = self.__dict__.get(fname)
            if raw is None:
                continue
            if meta.get("block") == "period" or meta.get("fill_forward"):
                coerced = {
                    kper: self._coerce_item_list(rows, item_cls) for kper, rows in raw.items()
                }
                object.__setattr__(self, fname, coerced)
            else:
                object.__setattr__(self, fname, self._coerce_item_list(raw, item_cls))

    @staticmethod
    def _coerce_item_list(data, item_cls: type) -> list:
        items = []
        for row in data:
            if isinstance(row, item_cls):
                items.append(row)
            elif isinstance(row, dict):
                items.append(item_cls(**row))
            elif isinstance(row, (list, tuple)):
                items.append(item_cls(*row))
            else:
                raise TypeError(f"Can't coerce {row!r} to {item_cls.__name__}")
        return items

    def __post_init__(self) -> None:
        self._init_item_lists()
        super().__post_init__()


# ============================================================================
# ChdProto: models the real Chd (flopy4/mf6/gwf/chd.py)
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class ChdProto(ListPackageBase):
    dfn_name: ClassVar[str] = "gwf-chd"

    boundnames: bool = Field(default=False, json_schema_extra={"block": "options"})
    print_input: bool = Field(default=False, json_schema_extra={"block": "options"})

    # The field this whole prototype exists to test: SkipValidation is
    # what lets raw tuple/dict input (see demo() below) reach
    # ListPackageBase._init_item_lists() at all -- without it, pydantic's
    # own eager validation rejects the raw input before __post_init__ ever
    # runs (module docstring's "KEY FINDING").
    stress_period_data: Optional[SkipValidation[dict[int, list[ChdRowProto]]]] = Field(
        default=None, json_schema_extra={"block": "period", "fill_forward": True}
    )


# ============================================================================
# ModelBase: Component's full MutableMapping interface for a *list*-kind
# child field -- pydantic_dis_prototype.py's ComponentBase only exercised
# the "only" (single-child) case via Dis.ncf. This is the other half.
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class ModelBase(ComponentBase, MutableMapping):
    """Adapted from `Component`'s `MutableMapping` mixing + `_children`/
    `__getitem__`/`__setitem__`/`__delitem__`/`__iter__`/`__len__` -- the
    "list" kind only (a model holding several packages of the same slot,
    e.g. `chd: list[ChdProto]`); the "dict"-kind branch real `Component`
    also has isn't exercised here (out of scope, same as before)."""

    chd: list[ChdProto] = Field(default_factory=list, exclude=True)

    def _list_child_fields(self) -> list[str]:
        """`list[ComponentBase]`-typed fields -- the part `ComponentBase.
        _child_fields()` (Dis prototype) doesn't cover, since it only
        matches a field whose annotation IS (or directly wraps) a
        `ComponentBase` subclass, not `list[ComponentBase subclass]`."""
        names = []
        for fname, finfo in type(self)._pydantic_fields().items():
            ann = finfo.annotation
            if get_origin(ann) is list:
                (elem,) = get_args(ann)
                if isinstance(elem, type) and issubclass(elem, ComponentBase):
                    names.append(fname)
        return names

    @property
    def _children(self) -> dict[str, ComponentBase]:
        result: dict[str, ComponentBase] = {}
        for fname in self._list_child_fields():
            for child in getattr(self, fname):
                result[child.name] = child
        return result

    def _set_child_parents(self) -> None:
        """Adapted from `Component._set_child_parents`'s "list" branch.

        NOTE the same "is this still a default name" check real
        `Component._is_default_child_name()` needs: by the time a child
        reaches here, its own `__post_init__` (`ComponentBase.__post_init__`)
        has *already* defaulted `.name` to its lowercased class name --
        `child.name` is never actually `None` at this point. Checking
        `child.name is None` (this prototype's first cut) silently failed
        to rename same-class siblings, since only the first one collided
        (the rest stayed at the shared class-name default, `not in used`
        yet). Confirmed by running this file and seeing `['chdproto',
        'chd1']` instead of `['chd0', 'chd1']` -- fixed below.
        """
        super()._set_child_parents()
        for fname in self._list_child_fields():
            used: set[str] = set()
            for i, child in enumerate(getattr(self, fname)):
                object.__setattr__(child, "parent", self)
                is_default = child.name == type(child).__name__.lower()
                if is_default or child.name in used:
                    object.__setattr__(child, "name", f"{fname}{i}")
                used.add(child.name)

    def __getitem__(self, key):
        return self._children[key]

    def __setitem__(self, key, value):
        if not isinstance(value, ComponentBase):
            raise TypeError(f"Expected a ComponentBase, got {type(value).__name__}")
        for fname in self._list_child_fields():
            current = getattr(self, fname)
            for i, child in enumerate(current):
                if child.name == key:
                    object.__setattr__(value, "name", key)
                    object.__setattr__(value, "parent", self)
                    current[i] = value
                    return
        # No existing child named `key` -- attach fresh to the (only, for
        # this prototype) list field matching value's type.
        for fname in self._list_child_fields():
            finfo = type(self)._pydantic_fields()[fname]
            (elem,) = get_args(finfo.annotation)
            if isinstance(value, elem):
                object.__setattr__(value, "name", key)
                object.__setattr__(value, "parent", self)
                getattr(self, fname).append(value)
                return
        raise TypeError(f"No field on {type(self).__name__} accepts a {type(value).__name__}")

    def __delitem__(self, key):
        for fname in self._list_child_fields():
            current = getattr(self, fname)
            for i, child in enumerate(current):
                if child.name == key:
                    del current[i]
                    return
        raise KeyError(key)

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)


# ============================================================================
# Demonstration / smoke test
# ============================================================================


def _assert_plain_typed_field_rejects_raw_tuple() -> None:
    """Control case for the module docstring's "KEY FINDING": the identical
    field, WITHOUT `SkipValidation`, on the same raw input `ChdProto`
    above accepts -- confirms the rejection is really pydantic's default
    eager validation, not some other mistake in this prototype."""
    from pydantic import ConfigDict
    from pydantic.dataclasses import dataclass as _dc

    @_dc(config=ConfigDict(arbitrary_types_allowed=True, extra="forbid"), kw_only=True)
    class _NoSkip:
        rows: Optional[dict[int, list[ChdRowProto]]] = None

    try:
        _NoSkip(rows={0: [((0, 0, 0), 1.0)]})
        raise AssertionError("expected a validation error")
    except AssertionError:
        raise
    except Exception as e:
        print(f"  plain-typed field rejects the same raw tuple -> {type(e).__name__} as expected")


def demo() -> None:
    print("=" * 70)
    print("Pydantic Chd/MutableMapping prototype")
    print("=" * 70)

    # -- Item-list coercion: raw tuple, raw dict, and real-instance forms,
    # matching Package._coerce_item_list's three main input shapes.
    chd = ChdProto(
        stress_period_data={
            0: [((0, 0, 0), 1.0), {"cellid": (0, 0, 1), "head": 2.0, "boundname": "b1"}],
            1: [ChdRowProto(cellid=(0, 0, 2), head=3.0)],
        }
    )
    print(f"\nstress_period_data: {chd.stress_period_data}")
    assert isinstance(chd.stress_period_data[0][0], ChdRowProto)
    assert chd.stress_period_data[0][0].cellid == (0, 0, 0)
    assert chd.stress_period_data[0][1].boundname == "b1"
    assert chd.stress_period_data[1][0].head == 3.0

    print("\nEager pydantic validation without SkipValidation (confirms the finding):")
    _assert_plain_typed_field_rejects_raw_tuple()

    # -- MutableMapping over a list-kind child field.
    model = ModelBase(chd=[ChdProto(), ChdProto()])
    print(f"\nlen(model): {len(model)}")
    assert len(model) == 2
    names = list(model)
    print(f"child names (auto-assigned, field-name + index): {names}")
    assert names == ["chd0", "chd1"]
    assert model["chd0"].parent is model

    extra = ChdProto()
    model["chd2"] = extra
    assert model["chd2"] is extra and extra.name == "chd2" and extra.parent is model
    print(f"after __setitem__('chd2', ...): {list(model)}")

    del model["chd1"]
    print(f"after __delitem__('chd1'): {list(model)}")
    assert "chd1" not in model
    assert len(model) == 2

    print("\nAll assertions passed.")


if __name__ == "__main__":
    demo()
