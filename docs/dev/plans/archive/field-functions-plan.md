# flopy4: one field function per DFN field type

**Archived 2026-10-19.** Done: merged as #463 ("Replace spec.field() with a function per field type"). Follow-up work is in [`record-unify.md`](../lists/record-unify.md).

Repo: pyphoenix-project (flopy4). Base: `origin/develop` (833753b9 at time of writing).
Work in a new worktree: `.claude/worktrees/field-functions`, branch `field-functions`.
Leave `pyphoenix-project-item-decorator` (8f606e3d, unpushed) alone; this plan replaces it.

## Decision

Replace the catch-all `flopy4.mf6.spec.field()` (~28 kwargs) with one function
per **DFN v2 field type** (`modflow_devtools/dfns/schema.py`), each taking the
attributes that type has in the schema. No class decorator / `field_transformer`.
No package-vs-item split: the schema doesn't have one, and an item field isn't
necessarily a "column" (items can be irregular: unions, keystrings, varying
width). Where a field sits is just whether it has a `block`.

Why:

- `field()` runs before attrs attaches the annotation, so it can't see the
  type. Today the generator restates the kind as flags (`array=True`,
  `arms=True`) so `field()` can pick eq / converter / on_setattr. If the
  function *is* the kind, it picks all of that itself at definition time.
- Rejected: inferring kind from the hint in a `field_transformer` (`@item`,
  8f606e3d):
  - `field_transformer` isn't inherited, so every row class must remember the
    decorator; forgetting it fails silently.
  - Hints are ambiguous: `tuple[int, ...]` is an int array (OC `steps`) but a
    cellid inside OBS's `Union[tuple[int, ...], int, str]`; a scalar cellid is
    a bare `tuple`; "union with arm classes" == "annotation is a string".
  - Behaviour split across field() + transformer + hint; needs
    `@dataclass_transform` re-declared.
  - Nothing it does needs the annotation at definition time: `to_union_arm`
    already resolves arms lazily (`takes_field=True`, `_union_field_arms`).
- Mirroring the schema makes codegen a near 1:1 mapping (DFN type → function,
  schema attributes → kwargs), and the vocabulary is the one the DFNs already
  use.
- The hint stays for type checkers and users. Schema attributes that only
  restate the Python type (e.g. `Array.dtype`) are left to the hint; everything
  else (direction, cellid model, index, pk/fk, shape, layered, ...) is a kwarg.

## One `shape`, as in the schema

The schema has a single `shape: list[str]` on both `Array` and `List`
(`[]` = unsized). Do the same; no separate `count`:

- grid array: `shape=("nlay", "nrow", "ncol")`
- inline array in an item: `shape=("auxiliary",)`, `("nseg-1",)`,
  `("packagedata.ncon(ifno)",)`. item.py already tells sibling-field /
  package-dim / lookup sizing apart from the expression
  (`_sized_by_field/_package/_lookup`).
- unsized: `shape=()` (or omitted) — rest of the row in an item (OC/PRP
  `steps`, PRP `fraction`). No sentinel needed because `array()` itself says
  it's an array.
- list: `shape=("nodes",)` replaces today's `dim="nodes"` (disu `cell2d`;
  the dim counting the rows; TDIS `nper` via `linked_dim`).
- cellid, as in the schema: shape starts with `ncelldim`. One cellid:
  `array(cellid="1", index=True, shape=("ncelldim",))`; cellids:
  `shape=("ncelldim", "numalphaj")`. So "one vs many" is `len(shape)`, not a
  flag. flopy4 already knows `ncelldim` as a shared dim
  (`gwe/dis.py shared_dims`, `LoadContext.ncelldim`, `item.infer_ncelldim`).
  Check how item.py's cellid width inference keys off this before switching.

## API (flopy4/mf6/spec.py)

Common to all (the schema's `InputFieldBase` + attrs): `default`, `validator`,
`converter`, `repr`, `eq`, `init`, `metadata`, `on_setattr`, `alias`,
`longname`, `optional`, `block` (set ⇒ a block-level field; unset ⇒ a field
of an item/record). Keep private hooks (`_recount`, `_check_dim`) and
converters (`to_ts_value[s]`, `to_signed_indexes`, `to_union_arm`,
`coerce_child`).

| function | schema type | kwargs | behaviour |
|---|---|---|---|
| `keyword()` | Keyword | — | bool flag; today's `tagged` metadata on items/records, plain bool option on packages |
| `string()` | String | `time_series`, `pk`, `fk` | `time_series` → `to_ts_value` |
| `integer()` | Integer | `index` (`True`/`"signed"`), `pk`, `fk`, `time_series` | `block == "dimensions"` → `_check_dim` hook (as today) |
| `double()` | Double | `time_series` | `time_series` (no block) → `to_ts_value` |
| `array()` | Array | `shape`, `layered`, `netcdf`, `index`, `fk`, `cellid`, `time_series`, `fill_forward` | see below |
| `list_()` (or `spec.list` via module namespace) | List | `shape`, `fill_forward` | list of Items (today `field(block=..., dim=..., eq=...)`) |
| `union()` | Union | `*kinds` | with kinds: token-level union (today `union=("cellid", "index", "string")`); without: arm-class union, converter `to_union_arm` (today `arms=True`) |
| `file()` | File | `direction`, `keyword` | today's `path()`, renamed to match the schema |
| `child()` | File → component | `direction`, `keyword` | as now |
| `record()`? | Record | — | nested record refs (`package.py.jinja` ~61–63 use plain `attrs.field`); only add if it carries something |

`array()` behaviour:

- Always `eq=ARRAY_EQ`, block-level or not. The tuple exception
  (`eq = ARRAY_EQ if shape and not array`) came in with #406 (count= →
  shape=), when "has a shape" stood in for "is numpy"; it isn't needed.
  Checked `array_eq` on tuple values: empty, nested (cellids), mixed with
  `TimeSeriesRef` objects and different lengths all behave like tuple `==`.
  Differences: NaNs compare equal (better), and **int vs float is unequal**
  (`(1, 2)` vs `(1.0, 2.0)`: tuple True, array_eq False, from its dtype
  check). That matters for item arrays without a converter (PRP `fraction`,
  GNC `alphasj`: user ints vs parsed floats). Fix in `array_eq`: compare
  numeric values regardless of int/float dtype for non-ndarray inputs (or
  generally, if no test relies on strict dtype), rather than special-casing
  at declaration. Run the tests both ways.
- `time_series`: block-level = time-array series name, no converter; in an
  item → `to_ts_values`. Still keyed on `block`, but that's what the name
  refers to, not a representation difference.
- `index="signed"` → `to_signed_indexes`; a single-name shape that's a
  sibling field → `_recount(name)` piped into on_setattr.
- Values stay numpy at block level and tuples in items; unifying the
  representation is out of scope, but equality no longer depends on it.

Open naming points (decide while implementing):

- List function: `list_()`, or `spec.list(...)` through the module
  namespace — either is fine (user). Pick whichever reads better in the
  generated modules.
- Decided: `path()` → `file()`.
- `keyword` metadata key: keep `"tagged"` to limit churn, or rename.

`fill_forward`, `write_if_empty`, `schema`, `repr=False`: grep generated code
for which types use them; put each only on those functions.

## Metadata changes

- Drop `"array"` (the function is `array()`; store `"type": "array"` or test
  `"shape" in metadata` — pick one helper and route consumers through it).
- Item arrays keep `"shape"` (unchanged key; now also `()` for unsized).
- Cellids: `"shape"` gains the leading `"ncelldim"`; consumers that do
  `metadata["shape"][0]` for the count must skip it. Helper e.g.
  `_count_expr(f)` in item.py.
- Lists: `"dim"` → `"shape"`. Consumers in package.py, component.py,
  structure.py — grep `"dim"`.
- `"signed"` → `"index": "signed"` (as in the schema); `to_tokens` etc.
  check `index == "signed"`.
- Unchanged: `block`, `layered`, `netcdf`, `fill_forward`, `time_series`,
  `index`, `pk`, `fk`, `cellid`, `union`, `optional`, `direction`,
  `_keyword`, `child`.

Consumers (metadata reads on develop, excluding codegen): item.py 31,
package.py 22, structure.py 13, spec.py 11, record.py 7, netcdf.py 5,
attrs_xarray.py 4, unstructure.py 2, component.py 1, load_context.py 1.
Row-array logic is mostly item.py: `construct_item`, `to_tokens`,
`from_tokens` (~line 697 `array_fields`), `_shape_dim`,
`_sized_by_field/_package/_lookup`, `_dim_counted`, `_count`,
`package_sized_fields`, `sized_by`, `_array_elem_type`. Don't disturb
package-array `shape` reads (package.py, netcdf.py, structure.py).

## Codegen (flopy4/mf6/utils/codegen)

Aim: dispatch on the DFN field type and pass schema attributes through.

- filters.py item emitters → schema functions:
  `attr_column` (generic, `rhs=f"field({margs})"`; take the function name),
  `value_column` → `double/integer/string`, `feature_id_column` →
  `integer(index=True, pk=/fk=)`, `union_column` → `union(...)`,
  `array_column` → `array(...)` (cellid shape gains `ncelldim`; fix the bare
  `tuple` annotation fallback), `class_union_column` → `union()`, scalar
  cellid (`tuple = field(cellid="1")`) → `array(cellid=..., index=True,
  shape=("ncelldim",))`. `file_column` → `file(...)`, `child_column` unchanged.
  Consider renaming these `*_column` helpers while there, since "column" is
  wrong for irregular items.
- filters.py package emitters: `field_metadata` + `field_call` (~547, 635)
  pick the function from the DFN type; drop the explicit `eq=ARRAY_EQ` line;
  lists: `dim=`/`linked_dim` → `shape=`. make.py:400 calls `field_call`.
- templates/package.py.jinja ~61–85: `attrs.field(metadata={"tagged": True})`
  → `keyword()`.
- Generated imports: only the functions used (check how the template builds
  the `from flopy4.mf6.spec import ...` line).

## Steps

1. Worktree + branch off `origin/develop`.
2. spec.py: add the schema functions alongside `field()`; keep `field()`
   working meanwhile.
3. item.py and other consumers: helpers for array-ness / count / signed,
   cellid `ncelldim`, list `shape`; switch reads.
4. Codegen: emit the new functions.
5. Regenerate classes against the same DFN version develop's classes were
   made from (check `flopy4 mf6 status` / sync metadata first;
   `pixi run generate-classes` targets modflow6@develop and may pull
   unrelated drift). `git diff --stat`: expect only field-call lines and
   imports.
6. Remove `field()` (or reduce it to nothing) once generated and hand-written
   code no longer use it. Fix hand-written uses and tests
   (`test/mf6/test_mf6_codegen.py` asserts on `array=True`/`arms=True`).
   Same for `path()` → `file()`: grep hand-written modules (e.g.
   `gwe/__init__.py` netcdf files) and codegen (`field_call`'s `fn = "path"`,
   `file_column`, make.py ~471).
7. mypy: the attrs plugin doesn't see our wrappers as field specifiers (see
   comment in `attr_column`); confirm no regression, and only if needed add
   `@dataclass_transform(field_specifiers=...)` on base classes.
8. Test: `pixi run test`, mypy, ruff. Compare with develop for pre-existing
   failures.
9. Local commits only (don't push): (a) spec functions + consumers,
   (b) codegen + regenerated classes, (c) remove `field()` kwargs /
   `field()`, (d) list `dim` → `shape` if it's big enough to separate.
   Messages end with the Co-Authored-By line.

## Not in scope

- Inferring anything from type hints.
- Unifying numpy (package) vs tuple (item) array representations (equality
  is unified; see `array()`).
- modflow-devtools DFN schema changes.

## Outcome (implemented on `field-functions`, local commits only)

728ba10c array_eq, fc526076 field functions + codegen + regenerated classes,
09a17e2b remove field()/path(). Deviations from the plan:

- `array_eq`: ints vs floats compare by value only for tuples/lists; ndarrays
  still need equal dtypes (`test_eq_array_dtype_and_shape_matter` relies on it).
- Lists: `list_(shape=...)` is the kwarg, but the metadata key stays `"dim"`.
  Several package-level consumers treat any `"shape"` as an array
  (`attrs_xarray._period_dim`, attrs_xarray:213, unstructure:295), so a list
  carrying `"shape"` would be misread.
- Every function records `metadata["type"]` (DFN type name); item.py's
  `_is_array` reads that (minus single cellids) instead of `"array"`.
- Record classes' inner fields (package.py.jinja) still use plain
  `attrs.field(metadata={"tagged": True})`; they never went through `field()`
  and a tagged record value isn't necessarily a Keyword. Left alone.
- File lists (`ts_file: list[Path]`) use `file()` (they need direction/keyword).
- `keyword()` always sets `tagged`, as the schema derives it; harmless at
  package level (only read for dict-valued arrays there).
- Regenerated from local modflow6 at 524d1ace; LAK/MAW (and gwf-lak.lark)
  drift under the newer devtools, so only the codegen delta was applied to them.
