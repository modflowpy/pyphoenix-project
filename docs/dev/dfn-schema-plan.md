# DFN schema plan

This document outlines a plan to formalize and iterate the MF6 DFN specification.

## Contents

- [Overview](#overview)
- [Background](#background)
- [Design](#design)
  - [Components](#components)
    - [Parent bindings](#parent-bindings)
    - [Multi-packages](#multi-packages)
  - [Blocks](#blocks)
    - [Block flavors](#block-flavors)
      - [Dictionary block](#dictionary-block)
      - [List block](#list-block)
    - [Exceptions](#exceptions)
    - [Block class](#block-class)
  - [Fields](#fields)
    - [Shared attributes](#shared-attributes)
      - [`name`](#name)
      - [`type`](#type)
      - [`longname`](#longname)
      - [`description`](#description)
      - [`optional`](#optional)
      - [`default`](#default)
      - [`developmode`](#developmode)
    - [Other attributes](#other-attributes)
      - [`reader`](#reader)
      - [`tagged`](#tagged)
      - [`preserve_case`](#preserve_case)
      - [`jagged_array`](#jagged_array)
      - [`numeric_index`](#numeric_index)
      - [`time_series`](#time_series)
      - [`layered`](#layered)
      - [`valid`](#valid)
      - [`repeat`](#repeat)
      - [`just_data`](#just_data)
      - [`block`](#block)
      - [`block_variable`](#block_variable)
      - [`netcdf`](#netcdf)
    - [Scalars](#scalars)
      - [Keyword](#keyword)
      - [String](#string)
      - [Integer](#integer)
      - [Double](#double)
      - [Path](#path)
    - [Composites](#composites)
      - [Array](#array)
      - [Record](#record)
      - [Union](#union)
      - [List](#list)
- [Cross-cutting constraints](#cross-cutting-constraints)
  - [Array dimensions](#array-dimensions)
  - [Primary/foreign keys](#primaryforeign-keys)
    - [Examples](#examples)
  - [Parent/child relations](#parentchild-relations)
  - [Solution compatibility](#solution-compatibility)
  - [Format variants](#format-variants)

## Overview

The MODFLOW 6 definition (DFN) file format is a simple text format used to specify the logical structure of MODFLOW 6 input components. This includes shape, relationships, and various other characteristics. Taken together, a full set of DFNs carry several types of information: which components exist, what fields they have, component- and field-level attributes, and how components may be connected to one another. DFNs also inevitably reflect representational choices and may carry format-specific information.

DFNs must be interpreted in the context of the [natural language specification](https://modflow6.readthedocs.io/en/latest/_dev/dfn.html) describing them, as well as the MF6IO documentation, which describes MF6 input parsing routines. While DFNs are versioned in sync with MF6, the DFN schema itself is informal and unversioned.

Though the existing DFN spec is unversioned, this document will refer to it as **v1** for convenience. This schema is implicit in the DFN files' contents understood with reference to the MF6IO guide. This document describes a plan to formalize and version the DFN specification, ultimately producing formally versioned **v2+** DFN schemata.

## Background

DFNs don't map 1-1 to hydrologic processes. A DFN describes a single way of representing a process; not necessarily the only way. The purpose of representational variants is to allow the user to trade performance and convenience as appropriate for the case at hand. For example, a model with just a few wells is most easily defined with the standard WEL package, while a model with wells covering most of the grid may be easier to express in terms of grid-shaped arrays with WELG.

For small data, representation is less critical. This is the case for the DFN schema itself; because it is relatively small and presents no difficulty to read or write, by machine or by hand, it has no need for compressed arrays or representational variants. Given sufficiently expressive serialization formats and small enough data, the format can be chosen independently of the data to be encoded: DFNs could be written to TOML, YAML, or JSON.

But representation matters for MF6 input data, which may be large. As such, the logical structure of a simulation cannot be completely agnostic to input file format or to internal implementation. Representational choices must be made. These choices are reflected in component definitions.

For example, the purpose of `maxbound` is to tell MF6 how many array slots to allocate before loading proceeds. Insofar as one can imagine `maxbound` being unnecessary with a dense internal/external representation, or if MF6 counted lines before allocating arrays, `maxbound` could be considered a secondary, contingent piece of information, unlike the described boundary condition itself, whose hydrologic meaning is primary and invariant whether stored sparsely as a list of records or densely as grid-aligned arrays.

But given that each component reflects a conscious choice about convenience/performance with corresponding tradeoffs, information like `maxbound`, necessary to some particular representional scheme, can be considered primary or fundamental to the structure of the component. Moreover, while all input component variants currently load to a consistent sparse internal representation, other internal representations have been considered. If runtime (not just load-time) performance becomes conditional on selection of components the line between structural and format-specific information will blur even more.

Some representations may be more expressive than others. For example, the sparse list representation of period block data permits multiple entries per cell (e.g., multiple wells at the same node), something a dense grid-aligned array cannot express.

## Design

The aim is to provide structure and rigor to the DFN specification without departing too much from the general approach taken in v1. Fundamental concepts like 1 DFN per possible representation of a component, as described above, will stay. Changes will typically be motivated by one or more of the following:

**Versioning.** Allow modifying the schema in a disciplined way.

**Validation.** Allow checking if a component specification conforms.

**Explicitness.** Make information currently implicit in the DFNs explicit.

**Expressivity.** Make valid data easy to represent, invalid data impossible.

**Consistency.** Consolidate conceptually similar patterns where appropriate.

### Components

Each component is specified by a DFN. Component definitions consist of zero or more block definitions (see below).

Component definitions may also include component-scoped information:

- the component's (possible) parent(s), if any
- whether multiple instances of the component are allowed

#### Component definition

A component definition is an immutable object with top-level attributes: `name`, `schema_version`, `parent`, `multi`, `advanced`, `variant_of`, and `blocks`.

`children` is an optional attribute, absent in flat specs and populated when components are organized into a hierarchy. Top-down traversal is also supported without building a full hierarchy: a full specification object can invert the bottom-up `parent` declarations on demand.

#### Parent bindings

See the section on parent-child relations below.

#### Multi-packages

Components of which multiple instances are allowed are called "multi-packages", indicated in v1 by a special comment line at the top of the DFN:

```
# flopy multi-package
```

In v2, introduce a top-level component attribute `multi`.

### Blocks

A block is group of related fields, essentially a product type. Record fields are also product types. The distinction is that records occupy a single line in MF6 input files, while blocks are multiline constructs delimited by headers, e.g.

```
begin <block name>
   field1 value
   field2 value
end <block name>
```

#### Block flavors

Blocks are treated differently depending on the structural composition of their top-level fields. Two block types can be identified: dictionary and list.

There is one exception: SIM-NAM `solutiongroup`, in which a single tagged scalar `mxiter` preceeds a list field. TODO: choose whether to support this pattern. If so, it voids the distinction between dictionary and list blocks. One can imagine a more flexible rule 

##### Dictionary block

A dictionary block consists of one or more top-level scalar, record, or array fields. If the block contains more than one field, all fields must be tagged.

##### List block

A list block consists of exactly one top-level list field. Rows are read sequentially by `urword`; each row matches the list's record or union item type.

#### Exceptions

#### Block class

Blocks are first-class objects in v2 with four attributes: `name`, `fields`, `repeats`, and `optional`.

The `repeats` attribute indicates that the block may be repeated. Each repetition must have a unique label. The label must follow the `begin`/`end` delimiters. This replaces the `block_variable` attribute used in v1. In v2 the label takes the place of the explicit block variables:

- stress package `period.iper`: period number
- `utl-tas.time.time_from_model_start`: simulation time
- `utl-obs.continuous.output`: output file record

### Fields

In v1, fields are described by a single set of attributes, some mandatory, some optional, depending on the field type. Describing all field types with a single field definition is error-prone and requires manual validation, as it is possible to represent invalid state. It can also make it difficult to determine what type a field is: e.g., scalars and arrays are distinguished in v1 by a non-empty `shape` attribute; `type` alone is not sufficient. In v1, `type` may well be understood as "dtype", with scalar fields as special cases of arrays. (The `.array` syntax to retrieve the value of a scalar in FloPy 3.x may evidence such an understanding.)

In v2, define a field as a [sum type](https://en.wikipedia.org/wiki/Tagged_union) (discriminated union) of concrete types, each consisting only of the attributes relevant to it. Concrete types are discriminated by the `type` attribute.

#### Shared attributes

There is a core set of attributes shared by all field types:

- `name`
- `type`
- `longname`
- `description`
- `optional`
- `default`
- `developmode`

##### `name`

The field's name.

##### `type`

The field's type, one of:

- `keyword`
- `integer`
- `double`
- `array`
- `string`
- `path`
- `record`
- `union`
- `list`

##### `longname`

A longer, more descriptive name. From the [NetCDF conventions](https://docs.unidata.ucar.edu/nug/current/attribute_conventions.html#long_name). May contain spaces.

##### `description`

A detailed description of the field.

##### `optional`

Indicates that the field is not mandatory and may be omitted. May be applied to blocks and to fields, both composite and scalar.

##### `default`

The field's default value. Only relevant for optional fields. TODO: determine whether to keep. MF6 doesn't read DFN defaults, only flopy does. MF6 implements defaults internally, so care must be taken to keep DFNs in sync, or maybe IDM could read the default from the DFNs.

##### `developmode`

Feature flag indicating that the field is not to be released yet, only to be allowed in develop mode builds.

#### Other attributes

Some v1 attributes are preserved as-is. Some are renamed with semantics preserved. Others may have the same name with modified semantics, or a new name and modified semantics.

| v1 attribute | v2 fate | notes |
|---|---|---|
| `reader` | Drop | Infer from field/block type and attributes. |
| `tagged` | Keep | Some records may have a mix of tagged and untagged subfields. And arrays may not be tagged if the array's identity is clear from the block name, as for UTL-TAS tas_array. |
| `preserve_case` | Rename `case_sensitive` | No longer needed for path strings, still necessary for some others (e.g. `crs`). |
| `time_series` | Keep | Overloaded; different semantics for scalars and arrays. |
| `layered` | Drop | Perfectly correlated with `nlay` in shape. |
| `jagged_array` | Drop | Raggedness is cosmetic, simply parse as 1D. Only used for DISU `ja`. |
| `numeric_index` | Drop | Replace with explicit PK/FK semantics, see section below. |
| `valid` | Keep | Applicable only to strings and integers. |
| `repeating` | Rename/retype to `repeat: str | None` | Unifies UTL-TAS and GWF-RCHA/EVTA aux patterns, see section below. |
| `just_data` | Drop | Only used in UTL-TAS; use `tagged` instead. |
| `block_variable` | Drop | Replace with first-class block repetition semantics, see section below. |
| `block` | Drop | Field membership in block hierarchy makes inline attribute redundant. |
| `netcdf` | Keep (for now) | Required so long as NetCDF is opt-in for individual fields. Not necessary if all fields are to be read from NetCDF files, or if field-level inclusion in NetCDF files can be determined by some rule (e.g. data but not configuration fields). |

##### `reader`

The v1 `reader` indicates which MF6 parsing routine is to be used for the field. This can be inferred in v2 from the field type and other attributes, so `reader` can be dropped: arrays are read with READARRAY, other field types with urword.

##### `tagged`

The v1 `tagged` attribute indicates whether a field, usually but not necessarily a record subfield, must be preceded by its name. This attribute remains in v2 and becomes optional.

By default, `tagged=True`. Tagging is only optional for fields whose identity can be unambiguously determined from their value or their position in a line or block. Some fields must always be `tagged`:

1. Fields in a dictionary block.
2. Keyword fields. Only the presence/absence of the keyword can signal the field's value.

Setting `tagged=False` for either of these cases is a validation error.

Some records mix tagged and untagged subfields. For example, GWF-OC's `formatrecord`.

##### `preserve_case`

The MF6 parser converts strings to uppercase by default. The `preserve_case` flag in v1 indicates that a string field should not be uppercased. The main use case is file paths, but there are other case-sensitive strings (e.g. CRS). Rename to `case_sensitive` in v2, and apply only to non-path fields, since case-sensitivity can be assumed for paths.

##### `jagged_array`

The `jagged_array: str` attribute in v1 marks an array field which can be spread across multiple lines, with varying numbers of elements per line; the number determined by the named array (`iac`). Used only for DISU `connectiondata`.

This exists for the benefit of FloPy 3.x only. Drop in v2. The MF6 input file parser has no concept of raggedness; `ja` is read as a flat 1D array of shape `NJA`.

##### `numeric_index`

In v1 `numeric_index` marks fields that index an element of some collection. In general, the index is into a list defined in the same package. But there are more exotic cases; for example, `iper` block indices representing period numbers, or UTL-OBS `id`/`id2` fields accepting either a boundary name or a cellid, and for which the target collection may be 1) a list defined in another package or 2) the grid's node list, which is implicit in the discretization, not an explicit field.

Replace `numeric_index` in v2 with explicit PK/FK semantics (see section below). Valid only on integer and string subfields of a record which is itself a list's item type.

##### `time_series`

In v1 `time_series` marks fields which may be configured as a scalar- or array-valued timeseries.

Applied to a string (`reader urword`) field, indicates that it accepts either a real numeric value or a TS name referencing a `utl-ts` time series object.

Applied to an array (`reader readarray`) field, indicates that it accepts either inline array data using READARRAY syntax, or a TAS name referencing a time-array series object. At any model time, the TAS provides an interpolated grid-shaped array.

##### `layered`

In v1 `layered` marks array fields that must be read as separate layer arrays: distinct READARRAY sections for each layer, rather than one with one greater dimension. Required because the READARRAY routine works on arrays of at most 2 dimensions.

Every array whose shape contains `nlay` also has `layered`, and no array with `nlay` in its shape is non-layered, so `layered` can be dropped in v2 and inferred from dimensions.

##### `valid`

In v1 `valid` enumerates permissible values for string fields. Keep in v2, and allow on integers too.

##### `repeat`

In v1 `repeating` has been applied in two different ways, only one of which is still in use:

- For UTL-TAS `tas_array`, `repeating` indicates that the `time` block may contain multiple array values, up to the number of timeseries names provided in `time_series_name`.
- Prior to MF6.6.0, PRT-PRP and PRT-OC used `repeating` to signal an "inline" 1D array that is not formatted according to READARRAY requirements, but simply consists of a single line of space-separated elements; could also be considered a variadic tuple. These usages were unique and non-standard, and the relevant fields were removed in MF6.6.0.

GWF-RCHA/EVTA period block `aux` shares the same semantics as UTL-TAS `tas_array`: multiple READARRAY calls per block, up to the number of elements (`naux`) in the `auxiliary` string array. But `aux` is not annotated with `repeating`; the repetition is implicit.

In v2, rename `repeating` to `repeat`, and switch from a boolean to a string naming a 1D array field in the same component whose length determines how many times the `repeat`-annotated field is repeated sequentially within a single block. Then apply to both the UTL-TAS and RCHA/EVTA cases. Also make the shape of the array field meaningful, even if it is not an explicitly defined field (e.g., instead of `any1d`, introduce `ntas` or similar, analogous to `naux`).

Perhaps `repeat` could alternatively accept a scalar dimension field identifying the repetition count. This pattern does not currently appear in the DFN corpus, but could be useful in future.

##### `just_data`

In v1 `just_data` marks a field whose value occupies the entire block body, and signals the absence of a keyword tag. This attribute is used only for UTL-TAS `tas_array`: this indicates that each `begin time X` block header will be followed by READARRAY input with no leading keyword (tag).

This is redundant with `tagged` and unnecessary in v2.

##### `block`

In v1 `block` signals a field's membership in a block. This is necessary as in v1, DFN blocks are delimited by cosmetic comment lines which are ignored by the MF6 parser. In v2, an explicit `block` attribute is unnecessary: membership is expressed structurally, with field nested inside blocks. When serialized to TOML, membership can therefore be expressed as a table path (e.g. `[gwf-dis.griddata.botm]`).

##### `block_variable`

In v1 `block_variable` marks fields like `iper` which appear in the block header line rather than within the block body. The purpose of these is to distinguish blocks when a block may be repeated (e.g. period block, TAS time block). Drop in v2; first-class block repetition via block labels suffices instead (see `repeat` section above).

##### `netcdf`

In v1 `netcdf` marks fields that can appear in NetCDF input files. Keep in v2 for now, pending a decision whether fields will continue to opt into NetCDF support or whether fields will be included/excluded based on some rule.

#### Scalars

##### Keyword

Type `keyword`. Represents a boolean choice. In input files, the presence of a keyword indicates true, its absence false.

##### String

Type `string`.

Attributes (beyond base):
- `tagged: bool = False`: Indicates that the field value should be preceded by the field name. Valid only for record subfields.
- `valid: list[str] | None`: Permitted values (enumeration constraint). Empty list is treated as absent.
- `case_sensitive: bool = False`: Indicates that the string's case must be preserved. The MF6 parser uppercases strings by default. Renamed from v1's `preserve_case`.
- `pk: bool = False`: Marks this scalar as the primary key of its containing list's item record. Valid only on integer or string scalars that are columns in a list item record. Exactly one column per list item may be marked pk.
- `fk: str | None = None`: Marks this scalar as a foreign key. Valid only on integer or string scalars that are columns in a list item record. Three forms: (1) hierarchical path `"block.field"` or `"component.block.field"` — fully static, used without `fk_ref`; (2) sentinel `"node"` — grid cell reference, used without `fk_ref`; (3) bare block name (e.g., `"packagedata"`) — used together with `fk_ref` to name the block within the runtime-resolved target component, leaving only the pk field to be discovered. See "Primary/foreign keys".
- `fk_ref: str | None = None`: For FKs whose target component is only known at runtime. Names a sibling string field whose value identifies the target component. May be set alone (block within target also unknown) or together with `fk` as a bare block name (block known, component not). See "Primary/foreign keys".

##### Integer

Type `integer`.

Attributes (beyond base):
- `tagged: bool = False`: Indicates that the field value should be preceded by the field name. Valid only for record subfields.
- `valid: list[str] | None`: Permitted values (enumeration constraint). Empty list is treated as absent.
- `dimension: bool = False`: Marks a valid target for shape expressions; enables shape validation at schema load time. Fields in `dimensions` blocks are primary candidates, but some `options` scalars also qualify (e.g. `naux`).
- `time_series: bool = False`: Marks fields where the parser accepts either a numeric literal or a time-series name (referencing a `utl-ts` object). Not inferrable from structural type. Also appears on array fields (where it references a `utl-tas` object instead). Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.
- `pk: bool = False`: Marks this scalar as the primary key of its containing list's item record. Valid only on integer or string scalars that are columns in a list item record. Exactly one column per list item may be marked pk.
- `fk: str | None = None`: Marks this scalar as a foreign key. Valid only on integer or string scalars that are columns in a list item record. Three forms: (1) hierarchical path `"block.field"` or `"component.block.field"` — fully static, used without `fk_ref`; (2) sentinel `"node"` — grid cell reference, used without `fk_ref`; (3) bare block name (e.g., `"packagedata"`) — used together with `fk_ref` to name the block within the runtime-resolved target component, leaving only the pk field to be discovered. See "Primary/foreign keys".
- `fk_ref: str | None = None`: For FKs whose target component is only known at runtime. Names a sibling string field whose value identifies the target component. May be set alone (block within target also unknown) or together with `fk` as a bare block name (block known, component not). See "Primary/foreign keys".

##### Double

Attributes (beyond base):
- `tagged: bool = False`: Indicates that the field value should be preceded by the field name. Valid only for record subfields.
- `time_series: bool = False`: Marks fields where the parser accepts either a numeric literal or a time-series name (referencing a `utl-ts` object). Not inferrable from structural type. Also appears on array fields (where it references a `utl-tas` object instead). Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.

##### Path

Type `path`.

Attributes (beyond base):
- `mode: Literal["filein", "fileout"]`: Whether the path is to an input or output file.

First-class path type replaces the v1 approach using a record with 3 subfields: keyword name, "filein" or "fileout" keyword, and file path. The `preserve_case` attribute is no longer needed as path fields can be assumed case-sensitive.

#### Composites

Three kinds of composite type are relevant to MF6: [product](https://en.wikipedia.org/wiki/Product_type) (record), [sum](https://en.wikipedia.org/wiki/Tagged_union) (union), and collection (array, list).

In v1, each component definition is a flat list of field specifications. The structure of composite fields is inferred from the field `type` (`recarray`, `record` or `keystring`),other attributes (e.g. `in_record`), and the order in which field definitions appear.

In v2, define composite fields as explicitly nested, so that the composite structure is reflected in the schema. Product and sum types have multiple nested subfields. Lists have a single nested subfield. Arrays have no nested subfields; see below.

##### Array

Type `array`.

Arrays are not proper composites in v1 or v2. An array does not have an item subfield as does a list. Instead, it has a `dtype` attribute identifying its scalar element type. An array may not contain composites; `dtype` must be a scalar type.

Attributes (beyond base):
- `dtype: str`: The array's data type. Must be one of the scalar types.
- `shape: list[str]`: The array's shape, defined by reference to dimension scalars.
- `time_series: bool = False`: Marks fields where the READARRAY invocation may be replaced by a TAS name referencing a `utl-tas` time-array series object. At any model time, the TAS provides an interpolated grid-shaped array. Distinct from the scalar case: references `utl-tas`, not `utl-ts`. Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.
- `repeat: str | None = None`: Names the field (within the same component) whose runtime length determines how many times this field is read sequentially within an array block, with each reading appended to an accumulated sequence. See `repeat` section below.

##### Record

Type `record`. Product type. In MF6 input files, records appear on a single line. Record subfields may or may not be `tagged`. While blocks can be considered product types also, in the DFN specification only records are considered fields; blocks are considered named collections of related fields.

Attributes (beyond base):
- `fields: dict[str, Scalar | Array | Record | Union]`: subfields, required.

**Note:** if an array appears in a record, it will appear inline, not in the READARRAY format. TODO: info like this should be in a separate format-scoped document.

**Note:** if a nested record appears inside another record, the inner record's contents should appear inline inside the outer record's contents, on the same line.

##### Union

Type `union`, renamed from v1's `keystring`. Sum type.

Attributes (beyond base):
- `arms: dict[str, Scalar | Record]`: subfields, required.

**Note:** 

##### List

Type `list`, renamed from v1's `recarray`. Collection type. Unlimited but for one rule: a list may not contain another list.

Attributes (beyond base):
- `item: Record | Union`: subfield (item type), required.

## Cross-cutting constraints

Field and component definitions are not entirely self-contained. Some fields may refer to other fields, in the same component or in another. Likewise, component definitions may refer to other component definitions. Several kinds of cross-cutting constraints exist:

- array dimensions
- primary/foreign keys
- parent-child relations
- solution compatibility
- input format variants

### Array dimensions

A scalar integer field defined in one component can be referenced by name in the `shape` expression of an array field in the same or another component.

In v2, shape expressions may only reference declared dimension names. Two kinds exist:

- **Explicit dimensions**: integer scalar fields marked `dimension=True`. Fields in `dimensions` blocks are primary candidates; some `options` scalars also qualify (e.g. `naux`).
- **Derived dimensions**: dimensions not present as explicit DFN fields but computable from other fields. Examples: `nodes` (product of grid dimension fields for structured grids), `nja` (derived from the connectivity array). Derived dimensions are declared explicitly in the schema with a defining expression.

A shape expression referencing a name that is neither an explicit `dimension` field nor a declared derived dimension is a schema validation error.

### Primary/foreign keys

Sometimes a column in one list identifies a row in another list, or a grid cell. This can be modelled in v2 as a primary key (PK) / foreign key (FK) relation. PK/FK attributes are valid on integer and string scalar fields that are columns in a list item record.

In v1 this was indicated by `numeric_index`. This attribute was overloaded as both primary and foreign key:

- PK: e.g. `packagedata.lakeno`, `packagedata.rno`, `vertices.iv`, `cell2d.icell2d`
- FK: e.g. `period.lakeno`/`rno`, `connectiondata.iconn`
- String usage: `utl-obs.continuous.id1`/`id2` also carry `numeric_index`, even though they are string fields; the relationship is PK/FK-like.

The `ja` array in DISU also carries `numeric_index`, but as a flat array whose elements encode grid topology positionally (not a distinct index into a list), this is unnecessary in v2.

In v2, scalar field attributes can encode PK/FK semantics: `pk`, `fk`, and `fk_ref` (see scalar field section above).

The `fk` attribute can take one of three forms:

- **Hierarchical path** — `"block.field"` for within-component references, `"component.block.field"` for cross-component references where the target is statically known. Used without `fk_ref`.
- **`"node"` sentinel** — indicates a grid cell reference. The target is the parent model's spatial discretization, resolved at runtime. Used without `fk_ref`, wherever a field carries a cellid (e.g., `cellid` columns in sparse stress period blocks, the integer arm of `utl-obs.continuous.id`).
- **Bare block name** (e.g., `"packagedata"`) — used together with `fk_ref`. `fk_ref` resolves the target component at runtime; `fk` names the block within it. The codec then finds the unique `pk=True` field in that block. A bare block name contains no dot and is not `"node"`.

The `fk_ref` attribute names a sibling string field whose runtime value identifies the target component. Two sub-cases exist:

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

Parent-child relationships are intrinsic to a component's identity and should be explicitly defined. A component's valid parents range from fully constrained (a single named component type, e.g. `gwf-chd` always under `gwf-nam`) to loosely constrained (any component of a given semantic type, e.g. any package) to unconstrained (any parent). Components with looser parent constraints are historically called "subpackages". All relationships are resolved at simulation instantiation time; the schema states the constraint, not the instance.

In v1 DFNs, parent-child relationships are implicit or encoded in special comment lines. Fixed relationships are implicit in component naming (e.g., `gwf-*` is always a child of a GWF model); subpackage relationships are declared via `# flopy subpackage` / `# flopy parent_name_type` comment pairs.

In v2, all parent relationships can be made explicit with a component attribute `parent`:

- `None` — no parent; the component is simulation-level.
- `"*"` — matches any parent component type.
- A string or list of strings — declares the set of valid parent component types. Entries are either:
  - **Type names** (`"model"`, `"package"`) — matches any component of that semantic type. Type names never contain a hyphen.
  - **Component IDs** (`"gwf-sfr"`, `"gwf-nam"`) — matches only that specific component type. Component IDs always contain a hyphen.
  - In a mixed list, a type name subsumes any named component of the same type: `["gwf-sfr", "package"]` reduces to `["package"]` since `gwf-sfr` is a package.

**Examples:**

| v1 encoding | v2 `parent` |
|---|---|
| _(implicit from `gwf-*` naming convention)_ | `"gwf-nam"` |
| `parent_name_type parent_package MFPackage` | `"package"` |
| `parent_name_type parent_model MFModel` | `"model"` |
| _(obs, attached to model or package)_ | `["model", "package"]` |
| _(subpackage restricted to specific components)_ | `["gwf-sfr", "gwf-maw"]` |
| _(attached to any parent)_ | `"*"` |

### Solution compatibility

Solver components are called "solution packages", indicated in v1 by a comment at the top of the DFN:

```
# flopy solution_package ims *
```

The right-most two tokens are respectively the solution package abbreviation, and the model types the package may be used to solve. In v1 both IMS and EMS currently use "*", meaning the v1 spec does not reflect existing constraints about which solutions may be used with which models.

In v2 a top-level component attribute should reflect constraints: that numerical models must be solved by IMS and explicit models by EMS. We can either explicitly list the model types that each solver package can solve, or we can derive this by annotating models and solver packages as numerical or explicit, and matching them to each other. TODO: decide how to do this.

### Format variants

In v1, component variants can be identified by naming convention (suffix "a" or "g").

In v2, a component-level attribute like `variant_of` can identify format-variant pairs (e.g. `gwf-welg` is a variant of `gwf-wel`). This requires choosing which variant is the "canonical" component.

The dictionary vs list block distinction is part of what structurally defines a variant; `gwf-wel` and `gwf-welg` are different representations/serializations of the same semantics.
