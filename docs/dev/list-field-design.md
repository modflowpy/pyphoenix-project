# List field design

## Overview

MODFLOW 6 DFN `list` fields — used for packagedata blocks, connectiondata blocks, period blocks, and other tabular or semi-tabular inputs — are represented in the object model as `list[ItemType]`, where `ItemType` is a typed record class generated from the DFN.

This document describes the design, the rationale, and the implementation conventions that follow from it.

## Background: the fan-out problem

The previous approach exploded each `list` field into N separate `NDArray` attrs, one per column, all sharing the same dimension (e.g., `nlakes`). This required:

- A `_<block>` buffer attr, `__attrs_post_init__`, `_get_block`, and `_set_block` to service the scatter/gather round-trip
- A `__block_col_maps__` ClassVar duplicating the column schema
- Fill-value logic to mark absent cells in dense grid arrays
- Complex special-casing in the converter (`structure_array`, `_hack_period_non_numeric`, `_LIST_BLOCK_NAMES`) to reassemble rows at write time and scatter them at read time

The fundamental problem: the fan-out is an internal representation choice that buys nothing. The DFN describes rows; the Python object model should describe rows; the xarray view describes columns. The fan-out conflated storage with view.

## Design

### Primary representation: `list[ItemType]`

Every DFN `list` field maps to a Python `list` of typed item objects. `ItemType` is a generated `attrs` class (slots, frozen or mutable as appropriate) corresponding to the DFN's `item` field — either a `Record` or a `Union`.

```python
# Static tabular list (item type: Record)
packagedata: Optional[list[LakPackagedataItem]] = field(block="packagedata", default=None)

# Repeating period block (item type: Record)
period: Optional[dict[int, list[ChdPeriodItem]]] = field(block="period", default=None)

# Repeating period block with keystring (item type: Union)
period: Optional[dict[int, list[OcPeriodItem]]] = field(block="period", default=None)
```

Repeating blocks (i.e., DFN blocks with `repeats: true`, canonically the period block) use `dict[int, list[ItemType]]`, where the key is the block label (stress period number). This preserves the fill-forward semantics: a period that is not explicitly specified inherits the most recent prior specification.

### Item classes

Item classes are generated `attrs` classes with `slots=True`. One class is generated per DFN record definition; unions produce one class per arm.

```python
@attrs.define(slots=True)
class LakPackagedataItem:
    ifno: int
    strt: float
    nlakeconn: int
    aux: list[float] | None = attrs.field(default=None)
    boundname: str | None = attrs.field(default=None)

@attrs.define(slots=True)
class OcSavePeriodItem:
    rtype: str       # HEAD | BUDGET | ...
    ocsetting: str   # ALL | FIRST | LAST | STEPS n1 n2 ...

@attrs.define(slots=True)
class OcPrintPeriodItem:
    rtype: str
    ocsetting: str

OcPeriodItem = OcSavePeriodItem | OcPrintPeriodItem
```

`slots=True` reduces per-instance memory overhead, which matters when lists contain many rows. If the project migrates from `attrs` to pydantic, item classes migrate to `@pydantic.dataclasses.dataclass(config=ConfigDict(slots=True))`, which is a supported configuration in pydantic v2.

### Derived dimensions

Dimensions that were formerly stored attrs (e.g., `nlakes`, `nconnectiondata`) become computed properties:

```python
@property
def nlakes(self) -> int | None:
    return len(self.packagedata) if self.packagedata else None
```

They are not stored, not passed to the constructor, and not part of the xattree dimension graph. The DFN `dimensions` block values are written at serialization time by reading `len()` of the corresponding list field.

### Views

#### DataFrame (tabular lists)

For list fields with a uniform `Record` item type (i.e., not a union), a DataFrame view is available:

```python
@property
def packagedata_df(self) -> pd.DataFrame | None:
    if self.packagedata is None:
        return None
    return pd.DataFrame([attrs.asdict(r) for r in self.packagedata])
```

DataFrames are also accepted on construction and attribute assignment; the setter converts them to `list[ItemType]` internally.

#### xr.Dataset (spatial period data)

For period blocks with spatial content (CHD, WEL, DRN, etc.), an xarray Dataset view can be provided on demand. This is the "fan-out to columns" representation that was previously the primary storage:

```python
def period_as_dataset(self) -> xr.Dataset | None:
    """Materialize period data as an (nper, nodes) Dataset."""
    ...
```

This view is computed lazily and not cached. It is appropriate for spatial operations and for packages that are variants of the list-based form (grid-array variants like CHDG, RCHA).

The key reversal: the fan-out is a **view**, derived from the list, not the ground truth from which the list is reconstructed.

## Field categories

Three categories of list field exist. The design handles all three uniformly via `list[ItemType]`, but the item types and outer containers differ:

| Category | DFN example | Python type | Item type |
|---|---|---|---|
| Static list block | `gwf-lak` packagedata | `Optional[list[ItemType]]` | `Record` dataclass |
| Repeating period block, spatial | `gwf-chd` period | `Optional[dict[int, list[ItemType]]]` | `Record` dataclass |
| Repeating period block, keystring | `gwf-oc` period | `Optional[dict[int, list[ItemType]]]` | `Union` of arm dataclasses |
| Repeating period block, flag | `gwf-sto` period | `Optional[dict[int, str]]` | `str` (or small literal union) |

## Converter impact

The `structure_array` converter is not needed for list fields. The ingress converter for a list block:

1. Parses rows from the token stream (already done by the reader)
2. Constructs `[ItemType(**row) for row in rows]`

The egress converter for a list block:

1. Iterates `[attrs.asdict(item) for item in field_value]`
2. Writes each row

No fill-value logic, no sparse COO construction, no shape resolution, no dimension inference. The `_hack_period_non_numeric` special case for OC disappears; OC period data is just a list of `OcPeriodItem` records that serialize naturally.

## Codegen impact

The code generator no longer emits, per list block:

- Per-column array attrs (e.g., `packagedata_ifno`, `strt`, `nlakeconn`, ...)
- `__block_col_maps__` ClassVar
- `_<block>` buffer attr
- `__attrs_post_init__` scatter logic
- `_get_block` / `_set_block` methods and property boilerplate

Instead it emits, per list block:

- One item class definition (or imports it from a shared module)
- One field declaration: `packagedata: Optional[list[LakPackagedataItem]] = field(...)`
- One derived-dimension property if the block has a declared dimension

A package like `gwf-lak`, which was 561 lines under the fan-out pattern, is expected to be approximately 80–100 lines.

## Rationale for `list[ItemType]` over `pd.DataFrame`

`pd.DataFrame` is the canonical representation for tabular data operations (selection, groupby, merge). It is not the right primary storage for this use case because:

1. **Union item types.** DFN `union` item fields (keystrings) cannot be cleanly represented in a DataFrame without collapsing type information into `None`/`NaN` columns. `list[UnionType]` covers both tabular (record) and non-tabular (union) cases uniformly.

2. **API for construction and mutation.** `list.append`, `item.field = value`, and list comprehensions are idiomatic Python for building and modifying a sequence of records. DataFrame row mutation (`pd.concat`, `.loc`) is more awkward for the "modeler editing a few parameters" use case.

3. **Type safety.** A typed list is statically checkable; a DataFrame is opaque to type checkers.

4. **Consistency.** One representation pattern in codegen and the converter, regardless of item type.

DataFrame is valuable as a **view** and as an **accepted input format**. It is not the primary storage.
