## Recommended steps

### Step 1: Audit and trim the `Field` base class

Go through each attribute on `Field` and decide whether it belongs on the base (all versions), `FieldV1` only, or `FieldV2` only. Move v1-specific attrs down to `FieldV1`. After this, `FieldV2` should be able to add or override attributes explicitly rather than inheriting everything and defining nothing.

### Step 2: Write a formal v1→v2 transform spec

A document (probably in `modflow-devtools/docs/md/dev/`) that lists every transform rule explicitly — type renames, attribute removals, structural changes — with examples. The "current transforms" section above is a starting draft. Convert every "implicit" row in the attribute table to an explicit decision, and add the corresponding code to `MapV1To2` where it's missing. This document becomes the spec that both the transform code and downstream consumers can be checked against.

### Step 3: Fill in `FieldV2`

Once steps 1–2 are settled, `FieldV2` should positively define the v2 attribute set. This means resolving the open questions above as part of v2 itself — not deferring them to a future version:

- **Pydantic**: Switch schema classes to pydantic models (open question 3). This gives JSON Schema export for free, satisfying the formal specification requirement from pyphoenix issue #246.
- **Structural/format scope separation**: The structural schema describes what a variable *is*; how it is read from or written to a file is a separate, format-layer concern. Two main consequences:
  - v1 field attributes that are purely format concerns — `reader`, `tagged`, `preserve_case`, `layered`, `time_series`, `repeating` — do not belong in the v2 structural schema. Rather than a separate `FormatSpec` object, format annotations are co-located as typed attributes on the relevant type-specific field subclasses (`ScalarFieldV2`, `ArrayFieldV2`). `jagged_array` is dropped entirely (not a structural property; Python codec concern only). `tagged` is derivable and dropped. `preserve_case` is dropped under the always-preserve-case policy. `string` fields with `time_series=true` are retyped as `double` in the structural transform, with `time_series=True` retained on the v2 field. See `dfn_format_rules.md` for the full attribute lifecycle table.
  - Period block data is the canonical example of format obscuring structure. v1 encodes it as a `recarray` with a `cellid` column because MF6 reads it as a sparse `(cell, value...)` list. Structurally, each column is a distinct variable defined over a spatial subset of the grid with a shape determined by grid type and time dimension. `MapV1To2.map_period_block()` already does this expansion correctly; the v2 schema should make the distinction principled rather than a special-case transform.
- **Explicit parent-child hierarchy**: Parent-child relationships should be first-class in the schema. Rather than a single `FieldV2` class with a generic `children: Fields | None` dict (whose semantics depend on the parent's `type` string), introduce type-specific pydantic model subclasses, each with typed child attributes:
  - `ScalarFieldV2` — `keyword`, `integer`, `double`, `string`; no children
  - `ArrayFieldV2` — scalar type with a shape; no children
  - `RecordFieldV2` — has `fields: dict[str, FieldV2]` (named columns, required)
  - `ListFieldV2` — has `item: RecordFieldV2 | UnionFieldV2` (row type, required)
  - `UnionFieldV2` — has `arms: dict[str, FieldV2]` (named alternatives, required)

  With pydantic, `type` becomes the discriminator for a top-level union alias: `FieldV2 = Annotated[ScalarFieldV2 | ArrayFieldV2 | RecordFieldV2 | ListFieldV2 | UnionFieldV2, PydanticField(discriminator="type")]`. Invalid states (e.g. a `list` with `arms` set) become unrepresentable. The `type` attribute is already present in the TOML format, so no serialization change is needed.

- **Component relationship graph**: Parent-child relationships are intrinsic to a component's identity and stay on `Dfn`. `Dfn.parent: str | None` declares a fixed parent (e.g. `gwf-chd` always under `gwf-nam`). `Dfn.accepts: list[str]` declares which subpackage types a parent can contain (replaces `subcomponents`). A subpackage with no declared parent is a "free" subcomponent — the parent signals compatibility via `accepts`, and the edge is resolved at simulation instantiation time. `DfnSpec` provides traversal and lookup methods but does not own the relationship data.

These are goals for v2 — the schema is not finalized until they are addressed.

### Step 4: Audit pyphoenix-project's codec against the formal spec

`structure.py`, `unstructure.py`, and `TypedTransformer` all make assumptions about what a v2 field looks like. Once there is a formal spec, audit these against it and fix any discrepancies.

Note: `dfn2lark.py` imports from the v1.1 module (`modflow_devtools.dfn`) intentionally — grammar generation is a format concern and should remain on v1.1. It is not a migration candidate for this step.
