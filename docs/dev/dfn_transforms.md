## Current transforms (v1 → v2), as implemented

These are the rules currently encoded in `MapV1To2`. They are the closest thing to a formal spec that exists.

### Type system

| v1 type | v2 type | Notes |
|---|---|---|
| `double precision` | `double` | rename |
| `recarray` | `list` | structural: recarray becomes a `ListFieldV2` with a typed `item` |
| `keystring` | `union` | structural: keystring becomes a `UnionFieldV2` with named `arms` |
| `record` | `record` | becomes `RecordFieldV2` with typed `fields` |
| `keyword`, `integer` | same | becomes `ScalarFieldV2` |
| `string` (no `time_series`) | `string` | becomes `ScalarFieldV2` |
| `string` + `time_series=true` | `double` | format artifact: declared `string` in v1 to allow TS name or numeric literal; structurally `double` with `time_series=true` in the format layer |
| scalar with `shape` != None | `array` | becomes `ArrayFieldV2` |

### Attribute lifecycle

`MapV1To2` removes `in_record`, `tagged`, and `preserve_case` explicitly (via a `remap` visitor). All other v1 attributes are handled implicitly: `FieldV2.from_dict` only accepts keys that match `Field`'s annotations, so any v1 attribute not present on `Field` is silently dropped. This means the v2 attribute set is currently defined by what `Field` happens to declare, not by a conscious per-attribute decision.

| v1 attribute | v2 fate | How decided | Notes |
|---|---|---|---|
| `in_record` | **dropped** | explicit (`remap` visitor) | structural artifact; children now explicit via typed attributes (`fields`, `item`, `arms`) on type-specific subclasses |
| `tagged` | **→ format layer (derived)** | explicit (`remap` visitor) | derivable from block `input_style` + field position; not stored explicitly — the format layer reconstructs it from block style and structural position |
| `preserve_case` | **→ format layer** (`FieldFormat.preserve_case`) | explicit (`remap` visitor) | universally true for filename strings; never appears on non-filename strings |
| `default_value` | renamed → `default` | explicit (popped in `_map_field`) | |
| `reader` | **→ format layer** (`BlockFormat.input_style`) | should be explicit | determines block input style; two values: `urword` (keyword-value/table) and `readarray` |
| `layered` | **→ format layer** (`FieldFormat.layered`) | should be explicit | exclusively on griddata arrays; per-layer READARRAY |
| `mf6internal` | **dropped** | implicit | code-gen hint; not a schema concern |
| `block_variable` | **dropped** | implicit | period-block marker; handled structurally by `map_period_block` |
| `time_series` | **→ format layer** (`FieldFormat.time_series`) | should be explicit | fields with `type=string` + `time_series=true` are retyped as `double` in the structural schema (see type system table) |
| `jagged_array` | **→ format layer** (`FieldFormat.jagged_array`) | should be explicit | DISU `connectiondata` only; value is name of counter array (`iac`) |
| `repeating` | **→ format layer** (`FieldFormat.repeating`) | should be explicit | field may appear multiple times (values appended); 3 occurrences total |
| `numeric_index` | **decision pending** | implicit | needs decision: structural (affects index interpretation) or annotation layer? |
| `deprecated`, `removed` | **keep in structural schema** | should be explicit | metadata flags, not format or codegen concerns |
| `just_data` | **dropped** | implicit | |

The implicit drops are not wrong in practice, but they are undocumented decisions. Formalizing means converting each "implicit" row into an explicit, documented choice — either confirming the drop (and making it explicit in the transform code) or deciding to retain/relocate the attribute.

### Structural transforms

- **Period block recarrays**: A period block containing a single `recarray` is expanded into individual array variables, one per column. `cellid` is consumed to add `nnodes` to the shape. `maxbound` is dropped from shape. New shape: `(nper[, nnodes][, ...remaining dims])`.
- **Record children**: v1 encodes record fields inline as separate top-level variables with `in_record = True`. v2 nests them in `RecordFieldV2.fields: dict[str, FieldV2]`.
- **Union choices**: v1 encodes keystring alternatives as separate `in_record` variables. v2 nests them in `UnionFieldV2.arms: dict[str, FieldV2]`.
- **List item**: v1's `recarray` + inline `in_record` fields become a `ListFieldV2` with `item: RecordFieldV2 | UnionFieldV2` as the row type.
- **Time-series string fields**: Fields with `type=string` and `time_series=true` in v1 are structurally `double` — they are declared `string` in v1 only to bypass numeric validation, since the parser must accept either a numeric literal or a time-series name. The v1→v2 transform should retype these as `double` (a `ScalarFieldV2` or `ArrayFieldV2`) and move `time_series=true` to the format layer.

## Format variation catalog

Based on an exhaustive survey of the MF6 DFN files, these are all the format variations present.

### Block-scoped input styles

| Block name | Input style | Notes |
|---|---|---|
| `options`, `dimensions`, `linear`, `nonlinear`, `solutiongroup` | keyword-value | Each field is a tagged keyword or record |
| `griddata` | READARRAY | Each field is a separate READARRAY invocation; exclusively this block |
| `connectiondata` (DISU only) | READARRAY | Uses jagged arrays keyed by `iac`; all other packages use table |
| `period` (sparse) | sparse list (`urword`) | Classic stress packages: `(cellid, value...)` rows per period |
| `period` (array-based) | READARRAY per field | `gwf-evta`, `gwf-rcha`, and the `-g` suffix packages (`gwf-chdg`, `gwf-drng`, `gwf-ghbg`, `gwf-rivg`, `gwf-welg`, `utl-spca`); spatially complete arrays rather than sparse lists |
| `packagedata`, `vertices`, `cell2d`, `exchangedata`, `gncdata`, etc. | table | Recarray of rows; `urword` reader |
| all other named blocks | table or keyword-value | `urword` reader |

### Field-scoped format annotations

Five v1 attributes are genuine field-level format annotations that cannot be inferred from block type or structural type:

| Attribute | Effect | Where | Notes |
|---|---|---|---|
| `layered` | Per-layer READARRAY input | `griddata` integer/double arrays | Exclusively appears with `readarray` reader; each layer specified as a separate READARRAY section |
| `preserve_case` | No case-folding on string read | Options-block filename strings (`in_record=true`) | Universally applied to filename strings; never appears on non-filename strings |
| `time_series` | Value may be a time-series name | `period` block doubles and strings; some `packagedata` and `outlets` doubles | When `true`, the parser accepts either a numeric literal or a TS name. Fields typed `string` with `time_series=true` are structurally `double` — `string` is used in v1 to bypass numeric validation. The v1→v2 transform should retype these as `double` and retain `time_series=true` in the format layer |
| `jagged_array` | Ragged array; row lengths from a named counter array | DISU `connectiondata` only | Value is the name of the counter array (`iac`); used exclusively with `readarray` reader |
| `repeating` | Field may appear multiple times (values appended) | Tracking times (`prt-oc`, `prt-prp`) and TAS (`utl-tas`) | Very rare; 3 occurrences total |

`tagged` (whether a keyword token precedes a field's value) is mostly derivable from block style and position: `in_record` fields are untagged (positional); top-level fields in `urword` blocks are tagged. Exceptions exist but are few. It is not listed here as a field-scoped annotation because it does not need to be carried explicitly in most cases — the format layer can reconstruct it from block style and the structural field position.
