# DFN format inference rules

This document derives rules by which format behavior can be inferred from or validated against a v2 structural schema, and records structural annotation decisions that required corpus analysis to settle. The goal is to determine which format properties are fully derivable from structure (and need not be stored), which must remain as explicit annotations, and which pending type-system decisions determine the answer.

All rules were verified against the full DFN corpus in `modflow6/doc/mf6io/mf6ivar/dfn/`.

---

## Block-level rules

A block's input style is fully determined by the structural composition of its top-level fields. No block-name-to-style mapping is needed. Three mutually exclusive cases exist:

### 1. Keyword-value block

**Pattern:** All top-level fields are scalar or record type (`keyword`, `integer`, `double`, `string`, `record`, `union`).

**Input style:** Each field is read by `urword`. Scalar fields are preceded by their keyword name. Record fields are read as tagged keyword + optional subsequent keywords + positional values.

**Examples:** `options`, `dimensions`, `linear`, `nonlinear`, `solutiongroup` (after excluding the block-variable field — see below).

### 2. READARRAY block

**Pattern:** At least one top-level field is an array type (structural type `array`, i.e. a scalar type with a non-null `shape`).

**Input style:** Each array field is a separate READARRAY invocation. All fields in the block share this style; there are no mixed array/non-array blocks in the corpus.

**Examples:** `griddata`, DISU `connectiondata`, array-based `period` blocks in `gwf-rcha`, `gwf-evta`, and all `-g`/`-a` suffix packages.

**Sub-case — DISU `connectiondata`:** These fields have variable-length rows determined by the `iac` counter array. In v1, this was annotated with `jagged_array: str`. In v2, `jagged_array` is dropped — the Fortran parser reads these as flat 1D arrays; the ragged structure is a Python codec concern. Input style for the block remains READARRAY.

### 3. List/table block

**Pattern:** Exactly one top-level field is a list type (structural type `list`).

**Input style:** Rows are read sequentially by `urword`; each row matches the list's record or union item type.

**Examples:** `period` blocks in sparse stress packages (`gwf-chd`, `gwf-wel`, etc.), `packagedata`, `vertices`, `cell2d`, `exchangedata`, `gncdata`, `models`, `exchanges`, `packages`, `tracktimes`, `solutiongroup`.

---

## Block-variable fields

Every repeatable block (one that can appear multiple times, such as `period` or `time`) contains exactly one field with `block_variable=true`. This field (always named `iper` or equivalent) is the block instance label — it appears on the `BEGIN PERIOD n` line, not inside the block body.

In v2, block-variable fields are **not counted** when applying the block-composition rules above. They are a block-level structural mechanism (block repetition keying), not a data field within the block. Their `block_variable` marker should be dropped from the field schema in v2 and replaced with a first-class block repetition concept at the component/block level.

---

## `tagged` — fully derivable

The `tagged` attribute indicates whether a field's name appears as a literal keyword token in the input file before the field's value. It is completely derivable from structural position and field type in v2 and need not be stored.

**Derivation rules:**

1. **`keyword` type anywhere:** always tagged — the keyword IS its own token; it appears with no associated value.
2. **Top-level field in a keyword-value block:** tagged — its name precedes its value in the input file.
3. **Field inside a record (`in_record=true` in v1):** depends on type:
   - `keyword` members of a record: tagged (they are the keywords that introduce or select the record's structure)
   - All other types (`integer`, `double`, `string`, `array`): untagged — positional within the record

No exceptions to these rules were found in the corpus.

---

## `preserve_case` — drop in v2

`preserve_case=true` marks string fields where the v1 parser must not fold the value to uppercase. Two categories exist in the corpus: file path fields (`in_record=true`) and verbatim string scalars (e.g. `crs`, `list`, `tdis6`).

**Decision:** Adopt an always-preserve-case policy in v2. The v1 parser uppercases string values by default, which is an MF6-format-specific behavior with no relevance to the Python data model. In v2, all string and path values are preserved as-is. `preserve_case` is therefore a no-op annotation in v2 and is dropped from the field schema entirely.

**`path` type:** A `path` type is retained in the v2 type system (as in `spec.py`'s `path()` decorator) for semantic reasons — to distinguish file-reference strings from generic strings — not for case handling. The `crs` field remains `string` type; no edge-case annotation is needed.

**In v2:** `preserve_case` is dropped. Path fields use type `path`.

---

## `time_series` — must be explicit

`time_series=true` marks fields where the parser accepts either a numeric literal or a time-series name (a string token referencing a named TS object). It cannot be inferred from structural type alone, since many `double` fields in the same blocks do not carry this property.

**Corpus distribution:**

| v1 type | block | reader | in_record | count |
|---|---|---|---|---|
| `double precision` | `period` | `urword` | true | 96 |
| `string` | `period` | `urword` | true | 55 |
| `double precision` | `packagedata` | `urword` | true | 13 |
| `double precision` | `period` | `readarray` | — | 6 |
| `double precision` | `outlets` | `urword` | true | 4 |
| `string` | `packagedata` | `urword` | true | 1 |

The 55 `string`+`time_series=true` fields are structurally `double` — they are declared `string` in v1 to bypass numeric validation (the parser must accept a non-numeric TS name). In v2, these are retyped as `double` and `time_series=true` is retained as a format annotation.

**In v2:** `time_series: bool` on `ScalarFieldV2` (double) and `ArrayFieldV2` (double), where applicable.

---

## `layered` — must be explicit

`layered=true` marks READARRAY array fields that are provided as separate per-layer READARRAY invocations, one per layer, rather than as a single call.

The presence of a layer dimension in `shape` (e.g. `nlay`) is a necessary but not sufficient condition for `layered=true`. Example from `gwf-dis`:

| field | shape | layered |
|---|---|---|
| `top` | `(ncol, nrow)` | — |
| `botm` | `(ncol, nrow, nlay)` | `true` |
| `idomain` | `(ncol, nrow, nlay)` | `true` |
| `delr` | `(ncol)` | — |
| `delc` | `(nrow)` | — |

The `nlay` dimension in `shape` correlates with `layered=true` in `gwf-dis`, but this is not a universal rule — shapes like `(ncpl, nlay)` or `(nja)` may or may not be layered depending on context.

**In v2:** `layered: bool` on `ArrayFieldV2`. Present only in READARRAY blocks.

---

## `jagged_array` — drop in v2

`jagged_array: str` marks READARRAY fields whose row lengths vary and are determined by a named counter array (`iac`). Appears only in DISU `connectiondata` blocks (15 occurrences across `gwf-disu`, `gwe-disu`, `gwt-disu`).

**Decision:** Drop from the structural schema. The Fortran IDM (`InputParamDefinitionType` in `InputDefinition.f90`) has no `jagged_array` field. In the MF6 Fortran parser, `ja` is read as a plain flat 1D integer array of shape `NJA` — no ragedness is expressed at the parser level. The jagged presentation (converting a flat `ja` array into a variable-length list of neighbor lists) is a Python data-presentation transform, not a structural property of the data. It belongs in the codec layer, not the schema.

**In v2:** `jagged_array` is dropped. The `connectiondata` arrays remain `ArrayFieldV2` with shape `NJA`.

---

## `numeric_index` → `index` — structural, must be explicit

`numeric_index=true` marks integer fields that carry 1-based indices in the MF6 input file and should be presented 0-based to Python tools. It is a structural semantic annotation, not a format annotation — it affects how values are interpreted by the codec and codegen.

Very common: appears in ~100 fields across all model types (connection arrays, vertex references, cell-to-cell links, package-specific index columns).

**v2 design — primary key / foreign key semantics:**

The v1 `numeric_index` annotation is replaced by two cooperating mechanisms:

1. **`ListFieldV2.key: str | None`** — names the column within a list's record type that serves as the primary key (a unique, 1-based row identifier). The named column must itself have `index=True` on its `ScalarFieldV2`. A Pydantic `model_validator` enforces this consistency at schema load time. Example: `packagedata` has `key="ifno"` where `ifno` is a 1-based feature number.

2. **`ScalarFieldV2.index: bool = False`** — marks an integer scalar as a 1-based index. Set to `True` on PK columns (the column named by `ListFieldV2.key`) and on FK columns that reference PKs in other lists (e.g. a connection table's `ifno` column referencing `packagedata.ifno`). The codec applies 0-based conversion to all fields where `index=True`.

This design makes primary/foreign key relationships first-class and explicit, replacing the flat `numeric_index` flag with a relational structure that can be validated and queried.

**`utl-obs` `id`/`id2` fields:** These accept either a boundary name (string) or a cellid (integer, 1-based). In v2, they are modeled as `UnionFieldV2` with two arms: a `string` arm for boundary names and an `integer` arm with `index=True` for cellid values. No special `numeric_index` annotation is needed.

**`block_variable` / `iper` fields:** The `iper` block label (e.g. `BEGIN PERIOD 5`) is a 1-based period number, but it is not a field in the block body — it is the key of a first-class block repetition mechanism. It does not need an `index` annotation; the block repetition model handles its semantics directly.

**In v2:** `index: bool = False` on `ScalarFieldV2` (integer). `key: str | None` on `ListFieldV2` with a `model_validator` that asserts the named column exists and has `index=True`.

---

## `valid` — structural, must be explicit

`valid` lists the permitted token values for a `string` field (an enumeration constraint). Appears on 15 fields across the corpus. Examples: advection scheme (`central`, `upstream`, `tvd`), sorption type (`linear`, `freundlich`, `langmuir`), solution type (`ims6`, `ems6`).

This is a structural constraint on allowed values. Not inferrable.

An empty `valid` (no values listed) appears on `block_variable` fields (`iper`, etc.) and is a v1 formatting artifact — not a constraint. Empty `valid` should be treated as absent.

**In v2:** `valid: list[str] | None` on `ScalarFieldV2` (string).

---

## `repeating` — must be explicit

`repeating=true` marks a field that may appear multiple times in a block, with each occurrence appended to an accumulated value. Active in only one field in the current corpus:

- `utl-tas.dfn` → `tas_array` (time block, READARRAY, `just_data=true`) — time-array series data repeated once per TAS name

Two additional occurrences in `prt-oc.dfn` and `prt-prp.dfn` are `removed 6.6.0`.

Not inferrable. **In v2:** `repeating: bool` on relevant field types.

---

## `just_data` — drop in v2

`just_data=true` appears exactly once in the corpus: `utl-tas.dfn` `tas_array`. It marks a field whose value occupies the entire block body with no keyword prefix — pure data, no structural framing. This is the only occurrence and is co-located with `repeating=true` on the same field.

Rather than carrying `just_data` as a general field attribute in v2, this case should be handled by the structural description of the block itself (a single array field with no keyword, read by READARRAY). The attribute can be dropped from the schema.

---

## `block_variable` — drop in v2

`block_variable=true` marks the integer field that labels a repeated block instance (always `iper` or equivalent — the number on the `BEGIN PERIOD n` line). Present in virtually every repeatable block in the corpus.

In v2, block repetition should be a first-class concept at the block/component level. The block-variable field is not a data variable — it is a block-level structural mechanism. Dropping it from the field schema and modeling block repetition explicitly (e.g., a `repeatable: bool` or `key_field: str` attribute on the block) is cleaner.

---

## Cross-component references

Two distinct kinds of cross-component reference exist in the corpus.

### 1. Dimension references

A scalar integer field defined in one component is referenced by name in the `shape` expression of an array field in the same or another component. Examples: `nlay`, `nrow`, `ncol` (grid packages), `nper` (`tdis`), `nodes`, `nja`, `nvert`, `ncpl`, `naux`.

**Decision:** Add `dimension: bool = False` to `ScalarFieldV2` (integer). Shape expressions may only reference `dimension=True` fields; a reference to any other field is a schema validation error. This makes explicit what was an implicit contract in v1 and enables shape validation at schema load time.

Fields in `dimensions` blocks are the primary candidates, but some `options` scalars also qualify (e.g., `naux`). `maxbound` does not — it is a formatting artifact dropped from the structural schema.

### 2. Index/FK references

An integer column in one list identifies a row in another. Within-component cross-block FKs are covered by `ListFieldV2.key` + `ScalarFieldV2.index`. Cross-component integer FKs are rare in the corpus; `index=True` on both the PK and FK columns is sufficient for the codec. A `DfnSpec`-level FK edge index is deferred.

### Why not unify?

Both cross component boundaries but serve fundamentally different purposes:

| | Dimension reference | FK reference |
|---|---|---|
| Target | scalar value | row identity |
| Consumer | shape expression (array bound) | column value (row lookup) |
| Resolved | once, at component init | per-row, at data access |

A unified mechanism requires a `kind` discriminator that immediately branches into different code paths — abstraction without payoff.

---

## `block` — drop from field schema in v2

In v1, `Field.block: str` places a field into a named block as an inline attribute. In v2, block membership is expressed structurally: fields are nested inside block objects in the schema hierarchy, so `block` on a field is redundant. In the TOML serialization format, block membership is expressed by table path (`[gwf-dis.griddata.botm]`), not an inline attribute.

**In v2:** `block` is dropped from the field schema. It is a loader/serializer concern, not a field attribute.

---

## `netcdf` — drop from structural schema

`netcdf` on the v1 `Field` base class marks fields that can appear in NetCDF output. This is an output-format annotation, not a structural property. The Fortran IDM (`InputParamDefinitionType`) has no `netcdf` field. NetCDF output spec is a separate concern from the structural input schema.

**In v2:** `netcdf` is dropped from the field schema.

---

## Summary table

| v1 attribute | v2 fate | Reason |
|---|---|---|
| `tagged` | **derivable, drop** | Determined by block type + field type + position |
| `preserve_case` | **drop** | Always-preserve-case policy; `path` type retained for semantics only |
| `time_series` | **explicit** (`ScalarFieldV2`, `ArrayFieldV2`) | Not inferrable; many `double` fields lack it |
| `layered` | **explicit** (`ArrayFieldV2`) | Not inferrable from shape alone |
| `jagged_array` | **drop** | Not in Fortran IDM; `ja` is flat 1D array; jagged presentation is a Python codec concern |
| `numeric_index` | **replaced** → `ScalarFieldV2.index` + `ListFieldV2.key` | PK/FK semantics; `model_validator` enforces key consistency |
| `valid` | **explicit** (`ScalarFieldV2` string) | Structural constraint; not inferrable |
| `repeating` | **explicit** | Not inferrable; behavior is file-format-level |
| `just_data` | **drop** | Single occurrence; handled structurally |
| `block_variable` | **drop** | Replace with first-class block repetition at block level |
| `block` | **drop** | Field position in block hierarchy makes inline attribute redundant |
| `netcdf` | **drop** | Output-format annotation; not in Fortran IDM; not a structural property |

**New in v2:**

| v2 attribute | Field class | Purpose |
|---|---|---|
| `dimension: bool` | `ScalarFieldV2` (integer) | Marks valid targets for shape expressions; enables shape validation |
| `index: bool` | `ScalarFieldV2` (integer) | Marks 1-based indices; codec applies 0-based conversion |
| `key: str \| None` | `ListFieldV2` | Names the PK column; `model_validator` asserts column exists and has `index=True` |
