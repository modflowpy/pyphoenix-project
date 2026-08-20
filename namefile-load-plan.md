# Plan: namefile loading via recursive structuring

## Background

This plan grew out of a review of two things:

1. PR #336 ("decouple xattree from codegen with api changes"), which rewrote
   the codegen-v2 package pipeline (`Package` subclasses: Npf, Ic, Chd, ...).
   It also added a `chunks=` parameter to `Package.load()` that wraps an
   already-eagerly-loaded numpy array in dask post hoc — this provides no
   real streaming/lazy read benefit (confirmed by the PR's own profiling
   comments) and should be removed; the eager `Package.load(path, dims)`
   path itself is worth keeping.
2. PR #284 ("input file loading", branch `load`, open, rough), which
   prototypes recursive namefile loading: `Component.load()` no longer
   manually loops over `self.children`; instead, a namefile's
   `packages`/`models`/`exchanges`/`solutiongroup` blocks are parsed as
   binding records, and a `Binding.to_component()` helper resolves each one
   by looking up its type token in an `FTYPES` registry and recursively
   calling `component_cls.load(path)`. This recursive-via-structuring
   design is good and should be adopted. However PR #284's base predates
   PR #336 by 27 commits — its `structure.py` is written against the old
   xattree-spec system (`get_xatspec`, `xattree.has`, etc.) and can't be
   merged as-is against current `develop`.

## Key correction driving Phase 0

PR #336 introduced a new, ad hoc field-metadata convention for codegen-v2
package fields (`metadata["dfn_block"]`, `metadata["schema"]`,
`metadata["oc_action"]`, detected via `has_dfn_metadata()`/`"dfn_block" in
f.metadata`), distinct from the metadata convention used everywhere else in
the codebase (`metadata["block"]`, set via `flopy4/mf6/spec.py`'s
`field()`/`array()`/`dim()`/`coord()` helpers, which wrap real `xattree`
field descriptors from `flopy4/spec.py`). `Model`, `Simulation`, `Gwf`, and
all other hand-written components still use the `block=` convention; only
the codegen-v2-generated leaf packages deviated.

This spanned both directions of the codec: ingress (`structure.py`'s
`_structure_codegen_v2` reading `dfn_block`/`schema`/`oc_action`), egress
(`unstructure.py`'s `has_dfn_metadata()` branching on which convention a
class uses), and `Package.__attrs_post_init__` (`package.py`) branching on
`"dfn_block" in field.metadata` to decide whether to run v2-specific
post-init logic.

Having two conventions is why a generalized structuring/binding-resolution
step (needed for namefile loading) would otherwise have to understand both.
Rather than build that dual-support permanently, fix the root cause first:
realign codegen-v2 field metadata onto the established `block=`/xattree
descriptor convention. This is a **prerequisite**, not an optional cleanup
— it removes the fork before more code gets built on top of the wrong side
of it.

**Scope/risk note:** 76 generated package files carried `dfn_block`
metadata (all of `gwf/`, `gwt/`, `gwe/`, `prt/`, `utl/`, `exg/` except
`dis`/`disv`/`tdis`/`ncf`, which are hand-written). Fixing the generator and
regenerating touched all of them — needed careful, incremental validation
against `test_mf6_codec.py`, `test_mf6_codegen.py`,
`test_converter_structure.py`, `test_dataframe_api.py`, and
`test_row_api.py` — the test files PR #336 rewrote, since those encoded the
to-be-changed behavior.

---

## Phase 0 — Realign codegen-v2 field metadata onto the `block=` convention

**Status: done.** Landed in `3eda3f9` ("consistent field metadata approach",
#339). One field-metadata convention is now used by every component,
hand-written or generated: `flopy4/mf6/spec.py`'s `field()`/`path()`/
`array()` carry `block=`/`schema=`/`oc_action=` as first-class kwargs.
`dfn_block`/`has_dfn_metadata()` no longer exist anywhere in the tree, and
the ingress/egress/`__attrs_post_init__` dual-path branches described above
are gone — one structuring path, not two. The `chunks=` removal (Background
item 1) landed in the same commit.

---

## Phase 0.5 — Eliminate the `dfn_type` field-metadata key

**Status: done except step 9 (`Column`) — folded into Phase 0.6.** Landed
in the same `3eda3f9` commit as Phase 0. `dfn_type` duplicated information
already recoverable from the Python type hint (scalar fields) or the
`inout` metadata key (file-record fields), so it's gone from `field()`/
`path()` and from codegen. Griddata and READARRAY period fields — the only
two categories ever dask-backed — now type as `IntArrayLike`/
`FloatArrayLike`, a dtype-parameterized structural `Protocol` in
`flopy4/mf6/_types.py` (matches numpy, dask, and any other duck-array type
with no per-library import, unlike the old explicit `Union[NDArray,
da.Array]`). The only remaining `dfn_type` occurrences live inside
`Column`/`Schema` (`flopy4/mf6/schema.py`), which Phase 0.6 removes
wholesale.

---

## Phase 0.6 — Eliminate `Column`/`Schema`; make `Row` the sole row-item
schema, described with `field()` (no new builder)

**Motivation.** Every list/recarray block (packagedata, connectiondata,
period, ...) is currently described **twice** from the same source data:
codegen emits both a `Column`-list `Schema` subclass (a hand-rolled
dataclass-based metadata system) and an `@attrs.define` `Row` nested class
with a hand-generated `__iter__`, from the identical schema dict. E.g.
`gwf/chd.py` carries both a `Row` class and a `_PeriodSchema(Schema)` class
describing the same 3 columns (`cellid`/`head`/`boundname`), with
`Row.__iter__` manually kept in column-order sync with `Schema.columns()`.
Same "two conventions describing one thing" problem Phase 0 fixed for
scalar package fields, just not yet fixed for list-row fields.
`flopy4/mf6/record.py`'s `Record` mixin (used for tagged inline records
like `Ims.Rclose`) already demonstrates the target pattern: one
`@attrs.define` class, metadata-tagged fields, generic
`attrs.fields(cls)`-driven (de)serialization — no parallel schema
description needed.

**Goal:** `Row` (and `PackagedataRow`, `ConnectiondataRow`, etc.) becomes
the *only* description of a list block's columns. `Column`/`Schema` are
deleted. No new field-builder function — Row fields use the *same*
`field()` used everywhere else, extended with a couple of narrow kwargs.
Auditing what `Column`'s attributes (`role`, `dfn_type`, `optional`,
`shape`, `time_series`, `dtype`, `prefix`) actually do — checked against
real usage and occurrence counts, not assumed — shows most are dead,
redundant with the field's own name/type, or a bug:

| `Column` attribute | Occurrences | Disposition |
|---|---|---|
| `role="value"` | 121/182 (66%) | Dropped — the fallback branch everywhere it's read; not a role, the *absence* of one. |
| `role="cellid"` | 18/182 | Dropped — 18/18 occurrences are on a field literally named `cellid` (MF6's own DFN convention reserves that name). Inferred from the field name. |
| `role="boundname"` | 17/182 | Dropped — 17/17 always named `boundname`. Inferred from the field name. |
| `shape` | dead | Dropped — grepped every read site; `col.shape` is never consulted at runtime. `cellid`'s width (`ncelldim`) is always computed dynamically from grid type / token count. |
| `dtype` | buggy | Dropped — confirmed actively wrong: string columns tagged `dtype="np.object_"` get incorrectly typed `Union[float, str]` instead of `str` (e.g. `gwf/buy.py`'s `modelname`). Storage dtype should come *from* the Row field's own annotation via `to_field_type()` (same principle as Phase 0.5), not be a second, independently-settable fact that can drift from it. |
| `prefix` | 5/182 | Dropped as a bespoke string blob. All 5 are file-reference columns where MF6 writes fixed tokens before a filename (LAK `TABLES`: `ifno TAB6 FILEIN <file>`; SSM `FILEINPUT`: `pname SPC6 FILEIN <file>`; FMI: `FILEIN <file>`) — retype these `Path` and reuse the *existing* `path(inout="filein")` convention instead of inventing new row-level machinery. |
| `time_series` | genuine | Kept as-is — `field()` already has this kwarg. Confirmed necessary: drives try-float-then-string *parse order*, not inferable from the `Union[float, str]` annotation alone. |
| `role="feature_id"` | 17/182 | Replaced — see below. |
| `role in ("keystring", "keystring_value", "inline_keyword")` | 9/182 | Dropped entirely — see below. |
| (implicit: `aux: tuple` positional field) | n/a | Kept, but synthesized by codegen for period blocks, not per-DFN-column. Still needs special (name-based) handling in the generalized iteration logic. |

**`feature_id` → adopt `pk`/`fk` from modflow-devtools' DFN spec.**
`dfnspec.md` ("Primary/foreign keys") already formalizes this with
`pk`/`fk`/`fk_ref` attributes on integer/string list-item columns, a
better fit than flopy4's ad hoc `role="feature_id"`: `fk: "node"` is a
literal match for `role="cellid"`; `pk: true` / `fk: "packagedata.<field>"`
matches the rest of today's `feature_id` columns and — unlike flopy4's
flag, which only says "shift by one" — records *what the column refers
to*. The spec's jagged/variadic-array case (`gwf-sfr.connectiondata.ic`'s
shape given by `packagedata.ncon(rno)`) is a real MF6 pattern flopy4 has
no equivalent for today, and dovetails with Phase 1.4's dimension work.

`pk`/`fk` are only populated in the DFN corpus for a subset of packages
today (see Phase 0.6a's Findings for current coverage). **Resolved:**
rather than have flopy4 carry a `numeric_index`/`cellid` fallback (an
attribute `dfnspec.md` no longer documents at all), the DFN corpus is being
backfilled with `pk`/`fk`/`fk_ref` upstream in modflow-devtools (owner:
wpbonelli). `make.py` should read `pk`/`fk`/`fk_ref` directly, no fallback
path.

`pk`/`fk` aren't purely an int concern — `dfnspec.md`'s own example table
includes *string* pk/fk too (`gwf-mvr.packages.pname`/`period.pname1`,
currently untagged upstream). The 1-based↔0-based conversion is meaningless
for a string reference, so the runtime rule should be "`pk`/`fk` set **and**
the field is int-typed → apply the shift," not "any tagged column →
shift."

**Scope boundary:** `fk_ref` (runtime component resolution) and the
jagged/variadic-row-array case are **out of scope for Phase 0.6** — flopy4
has no variadic-row-array support today, and building it is new capability,
not a schema-representation cleanup. Phase 0.6 only needs `pk`/`fk` far
enough to drive the existing 1-based↔0-based conversion; richer resolution
belongs with Phase 1's dimension work or a dedicated follow-up.

**`keystring`/`keystring_value`/`inline_keyword` — resolved: drop all
three, no replacement metadata needed on `Row`.**

- **`inline_keyword` dissolves into "just a `bool` field."**
  `flopy4/mf6/record.py`'s `Record.to_tokens` already emits *any*
  bool-typed field (tagged or not) as its own uppercased name when `True`
  and nothing when `False` — exactly SSM's `mixed` column. A plain
  `mixed: bool = False` field gets this behavior for free once row
  iteration goes through the same generic logic.
- **`keystring`/`keystring_value` were never a real implementation of a
  union — they're where "keystring" as a DFN concept was abandoned
  upstream.** Traced in modflow-devtools' snapshot history: `keystring`/
  `choices` was renamed `union`/`arms` starting `dev1`, and every
  occurrence of "keystring" is gone from the corpus and from `dfnspec.md`
  since. `type: union` is now a proper first-class composite: a field
  discriminated by a leading keyword token, each arm either a bare
  scalar/keyword or (for `auxiliaryrecord`) a full nested `record`.
  flopy4's `role="keystring"`/`"keystring_value"` predates this rename and
  flattens the whole union down to a fixed two-column `{keyword: str,
  value: object}` pair.

  This isn't just a naming issue — it's a **confirmed data-loss bug**.
  Reproduced directly against `Lak._PeriodSchema`: parsing
  `["1", "AUXILIARY", "concentration", "5.0"]` silently drops the `5.0`
  (`auxval`) — there's no third column to catch it, because the flattened
  schema has no concept of a multi-field arm. `structure.py`'s parse loop
  and `unstructure.py`'s serializer both route `keystring`/
  `keystring_value` through the same single-token/generic-`value`-column
  path — they carry **zero** distinguishing runtime behavior from an
  ordinary `role="value"` column today. `gwf/sto.py`'s scalar
  `role="keystring"` (`storagestate`) makes the same point from the other
  direction: STO's `type: union` has two zero-payload keyword arms
  (`transient`/`steady-state`), so it's processed identically to a plain
  string column already — the tag adds nothing.

  Real union support — dispatch on the leading keyword token, per-arm
  types, reusing `record.py`'s tagged-field machinery for record arms — is
  genuine new capability, not a rename, and only touches 3-4 packages
  (`gwf/lak.py`, `gwe/lke.py`, `gwt/lkt.py`, `gwf/sto.py`'s zero-payload
  case). Out of scope for Phase 0.6, split out as **Phase 0.7**. Phase 0.6
  just deletes the roles and, for now, leaves LAK/LKT/STO period rows
  exactly as buggy/simplified as they are today (not a regression) rather
  than blocking `Column`/`Schema` removal on designing union support.

**Steps.** Today's 76 generated `Row` classes carry **zero**
`field()`-based metadata (e.g. `Lak.PackagedataRow.ifno: int` is a bare
attrs field) — that tagging is what step 9 (codegen) adds, and step 9 is
blocked on the upstream `pk`/`fk` backfill (see Phase 0.6a). So only a
subset of these steps are actually unblocked today:

*Unblocked, no regression risk (steps 1-2 landed in `f1dd830` / #341;
step 3 still open):*

1. ~~Extend `field()` in `flopy4/mf6/spec.py` with `pk: bool = False`,
   `fk: str | None = None`.~~ **Done.**
2. ~~Retype the 5 `prefix=`-using file-reference row columns as `Path`
   fields via `path()`.~~ **Done.**
3. Build the *name-based* half of the generalized row-iteration mixin
   (extend `flopy4/mf6/record.py` or add a sibling): `cellid` (variable-
   width tuple unpacking + 1-based shift), `boundname` (deferred to end of
   row, `boundnames`-gated), `aux` (positional tuple, `yield from`).
   Resolved by reserved field *name*, not `pk`/`fk` metadata, so no
   backfill dependency. Land as standalone, unit-tested infrastructure —
   do **not** wire into `package.py`/`structure.py`/`unstructure.py` yet
   (see step 5).

*Entangled with the `pk`/`fk` backfill and step 9's codegen change —
designable now, landable only with step 9/10:*

4. Add the `pk`/`fk`-driven half of the mixin (int-typed `pk`/`fk`-tagged
   columns get the 1-based↔0-based shift; string pk/fk don't;
   `time_series` drives float/string coercion order). Can be unit-tested
   against synthetic fixtures now, but is dead code against real generated
   `Row` classes until step 9 tags their fields.
5. Update the three runtime consumers (`package.py`'s schema/dtype init,
   `structure.py`'s row parser, `unstructure.py`'s row serializer) to read
   `attrs.fields(RowClass)` instead of `Schema.columns()`. **Blocked**:
   swapping this in before step 9 regenerates silently drops the shift for
   all 17 `feature_id` columns, since those fields carry no `pk`/`fk` tags
   yet.
6. Drop the `__{block}_schema__`/`__period_schema__` ClassVar aliases;
   `field(schema=...)` can name the `Row`/`*Row` class directly. Depends on
   step 5.
7. Drop `role in ("keystring", "keystring_value", "inline_keyword")`
   entirely — no replacement metadata (real union support is Phase 0.7).
   `mixed`-style columns become plain `bool` fields; LAK/LKT/STO period
   rows keep their current (already lossy) shape for now. **Blocked**:
   today this is the only parsing/serialization path those three packages
   have; removing it breaks them unless done atomically with step 9's
   regen.
8. Delete `flopy4/mf6/schema.py`. **Hard blocked**: all 76 generated files
   still import and subclass `Schema`. Cannot delete until step 9's regen
   stops emitting those references.

*Blocked on the modflow-devtools `pk`/`fk`/`fk_ref` corpus backfill (owner:
wpbonelli) landing for `gwf/`, `gwt/`, `gwe/`, `prt/`, `utl/`, **and** on
Phase 0.6a (flopy4's own codegen migration onto a DFN module that has
`pk`/`fk` at all):*

9. Codegen (`make.py`, `filters.py`): read `pk`/`fk`/`fk_ref` directly off
   the (by then backfilled) DFN attributes; collapse `row_class()` +
   `schema_class()` into one filter emitting plain typed attributes where
   no metadata is needed and `field(pk=..., fk=..., time_series=...)` only
   where it is; delete `schema_class()`; drop `Column`/`Schema` imports
   from the package template.
10. Regenerate all codegen-v2 packages; diff to confirm: `Row`/`*Row`
    fields are either plain typed attributes or `field(pk=...)`/
    `field(fk=...)`/`field(time_series=...)`; `Column`/`Schema` and
    `_XxxSchema`/`__xxx_schema__` are gone. Steps 5-8 land together with
    this step.

*Either order, after the above:*

11. Rewrite tests: delete `test_mf6_schema.py`; fold any still-relevant
    assertions into `test_mf6_row_api.py`; check `test_mf6_codegen.py` for
    `schema_class`/`Column` assertions.
12. Re-run the full suite, particular attention to `test_mf6_codec.py`,
    `test_mf6_row_api.py`, `test_dataframe_api.py`,
    `test_converter_structure.py`.

**Why before Phase 1, not after:** Phase 1's generalized structuring pass
wants exactly one field-introspection idiom to special-case (`field()`-
tagged attrs fields, resolved via `attrs.fields()`). Doing this first means
there's no second, `Schema`-shaped idiom left for that pass to also learn
about — and if `pk`/`fk` land now, Phase 1's binding resolution and
Phase 1.4's dimension propagation inherit real relational metadata instead
of reverse-engineering it later.

---

## Phase 0.6a — Migrate flopy4 off `modflow_devtools.dfn` onto
`modflow_devtools.dfns` (dev3, pydantic-native)

**Status: in progress (2026-07-16). Step 1 done. Devtools-side
`numeric_index` fix landed upstream and verified**: all 5 previously-
missing fields (`buy.irhospec`, `csub.icsubno`, `vsc.iviscspec`,
`prp.irptno`, `ats.iperats`) now carry `pk=True`, and LAK's relational case
(`outlets.lakein` → `fk="packagedata.ifno"`) is unaffected. No temporary
override stopgap needed. Ready for the atomic rewrite (step 2).

Prerequisite for Phase 0.6 step 9, discovered while attempting to start it:
`pk`/`fk` only exist in devtools' newer `modflow_devtools.dfns` module
(pydantic schema, discriminated `Scalar | Array | Record | Union | List`
field types, currently `CURRENT_SCHEMA_VERSION = "2.0.0.dev3"`). Every
flopy4 consumer of DFN metadata — `spec.py`, the codegen utils
(`make`/`filters`/`overrides`/`dfn2py`), and the codec reader chain
(`dfn2lark`, grammar filters, transformer) — still imports the older,
now-deprecated `modflow_devtools.dfn` module (flat TypedDict `Field`, no
`pk`/`fk` at all). Regenerating against real `pk`/`fk` metadata requires
this migration first.

**Decisions (locked 2026-07-16):**
- Target schema version `"2.0.0.dev3"` (current), not an earlier pin.
- Adopt the pydantic `Field`/`Block`/`Component` types **natively**
  throughout — no permanent translation shim back to the legacy TypedDict
  shape (would recreate the "two conventions" problem Phase 0 eliminated).
- `overrides.py`'s dict-patching layer compensates for `dfn2toml`'s lossy
  conversion, which is being fixed upstream directly (owner: wpbonelli, in
  progress) — don't port its *internal patch logic* as-is, revisit/shrink
  once the upstream fix lands. Its *call boundary* does move now, in
  lockstep with `filters.py`.

**Findings:**
- `LocalDfnRegistry.spec()`/`RemoteDfnRegistry.spec()` already do
  fetch+migrate+validate in one call for the current schema version — no
  separate manual `migrate()` step needed. But flopy4's sync command never
  calls `.spec()` for field metadata today — it fetches raw `.dfn` files
  and re-parses them itself via the legacy loader, discarding the registry
  entirely for this purpose. A `dfns=` bridge parameter already exists in
  the codegen entrypoint but was never wired to a real `dev3` call.
- pk/fk corpus coverage, checked at the field level: of the 17
  `role="feature_id"` columns across flopy4's 76 generated packages, only
  the LAK family (12 of 17) has real `pk`/`fk` upstream. The remaining 5
  (`buy.irhospec`, `csub.icsubno`, `vsc.iviscspec`, `prp.irptno`,
  `ats.iperats`) are self-referential primary keys on their own block,
  needing only `pk: true`, no `fk`.
  - **Root cause, not just missing backfill**: the v1→v2 migration
    script's relation-resolver derives pk/fk purely from two structural
    signals (v1 recarray shape lookups, same-field-name recurrence across
    sibling blocks) and never consults the legacy `numeric_index` flag at
    all — a field with `numeric_index: true` that doesn't also match one
    of those two signals is silently dropped. Fix (owner: wpbonelli,
    separate devtools-side track, in progress): add `numeric_index: true`
    with no structural match → `pk: true` as a third signal.
  - Not a blocker for the migration itself (the new schema drops
    `numeric_index` entirely regardless) — only affects the *timing* of
    step 9's final regeneration, which should run after the devtools fix
    lands or those 5 fields silently lose their `pk`.
  - Not relevant to current scope: MAW/SFR/UZF and gwt/gwe equivalents
    already have upstream `pk`/`fk` but aren't generated in flopy4 yet;
    MVR's string pk/fk are also still untagged upstream (fine to defer, no
    behavioral effect until Phase 1's relational resolution).

**Choreography.** `registry.spec(schema_version=X)` is strictly binary —
there's no intermediate shape between the legacy fallback and the pydantic
migrate/validate path, so there's no valid state where the `filters.py`/
`make.py` rewrite has landed but the version string still says `dev1`.
That means the rewrite, the version-string flip, and `overrides.py`'s
call-boundary update have to land as **one atomic unit**, not staged
separately. `spec.py` is small enough to land with the same rewrite. The
codec/reader path (`dfn2lark.py` etc.) loads DFNs via its own, wholly
separate call and never goes through the codegen entrypoint's version
constant — genuinely decoupled, can migrate on its own schedule.

**Steps:**

1. ~~Wire the real entrypoint~~ — **done** (`registry.spec()` plumbed
   through the codegen CLI, still requesting `dev1` at the time, pure
   refactor).
2. **Atomic pydantic-native rewrite + version flip.** In one PR/landing:
   - Rewrite `filters.py`, then `make.py`, to walk the pydantic
     `Component`/`Block`/`Field` tree (`isinstance` dispatch over
     `Scalar | Array | Record | Union | List`) instead of dict `.get()`
     probing on the legacy TypedDict. `filters.py` first since `make.py`'s
     templates call into its leaf-level field-metadata emission. Largest,
     highest-risk part of the whole plan. Prefer devtools' own built-in
     traversal (`ComponentBase.get_fields(recurse=True)`, `get_block()`)
     over reimplementing a flopy4-side block-threading equivalent —
     confirmed both already exist and cover what's needed.
   - Scope explicitly **excludes** redesigning OC-record and
     keystring-period handling to reflect DFN structure literally instead
     of flattening (see Phase 0.6b) — carved out so this step's
     regenerate-diff stays clean (identical except pk/fk). Port today's
     flatten behavior as-is; 0.6b replaces it afterward.
   - Update `overrides.py`'s call boundary to the new field type; leave
     internal patch rules mostly as-is (expected to shrink once the
     upstream TOML fix lands).
   - Update `spec.py`'s field-type import source and construction to match
     the concrete pydantic types now in play.
   - Develop/test against dev3 fixtures loaded directly
     (`LocalDfnRegistry(path=...).spec(schema_version="2.0.0.dev3")`),
     independent of the production entrypoint's constants, so the rewrite
     can be built and verified before touching it.
   - Land the version-string flip as the final commit of this same PR,
     once everything above passes against dev3 fixtures.
   - Regenerate all 76, diff, review, commit. Expect the LAK family to gain
     real `pk=`/`fk=` tags; everything else field-declaration-identical,
     *provided* the devtools-side `numeric_index` fix has landed first —
     otherwise the 5 affected fields silently lose their `pk`. If timing
     doesn't line up, add a temporary 5-field `pk: true` patch in
     `overrides.py` as a stopgap and drop it once the upstream fix ships.
3. **Codec reader path** (decoupled, independent schedule): same
   tree-walk conversion for the reader/grammar chain. `field["block"]`
   isn't a per-field attribute in the new schema (block membership is
   structural via `Block.fields`), but `ComponentBase.get_block()` already
   does this reverse lookup. Own independent `schema_version` literal, no
   ordering dependency on step 2.

**Ordering:** step 2 is the only place the devtools-side `numeric_index`
fix matters, and only for the regenerate-and-diff sub-step, not rewrite
correctness (mitigated by the temporary-override fallback if needed). Step
3 has no dependency on step 2. Step 2 blocks Phase 0.6 step 9 specifically
— nothing else. Phase 0.6b is carved out of step 2 and can land any time
after it.

---

## Phase 0.6b — Reflect DFN structure literally instead of custom-flattening

**Status: scoping (2026-07-19). Structural survey complete.** Carved out
of Phase 0.6a step 2 mid-survey. No code changes yet; next step is the
concrete design pass for the `List[Union[Record]]`-shaped rendering (OC
records, keystring periods), then starting Phase 0.6a step 2's actual
`filters.py`/`make.py` rewrite.

**Decision:** generated classes should mirror DFN block/field/record/
union/list structure directly rather than being custom-flattened into
shapes invented during early codegen experimentation. Those flattening
transformations predate dev3's real discriminated `Union` type and were,
in every case found so far, workarounds for the old schema's inability to
represent the true structure — not worth preserving now that it can be
represented faithfully. Confirmed candidates:

- **OC-family period records** (`gwf/gwt/gwe/prt-oc`): dev3 represents
  `saverecord`/`printrecord` as a `List` field (`output`) whose `item` is a
  `Union` with `saverecord`/`printrecord` `Record` arms — not two flat
  sibling record fields, which is what the current v1-derived schema shows
  and what today's codegen assumes. Current codegen further flattens this
  into hardcoded per-rtype fields (`save_head`, `print_budget`, ...) via a
  hand-maintained rtype table — redundant now that the valid rtype strings
  are already in the schema. Replace with a representation that mirrors
  the `List[Union[Record]]` shape directly; drop the hardcoded table.
- **Keystring periods** (LAK/SFR/MAW/UZF): currently consolidated into an
  approximated `(number, keyword, value)` recarray — codegen's own comment
  admits this is lossy ("a proper typed representation requires a sealed
  class hierarchy or tagged variant type... deferred pending upstream
  devtools schema work"). Dev3's real `Union` types resolve exactly the gap
  that comment describes; replace with a faithful representation.
- **Standard stress-package period blocks** (CHD/WEL/DRN/...): current
  v1-derived schema shows these as flat top-level `Array` fields per column
  in the period block, with `cellid` hardcoded/synthesized (never a real
  field). Confirmed dev3 represents these identically to any other list
  block: a real `List[Record]` (`stress_period_data`) with `cellid` as a
  genuine typed `Array` field (`shape=["ncelldim"]`), alongside
  `head`/`aux`/`boundname` as normal Record fields — no synthesis needed.
  The "period array fields vs. list block" special-case split, and the
  synthetic-cellid injection, likely collapse into the same generic
  list-block handling already used for `packagedata`/`connectiondata`/etc.
- **The `layered` flag** (griddata arrays like NPF's `k`/`k22`/`icelltype`,
  STO's `ss`/`sy`): ~~dev3's `Array` schema has no `layered` field at all~~
  **correction (2026-08-18): this premise was wrong, see below.** Even in
  the *current* generated code, `layered=True` sits alongside an unchanged
  flat shape — it was never encoding a different in-memory shape, only a
  text-serialization choice (whether an array may be split into per-layer
  `CONSTANT`/`INTERNAL` blocks when written). The write path already
  derives this dynamically and correctly, and the read grammar already
  discriminates `single_array` vs `layered_array` from the literal token
  present in the file, not from a prediction. The static-flag readers on
  the ingress/netcdf side are instances of the same "static metadata
  standing in for a per-instance, dynamically-derivable choice" pattern as
  the OC rtype table.

  **Correction (2026-08-18):** "dev3 has no `layered` field" was an
  artifact of a migration bug, not a schema design choice — `layered` was
  being silently dropped by the v1→v2 migration script (never actually
  removed from the schema) and has since been fixed upstream (devtools
  `f3ae0f4`, "fix(dfns): migrate/render missing attributes" #345, landed
  2026-08-14): it's migrated onto `Array` correctly now and wired into
  devtools' own `render()` so generated MF6IO-guide-style block templates
  show `NAME [LAYERED]` correctly, matching the real reference guide. It
  is real, intentional schema data, not vestigial — confirmed by walking
  the commit history of `modflow_devtools/dfns/schema.py` back to its
  original commit (`750f63b`, #311): `layered` was absent from `Array`
  there too, so this genuinely was an unmigrated gap the whole time, not a
  deliberate omission that got reversed.

  This does not change flopy4's read/write conclusion above — the
  empirical derivation rule (`layered` iff `nlay` in shape) still holds,
  and flopy4's writer/reader still don't need `layered` as an internal
  behavior flag, since the writer already derives the split dynamically
  and the reader already discriminates from the literal token in the
  file. **Revised decision:** don't add `layered` back into flopy4's
  generated field metadata (still unnecessary for read/write behavior),
  but Phase 0.6a step 2's tree-walk should treat `Array.layered` as an
  ordinary, always-present attribute (not something to special-case as
  absent) when walking the pydantic schema. The ingress/netcdf fix
  described above (stop assuming a field is statically layered-or-not) is
  still worth doing — dynamic derivation is more correct than a static
  default-`True` assumption — but it's now a clarity/correctness cleanup,
  not a forced consequence of a schema gap that no longer exists.

**Consequences:** changes the generated API shape for OC-family and
keystring-period packages (field names/types users see change, not just
internals) — touches downstream tests and any code constructing these
fields today. Also requires fixing the ingress `layered` use sites and
netcdf's default-`True` `layered` read to stop depending on a static flag,
deriving the same decisions dynamically instead (matching how the writer
already works) — `layered` is present in the schema, but flopy4 still
doesn't need it as a behavior switch. Deliberately **not** part of Phase
0.6a step 2's
landing so that step 2's regenerate-diff stays clean (identical except
pk/fk); lands as its own reviewable change, sequenced after or alongside
step 2.

**Steps:** TBD, pending a concrete design for how a literal
`List[Union[Record]]`-shaped field (and similar) should render in generated
Python — this needs its own design pass before implementation starts.

**Survey findings (structural survey, complete as of 2026-07-19).**
Loaded a real local DFN corpus (ahead of what flopy4 currently tracks —
fine for structural survey purposes) via
`LocalDfnRegistry(path=...).spec(schema_version="2.0.0.dev3")` and
introspected real component/block/field objects directly in a throwaway
script rather than reasoning from `schema.py` source alone — several
findings below only became clear by checking actual data.

*Settled, no surprises — pure retype for Phase 0.6a step 2, `isinstance`
dispatch, same output:* `pk`/`fk`; file records (`Record` + one `File`
child, both `filein`/`fileout` directions); embedded compound records with
keyword trigger; aux variable lists (plain `Array(dtype="string",
shape=[])`); the `dimensions` block itself (a normal `Block` of `Integer`
fields); prefix/row-keyword columns in list blocks (the `is_prefix`/
`is_row_keyword` distinction is carried by `Keyword` type + `optional`
exactly as today — `Record.fields` is an ordered dict in DFN declaration
order, so the accumulate-prefix algorithm ports directly); `cellid` in a
genuine static list block (checked MAW/SFR `connectiondata` — same real
`Array(dtype="integer", shape=["ncelldim"])` field already confirmed for
period blocks, no special casing beyond what's documented above);
collision-name resolution and dimension resolution for list blocks
(`List.shape` is a real `list[str]`, so string-parsing simplifies to a
direct list read; the alias/suffix-matching and `"maxbound"`-literal
fallback logic both carry over unchanged, verified against real examples;
`collision_names` itself is pure Python-side logic with zero dependency on
the source schema).

*Needs new traversal, same output for now (step 2 scope):* OC records and
keystring periods need deeper `List`/`Union` tree-walking to locate, but
step 2 should port today's flattened *output* as-is — the redesign is
0.6b's job, not step 2's.

*Delete/simplify rather than port (step 2 scope, net complexity
reduction):* the flat-fields/block-threading helper (devtools' own
recursive field/block lookups already cover this); the dual legacy-DFN/
v2-DFN parameter threading used for numeric_index/block-schema v1-bridging
(vestigial now `pk`/`fk` are native everywhere — confirmed a real block
that today is only discoverable via the legacy-DFN fallback, e.g. SSM's
`fileinput`, is present natively as an ordinary `List` field under dev3, so
a single walk over the component's blocks replaces the current two-source
merge); the separate "readarray" detection flag for G-variant period
packages (confirmed G-variant period fields are plain `Array`s directly in
the period block, standard packages' period fields are `List[Record]` —
`isinstance` alone distinguishes them).

*Phase 0.6b redesign candidates (API-shape change, own design pass, listed
above):* OC records; keystring periods; standard stress-package period
blocks; the `layered` flag.

**Decision (2026-08-18): 0.6a step 2 and 0.6b are merged into one effort,
not staged sequentially.** Reasoning: building 0.6a step 2's tree-walk for
OC/keystring against the *old* flattened output requires the same
`List` → `Union.arms` → `Record.fields` descent that a faithful
representation needs — the "port as-is" step buys nothing but a second
rewrite of the same code shortly after, and produces two consecutive
breaking changes to the same ~10 packages instead of one. It also
surfaced a structural finding that makes deferring 0.6b actively wasteful:
OC's nested `ocsetting` union (`all|first|last|frequency|steps`) and
LAK's `laksetting` union are **the same mechanism** — a discriminated
union keyed by a leading keyword token, arms either bare scalars or
sub-records. Phase 0.7 (below) was scoped as a separate, later effort to
design exactly this mechanism for LAK/STO; designing it once now and
applying it to both OC and the keystring packages is more principled than
building a one-off OC flattener and a proper union type later. Standard
stress-package period blocks (CHD/WEL/DRN/...) have no such complication
— `list-design.md`'s `list[ItemType]` target already covers them exactly
as a plain `List[Record]`, so there's nothing "old-shaped" to carry
forward there either.

**Union field Python shape (unblocks OC + keystring together):**
following `list-design.md`'s per-arm-class pattern, each union arm
becomes its own generated `attrs` item class; the field type is a Python
`Union` of those classes (e.g. `Optional[list[OcSaverecordItem |
OcPrintrecordItem]]` for OC's `output`, `Optional[dict[int,
list[LakStatusItem | LakStageItem | ... | LakAuxiliaryrecordItem]]]` for
LAK's `perioddata`). Parsing dispatches on the leading keyword token
against each arm's trigger keyword. Each item class carries its own real
`fk` where the schema has one (e.g. `LakRateItem.outletno: int =
field(fk="outlets.outletno")`) instead of collapsing to an untyped
`value` column. This generalizes the OC-specific per-rtype expansion the
current codegen already hardcodes (`_OC_RTYPES`) into one mechanism used
uniformly — no per-package rtype table needed, since arms are read
directly from the schema's `Union.arms`.

**Course correction (2026-08-18, later same day): the union-item-class shape
above is validated but deferred, not wired in.** Built and verified the
tree-walker + union-item-class generator against real LAK/OC/SFR data
(scratchpad prototype, `composite_v3.py`) — it works and generalizes
correctly across three structurally different real cases. But before wiring
it into `make.py` for real, checked what actually *reads* the generated
output at runtime (`flopy4/mf6/converter/ingress/structure.py`,
`egress/unstructure.py`) and found they're driven generically by the
existing `Column`/`Schema`/`role=` mechanism (`flopy4/mf6/schema.py`) —
`role in ("cellid", "feature_id", "value", "boundname", "keystring",
"keystring_value", "inline_keyword")` — not per-package logic. That
mechanism has no way to represent "one of N distinct typed classes, chosen
by keyword" (what the union-item-class design produces); it can only
represent flat columns. Wiring the union-item-class shape into real
packages therefore needs new ingress/egress dispatch code, which hasn't
been scoped. Separately confirmed `list-design.md`'s `list[ItemType]`
target (bare attrs objects, no `Schema`/`Column` at all) **is not yet the
runtime representation for anything** — Phase 0.6 (which owns that
migration) is "steps 1-2 done, step 3+ next", still in progress, so
`Row`+`Schema`/`Column` is still what every currently-generated package
(including plain list blocks like LAK `packagedata`, not just the
keystring ones) actually round-trips through today.

**Revised plan:** the 0.6a+0.6b codegen rewrite targets the *existing*
`Row`+`Schema`/`Column`/`role=` output shape, sourced from the dev3
pydantic tree instead of the legacy schema — i.e., functionally reproduce
today's generated shape (including OC's per-rtype fields and the
`(index, keyword, value)` approximation for LAK/SFR/MAW/UZF period data)
from the new source, rather than emitting the union-item-class shape live.
Concretely this is *not* a return to "port the exact old flattening
code" — real improvements land immediately: `_OC_RTYPES`'s hardcoded table
is replaced by reading `rtype.valid` directly from the schema (confirmed
correctly populated, see `devtools/todo.md`), and the LAK/SFR/MAW/UZF
`extra_period_fields` TOML-override mechanism is no longer needed at all,
since the keystring arms are now discoverable directly from `Union.arms`
rather than requiring a hand-maintained override entry per package. Only
the *output shape* (flat `role="keystring"/"keystring_value"` columns,
not typed per-arm classes) stays as today, for runtime-compatibility
reasons. The union-item-class mechanism becomes a follow-up phase, to be
sequenced *after* Phase 0.6's `Row` migration actually lands (building
typed union arms on top of real `Row` objects, not on top of `Schema`/
`Column`) rather than merged into this pass — the earlier merge decision
above (0.6a+0.6b+0.7 as one effort) undercounted this runtime dependency;
0.7's *design* (this section) still stands, only its landing sequencing
changes. `composite_v3.py`'s logic is worth keeping as a starting point
when that follow-up phase starts.

*Not yet started:* actual code changes for the merged 0.6a+0.6b effort —
the structural survey above and the union-shape decision are the only
work done so far; nothing has landed. Regenerate a fresh baseline codegen
snapshot (via the current legacy loader) before starting the rewrite, so
there's something to diff the pydantic-native output against — any
previously-generated baseline lived under a session-scoped scratchpad path
and does not survive between sessions.

**Next concrete action:** start the `filters.py` rewrite in bite-sized,
independently-verifiable slices: (1) leaf name/path/class-name helpers —
no field-type dispatch, lowest risk; (2) field classification as
`isinstance`/`match` dispatch on `Keyword|Integer|Double|String|Array|
Record|Union|List|File`; (3) Record/Union/List tree-walking, including the
new union-item-class mechanism above; (4) wire `make.py`'s spec-builders
to the new dispatch; (5) migrate `test_mf6_codegen.py`'s `all_dfns`
fixture off the legacy loader; (6) regenerate all 76 and diff against the
pre-rewrite baseline.

---

## Phase 0.7 — Model DFN `union` fields properly (replaces `keystring`/
`keystring_value`/`inline_keyword`)

**Status (2026-08-18): absorbed into the merged Phase 0.6a+0.6b effort
above** — the union-field mechanism this phase designs is needed for OC's
`ocsetting` union too, not just LAK/STO, and building it twice (once
ad hoc for OC's flattening, once properly here) was the reasoning for the
merge. This section's design steps (1, 4, 5) still apply as written; step
2's Python-type decision is now made (see the merged section above); step
3's "current `role="keystring"` two-column flattening" being replaced no
longer exists as an intermediate state to replace — the merged effort
goes straight to the union representation. Kept here for the scope list
(`gwf/sto.py`'s `storagestate`) and the `AUXILIARY` regression case, both
still relevant.

**Goal:** give list-item records a real discriminated-union field type,
matching modflow-devtools' `type: union`/`arms` (see `dfnspec.md`,
"Union"), and use it for LAK/LKT/STO period settings instead of the
flattened, data-lossy `{keyword, value}` pair Phase 0.6 deletes. This is
new capability (and a bugfix — see the reproduced `AUXILIARY` data-loss
case in Phase 0.6), not a rename, so it's split out from Phase 0.6's
`Column`/`Schema` removal.

**Scope:** 3 packages today (`gwf/lak.py`, `gwe/lke.py`, `gwt/lkt.py` —
the `laksetting`-shaped period union) plus `gwf/sto.py`'s `storagestate`
as a degenerate zero-payload special case of the same mechanism.

1. Design the Python shape of a union field: a small dispatcher (sibling
   to `flopy4/mf6/record.py`'s `Record`, or an extension of it) that reads
   the leading keyword token, looks it up against the arms, and either
   parses a bare scalar (most arms: `stage`, `rainfall`, `status`, ...,
   each with its own `time_series`/dtype per the DFN) or delegates to
   `Record.from_tokens` for a multi-field arm (`auxiliaryrecord`).
   Serialization is the mirror via `to_tokens`.
2. Decide the generated Python type: likely `Union[<scalar arms>, <one
   attrs class per record arm>]` on the `Row` field, or a small wrapper
   type — needs a concrete design pass, not assumed here.
3. Update codegen (`make.py`/`filters.py`/templates) to emit this shape
   from DFN `type: union`/`arms` instead of the current `role="keystring"`
   two-column flattening.
4. Update `structure.py`/`unstructure.py`'s row parse/serialize to
   dispatch through the union instead of the generic `keystring_cols`
   branch being deleted in Phase 0.6.
5. Regression test: the reproduced `AUXILIARY <auxname> <auxval>`
   round-trip case above must preserve both values.
6. Regenerate `lak.py`/`lke.py`/`lkt.py`/`sto.py`; re-run
   `test_mf6_row_api.py`/`test_mf6_codec.py` for these packages
   specifically.

**Ordering:** independent of Phase 1/2 (parallelizable, like Phase 3) —
doesn't block namefile loading, since it only affects LAK/LKT/STO period
parsing correctness. Can land any time after Phase 0.6 removes the old
roles it replaces.

---

## Phase 1 — Generalize structuring to resolve bindings

With Phase 0 done, there is exactly one field-metadata convention, so this
phase is simpler than originally scoped — no more "check `dfn_block` OR
`block`."

Target: `component.py`, `converter/ingress/structure.py`

1. Add a component-type registry keyed by MF6 file-type token: `ftype:
   ClassVar[str | None] = None` on `Component`, populated in
   `__attrs_init_subclass__` alongside the existing `COMPONENTS` dict.
   Reuse the model-qualified-key pattern already there (`component.py`) to
   avoid collisions between e.g. `gwf.Ic` and `gwt.Ic`.
2. Write a `_resolve_binding` helper: given a field whose declared type is
   a `Component` subclass (or `list[...]`/`dict[str, ...]`/`Union[...]` of
   them) and a parsed row shaped `[type_token, filename, *names]`, resolve
   the target class (disambiguating `Union` members by `type_token`), then
   call `TargetClass.load(workspace / filename)` recursively.
3. Route any `block=`-tagged field whose value looks binding-shaped through
   `_resolve_binding` instead of the scalar-kwarg path in the (now single)
   structuring function.
4. Dimension propagation: check whether `flopy4/dimensions.py`'s existing
   `DimensionProvider`/`DimensionResolver`/`resolve_dims()` (already
   in-flight, uncommitted) is sufficient for "NPF picks up nlay/nrow/ncol
   from a DIS sibling loaded moments earlier during the same structuring
   pass," or needs a small load-order-aware cache. Prefer extending this
   existing mechanism over introducing a separate contextvar
   (`DimContext`) as PR #284 did. Now informed by Phase 0.6's `pk`/`fk`
   metadata where relevant (e.g. resolving a foreign-key-typed field's
   target component/block).
5. Simplify `Component.load()` / `Context.load()` to drop the manual
   `for child in self.children: child.load()` loop — recursion now lives
   inside structuring (steps 2-3).

---

## Phase 2 — Wire it through Model/Simulation, prove it end-to-end

Target: `context.py`, `component.py`, one real example model

1. Decide the load entrypoint: give `Context` its own codec-based `load()`
   (parallel to `Package.load`), or — since structuring is now fully
   generic after Phase 1 — lift `Package.load()`'s body up to
   `Component.load()` as a single implementation used by everything.
2. Run `Simulation.load(path/"mfsim.nam")` against an existing example
   (`docs/examples/quickstart.py` or `twri.py`) and iterate until the full
   tree loads: Tdis, each Model with its packages, Exchanges, Solutions.
3. Confirm DIS-before-NPF/IC ordering and dims propagation (Phase 1.4)
   actually work end to end, not just in isolation.

---

## Phase 3 — Namefile grammar refinement (parallelizable, not blocking)

`basic.lark` already parses `packages`/`models`/`exchanges`/`solutiongroup`
blocks into generic `[type, fname, *names]` rows, which is sufficient input
for Phase 1-2. This phase is a validation/error-message improvement, not a
prerequisite, and can happen any time — including in parallel with Phases
1-2.

Target: `codec/reader/dfn2lark.py`, `grammar/templates/component.lark.jinja`,
`grammar/templates/macros.jinja`

1. Port PR #284's typed-record generation for `packages`/`models`/
   `exchanges`/`solutiongroup` blocks (generic `list` → typed
   `packages_record: ftype fname pname NEWLINE` etc.). This is
   generator/template-only and doesn't touch xattree or structuring, so it
   should port over close to as-is. (Namefile-grammar "records" here are
   an unrelated concept to `flopy4/mf6/record.py`'s `Record` class — same
   word, different layer: Lark grammar rows vs. Python inline-record
   objects. No overlap, just a naming coincidence worth not confusing.)
2. Switch the loader to `get_typed_parser()` for components with a
   validated typed grammar; keep `get_basic_parser()` as fallback.

---

## Phase 4 — Cleanup

1. Close or narrow PR #284 to the salvageable pieces (the grammar template
   diff from Phase 3, and the `FTYPES`/binding-resolution *design* — not
   its `structure.py`, which is superseded by Phase 1).
2. Port `test_mf6_load_integration.py` / `test_mf6_load_all_models.py` from
   PR #284 as acceptance tests for Phase 2, rewritten against the new
   implementation.
3. Update `docs/dev/` (several files touched by PR #284:
   `on_representations.md`, `sdd.md`, `grammar-issues.md`, etc.) to
   describe the final single-convention structuring/binding design, since
   PR #284's docs describe the old-xattree-spec version of this work.

---

## Suggested order

~~Phase 0~~ → ~~Phase 0.5~~ → **Phase 0.6 (steps 1-2 done, step 3+ next)**
⟷ **Phase 0.6a+0.6b, merged (in progress, blocks Phase 0.6 step 9)** →
Phase 1 → Phase 2 → (Phase 3 any time) → Phase 4. Phase 0.7 is absorbed
into the merged 0.6a+0.6b effort (see that section) rather than landing
separately afterward.

Phase 0.6 is comparable in blast radius to Phase 0 — touches every
codegen-v2 package with a list/recarray block, plus `package.py`,
`structure.py`, `unstructure.py`, and the codegen filters — so it lands as
its own reviewable step before Phase 1 is written against the post-
`Column` field-introspection story. See Phase 0.6's Steps for the current
blocking/sequencing detail (steps 4-8 designable now, landable only with
steps 9-10's regen, which itself waits on the devtools `pk`/`fk` backfill
**and** Phase 0.6a). Phase 0.7 fixes a real bug (silent data loss on LAK
`AUXILIARY` period rows) but is scoped to 3-4 packages and doesn't block
namefile loading, so it's parallelizable rather than sequenced.
