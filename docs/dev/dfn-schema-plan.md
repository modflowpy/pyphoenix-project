# DFN specification

- [Overview](#overview)
- [Components](#components)
  - [Shared attributes](#shared-attributes)
    - [`type`](#type)
    - [`name`](#name)
    - [`blocks`](#blocks)
    - [`parent`](#parent)
    - [`schema_version`](#schema_version)
  - [Component types](#component-types)
    - [Simulation](#simulation)
    - [Model](#model)
      - [Type-specific attributes](#type-specific-attributes)
        - [`solution`](#solution)
    - [Package](#package)
      - [Type-specific attributes](#type-specific-attributes-1)
        - [`multi`](#multi)
        - [`subtype`](#subtype)
        - [`variant_of`](#variant_of)
- [Blocks](#blocks-1)
  - [Attributes](#attributes)
    - [`name`](#name-1)
    - [`fields`](#fields)
    - [`repeats`](#repeats)
    - [`optional`](#optional)
- [Fields](#fields-1)
  - [Shared attributes](#shared-attributes-1)
    - [`name`](#name-2)
    - [`type`](#type-1)
    - [`longname`](#longname)
    - [`description`](#description)
    - [`optional`](#optional-1)
    - [`default`](#default)
    - [`developmode`](#developmode)
    - [`netcdf`](#netcdf)
  - [Scalars](#scalars)
    - [Keyword](#keyword)
    - [String](#string)
      - [Type-specific attributes](#type-specific-attributes-2)
        - [`tagged`](#tagged)
        - [`valid`](#valid)
        - [`case_sensitive`](#case_sensitive)
        - [`pk`](#pk)
        - [`fk`](#fk)
        - [`fk_ref`](#fk_ref)
    - [Integer](#integer)
      - [Type-specific attributes](#type-specific-attributes-3)
        - [`tagged`](#tagged-1)
        - [`valid`](#valid-1)
        - [`dimension`](#dimension)
        - [`time_series`](#time_series)
        - [`pk`](#pk-1)
        - [`fk`](#fk-1)
        - [`fk_ref`](#fk_ref-1)
    - [Double](#double)
      - [Type-specific attributes](#type-specific-attributes-4)
        - [`tagged`](#tagged-2)
        - [`time_series`](#time_series-1)
    - [Path](#path)
      - [Type-specific attributes](#type-specific-attributes-5)
        - [`mode`](#mode)
  - [Composites](#composites)
    - [Array](#array)
      - [Type-specific attributes](#type-specific-attributes-6)
        - [`dtype`](#dtype)
        - [`shape`](#shape)
        - [`time_series`](#time_series-2)
        - [`repeat`](#repeat)
    - [Record](#record)
      - [Type-specific attributes](#type-specific-attributes-7)
        - [`fields`](#fields-2)
    - [Union](#union)
      - [Type-specific attributes](#type-specific-attributes-8)
        - [`arms`](#arms)
    - [List](#list)
      - [Type-specific attributes](#type-specific-attributes-9)
        - [`item`](#item)
  - [Array dimensions](#array-dimensions)
    - [Derived dimensions](#derived-dimensions)
    - [Row-level column lookups](#row-level-column-lookups)
    - [Scope and resolution](#scope-and-resolution)
  - [Primary/foreign keys](#primaryforeign-keys)
    - [Examples](#examples)

## Overview

A MODFLOW 6 simulation consists of a hierarchy of modules, each module representing some functional element, such as a grid discretization, a hydrologic process (i.e. model), or a boundary condition.

This document distinguishes **modules**, conceptual units of functionality as defined in the MF6 IO guide, from **components**: particular representations of modules.

Each component may be configured by a corresponding input file. The MODFLOW 6 definition (DFN) file format is a simple text format used to specify MF6 component input, including the structure of components and fields, relationships between components, and in certain cases, file format information. DFNs map 1-1 to components and should not be expected to map 1-1 to modules. Each DFN is one single way of representing a module; not necessarily the only way. Several representational variants may exist, usually to trade performance and convenience characteristics as appropriate for the use case.

A note on terminology: "definition" is commonly abbreviated as "DFN" and the terms are used interchangeably. The terms "specify/specification" must be used with care, so it is clear what is being specified. DFN files (assuming knowledge of general MF6 input format rules) specify input files. This document and the schema it describes specify DFN files.

## Components

Each component is specified by a DFN. Component definitions consist primarily of a name, zero or more block definitions, as well as other optional attributes.

- `type`: the component type (`"simulation"`, `"model"`, or `"package"`)
- `name`: the component's name
- `blocks`: block definitions
- `parent`: parent component(s)
- `schema_version`: DFN schema version

Components may refer to, i.e. be constrained by, other components. Cross-component constraints include parent-child relations, solution compatibility, and format variants.

### Shared attributes

#### `type`

The component's type. Required. One of:

- `"simulation"`: the root of the runtime hierarchy.
- `"model"`: a hydrologic process model.
- `"package"`: a model input package.

#### `name`

The component's name. This is by convention the hyphenated `abc-xyz` stem of the DFN file name. Required.

#### `blocks`

The component's input blocks. A component may be empty, i.e. have no blocks. See section below.

#### `parent`

Except for the simulation, which is the root of the runtime hierarchy, all MF6 components have a parent. Parent-child relations may range from fully constrained (e.g., a `gwf-chd` package must be a child of a GWF model) to completely unconstrained. Components which may be attached to multiple possible parents are historically called **subpackages**.

Parent relationships are defined bottom-up with attribute `parent`:

- `None` — no parent; only valid for the root, i.e. simulation.
- `"*"` — unconstrained; any parent component type is allowed.
- A string or list of strings — declares the set of valid parent component types. Entries are either:
  - **Component type names:** `"simulation"`, `"model"`, or `"package"`.
  - **Concrete component names:** e.g. `"gwf-sfr"`, `"gwf-nam"`

**Note:** Type names and concrete component names may be mixed. A type name subsumes any named component of the same type: e.g., `["gwf-sfr", "package"]` reduces to `["package"]` since `gwf-sfr` is a package.

#### `schema_version`

The version of the DFN schema. Optional but recommended.

### Component types

Three component types can be distinguished: simulation, model, and package. 

#### Simulation

The simulation is the root of the MODFLOW 6 runtime module hierarchy. A simulation may contain one or more models, organized into one or more solutions. It has no parent (`parent: None`) and no type-specific attributes beyond those shared by all components.

#### Model

A model represents a hydrologic process. Models are managed and solved by the simulation.

##### Type-specific attributes

###### `solution`

MF6 supports different solution schemes: implicit solutions (solve systems of coupled equations iteratively) and explicit solutions (used when closed-form solutions are available). A model declares which solution type it requires with the optional `solution` attribute. The supported solution types are `"ims"` and `"ems"` (full solution names `"sln-ims"` and `"sln-ems"` are also permitted). Solution packages do not redundantly declare which model types they support; compatibility is determined entirely from the model side.

#### Package

A package is any component that is not a simulation or a model.

##### Type-specific attributes

###### `multi`

Components of which multiple instances are allowed are called "multi-packages". Optional attribute `multi`, defaulting false, indicates that a component is a multi-package.

###### `subtype`

Optional discriminator indicating the package's functional role. Several package subtypes may be distinguished: solutions, exchanges, stress packages, advanced packages, and utility packages.

- `"solution"`: provides solving capability for models. Compatibility with a model is determined by the model's `solution` attribute.
- `"exchange"`: connects two models, enabling them to share boundary conditions or state at their interface. Parent is the simulation.
- `"stress"`: imposes boundary conditions on a model. Period data is provided per stress period; each period block replaces the full set of stresses for that period.
- `"advanced"`: an advanced stress package. Differs from `"stress"` in three key ways:
  1. Solves a continuity equation. Each feature (well, reach, lake cell, UZF cell) internally balances inflows, outflows, and change in storage. Traditional stress packages impose static conditions and do not have an internal water budget. **Note:** advanced packages can act as receivers in the Water Mover (MVR/MVE) package because they have an internal continuity equation to receive diverted water into. Traditional stress packages cannot.
  2. Has dynamic state variables. Advanced packages compute a dependent variable (e.g., lake stage, well head, reach stage) that is part of the solution. Traditional stress packages use fixed/user-specified values.
  3. Stress periods have feature replacement rather than block replacement semantics: when a new period block configuration is provided, traditional stress packages replace the entire previous configuration; advanced packages perform partial updates, modifying only features explicitly appearing in the new period block. **Note:** both simple and advanced packages fill-forward across omitted stress periods; the distinction is only in what happens when a new period block configuration is specified.
- `"utility"`: an auxiliary package that may be attached to models or packages, such as time series, time-array series, or observations. Utility packages (`utl-*`) are distinguished from primary model input packages by providing configurational or cross-cutting concerns rather than representing a first-class hydrologic process. They may support `multi` and `variant_of`; they never have `subtype` `"solution"`, `"exchange"`, `"stress"`, or `"advanced"`.

`subtype: None` (the default) covers packages that don't fall into any named category, such as output control packages.

###### `variant_of`

Some modules may be represented by several different components: e.g., typical stress packages define period data sparsely as a list, while layer- and grid-array variants allow providing period data as arrays.

A package may signal that it has equivalent functional semantics as another component with the `variant_of` attribute. This attribute is only meaningful on packages (including utility packages); variants of models or simulations are not supported.

## Blocks

A block is group of related fields, essentially a product type. Record fields are also product types; the distinction is that records occupy a single line in MF6 input files, while blocks are multiline constructs delimited by headers, e.g.

```
begin <block name>
   field1 value
   field2 value
end <block name>
```

Blocks are treated differently depending on the structural composition of their top-level fields. The sample above is typical of a block containing configuration options, which is essentially a dictionary mapping field names to values.

A field's value need not be preceded by its name; see the `tagged` section below. Tagged fields must precede any and all untagged fields in the block definition and consequently in input files.

### Attributes

#### `name`

The block's name. Required. This is the identifier used in `begin <name>` / `end <name>` delimiters in MF6 input files.

#### `fields`

The block's fields, in definition order. A block may have no fields (empty block).

#### `repeats`

`bool = False`. Whether the block may appear multiple times in an input file. When true, each occurrence is read independently, and associated with a unique label. The canonical repeating block is the period block, whose label is the stress period number.

#### `optional`

`bool = False`. Whether the block may be omitted entirely from the input file. An absent optional block is treated as empty.

## Fields

A field is a [tagged union](https://en.wikipedia.org/wiki/Tagged_union) of concrete data types, discriminated by a `type` attribute. A field consists of a set of attributes, some shared, some type-specific.

Field definitions are not entirely self-contained. Some fields may refer to other fields, in the same component or in another. There are two cases of this:

- array dimensions
- list primary/foreign keys

These cases are associated with type-specific attributes described below.

### Shared attributes

There is a core set of attributes shared by all field types:

- `name`
- `type`
- `longname`
- `description`
- `optional`
- `default`
- `developmode`

#### `name`

The field's name.

#### `type`

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

#### `longname`

A longer, more descriptive name. From the [NetCDF conventions](https://docs.unidata.ucar.edu/nug/current/attribute_conventions.html#long_name). May contain spaces.

#### `description`

A detailed description of the field.

#### `optional`

Indicates that the field is not mandatory and may be omitted. May be applied to both composite and scalar fields.

#### `default`

The field's default value. Only relevant for optional fields. TODO: determine whether to keep. MF6 doesn't read DFN defaults, only flopy does. MF6 implements defaults internally, so care must be taken to keep DFNs in sync, or maybe IDM could read the default from the DFNs.

#### `developmode`

Feature flag indicating that the field is not released yet, only allowed in develop mode builds.

#### `netcdf`

Marks a field that can appear in NetCDF input files.

### Scalars

Scalar fields define a single value.

#### Keyword

Type `keyword`. Represents a boolean choice. In input files, the presence of a keyword indicates true, its absence false.

#### String

Type `string`.

##### Type-specific attributes

###### `tagged`

`bool = False`. Indicates that the field value should be preceded by the field name. Valid only for record subfields.

###### `valid`

`list[str] | None`. Permitted values (enumeration constraint). Empty list is treated as absent.

###### `case_sensitive`

`bool = False`. Indicates that the string's case must be preserved. The MF6 parser uppercases strings by default.

###### `pk`

`bool = False`. Marks this scalar as the primary key of its containing list's item record. Valid only on integer or string scalars that are columns in a list item record. Exactly one column per list item may be marked pk.

###### `fk`

`str | None = None`. Marks this scalar as a foreign key. Valid only on integer or string scalars that are columns in a list item record. Three forms: (1) hierarchical path `"block.field"` or `"component.block.field"` — fully static, used without `fk_ref`; (2) sentinel `"node"` — grid cell reference, used without `fk_ref`; (3) bare block name (e.g., `"packagedata"`) — used together with `fk_ref` to name the block within the runtime-resolved target component, leaving only the pk field to be discovered. See "Primary/foreign keys".

###### `fk_ref`

`str | None = None`. For FKs whose target component is only known at runtime. Names a sibling string field whose value identifies the target component. May be set alone (block within target also unknown) or together with `fk` as a bare block name (block known, component not). See "Primary/foreign keys".

#### Integer

Type `integer`.

##### Type-specific attributes

###### `tagged`

`bool = False`. Indicates that the field value should be preceded by the field name. Valid only for record subfields.

###### `valid`

`list[str] | None`. Permitted values (enumeration constraint). Empty list is treated as absent.

###### `dimension`

`bool = False`. Marks a valid target for shape expressions; enables shape validation at schema load time. Fields in `dimensions` blocks are primary candidates, but some `options` scalars also qualify (e.g. `naux`).

###### `time_series`

`bool = False`. Marks fields where the parser accepts either a numeric literal or a time-series name (referencing a `utl-ts` object). Not inferrable from structural type. Also appears on array fields (where it references a `utl-tas` object instead). Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.

###### `pk`

`bool = False`. Marks this scalar as the primary key of its containing list's item record. Valid only on integer or string scalars that are columns in a list item record. Exactly one column per list item may be marked pk.

###### `fk`

`str | None = None`. Marks this scalar as a foreign key. Valid only on integer or string scalars that are columns in a list item record. Three forms: (1) hierarchical path `"block.field"` or `"component.block.field"` — fully static, used without `fk_ref`; (2) sentinel `"node"` — grid cell reference, used without `fk_ref`; (3) bare block name (e.g., `"packagedata"`) — used together with `fk_ref` to name the block within the runtime-resolved target component, leaving only the pk field to be discovered. See "Primary/foreign keys".

###### `fk_ref`

`str | None = None`. For FKs whose target component is only known at runtime. Names a sibling string field whose value identifies the target component. May be set alone (block within target also unknown) or together with `fk` as a bare block name (block known, component not). See "Primary/foreign keys".

#### Double

Type `double`.

##### Type-specific attributes

###### `tagged`

`bool = False`. Indicates that the field value should be preceded by the field name. Valid only for record subfields.

###### `time_series`

`bool = False`. Marks fields where the parser accepts either a numeric literal or a time-series name (referencing a `utl-ts` object). Not inferrable from structural type. Also appears on array fields (where it references a `utl-tas` object instead). Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.

#### Path

Type `path`.

##### Type-specific attributes

###### `mode`

`Literal["filein", "fileout"]`. Whether the path is to an input or output file.

### Composites

Three kinds of composite type are relevant to MF6: [product](https://en.wikipedia.org/wiki/Product_type) (record), [sum](https://en.wikipedia.org/wiki/Tagged_union) (union), and collection (array, list).

Composite fields are explicitly nested so that the composite structure is reflected in the schema. Product and sum types have multiple nested subfields. Lists have a single nested subfield. Arrays have no nested subfields; see below.

#### Array

Type `array`.

Arrays are not proper composites. An array does not have an item subfield as does a list. Instead, it has a `dtype` attribute identifying its scalar element type. An array may not contain composite elements; `dtype` must be a scalar type.

##### Type-specific attributes

###### `dtype`

`str`. The array's data type. Must be one of the scalar types.

###### `shape`

`list[str]`. The array's shape. Each element is a shape expression — either a global dimension name (explicit or derived; see [Array dimensions](#array-dimensions)) or a row-level column lookup (see [Row-level column lookups](#row-level-column-lookups)). The latter form is only valid when the array is a subfield of a record.

###### `time_series`

`bool = False`. Marks fields where the READARRAY invocation may be replaced by a TAS name referencing a `utl-tas` time-array series object. At any model time, the TAS provides an interpolated grid-shaped array. Distinct from the scalar case: references `utl-tas`, not `utl-ts`. Note that `utl-tas` currently only works with layered arrays, not full-grid arrays, though generalizing has been considered.

###### `repeat`

`str | None = None`. Names the field (within the same component) whose runtime length determines how many times this field is read sequentially within an array block, with each reading appended to an accumulated sequence. See `repeat` section below.

#### Record

Type `record`. Product type. In MF6 input files, records appear on a single line. Record subfields may or may not be `tagged`. While blocks can be considered product types also, in the DFN specification only records are considered fields; blocks are considered named collections of related fields.

##### Type-specific attributes

###### `fields`

`dict[str, Scalar | Array | Record | Union]`. Subfields, required.

**Note:** An array appearing as a subfield of a record is read inline on the same line, not in the READARRAY format. If the array's `shape` uses a row-level column lookup, the record is effectively a variadic tuple: its width varies per row as determined by a column in a FK-linked list. See [Row-level column lookups](#row-level-column-lookups).

**Note:** if a nested record appears inside another record, the inner record's contents should appear inline inside the outer record's contents, on the same line.

#### Union

Type `union`. Sum type.

##### Type-specific attributes

###### `arms`

`dict[str, Scalar | Record]`. Subfields, required.

**Note:** 

#### List

Type `list`. Collection type. Unlimited but for one rule: a list may not contain another list. Lists are distinct from arrays in two ways: a list element may be a composite type and a list admits sparse representations.

##### Type-specific attributes

###### `item`

`Record | Union`. Subfield (item type), required.

### Array dimensions

A scalar integer field defined in one component can be referenced by name in the `shape` expression of an array field in the same or another component.

Shape expressions may only use one of three recognized forms:

- **Explicit dimensions**: integer scalar fields marked `dimension=True`. Fields in `dimensions` blocks are primary candidates; some `options` scalars also qualify (e.g. `naux`).
- **Derived dimensions**: dimensions not present as explicit DFN fields but computable from other fields. Declared with the component attribute `derived_dims` (see below).
- **Row-level column lookups**: per-row quantities of the form `block.column(fk_field)`, valid only for array subfields of records. Not resolvable globally; evaluated per record row at parse time. See below.

A shape expression that does not match one of these forms is a schema validation error.

#### Derived dimensions

The optional component attribute `derived_dims` maps dimension names to expressions with which to evaluate the dimension size. Expressions use Python arithmetic syntax. Operands may be:

- Explicit dimensions: any `dimension: true` field in this component
- Derived dimensions: another derived dimension; circular dependencies are a schema error
- Functions of columns in a tabular list block: `sum(block.list.column)` sums the integer values of `column` across all rows of list field `list` in block `block`. When the list field shares its name with its containing block — the MF6 convention — the block qualifier may be omitted: `sum(list.column)`.

Canonical examples:

```yaml
# gwf-dis
nodes: "nlay * nrow * ncol"

# gwf-disv
nodes: "nlay * ncpl"

# gwf-lak
total_lake_connections: "sum(packagedata.nlakeconn)"

# gwf-evt
nseg_minus_1: "nseg - 1"
```

#### Row-level column lookups

An array appearing as a subfield of a record may have its size determined per row by a value in another list. The shape expression form for this is:

```
block.column(fk_field)
```

where:
- `block` is the name of a list block in the same component
- `column` is an integer column in that list's item record
- `fk_field` is a sibling field in the same record whose `fk` attribute resolves to a PK in `block`

This notation is consistent with FK path conventions (`block.field` for within-component references). The parenthetical `(fk_field)` serves as the row selector, distinguishing this form from a derived dimension expression over the same path. Cross-component references extend the path naturally to `component.block.column(fk_field)`.

Validation rules:
- `fk_field` must be a sibling field in the same enclosing record
- `fk_field`'s `fk` attribute block portion must match `block`
- `column` must exist in `block`'s item record and be of type `integer`
- This form is only valid when the array is a subfield of a record; it is a schema error on a top-level array field

Unlike derived dimensions, row-level lookups are not pre-computable at load time. They are evaluated per row during parsing.

Canonical example — `gwf-sfr.connectiondata.ic`, whose length varies per reach according to the `ncon` column in `packagedata`:

```yaml
packagedata:
  type: list
  item:
    type: record
    fields:
      ifno:
        type: integer
        pk: true
      ncon:
        type: integer
      # ...

connectiondata:
  type: list
  item:
    type: record
    fields:
      ifno:
        type: integer
        fk: "packagedata.ifno"
      ic:
        type: array
        dtype: integer
        shape: ["packagedata.ncon(ifno)"]
```

`packagedata.ncon(ifno)` means: follow `ifno`'s FK to identify the `packagedata` row, then read `ncon` from it. Each `connectiondata` row has a different number of `ic` values. The `ic` array is read inline on the same line as the rest of the record, making the record a variadic tuple.

#### Scope and resolution

Shape expressions resolve in this order:

1. Local explicit dims: `dimension: true` fields in this component
2. Local derived dims: entries in this component's `derived_dims`, resolved in dependency order
3. Inherited dims: dims defined in the parent component's context

Row-level column lookups are not resolved via this scope chain. They are evaluated per record row at parse time, using the FK relationship declared on the referenced sibling field.

### Primary/foreign keys

Sometimes a column in one list identifies a row in another list, or a grid cell. This can be conceptualized as a primary key (PK) / foreign key (FK) relation. Integers and strings may encode PK/FK semantics with attributes `pk`, `fk`, and `fk_ref`.

**Note**: PK/FK attributes are only valid on integer and string fields, and only fields appearing as columns in a list item record type.

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
| `gwf-sfr.connectiondata.rno` | — | `"packagedata.rno"` | — | FK; also row selector for ic's shape lookup |
| `gwf-sfr.connectiondata.ic` | — | — | — | inline array; `shape: ["packagedata.ncon(rno)"]`; elements are signed reach refs (sign encodes upstream/downstream direction) |
| `gwf-sfr.period.rno` | — | `"packagedata.rno"` | — | within-component |
| `gwf-mvr.packages.pname` | `True` | — | — | string PK of the package list |
| `gwf-mvr.period.pname1` | — | `"packages.pname"` | — | string FK, within-component |
| `gwf-mvr.period.id1` | — | `"packagedata"` | `"pname1"` | component resolved from pname1; codec finds unique pk in packagedata |
| `utl-obs.continuous.id` (string arm) | — | — | `"obstype"` | **Open:** target block varies by package type; codec must handle case-by-case |
| `utl-obs.continuous.id` (integer arm) | — | `"node"` | — | grid cell reference |
| `gwf-wel.period.cellid` | — | `"node"` | — | grid cell reference |
