# On data representations

The topic of this document is data schemas, systems that work with them, and difficulties arising from data representations.

## Overview

The flopy4 MF6 parser handles representational mismatches between MODFLOW 6 DFN (Definition) files and our generated Python classes. This document describes the systematic transformation patterns implemented in `TypedTransformer` to bridge these gaps.

## The Dual Mismatch

### Primary: DFN ↔ Generated Classes

**The Core Issue**: Current DFN files conflate two separate concerns:

1. **Structure** (logical model): What variables exist, which components contain them, their types and dimensions
2. **Format** (serialization): How they appear in MF6 input files (tabular layout, record suffixes, keyword patterns)

**DFN Representation** (structure + format):
- Tabular "list input" (recarrays) with separate column definitions
- File record suffixes (e.g., `budget_filerecord`)
- Generic record types with keyword discriminators (e.g., `saverecord` + 'HEAD')

**Generated Python Classes** (structure only):
- Separate DataArrays for each conceptual field
- Clean field names without format artifacts
- Natural xarray idioms with dimensional indexing

### Derived: Grammar ↔ Spec

Because grammars are generated to **faithfully represent DFN structure** (including format), a secondary mismatch emerges:

- **Grammar**: Reflects DFN (structure + format)
- **Python Classes** (the "spec"): Reflect clean structure only

This grammar↔spec mismatch exists because of the primary DFN mismatch.

### Future Direction

We hope to eventually disentangle structure from format in DFN files, making format/serialization a separate concern. This would simplify or potentially eliminate much of the transformer's bridging work.

## Data Flow

```
DFN Files (MODFLOW 6 format definition)
    ↓
Grammar Generation (dfn2lark) ──┐
    ↓                            │ Both generated from DFN
Python Class Generation     ────┘ but with different goals
    ↓
Lark Parser (parse tree from grammar)
    ↓
TypedTransformer (bridge patterns) ← THIS DOCUMENT
    ↓                                 Bridges DFN→Class mismatch
Converter (structure into classes)
    ↓
Python Class Instances (xarray-based)
```

**Key insights**:
- **DFN files** currently conflate structure (logical model) with format (serialization details)
- **Grammar** is generated to faithfully represent DFN, including both structure and format
- **Python classes** are designed for clean structure only, using natural xarray idioms
- **TypedTransformer** bridges both mismatches: DFN↔Classes (primary) and Grammar↔Spec (derived)
- These patterns handle format-specific artifacts from DFN that don't belong in the Python class structure

## Transformation Patterns

### 1. List Input / Recarray Splitting

**Problem**: DFN defines tabular data columns as separate field definitions (format concern), but they represent a single logical recarray. We want separate arrays per field (clean structure).

**Example - WEL Package Period Block**:

DFN has separate field definitions for each column:
```
block period
name q
type double precision
shape (maxbound)

block period
name aux
type double precision
shape (maxbound, naux)

block period
name boundname
type string
shape (maxbound)
```

**Transformation pipeline**:

1. **Grammar generation**: Groups period fields into single `stress_period_data` recarray rule (see `group_period_fields()` in `grammar/filters.py:54`)
2. **Transformer**: Collects parsed records into `stress_period_data` key (`transformer.py:493`)
3. **Converter**: `structure_array()` unpacks `stress_period_data` into separate per-field arrays (`converter/ingress/structure.py:675`)

**Final Python class representation** (WEL):
```python
q: Optional[NDArray[np.float64]] = array(dims=("nper", "nodes"), ...)
aux: Optional[NDArray[np.float64]] = array(dims=("nper", "nodes"), ...)
boundname: Optional[NDArray[np.str_]] = array(dims=("nper", "nodes"), ...)
```

**Why**: DFN format concern (tabular columns) is bridged to clean structure (separate conceptual arrays).

### 2. Record Pattern: `{prefix}record` + Keyword

**Problem**: DFN defines generic record types with keyword discriminators (e.g., `saverecord`), but our Python classes expect specific field names for each variant.

**Example - OC Package**:

Grammar rule:
```lark
saverecord: "save"i word ocsetting
printrecord: "print"i word ocsetting
```

Input: `SAVE HEAD ALL`

Parse tree: `saverecord['HEAD', ocsetting_all]`

Python class expects: `save_head` field

**Transformation** (`transformer.py:582-600`):
```python
if data.endswith("record") and data not in self._flat_fields:
    if children and isinstance(children[0], str):
        prefix = data[:-6]  # Remove "record"
        keyword = children[0].lower().replace("-", "_")
        field_name = f"{prefix}_{keyword}"

        if field_name in self._flat_fields:
            return (field_name, value)
```

Result: `('save_head', 'ALL')`

**Why**: DFN uses generic format pattern with keyword discriminator; Python classes need explicit structure with named fields.

**Scope**: Affects all OC packages (CHF, GWE, GWF, GWT, OLF, PRT, SWF) plus others with similar patterns.

### 3. Grammar-Only Wrapper Unwrapping

**Problem**: Grammar generation introduces intermediate wrapper rules for organization (to reflect DFN structure), but they don't correspond to Python class fields.

**Example**:

Grammar:
```lark
ocsetting: ocsetting_all | ocsetting_first | ...
ocsetting_all: "all"i
```

Parse tree: `ocsetting[ocsetting_all]`

**Transformation** (`transformer.py:575-580`):
```python
if self._flat_fields and data not in self._flat_fields:
    if len(children) == 1:
        return children[0]  # Passthrough unwrap
```

Result: Returns `ocsetting_all` directly, bypassing the wrapper.

**Why**: Grammar wraps alternatives to reflect DFN hierarchical format; Python classes only need the terminal value (structure).

### 4. Record Suffix Stripping

**Problem**: DFN uses `*_filerecord` naming, but our Python classes use cleaner `*_file` names.

**Example**: `budget_filerecord` → `budget_file`

**Transformation** (`transformer.py:530-538`):
```python
if field is None and data.endswith("record"):
    stripped = data[:-6]
    field = self._flat_fields.get(stripped)
    if field is None and stripped.endswith("file"):
        field = self._flat_fields.get(stripped[:-4])
    if field is not None:
        data = stripped
```

**Why**: DFN `*record` suffix is a format artifact that doesn't belong in clean structural field names.

**Note**: This is a workaround pending DFN updates.

### 5. Version Suffix Stripping

**Problem**: Grammar rules include version suffixes (e.g., `tdis6`, `gwf6`) but our Python classes don't.

**Example**: `tdis6` → `tdis`

**Transformation** (`transformer.py:523-527`):
```python
if field is None and data.endswith("6"):
    stripped = data[:-1]
    field = self._flat_fields.get(stripped)
    if field is not None:
        data = stripped
```

### 6. Hyphen-Underscore Normalization

**Problem**: DFN uses hyphens, Python uses underscores.

**Example**: `field-name` → `field_name`

**Transformation** (`transformer.py:521`):
```python
if field is None and "-" in data:
    field = self._flat_fields.get(data.replace("_", "-"))
```

### 7. Union Alternative Handling

**Problem**: Union types in Python classes have alternatives that grammar represents with `_` separators.

**Example**: `ocsetting_all` where `ocsetting` is a union type in the Python class

**Transformation** (`transformer.py:501-516`):
```python
if "_" in data:
    parts = data.rsplit("_", 1)
    field_name, alternative_name = parts
    parent_field = self._flat_fields.get(field_name)
    if get_field_type(parent_field) == "union":
        if alternative_name in field_children:
            if get_field_type(alt_field) == "keyword":
                return alternative_name
            return children[0] if len(children) == 1 else children
```

### 8. Record Type Flattening

**Problem**: DFN record types have nested children that need to be collected into dicts.

**Transformation** (`transformer.py:546-564`):
```python
if field_type == "record":
    field_children = get_fields_dict(field.type)
    record_dict = {}
    for i, (child_name, _) in enumerate(non_keyword_children):
        if i < len(children):
            record_dict[child_name] = children[i]
    return data, record_dict
```

### 9. Keyword Field Handling

**Problem**: Keyword fields in DFN should become boolean flags.

**Transformation** (`transformer.py:543-544`):
```python
if field_type == "keyword":
    return data, True
```

## Implementation Location

All transformation patterns are implemented in:
- **File**: `flopy4/mf6/codec/reader/transformer.py`
- **Class**: `TypedTransformer`
- **Method**: `__default__(data, children, meta)`
- **Lines**: ~370-602

Grammar generation utilities:
- **File**: `flopy4/mf6/codec/reader/grammar/filters.py`
- **Functions**: `group_period_fields()`, `get_recarray_name()`, `is_period_list_field()`

## Design Principles

1. **Generic over specific**: Patterns use structural matching rather than hardcoded names
2. **Fail-safe**: Only activate when mismatch detected (when `data not in self._flat_fields`)
3. **Layered**: Patterns tried in order from specific to general
4. **Transparent**: Transformations preserve semantic meaning (structure) while removing format artifacts
5. **Separation of concerns**: Patterns bridge the conflation of structure+format in DFN toward clean structure in Python classes
6. **Maintainable**: Adding new packages shouldn't require transformer changes

## When to Add New Patterns

Add a new transformation pattern when:
1. A systematic format artifact in DFN needs to be removed from Python class structure
2. DFN conflates structure+format in a way that affects multiple packages
3. Grammar faithfully represents DFN (including format), but Python classes need clean structure only
4. Pattern can be expressed generically using structural matching
5. Converter alone can't bridge the gap (needs parse-stage transformation)

**Note**: As DFNs evolve to separate structure from format concerns, some patterns may become obsolete.

## Related Documents

- `transformer-dim-awareness.md`: How transformer handles xarray dimension names
- `array-converter-design.md`: How converter structures arrays from transformer output
- `grammar/README.md`: Grammar generation from DFN files

## Summary

The TypedTransformer's patterns address a dual mismatch:

1. **Primary**: DFN files conflate structure (logical model) with format (serialization)
2. **Derived**: Grammar faithfully represents DFN → Python classes represent clean structure → mismatch

These patterns systematically strip format artifacts from parsed data, preserving semantic structure while adapting representation. As DFN files evolve to separate concerns, this bridging layer may simplify or become unnecessary.

## History

**March 2026**: Added generic handlers for grammar-only wrappers and record patterns to fix OC period data loss bug, establishing systematic approach to handling structure/format conflation in DFN files.
