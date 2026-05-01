# DFN schema formalization plan

This document captures the current state of the DFN specification and outlines a plan to formalize it.

## Background

The MODFLOW 6 definition file ("DFN") format is a simple text format described in [natural language](https://modflow6.readthedocs.io/en/latest/_dev/dfn.html). The schema is implicit in this description and in the content of the existing DFN files, which must be read in the context of the MF6IO documentation (and vice versa).

**v1** is the existing schema. Its content is faithfully parsed from DFN files, with no alterations. Currently v1 is consumed by tooling in the MF6 repository.

**v1.1** is a slightly normalized version generated from v1 DFN files by `modflow_devtools.dfn`. It parses bools, resolves `common.dfn` substitutions, drops some attributes, and does some structural transforms. Flopy 3.x codegen consumes v1.1, serializing to/from TOML. v1.1 only exists due to poor planning (WPB) and will be retired with devtools v2. Flopy 3.x should be altered to consume v1 or v2 directly.

**v2** is the target. A more substantially transformed schema version has evolved as flopy 4.x development proceeds, facilitated by `modflow_devtools.dfns` (plural; distinct from the old `dfn` module). This document makes the v2 schema explicit and formalizes it. The newly formalized, versioned schema can be published with devtools 2.x, then become the foundation of flopy 4.x. MF6 tooling will later begin to consume v2 schema too.

## Principles

**Schema versioning.** Allows adding/removing from the schema in a disciplined way.

**Schema validation.** Allows checking if a given component specification conforms.

**Separation of concerns.** A fundamental distinction is between schema and serialization format. The content of DFN files could be written to TOML, YAML, or JSON. That content (the schema) describes the data's shape and characteristics: which components exist, what fields they have, how they are connected. In other words, structural information, defining the valid structure of each simulation component. Choice of data interchange format is a separate issue.

Another distinction is between simulation structure and MF6 input file format. Current DFN files carry both structural information and input file format information. For example, DFNs describe time-varying boundary condition fields not as distinct variables aligned to the grid and time discretizations, but as dataframes whose row count is an artificial dimension `maxbound`, corresponding to the sparse list-based input format MF6 expects in the period block. The sole purpose of `maxbound` is to inform the MF6 block parser how many array slots to allocate. Ideally the MF6 input specification would be agnostic to input file format, with format information either derived from the schema via a well-defined ruleset, or expressed as a separate schema annotation layer specifically scoped to MF6 input format, with the core specification responsible only for describing the simulation in a "canonical form" carrying only structural info.

**1 DFN file per input component.** DFN files do not currently map 1-1 to hydrologic processes. A DFN file describes a single way of representing a process, not necessarily the only one. Where multiple DFN files represent the same process in different formats (e.g. `gwf-wel`/`gwf-welg`, `gwf-rch`/`gwf-rcha`), the relationship should be explicit in the schema. Unification can be deferred to a future schema version.

**Explicit parent-child relationships.** Parent-child relationships are intrinsic to a component's identity and should be explicitly defined. Two parent-child relationship types are distinguished: fixed and free. Fixed-parent components have a single possible parent (e.g. `gwf-chd` always under `gwf-nam`). Free-parent components may be attached to multiple possible parents; historically we have called these "subpackages". Fixed-parent relations are specification invariants, while free-parent relationships are resolved later.

## Design

### Fields

The existing design attempts to shoehorn all field types into a single field definition. This is error-prone as invalid field definitions can be represented.

Refactor `modflow_devtools.dfns.schema.FieldV2` into a Pydantic discriminated union of the concrete field types:

```python
FieldV2 = Annotated[
    ScalarFieldV2 | ArrayFieldV2 | RecordFieldV2 | ListFieldV2 | UnionFieldV2,
    PydanticField(discriminator="type")
]
```

#### Field types

##### `ScalarFieldV2`

Types: `keyword`, `integer`, `double`, `string`, `path`.

Attributes (beyond base):
- `dimension: bool = False`: Marks a valid target for shape expressions; enables shape validation at schema load time. Fields in `dimensions` blocks are primary candidates, but some `options` scalars also qualify (e.g. `naux`). `maxbound` does NOT get `dimension=True`, it is a formatting concern to be dropped from the structural schema.
- `index: bool = False`: Marks a 1-based integer index field. Applies to PK columns (named by `ListFieldV2.key`) and FK columns referencing PKs in other lists.
- `time_series: bool = False`: Marks fields where the parser accepts either a numeric literal or a time-series name. Not inferrable from structural type. Also appears on `ArrayFieldV2`.
- `valid: list[str] | None`: Permitted values for `string` fields (enumeration constraint). Not inferrable. Empty `valid` (artifact of v1 `block_variable` fields) is treated as absent.

##### `ArrayFieldV2`

Type: `array`

Attributes (beyond base):
- `shape: list[str]`: The array's shape, defined by reference to dimension scalars.
- `layered: bool = False`: Marks READARRAY array fields provided as separate per-layer invocations, one per layer. Not inferrable from shape alone (presence of `nlay` in shape is necessary but not sufficient).
- `time_series: bool = False`: Same semantics as on `ScalarFieldV2`; applies to READARRAY double arrays.

##### `RecordFieldV2`

Type: `record`

Attributes (beyond base):
- `fields: dict[str, FieldV2]`: named columns, required.

##### `ListFieldV2`

Has `item: RecordFieldV2 | UnionFieldV2`: the row type, required.

Attributes (beyond base):
- `key: str | None`: Names the column within the list's record type that serves as the primary key (a unique, 1-based row identifier). A Pydantic `model_validator` asserts the named column exists and has `index=True`. Example: `packagedata` has `key="ifno"`.

##### `UnionFieldV2`

Has `arms: dict[str, FieldV2]`: named alternatives, required.

#### Field attributes

Some v1 attributes need to remain, some can be dropped.

| v1 attribute | v2 fate | Reason | Notes |
|---|---|---|---|
| `tagged` | drop | Determined by block type + field type + position | |
| `preserve_case` | drop | Always-preserve-case policy in v2; `path` type retained for semantics only | |
| `time_series` | keep for `ScalarFieldV2`, `ArrayFieldV2` | Not inferrable; many `double` fields in the same blocks lack it | |
| `layered` | keep for `ArrayFieldV2` | Not inferrable from shape alone; `nlay` in shape is necessary but not sufficient | |
| `jagged_array` | drop | Not in Fortran IDM; `ja` is a flat 1D array in MF6; raggedness is a codec concern | |
| `numeric_index` | replace with `ScalarFieldV2.index` + `ListFieldV2.key` | Explicit PK/FK semantics; `model_validator` enforces key consistency | |
| `valid` | keep for string `ScalarFieldV2` | Structural constraint; not inferrable | |
| `repeating` | keep | Not inferrable; behavior is file-format-level | |
| `just_data` | drop | Single occurrence (`utl-tas`); structurally inferrable | |
| `block_variable` | drop | Replace with first-class block repetition at block/component level | |
| `block` | drop | Field position in block hierarchy makes inline attribute redundant; codec concern | |
| `netcdf` | keep for now? | not in Fortran IDM, not a structural property, but temporarily necessary | how much longer will this be needed? |
| `reader` | **drop** | Infer from block type | |

#### `preserve_case`

The MF6 parser converts strings to uppercase by default. The `preserve_case` flag in v1 indicates that a string field should not be uppercased. The main use case is file paths, which will have a distinct field type in, but there are other case-sensitive strings (e.g. CRS), so we may still need the attribute in v2.

#### `jagged_array`

`jagged_array: str` marks READARRAY fields whose row lengths vary and are determined by a named counter array (`iac`). Appears only in DISU `connectiondata` blocks (15 occurrences across `gwf-disu`, `gwe-disu`, `gwt-disu`).

**Decision:** Drop from the structural schema. The Fortran IDM (`InputParamDefinitionType` in `InputDefinition.f90`) has no `jagged_array` field. In the MF6 Fortran parser, `ja` is read as a plain flat 1D integer array of shape `NJA` — no ragedness is expressed at the parser level. The jagged presentation is a Python data-presentation transform belonging in the codec layer, not the schema. The `connectiondata` arrays remain `ArrayFieldV2` with shape `NJA`.

#### `numeric_index`

`numeric_index=true` in v1 marks integer fields that carry 1-based indices and should be presented 0-based to Python tools. Very common: ~100 fields across all model types.

**Decision:** Replace with explicit PK/FK semantics:

1. **`ListFieldV2.key: str | None`** — names the column within a list's record type that serves as the primary key. The named column must have `index=True`. A Pydantic `model_validator` enforces this at schema load time.

2. **`ScalarFieldV2.index: bool = False`** — marks an integer scalar as a 1-based index. Set `True` on PK columns (named by `ListFieldV2.key`) and on FK columns referencing PKs in other lists. The codec applies 0-based conversion to all `index=True` fields.

**`utl-obs` `id`/`id2` fields:** These accept either a boundary name (string) or a cellid (integer, 1-based). Model as `UnionFieldV2` with two arms: a `string` arm for boundary names and an `integer` arm with `index=True` for cellid values. No special annotation needed.

**`iper` block labels:** 1-based period numbers but not annotated with `index=True` — they are not data fields in the block body; the block repetition model handles their semantics directly.

#### `tagged`

The `tagged` attribute previously indicated whether a field, usually a record subfield, must be preceded by its keyword name. This can be dropped as it can be derived from structural position and field type:

1. **`keyword` anywhere:** always tagged — the keyword IS its own token; it appears with no associated value.
2. **top-level field in a keyword-value block:** tagged — its name precedes its value in the input file.
3. **Field inside a record (`in_record=true` in v1):** depends on type:
   - `keyword` members: tagged (they introduce or select the record's structure)
   - All other types (`integer`, `double`, `string`, `array`): untagged — positional within the record

#### `time_series`

`time_series=true` marks fields where the parser accepts either a numeric literal or a time-series name (a string token referencing a named TS object). Not inferrable from structural type.

Corpus distribution:

| v1 type | block | reader | in_record | count |
|---|---|---|---|---|
| `double precision` | `period` | `urword` | true | 96 |
| `string` | `period` | `urword` | true | 55 |
| `double precision` | `packagedata` | `urword` | true | 13 |
| `double precision` | `period` | `readarray` | — | 6 |
| `double precision` | `outlets` | `urword` | true | 4 |
| `string` | `packagedata` | `urword` | true | 1 |

The 55 `string`+`time_series=true` fields are structurally `double` — declared `string` in v1 to bypass numeric validation. In v2, these are retyped as `double` with `time_series=True` retained.

WPB: what does "bypass numeric validation" mean? Why is time_series used on both scalars and arrays? I would think it'd only be valid for arrays..

**In v2:** `time_series: bool` on `ScalarFieldV2` (double) and `ArrayFieldV2` (double).

#### `layered`

`layered=true` marks READARRAY array fields provided as separate per-layer READARRAY invocations rather than a single call. The presence of a layer dimension in `shape` (e.g. `nlay`) is necessary but not sufficient.

Example from `gwf-dis`:

| field | shape | layered |
|---|---|---|
| `top` | `(ncol, nrow)` | — |
| `botm` | `(ncol, nrow, nlay)` | `true` |
| `idomain` | `(ncol, nrow, nlay)` | `true` |
| `delr` | `(ncol)` | — |
| `delc` | `(nrow)` | — |

**In v2:** `layered: bool` on `ArrayFieldV2`. Present only in READARRAY blocks.

WPB: why do we need this? isn't this an mf6 parser concern? layered is just one of the ways to specify a grid-shaped array.

#### `valid`

`valid` lists permitted token values for a `string` field (enumeration constraint). Appears on 15 fields in the corpus. Examples: advection scheme (`central`, `upstream`, `tvd`), sorption type (`linear`, `freundlich`, `langmuir`), solution type (`ims6`, `ems6`).

Structural constraint — not inferrable. Empty `valid` (v1 artifact on `block_variable` fields) is treated as absent.

**In v2:** `valid: list[str] | None` on `ScalarFieldV2` (string).

#### `repeating`

`repeating=true` marks a field that may appear multiple times in a block, with each occurrence appended to an accumulated value. Active in only one field in the current corpus:

- `utl-tas.dfn` → `tas_array` (time block, READARRAY, `just_data=true`) — time-array series data repeated once per TAS name

Two additional occurrences in `prt-oc.dfn` and `prt-prp.dfn` are `removed 6.6.0`.

Not inferrable. **In v2:** `repeating: bool` on relevant field types.

WPB: why is this needed, if it's only used for utl-tas -> tas_array, which seems like a normal array? What's the difference? I'd like to drop this if possible. Historically, I thought this was used to indicate a tuple was variadic, like the final field in a record potentially having multiple space separated values..

#### `just_data`

`just_data=true` appears exactly once: `utl-tas.dfn` `tas_array`. It marks a field whose value occupies the entire block body with no keyword prefix. Rather than carrying this as a general field attribute in v2, the case is handled by the structural description of the block itself (a single array field with no keyword, read by READARRAY). **Dropped in v2.**

WPB: how exactly is the utl-tas.dfn block supposed to look, with this? I don't understand why this was ever necessary in the first place.

#### `block`

In v1, `Field.block: str` places a field into a named block as an inline attribute. In v2, block membership is expressed structurally — fields are nested inside block objects in the schema hierarchy. In the TOML serialization format, block membership is expressed by table path (e.g. `[gwf-dis.griddata.botm]`), not an inline attribute. **Dropped from field schema in v2.**

#### `block_variable`

In v2, drop `block_variable` and replace with a first-class block repetition concept at the component/block level.

#### `netcdf`

`netcdf` on the v1 `Field` base class marks fields that can appear in NetCDF output. This is an output-format annotation, not a structural property. The Fortran IDM (`InputParamDefinitionType`) has no `netcdf` field. **Dropped in v2.**

WPB: until netcdf is fully supported in the MF6 IDM, we need this attribute to indicate that a field supports netcdf. it should probably be dropped eventually, but we likely won't be ready by the time we want to release v2.

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

WPB: what's the operative difference between readarray and keyword-value blocks?  Isn't a readarray block a special case of the latter?

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

v1 DFNs define the period block as containing a single `recarray` field with a `cellid` column. This is a sparse `(cell, value...)` list representation of one or more grid- and time-aligned variables, defined in v1 as recarray columns. Structurally, each column is a distinct variable defined over a spatial subset of the grid with a shape determined by grid type and time dimension. The v2 schema proposes to define period block variables separately, rather than in a combined/tabular form like v1.

The period block repeats to support time-varying data: v1 DFNs define period blocks with an index field with `block_variable=true`, typically called `iper`. This block index (perhaps better thought of as an arbitrary but unique label) appears on the `BEGIN PERIOD n` line, not inside the block body:

```
begin period 1
   ...
end period 1
```

WPB: so, how to handle repeating blocks, like the period block? What's the specific mechanism? We mentioned making this a first class concept, but I don't see specifics anywhere.

## Component-level attributes

Component-level pieces of information include:

- whether multiple instances of the component are allowed

### Multi-packages

Components of which multiple instances are allowed are called "multi-packages", and currently indicated by a special comment line at the top of the DFN:

```
# flopy multi-package
```

In v2, components can have a top-level attribute `multi` or similar.

## Cross-component constraints

Component definitions are not entirely self-contained. Some component definitions refer to other component definitions. Several kinds of cross-component constraints exist:

- dimension references
- row indices, i.e. PK/FKs
- parent-child relationships
- solution compatibility
- format variants

### Dimension references

A scalar integer field defined in one component can be referenced by name in the `shape` expression of an array field in the same or another component.

Examples: `nlay`, `nrow`, `ncol`, `nper`, `nodes`, `nja`, `nvert`, `ncpl`, `naux`.

Above we propose adding `dimension: bool = False` to `ScalarFieldV2`. Shape expressions may only reference `dimension=True` fields; a reference to any other field becomes a schema validation error. Fields in `dimensions` blocks are primary candidates, but some `options` scalars also qualify (e.g. `naux`), so instead of trying to infer which integer fields are dimensions from block names, make it explicit. Since `maxbound` is an artificial dimension only relevant for MF6 input file formatting, drop it from v2 structural schema.

### PK/FK relations

Sometimes an integer column in one list identifies a row in another. Within-component cross-block FKs are covered by `ListFieldV2.key` + `ScalarFieldV2.index`. Cross-component integer FKs are rare in the corpus; `index=True` on both the PK and FK columns is sufficient for the codec.

WPB: examples of cross-component FKs? Is that only for indices into the grid node list?

### Parent/child relations

In v1 DFNs, fixed parent-child relationships are implicit in component naming (e.g. `gwf-*` means the component is necessarily a child of a GWF model) while free parent-child relationships are encoded in a special comment line at the top of the DFN file, mainly for flopy's benefit.

In v2, these relationships should all be explicit:

- `Dfn.parent: str | None` — declares a fixed parent (e.g. `gwf-chd` always under `gwf-nam`).
- `Dfn.accepts: list[str]` — declares which subpackage types a parent can contain (replaces `subcomponents`).

A component with no declared `parent` is a "free" subcomponent: the parent signals compatibility with the subpackage via `accepts`, and the relationship is resolved at simulation instantiation time.  `DfnSpec` provides traversal and lookup methods but does not own the relationship data.

### Solution compatibility

Solver components are called "solution packages", and currently indicated by a comment at the top of the DFN, e.g.:

```
# flopy solution_package ims *
```

The right-most two tokens are respectively the solution package abbreviation, and the model types the package may be used to solve. In v1 both IMS and EMS currently use "*", meaning the v1 spec does not reflect existing constraints about which solutions may be used with which models.

In v2 a top-level component attribute should reflect constraints: that numerical models must be solved by IMS and explicit models by EMS. We can either explicitly list the model types that each solver package can solve, or we can derive this by annotating models and solver packages as numerical or explicit, and matching them to each other.

### Format variants

In v2, a component-level attribute like `Dfn.variant_of: str | None` can identify format-variant pairs (e.g. `gwf-welg` is a variant of `gwf-wel`). This does require choosing which variant is the "canonical" component.

## Related GitHub discussions

- `modflow-devtools` #262 — DFNs API (needs stable schema versioning)
- `modflow-devtools` #259 — schema naming discussion
- `modflow-devtools` #233 — separated format from schema version
- `pyphoenix-project` #246 — separate structural from format spec
- `pyphoenix-project` #282 — consider pydantic
- `pyphoenix-project` #205, #206, #218 — specific schema issues to resolve before finalizing
- `modflowpy/pyphoenix-project` discussion #47 — DFN schema/format (TOML design)
