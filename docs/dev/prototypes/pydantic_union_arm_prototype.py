"""
Pydantic prototype: the keystring-union-arm coercion path -- the one item
`pydantic_chd_prototype.py` explicitly left unmeasured ("the keystring-union
-arm case, e.g. LAK/SFR period settings, is a separate, still-unmeasured
surface"). Modeled on the real `flopy4/mf6/gwf/oc.py` `Oc` package, NOT a
synthetic example: `Oc` is the only in-repo package that exercises BOTH
layers of this machinery at once --

  1. Top-level union-arm dispatch: `Oc._stress_period_data` holds a
     `Save | Print` Item per row, dispatched by its leading keyword token
     (SAVE/PRINT) -- flopy4/mf6/item.py's `construct_union_item()`/
     `dispatch_union_item()`, called from `Package._coerce_item_list()`'s
     `isinstance(item_cls, tuple)` branch.
  2. Nested union-arm dispatch: `Save`/`Print`'s own `ocsetting` field is
     ITSELF a `All | First | Last | Frequency | Steps` Item, dispatched the
     same way, one level down -- flopy4/mf6/item.py's `construct_item()`,
     which detects a nested-union field via `_nested_union_classes()` and
     recurses into `construct_union_item()` for it.

Scope: only the raw-Python-value construction path (`Package.
_coerce_item_list` -> `construct_item`/`construct_union_item`), which is
what `Oc(stress_period_data={0: [(...)]})` goes through (confirmed against
the real package below). NOT `from_tokens`/`to_tokens` (the file-parsing
round trip) -- that machinery's pydantic-portability was already measured
independently in `pydantic_record_prototype.py` (a single nested class, not
a nested UNION of classes) and isn't repeated here; `ItemBase` below is
therefore deliberately thinner than the real `Item` mixin (no aux/boundname/
array-of-cellid handling either -- `Oc.Save`/`Oc.Print` don't have those,
and adding them wouldn't exercise anything this spike is about).

Baseline (real code, attrs) this reproduces byte-for-byte -- confirmed by
running against flopy4/mf6/gwf/oc.py directly before writing a line of this
file:

    >>> from flopy4.mf6.gwf import Oc
    >>> oc = Oc(stress_period_data={0: [
    ...     ("SAVE", "HEAD", "ALL"),
    ...     ("SAVE", "BUDGET", "STEPS", 1, 3, 5),
    ...     ("PRINT", "HEAD", "ALL"),
    ... ]})
    >>> [(type(r).__name__, type(r.ocsetting).__name__, getattr(r.ocsetting, "steps", None))
    ...  for r in oc.stress_period_data[0]]
    [('Save', 'All', None), ('Save', 'Steps', (1, 3, 5)), ('Print', 'All', None)]

Also matches test/mf6/test_mf6_adapters.py::test_oc_ocsetting_construct_item_positional
(`Oc(stress_period_data={0: [("SAVE", "HEAD", "ALL")]})` -> row is `Oc.Save`,
`row.ocsetting` is `Oc.All`) and the construction half of test/mf6/
test_mf6_codec.py::test_oc_ocsetting_typed_dispatch (the dump/load/
structure_component roundtrip in that test goes through a different code
path -- cattrs-based converters, out of scope here).

KEY FINDING: the whole thing ports with NO new mechanism beyond what the
two earlier prototypes already established -- it's a straight composition
of `pydantic_chd_prototype.py`'s `SkipValidation`-wrapped Item-list field
(now `Optional[SkipValidation[dict[int, list[Save | Print]]]]` instead of
`Optional[SkipValidation[dict[int, list[Row]]]]`) and
`pydantic_record_prototype.py`'s lazy forward-ref resolution (now a
`"OcProto.All | OcProto.First | ..."` STRING forward ref naming FIVE
sibling classes instead of one -- confirmed pydantic's lazy resolver
handles a multi-name `|`-joined forward ref exactly the same way it handles
a single-name one, no special-casing needed). The one genuinely new piece
of code is `_is_item_union()` below -- the pydantic-side replacement for
item.py's `_nested_union_classes()`, and (same win record_prototype.py
found for `_nested_class()`) it is SIMPLER than the attrs original: no
qualname-walking string parse, just `get_origin`/`get_args` on the already-
resolved `FieldInfo.annotation`, because by the time `record_fields()`'s
guarded `rebuild_dataclass()` has run, that annotation IS the real
`OcProto.All | OcProto.First | ...` union object, not a string.

Confirms the two remaining "Next steps" items from the plan doc's list are
no longer BOTH open -- this was the harder of the two (a real package using
double-nested keystring-union dispatch); the codegen-side change (emitting
`Field(json_schema_extra=...)` from make.py/filters.py) is still unmeasured,
but it's mechanical template work, not a new coercion mechanism -- nothing
found while writing this file suggests it would behave differently than the
by-hand `Field(...)` calls below.

Run directly: `python docs/dev/prototypes/pydantic_union_arm_prototype.py`
"""

from __future__ import annotations

import types
from typing import Annotated, Any, ClassVar, Optional, Union, get_args, get_origin

from pydantic import Field, SkipValidation
from pydantic.dataclasses import dataclass
from pydantic_dis_prototype import _CFG, PackageBase
from pydantic_record_prototype import keyword_of, record_fields

# ============================================================================
# ItemBase: thin port of flopy4/mf6/item.py's `Item` mixin -- just enough
# for construct_item()/construct_union_item() (see module docstring for what
# is deliberately NOT ported: to_tokens/from_tokens, aux/boundname/cellid).
# ============================================================================


class ItemBase:
    pass


# ============================================================================
# _is_item_union(): replaces item.py's `_nested_union_classes()` -- see
# module docstring's KEY FINDING for why this is simpler than the original.
# ============================================================================


def _is_item_union(annotation: Any) -> "tuple[type[ItemBase], ...] | None":
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        arms = tuple(
            a for a in get_args(annotation) if isinstance(a, type) and issubclass(a, ItemBase)
        )
        return arms or None
    return None


def dispatch_union_item(
    values: list, arm_classes: "tuple[type[ItemBase], ...]"
) -> "type[ItemBase] | None":
    """Port of item.py's `dispatch_union_item()`, unchanged in shape."""
    kw_map = {keyword_of(c).upper(): c for c in arm_classes if keyword_of(c)}
    for v in values:
        arm_cls = kw_map.get(str(v).upper())
        if arm_cls is not None:
            return arm_cls
    return None


def _collects_tail(finfo: Any) -> bool:
    """A field that swallows every remaining positional value -- either a
    nested Union[Item, ...] field (Oc's `ocsetting`) or an `array=True`
    field (Oc.Steps' `steps`). Port of construct_item()'s `tuple_idx`
    search condition, minus the aux/cellid arms real Item has that Oc's
    classes don't use (see module docstring)."""
    meta = finfo.json_schema_extra or {}
    if isinstance(meta, dict) and meta.get("array"):
        return True
    return _is_item_union(finfo.annotation) is not None


def construct_item(item_cls: type, values) -> "ItemBase":
    """Port of item.py's `construct_item()`."""
    fields = record_fields(item_cls)
    items = list(fields.items())
    tuple_idx = next((i for i, (_, f) in enumerate(items) if _collects_tail(f)), None)
    values = list(values)
    if tuple_idx is None:
        return item_cls(*values)
    _, finfo = items[tuple_idx]
    arm_classes = _is_item_union(finfo.annotation)
    before = values[:tuple_idx]
    trailing = values[tuple_idx:]
    tail_val = (
        construct_union_item(trailing, arm_classes) if arm_classes is not None else tuple(trailing)
    )
    return item_cls(*before, tail_val)


def construct_union_item(values, arm_classes: "tuple[type[ItemBase], ...]") -> "ItemBase | None":
    """Port of item.py's `construct_union_item()`, unchanged in shape."""
    values = list(values)
    arm_cls = dispatch_union_item(values, arm_classes)
    if arm_cls is None:
        return None
    kw = keyword_of(arm_cls).upper()
    kw_idx = next((i for i, v in enumerate(values) if str(v).upper() == kw), None)
    if kw_idx is not None:
        values = values[:kw_idx] + values[kw_idx + 1 :]
    return construct_item(arm_cls, values)


# ============================================================================
# _item_list_type(): pydantic_chd_prototype.py's version, extended (same as
# the real item_list_type()) to also return a tuple of arm classes.
# ============================================================================


def _unwrap_skip_validation(t: Any) -> Any:
    if get_origin(t) is Annotated:
        return get_args(t)[0]
    return t


def _unwrap_item(t: Any) -> "type[ItemBase] | tuple[type[ItemBase], ...] | None":
    if isinstance(t, type) and issubclass(t, ItemBase):
        return t
    return _is_item_union(t)


def _item_list_type(field_type: Any) -> "type[ItemBase] | tuple[type[ItemBase], ...] | None":
    args = get_args(field_type)
    inner = next((a for a in args if a is not type(None)), None)
    if inner is None:
        return None
    inner = _unwrap_skip_validation(inner)
    if get_origin(inner) is dict:
        _, val = get_args(inner)
        val = _unwrap_skip_validation(val)
        if get_origin(val) is list:
            return _unwrap_item(get_args(val)[0])
    return None


# ============================================================================
# UnionListPackageBase: Package._coerce_item_list, extended for the
# `isinstance(item_cls, tuple)` (keystring-union) branch
# pydantic_chd_prototype.py's ListPackageBase explicitly left out.
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class UnionListPackageBase(PackageBase):
    def _init_item_lists(self) -> None:
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
    def _coerce_item_list(data, item_cls) -> list:
        """Port of `Package._coerce_item_list()`, both branches (this
        prototype's whole reason for existing is the first one)."""
        if isinstance(item_cls, tuple):
            items = []
            for row in data:
                if isinstance(row, item_cls):
                    items.append(row)
                elif isinstance(row, dict):
                    kw = str(row.get("keyword", "")).upper()
                    arm = next((c for c in item_cls if keyword_of(c).upper() == kw), None)
                    if arm is not None:
                        items.append(arm(**{k: v for k, v in row.items() if k != "keyword"}))
                else:
                    item = construct_union_item(row, item_cls)
                    if item is not None:
                        items.append(item)
            return items
        items = []
        for row in data:
            if isinstance(row, item_cls):
                items.append(row)
            elif isinstance(row, dict):
                items.append(item_cls(**row))
            elif isinstance(row, (list, tuple)):
                items.append(item_cls(*row))
        return items

    def __post_init__(self) -> None:
        self._init_item_lists()
        super().__post_init__()


# ============================================================================
# OcProto: models the real Oc (flopy4/mf6/gwf/oc.py), just the
# stress_period_data slice this spike is about.
# ============================================================================


@dataclass(config=_CFG, kw_only=True)
class OcProto(UnionListPackageBase):
    dfn_name: ClassVar[str] = "gwf-oc"

    @dataclass(config=_CFG)
    class All(ItemBase):
        _keyword: ClassVar[str] = "all"

    @dataclass(config=_CFG)
    class First(ItemBase):
        _keyword: ClassVar[str] = "first"

    @dataclass(config=_CFG)
    class Last(ItemBase):
        _keyword: ClassVar[str] = "last"

    @dataclass(config=_CFG)
    class Frequency(ItemBase):
        _keyword: ClassVar[str] = "frequency"
        frequency: int = Field()

    @dataclass(config=_CFG)
    class Steps(ItemBase):
        _keyword: ClassVar[str] = "steps"
        steps: tuple = Field(default=(), json_schema_extra={"array": True})

    @dataclass(config=_CFG)
    class Save(ItemBase):
        _keyword: ClassVar[str] = "save"
        rtype: Union[float, str] = Field()
        ocsetting: (
            "OcProto.All | OcProto.First | OcProto.Last | OcProto.Frequency | "
            "OcProto.Steps"
        ) = Field()

    @dataclass(config=_CFG)
    class Print(ItemBase):
        _keyword: ClassVar[str] = "print"
        rtype: Union[float, str] = Field()
        ocsetting: (
            "OcProto.All | OcProto.First | OcProto.Last | OcProto.Frequency | "
            "OcProto.Steps"
        ) = Field()

    _StressPeriodDataItem = Save | Print

    stress_period_data: Optional[SkipValidation[dict[int, list[_StressPeriodDataItem]]]] = Field(
        default=None, json_schema_extra={"block": "period", "fill_forward": True}
    )


# ============================================================================
# Demonstration / smoke test
# ============================================================================


def demo() -> None:
    print("=" * 70)
    print("Pydantic keystring-union-arm prototype (real Oc shape)")
    print("=" * 70)

    complete = OcProto.Save.__pydantic_complete__
    print(f"\nSave.__pydantic_complete__ before any construction: {complete}")

    oc = OcProto(
        stress_period_data={
            0: [
                ("SAVE", "HEAD", "ALL"),
                ("SAVE", "BUDGET", "STEPS", 1, 3, 5),
                ("PRINT", "HEAD", "ALL"),
            ]
        }
    )
    print(f"Save.__pydantic_complete__ after construction: {OcProto.Save.__pydantic_complete__}")

    rows = oc.stress_period_data[0]
    print("\nstress_period_data[0]:")
    for r in rows:
        print(f"  {type(r).__name__}(rtype={r.rtype!r}, ocsetting={r.ocsetting!r})")

    assert isinstance(rows[0], OcProto.Save)
    assert isinstance(rows[0].ocsetting, OcProto.All)
    assert isinstance(rows[1], OcProto.Save)
    assert isinstance(rows[1].ocsetting, OcProto.Steps)
    assert rows[1].ocsetting.steps == (1, 3, 5)
    assert isinstance(rows[2], OcProto.Print)
    assert isinstance(rows[2].ocsetting, OcProto.All)

    # -- dict-form input, dispatched by an explicit "keyword" key (the
    # Package._coerce_item_list branch a raw tuple can't reach: a
    # column-oriented / already-typed-arm dict input).
    oc2 = OcProto(
        stress_period_data={0: [{"keyword": "print", "rtype": "HEAD", "ocsetting": OcProto.All()}]}
    )
    row2 = oc2.stress_period_data[0][0]
    assert isinstance(row2, OcProto.Print)
    assert isinstance(row2.ocsetting, OcProto.All)
    print(f"\ndict-form (explicit keyword) input: {row2}")

    # -- a real OcProto.Save/Print instance passed straight through.
    oc3 = OcProto(stress_period_data={0: [OcProto.Print(rtype="HEAD", ocsetting=OcProto.All())]})
    assert isinstance(oc3.stress_period_data[0][0], OcProto.Print)
    print(f"instance-form input passes through: {oc3.stress_period_data[0][0]}")

    print("\nAll assertions passed.")


if __name__ == "__main__":
    demo()
