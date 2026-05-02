# DFN schema formalization plan

This document captures the current state of the DFN specification and outlines a plan to formalize it.

## Background

The MODFLOW 6 definition file ("DFN") format is a simple text format described in [natural language](https://modflow6.readthedocs.io/en/latest/_dev/dfn.html). The schema is implicit in this description and in the content of the existing DFN files, which must be read in the context of the MF6IO documentation (and vice versa).

**v1** is the existing schema. Its content is faithfully parsed from DFN files, with no alterations. Currently v1 is consumed by tooling in the MF6 repository.

**v1.1** is a slightly normalized version generated from v1 DFN files by `modflow_devtools.dfn`. It parses bools, resolves `common.dfn` substitutions, drops some attributes, and does some structural transforms. Flopy 3.x codegen consumes v1.1, serializing to/from TOML. v1.1 only exists due to poor planning (WPB) and will be retired with devtools v2. Flopy 3.x should be altered to consume v1 or v2 directly.

**v2+** is the target. A more substantially transformed schema version has evolved as flopy 4.x development proceeds, facilitated by `modflow_devtools.dfns` (plural; distinct from the old `dfn` module). This document makes the v2 schema explicit and formalizes it. The newly formalized, versioned schema can be published with devtools 2.x, then become the foundation of flopy 4.x. MF6 tooling will later begin to consume v2 schema too.

## Principles

**Schema versioning.** Allows adding/removing from the schema in a disciplined way.

**Schema validation.** Allows checking if a given component specification conforms.

**Separation of concerns.** A fundamental distinction is between schema and serialization format. The content of DFN files could be written to TOML, YAML, or JSON. That content (the schema) describes the data's shape and characteristics: which components exist, what fields they have, how they are connected. In other words, structural information, defining the valid structure of each simulation component. Choice of data interchange format is a separate issue.

Another distinction is between simulation structure and MF6 input file format. Current DFN files carry both structural information and input file format information. A clear example of a pure format artifact is `maxbound` in v1 sparse stress period blocks: its sole purpose is to tell the MF6 block parser how many array slots to allocate. It carries no structural information and is dropped in v2. Where format information cannot be derived unambiguously from the structural spec, it is expressed as a separate annotation layer specifically scoped to MF6 input format. The core structural schema should be free of pure format artifacts.

Note: the sparse list representation of period block data (rows of `(cellid, value...)`) is **not** a format artifact — it is structurally meaningful. A sparse list covers an arbitrary subset of grid cells and permits multiple entries per cell (e.g., multiple wells at the same node), properties a dense grid-aligned array cannot express. The list vs. array distinction at the period block level is therefore preserved in v2; it is part of what structurally distinguishes component variants such as `gwf-wel` (sparse list) and `gwf-welg` (grid array). See "Format variants".

**1 DFN file per input component.** DFN files do not currently map 1-1 to hydrologic processes. A DFN file describes a single way of representing a process, not necessarily the only one. Where multiple DFN files represent the same process in different formats (e.g. `gwf-wel`/`gwf-welg`, `gwf-rch`/`gwf-rcha`), the relationship should be explicit in the schema. Unification can be deferred to a future schema version.

**Explicit parent-child relationships.** Parent-child relationships are intrinsic to a component's identity and should be explicitly defined. A component's valid parents range from fully constrained (a single named component type, e.g. `gwf-chd` always under `gwf-nam`) to loosely constrained (any component of a given semantic type, e.g. any package) to unconstrained (any parent). Components with looser parent constraints are historically called "subpackages". All relationships are resolved at simulation instantiation time; the schema states the constraint, not the instance.

## Design

### Fields

The existing design attempts to shoehorn all field types into a single field definition. This is error-prone as invalid field definitions can be represented.

Refactor `modflow_devtools.dfns.schema.FieldV2` into a Pydantic discriminated union of the concrete field types:

```python
Field = Annotated[
    ScalarField | ArrayField | RecordField | ListField | UnionField,
    PydanticField(discriminator="type")
]
```

#### V1 → V2 type mapping

| v1 type | v2 type | Notes |
|---|---|---|
| `double precision` | `double` | Renamed. |
| `recarray` | `list` | Becomes `ListFieldV2` with typed `item`. |
| `keystring` | `union` | Becomes `UnionFieldV2` with named `arms`. |
| `record` | `record` | Becomes `RecordFieldV2` with typed `fields`. |
| `keyword`, `integer`, `string`, `path` | same | Becomes `ScalarFieldV2`. |
| `string` + `time_series=true` | `double` | v1 used `string` to bypass numeric validation while accepting TS names; structurally `double` in v2 with `time_series=true` in the format layer. |
| scalar with non-null `shape` | `array` | Becomes `ArrayFieldV2`. |

V1 uses flat `in_record=True` top-level fields to represent structural nesting. V2 replaces this with explicit nesting: record columns go into `RecordFieldV2.fields`, union arms into `UnionFieldV2.arms`, and list item columns into `ListFieldV2.item`. The `in_record` attribute is dropped.

#### Field types

##### Scalar

Types: `keyword`, `integer`, `double`, `string`, `path`.

Attributes (beyond base):
- `dimension: bool = False`: Marks a valid target for shape expressions; enables shape validation at schema load time. Fields in `dimensions` blocks are primary candidates, but some `options` scalars also qualify (e.g. `naux`). `maxbound` does NOT get `dimension=True`, it is a formatting concern to be dropped from the structural schema.
- `time_series: bool = False`: Marks fields where the parser accepts either a numeric literal or a time-series name (referencing a `utl-ts` object). Not inferrable from structural type. Also appears on `ArrayFieldV2` (where it references a `utl-tas` object instead). Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.
- `valid: list[str] | None`: Permitted values for `string` fields (enumeration constraint). Not inferrable. Empty `valid` (artifact of v1 `block_variable` fields) is treated as absent.
- `pk: bool = False`: Marks this scalar as the primary key of its containing list's item record. Valid only on integer or string scalars that are columns in a `ListFieldV2` item record. Exactly one column per list item may be marked pk.
- `fk: str | None = None`: Marks this scalar as a foreign key. Valid only on integer or string scalars that are columns in a `ListFieldV2` item record. Three forms: (1) hierarchical path `"block.field"` or `"component.block.field"` — fully static, used without `fk_ref`; (2) sentinel `"node"` — grid cell reference, used without `fk_ref`; (3) bare block name (e.g., `"packagedata"`) — used together with `fk_ref` to name the block within the runtime-resolved target component, leaving only the pk field to be discovered. See "Primary/foreign keys".
- `fk_ref: str | None = None`: For FKs whose target component is only known at runtime. Names a sibling string field whose value identifies the target component. May be set alone (block within target also unknown) or together with `fk` as a bare block name (block known, component not). See "Primary/foreign keys".

##### Array

Type: `array`

Attributes (beyond base):
- `shape: list[str]`: The array's shape, defined by reference to dimension scalars.
- `time_series: bool = False`: Marks fields where the READARRAY invocation may be replaced by a TAS name referencing a `utl-tas` time-array series object. At any model time, the TAS provides an interpolated grid-shaped array. Distinct from the scalar case: references `utl-tas`, not `utl-ts`. Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.
- `repeat: str | None = None`: Names the field (within the same component) whose runtime length determines how many times this field is read sequentially within a single block occurrence, with each reading appended to an accumulated sequence. Non-null implies repeating. See `repeat` section below.

##### Record

Type: `record`

Attributes (beyond base):
- `fields: dict[str, FieldV2]`: named columns, required.

##### List

Type: `list`

Attributes (beyond base):
- `item: RecordField | UnionField`: the item type, required.

##### Union

Type: `union`

Attributes (beyond base):
- `arms: dict[str, FieldV2]`: named alternatives, required.

#### Field attributes

Some v1 attributes need to remain, some can be dropped.

| v1 attribute | v2 fate | Reason | Notes |
|---|---|---|---|
| `tagged` | keep | Can't reliably infer | |
| `preserve_case` | undecided | Needed for non-path case-sensitive strings (e.g. `crs`); may survive in v2 | |
| `time_series` | keep for `ScalarFieldV2`, `ArrayFieldV2` | Not inferrable; many `double` fields in the same blocks lack it | |
| `layered` | drop (derivable) | Exactly correlated with `nlay` in shape for readarray fields; zero corpus exceptions | |
| `jagged_array` | drop | Not in Fortran IDM; `ja` is a flat 1D array in MF6; raggedness is a codec concern | |
| `numeric_index` | replace with `ScalarFieldV2.pk` / `.fk` / `.fk_ref` | Explicit PK/FK semantics; `model_validator` enforces consistency | See "Primary/foreign keys" |
| `valid` | keep for string `ScalarFieldV2` | Structural constraint; not inferrable | |
| `repeating` | replace with `repeat: str | None` | Not inferrable; explicit count reference unifies utl-tas and RCHA/EVTA aux patterns | |
| `just_data` | drop | Single occurrence (`utl-tas`); structurally inferrable | |
| `block_variable` | drop | Replace with first-class block repetition at block/component level | |
| `block` | drop | Field position in block hierarchy makes inline attribute redundant; codec concern | |
| `netcdf` | keep until MF6 IDM support | not in Fortran IDM, not a structural property; required until netcdf is fully supported in MF6 IDM | drop when IDM support is complete |
| `reader` | **drop** | Infer from block type | |

#### `preserve_case`

The MF6 parser converts strings to uppercase by default. The `preserve_case` flag in v1 indicates that a string field should not be uppercased. The main use case is file paths, which will have a distinct field type in, but there are other case-sensitive strings (e.g. CRS), so we may still need the attribute in v2.

#### `jagged_array`

`jagged_array: str` marks READARRAY fields whose row lengths vary and are determined by a named counter array (`iac`). Appears only in DISU `connectiondata` blocks (15 occurrences across `gwf-disu`, `gwe-disu`, `gwt-disu`).

**Decision:** Drop from the structural schema. The Fortran IDM (`InputParamDefinitionType` in `InputDefinition.f90`) has no `jagged_array` field. In the MF6 Fortran parser, `ja` is read as a plain flat 1D integer array of shape `NJA` — no ragedness is expressed at the parser level. The jagged presentation is a Python data-presentation transform belonging in the codec layer, not the schema. The `connectiondata` arrays remain `ArrayFieldV2` with shape `NJA`.

#### `numeric_index`

`numeric_index=true` in v1 marks integer fields that carry 1-based indices and should be presented 0-based to Python tools. Very common: ~100 fields across all model types.

**Decision:** Replace with explicit PK/FK semantics via `ScalarFieldV2.pk`, `ScalarFieldV2.fk`, and `ScalarFieldV2.fk_ref` (see "Scalar" field type and "Primary/foreign keys" sections). Valid on integer and string scalars that are columns in a `ListFieldV2` item record.

**`utl-obs` `id`/`id2` fields:** Each accepts either a boundary name (string) or a cellid (integer). Both arms of the `UnionFieldV2` are FKs: the string arm is a string FK to a named boundary in a package resolved at runtime via `obstype` (`fk_ref="obstype"`); the integer arm is an integer FK to the parent model's spatial discretization (`fk_ref` as appropriate). No residual `index` attribute is needed.

**`iper` block labels:** Period numbers, but not a data field in the block body — the block repetition model handles their semantics directly. No pk/fk annotation.

#### `tagged`

The `tagged` attribute currently indicates whether a field, usually a record subfield, must be preceded by its keyword name. This cannot be dropped yet as it cannot consistently be derived from structural position and field type.

Two cases can be reliably derived:

1. **`keyword` anywhere:** always tagged — the keyword IS its own token; it appears with no associated value.
2. **top-level field in a keyword-value block:** tagged — its name precedes its value in the input file.

Fields inside records, however, are inconsistent and cannot be reliably derived. For example, GWF-OC's `formatrecord`. Also, `tagged` does not always appear where it should, e.g. GWF-NPF's `rewet_record`.

#### `time_series`

`time_series=true` in v1 marks fields where the parser accepts either a numeric literal or a time-varying external reference. Not inferrable from structural type. The attribute is used in two structurally distinct cases that are semantically analogous but mechanistically different:

**Scalar case (urword fields):** The field accepts either a numeric literal or a TS name referencing a `utl-ts` time series object. At any model time, the TS provides a single interpolated scalar value. The MF6 Fortran parser reads all tokens via `urword` as raw strings. For `double precision` fields, it immediately converts the string to a real number — passing a TS name string would be a fatal error. The v1 workaround was to declare these fields as `string` type, bypassing the numeric conversion; higher-level code then checks whether the string is a TS name or parseable as a number. These 55 fields are structurally `double` and are retyped as such in v2, with `time_series=True` retained to signal to the codec that TS names are also valid.

**Array case (readarray fields):** The field accepts either inline READARRAY data (a numeric array provided in the input file using READARRAY syntax: `CONSTANT`, `INTERNAL`, binary file reference, etc.) or a TAS name referencing a `utl-tas` time-array series object. At any model time, the TAS provides an interpolated grid-shaped array. Six fields in the corpus take this form: `gwf-rcha.recharge`, `gwf-rcha.aux`, `gwf-evta.rate`, `gwf-evta.aux`, `utl-spca.concentration`, `utl-spca.temperature`.

The two cases reference fundamentally different objects: TS (`utl-ts`) is a scalar-valued time function; TAS (`utl-tas`) is an array-valued time function.

**Schema constraint:** `ArrayFieldV2.time_series=True` requires `nlay` in shape, since utl-tas currently only supports layered arrays. A Pydantic `model_validator` enforces this at schema load time. The constraint may be relaxed in a future MF6 version if TAS support is extended to non-layered arrays. The attribute name `time_series` is kept for both in v2 because the name is established, and the two cases apply to disjoint field types (`ScalarFieldV2` vs `ArrayFieldV2`), so no ambiguity arises. The distinction is documented here rather than in the attribute name.

Corpus distribution:

| v1 type | block | reader | in_record | count |
|---|---|---|---|---|
| `double precision` | `period` | `urword` | true | 96 |
| `string` | `period` | `urword` | true | 55 |
| `double precision` | `packagedata` | `urword` | true | 13 |
| `double precision` | `period` | `readarray` | — | 6 |
| `double precision` | `outlets` | `urword` | true | 4 |
| `string` | `packagedata` | `urword` | true | 1 |

**In v2:** `time_series: bool` on `ScalarFieldV2` (double; references `utl-ts`) and `ArrayFieldV2` (double; references `utl-tas`).

#### `layered`

`layered=true` marks READARRAY array fields that are read as separate per-layer READARRAY invocations (one per layer) rather than a single call. The MF6 READARRAY routine uses the `LAYERED` keyword to signal this mode.

Example from `gwf-dis`:

| field | shape | layered |
|---|---|---|
| `top` | `(ncol, nrow)` | — |
| `botm` | `(ncol, nrow, nlay)` | `true` |
| `idomain` | `(ncol, nrow, nlay)` | `true` |
| `delr` | `(ncol)` | — |
| `delc` | `(nrow)` | — |

**Decision:** Drop from v2 — fully derivable from shape. A corpus-wide search confirms that every readarray field whose shape contains `nlay` has `layered=true`, and no readarray field with `nlay` in shape is non-layered (zero exceptions). The rule is logically sound: the MF6 READARRAY parser has no path to read a multi-layer array in a single call; the `LAYERED` keyword is mandatory when `nlay` is a dimension. Rule: `ArrayFieldV2` is layered iff `nlay` appears in its shape expression.

#### `valid`

`valid` lists permitted token values for a `string` field (enumeration constraint). Appears on 15 fields in the corpus. Examples: advection scheme (`central`, `upstream`, `tvd`), sorption type (`linear`, `freundlich`, `langmuir`), solution type (`ims6`, `ems6`).

Structural constraint — not inferrable. Empty `valid` (v1 artifact on `block_variable` fields) is treated as absent.

**In v2:** `valid: list[str] | None` on `ScalarFieldV2` (string).

#### `repeat`

`repeat: str | None` replaces v1's `repeating: bool`. When non-null, it names the field (within the same component, potentially in a different block) whose runtime length determines how many times the annotated field is read sequentially within a single block occurrence. Each reading is appended to an accumulated sequence.

Two patterns in the corpus share this structure — N sequential READARRAY calls per block occurrence, where N is the length of a declared list field:

- **`utl-tas.tas_array`** (`time` block, READARRAY): read once per named TAS per labeled `time` block. `repeat="time_series_name"`, where `time_series_name` is declared in the `attributes` block with `shape (any1d)`.
- **`gwf-rcha.aux` / `gwf-evta.aux`** (`period` block, READARRAY): read once per declared auxiliary variable per labeled `period` block. `repeat="auxiliary"`, where `auxiliary` is declared in the `options` block with `shape (naux)`.

The RCHA/EVTA `aux` fields carry no `repeating` annotation in v1 — the N-repetition behavior is implicit in the Fortran code, which loops explicitly over `naux`. V2 makes this explicit and consistent with utl-tas.

In both cases `repeat` names the declared list or array field whose length is the count, not a scalar dimension variable (e.g. `naux`). These are the same value; the field reference is used because it identifies a declared schema entity.

Two additional occurrences of `repeating=true` in `prt-oc.dfn` and `prt-prp.dfn` are `removed 6.6.0`.

**Codec mechanism:** the codec reads the referenced field to determine N, then reads the repeating field exactly N times, appending each result. This replaces the v1 "read until end of block" mechanism for `utl-tas` with an explicit pre-declared count.

#### `just_data`

`just_data=true` appears exactly once: `utl-tas.dfn` `tas_array`. It marks a field whose value occupies the entire block body with no keyword prefix — the `begin time X` line serves as the label, and the body is just raw READARRAY data with no field keyword.

**Dropped in v2.** The case is handled structurally by the `Block` class: a labeled block (`label="time_from_model_start"`) whose only body field is an unlabeled READARRAY field. The absence of a keyword prefix is derivable from structure (single body field, `tagged=false`, READARRAY reader) without an explicit attribute.

#### `block`

In v1, `Field.block: str` places a field into a named block as an inline attribute. In v2, block membership is expressed structurally — fields are nested inside block objects in the schema hierarchy. In the TOML serialization format, block membership is expressed by table path (e.g. `[gwf-dis.griddata.botm]`), not an inline attribute. **Dropped from field schema in v2.**

#### `block_variable`

In v2, drop `block_variable` and replace with a first-class block repetition concept at the component/block level.

#### `netcdf`

`netcdf` on the v1 `Field` base class marks fields that can appear in NetCDF output. This is an output-format annotation, not a structural property. The Fortran IDM (`InputParamDefinitionType`) has no `netcdf` field.

**Decision:** Keep in v2 until NetCDF is fully supported in the MF6 IDM. Once IDM support is complete and the attribute is no longer needed to bridge the gap, drop it.

### Blocks

A block is group of related fields; essentially a product type. Record fields are also product types; the distinction is that records occupy a single line in MF6 input files, while blocks are multiline constructs delimited by headers, e.g.

```
begin <block name>
   field1 value
   field2 value
end <block name>
```

#### Block types

A block's input style is determined by structural composition of its top-level fields. No block-name-to-style mapping is needed.

Three block types can be identified:

- keyword-value
- readarray
- list/table

READARRAY blocks and keyword-value blocks look superficially similar (both have a keyword token preceding a value), but the reader mechanism is entirely different. In keyword-value blocks, each field's value is read by `urword` — a single token on the same line. In READARRAY blocks, the value is read by the READARRAY routine, which consumes one or more subsequent lines, supports `CONSTANT`/`INTERNAL`/binary-file invocations, and handles layered arrays via multiple sequential calls. The codec derives which routine to invoke from the field types in the block — because there are no mixed array/non-array blocks in the corpus, the inference is unambiguous.

##### Keyword-value block

**Pattern:** All top-level fields are scalar or record type (`keyword`, `integer`, `double`, `string`, `path`, `record`, `union`).

**Input style:** Each field is read by `urword`. Scalar fields are preceded by their keyword name. Record fields are read as tagged keyword + optional subsequent keywords + positional values.

**Examples:** `options`, `dimensions`, `linear`, `nonlinear`, `solutiongroup` (after excluding the block-variable field — see below).

##### READARRAY block

**Pattern:** At least one top-level field is an array type (structural type `array`, i.e. a scalar type with a non-null `shape`).

**Input style:** Each array field is a separate READARRAY invocation. All fields in the block share this style; there are no mixed array/non-array blocks in the corpus.

**Examples:** `griddata`, DISU `connectiondata`, array-based `period` blocks in `gwf-rcha`, `gwf-evta`, and all `-g`/`-a` suffix packages.

**Sub-case — DISU `connectiondata`:** Fields have variable-length rows determined by the `iac` counter array. In v1, this was annotated `jagged_array: str`. In v2, `jagged_array` is dropped — the Fortran parser reads these as flat 1D arrays; the ragged structure is a Python codec concern. Input style for the block remains READARRAY.

##### List/table block

**Pattern:** Exactly one top-level field is a list (recarray) type

**Input style:** Rows are read sequentially by `urword`; each row matches the list's record or union item type.

**Examples:** `period` blocks in sparse stress packages (`gwf-chd`, `gwf-wel`, etc.), `packagedata`, `vertices`, `cell2d`, `exchangedata`, `gncdata`, `models`, `exchanges`, `packages`, `tracktimes`, `solutiongroup`.

V1 sparse stress period blocks contain a single `recarray` with a `cellid` column followed by per-variable value columns (e.g., `q` for wells). V2 preserves this as a `ListField` whose item record contains `cellid` (a FK to the parent model's spatial discretization) and one or more value columns. `maxbound` is dropped — it is a parser allocation hint with no structural meaning. The list-based representation is correct and natural: it specifies stress on an arbitrary spatial subset of the grid and supports multiple entries per cell (e.g., two wells in the same node). These properties cannot be expressed by a dense grid-aligned array. Array-based period blocks (`gwf-rcha`, `gwf-evta`, `-g` suffix packages) remain `ArrayField` — they are structurally distinct from sparse list blocks, not a transformed version of the same thing.

**Python representation:** Sparse list-based period data is represented as a `pandas.DataFrame` (or `geopandas.GeoDataFrame` where spatial operations are relevant), one row per entry. This is more ergonomic than an xarray `DataArray` for sparse, irregularly distributed features and is consistent with the list structure in the schema.

The period block repeats to support time-varying data: v1 DFNs define period blocks with an index field with `block_variable=true`, typically called `iper`. This block index (perhaps better thought of as an arbitrary but unique label) appears on the `BEGIN PERIOD n` line, not inside the block body:

```
begin period 1
   ...
end period 1
```

#### Block class

Blocks can be first-class objects in v2.

```python
class Block(BaseModel):
    name: str
    fields: dict[str, FieldV2]
    labeled: bool = False
    optional: bool = False
```

If `labeled`, the block may be repeated. Each repetition must have a unique label. The label must follow the `begin`/`end` delimiters. This replaces the `block_variable` attribute used in v1. In v2 the label takes the place of the explicit block variables:

- stress package `period.iper`: period number
- `utl-tas.time.time_from_model_start`: simulation time
- `utl-obs.continuous.output`: output file record

## Component-level attributes

Component-level pieces of information include:

- whether multiple instances of the component are allowed

### Multi-packages

Components of which multiple instances are allowed are called "multi-packages", and currently indicated by a special comment line at the top of the DFN:

```
# flopy multi-package
```

In v2, components can have a top-level attribute `multi` or similar.

## Cross-cutting constraints

Field and component definitions are not entirely self-contained. Some fields may refer to other fields, in the same component or in another. Likewise, component definitions may refer to other component definitions. Several kinds of cross-cutting constraints exist:

- array dimensions
- primary/foreign keys
- parent-child relations
- solution compatibility
- input format variants

### Array dimensions

A scalar integer field defined in one component can be referenced by name in the `shape` expression of an array field in the same or another component.

Examples: `nlay`, `nrow`, `ncol`, `nper`, `nodes`, `nja`, `nvert`, `ncpl`, `naux`.

#### V2

Shape expressions may only reference `dimension=True` fields; a reference to any other field becomes a schema validation error.

### Primary/foreign keys

Sometimes a column in one list identifies a row in another — or in a grid cell. This is modelled as a primary key (PK) / foreign key (FK) relation. PK/FK attributes are valid on integer and string scalar fields that are columns in a `ListFieldV2` item record.

#### V1

In v1 this is indicated by `numeric_index`. This attribute is overloaded as both primary and foreign key:

- PK: e.g. `packagedata.lakeno`, `packagedata.rno`, `vertices.iv`, `cell2d.icell2d`
- FK: e.g. `period.lakeno`/`rno`, `connectiondata.iconn`
- String usage: `utl-obs.continuous.id1`/`id2` also carry `numeric_index`, even though they are string fields; the relationship is PK/FK-like and should be marked in v2.

The `ja` array in DISU also carries `numeric_index`, but as a flat array whose elements encode grid topology positionally (not a distinct index column into a DFN list), this is unnecessary in v2.

#### V2

Three attributes on `ScalarFieldV2` encode PK/FK semantics — `pk`, `fk`, and `fk_ref` (described in full under "Scalar" above). A `model_validator` enforces type and structural constraints at schema load time.

#### `fk` path format

`fk` takes one of three forms:

- **Hierarchical path** — `"block.field"` for within-component references, `"component.block.field"` for cross-component references where the target is statically known. Used without `fk_ref`.
- **`"node"` sentinel** — indicates a grid cell reference. The target is the parent model's spatial discretization, resolved at runtime. Used without `fk_ref`, wherever a field carries a cellid (e.g., `cellid` columns in sparse stress period blocks, the integer arm of `utl-obs.continuous.id`).
- **Bare block name** (e.g., `"packagedata"`) — used together with `fk_ref`. `fk_ref` resolves the target component at runtime; `fk` names the block within it. The codec then finds the unique `pk=True` field in that block. A bare block name contains no dot and is not `"node"`.

#### `fk_ref` resolution

`fk_ref` names a sibling string field whose runtime value identifies the target component. Two sub-cases:

- **With `fk`** (bare block name): the codec resolves the component from `fk_ref`, then finds the unique `pk=True` field in the block named by `fk`. This is fully explicit and preferred when the target block is known. For all current corpus cases where `fk_ref` is used with a polymorphic integer pk target (SFR, MAW, UZF, LAK via `gwf-mvr`), the block is `packagedata`; `fk="packagedata"` should therefore always be set alongside `fk_ref` for these cases.
- **Without `fk`**: the target block is also unknown at schema time. The codec must resolve case-by-case. This mode is unavoidable when the target block itself varies by component (e.g., the `utl-obs.continuous.id` string arm, where the target is a boundary name field whose block varies by package type). Document these cases explicitly rather than relying on a generic convention.

#### Examples

| Field | `pk` | `fk` | `fk_ref` | Notes |
|---|---|---|---|---|
| `gwf-sfr.packagedata.rno` | `True` | — | — | PK of the reach list |
| `gwf-sfr.connectiondata.ic` | — | `"packagedata.rno"` | — | within-component |
| `gwf-sfr.period.rno` | — | `"packagedata.rno"` | — | within-component |
| `gwf-mvr.packages.pname` | `True` | — | — | string PK of the package list |
| `gwf-mvr.period.pname1` | — | `"packages.pname"` | — | string FK, within-component |
| `gwf-mvr.period.id1` | — | `"packagedata"` | `"pname1"` | component resolved from pname1; codec finds unique pk in packagedata |
| `utl-obs.continuous.id` (string arm) | — | — | `"obstype"` | **Open:** target block varies by package type; codec must handle case-by-case |
| `utl-obs.continuous.id` (integer arm) | — | `"node"` | — | grid cell reference |
| `gwf-wel.period.cellid` | — | `"node"` | — | grid cell reference |

### Parent/child relations

#### V1

In v1 DFNs, parent-child relationships are implicit or encoded in special comment lines. Fixed relationships are implicit in component naming (e.g., `gwf-*` is always a child of a GWF model); subpackage relationships are declared via `# flopy subpackage` / `# flopy parent_name_type` comment pairs.

#### V2

In v2, all parent relationships can be made explicit via `Dfn.parent: str | list[str] | None`:

- `None` — no parent; the component is simulation-level.
- `"*"` — matches any parent component type.
- A string or list of strings — declares the set of valid parent component types. Entries are either:
  - **Type names** (`"model"`, `"package"`) — matches any component of that semantic type. Type names never contain a hyphen.
  - **Component IDs** (`"gwf-sfr"`, `"gwf-nam"`) — matches only that specific component type. Component IDs always contain a hyphen.
  - In a mixed list, a type name subsumes any named component of the same type: `["gwf-sfr", "package"]` reduces to `["package"]` since `gwf-sfr` is a package.

**Examples (mapped from v1 comment encoding):**

| v1 encoding | v2 `parent` |
|---|---|
| _(implicit from `gwf-*` naming convention)_ | `"gwf-nam"` |
| `parent_name_type parent_package MFPackage` | `"package"` |
| `parent_name_type parent_model MFModel` | `"model"` |
| _(obs, attached to model or package)_ | `["model", "package"]` |
| _(subpackage restricted to specific components)_ | `["gwf-sfr", "gwf-maw"]` |
| _(attached to any parent)_ | `"*"` |

### Solution compatibility

#### V1

Solver components are called "solution packages", and currently indicated by a comment at the top of the DFN, e.g.:

```
# flopy solution_package ims *
```

The right-most two tokens are respectively the solution package abbreviation, and the model types the package may be used to solve. In v1 both IMS and EMS currently use "*", meaning the v1 spec does not reflect existing constraints about which solutions may be used with which models.

#### V2

In v2 a top-level component attribute should reflect constraints: that numerical models must be solved by IMS and explicit models by EMS. We can either explicitly list the model types that each solver package can solve, or we can derive this by annotating models and solver packages as numerical or explicit, and matching them to each other.

### Format variants

#### V1

In v1, variants can be identified by naming convention (suffix "a" or "g").

#### V2

In v2, a component-level attribute like `Dfn.variant_of: str | None` can identify format-variant pairs (e.g. `gwf-welg` is a variant of `gwf-wel`). This does require choosing which variant is the "canonical" component.

The list vs. array distinction at the period block level is part of what structurally defines a variant — `gwf-wel` and `gwf-welg` are not different serializations of the same structure; they have different field types (`ListField` vs. `ArrayField`) and different structural semantics (sparse per-cell entries vs. full-grid arrays). V2 preserves both representations as-is; unification is deferred to a future schema version.

## Related GitHub discussions

- `modflow-devtools` #262 — DFNs API (needs stable schema versioning)
- `modflow-devtools` #259 — schema naming discussion
- `modflow-devtools` #233 — separated format from schema version
- `pyphoenix-project` #246 — separate structural from format spec
- `pyphoenix-project` #282 — consider pydantic
- `pyphoenix-project` #205, #206, #218 — specific schema issues to resolve before finalizing
- `modflowpy/pyphoenix-project` discussion #47 — DFN schema/format (TOML design)
