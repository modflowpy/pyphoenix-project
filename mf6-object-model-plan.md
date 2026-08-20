# MF6 object model plan

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

**Steps. Status: all 12 done, landed 2026-08-19/20 in `6cdfb2a` (steps 9-10,
the pk/fk-tagged codegen rewrite) and `78c506b` (steps 3-8, 11-12, the
Row-mixin runtime rewrite).** `flopy4/mf6/schema.py` is deleted;
`flopy4/mf6/row.py` (a `Row` mixin, matching `record.py`'s `Record`
pattern) is now the sole row-item schema, introspected via
`attrs.fields()` by `package.py`, `structure.py`, and `unstructure.py`
directly — no separate `Schema`/`Column` lookup anywhere. All 76 (now 64,
after some consolidation in the dev3 regen) generated `Row` classes carry
real `field(pk=..., fk=..., time_series=...)` metadata sourced from the
dev3 DFN corpus. Two parsing bugs were found and fixed along the way (see
`78c506b`'s commit message): `row_class()` codegen was placing the
synthetic `aux` field ahead of a package's own optional non-aux columns
(wrong token order vs. the real DFN, e.g. EVT's `pxdp`/`petm`/`petm0`), and
`Row.from_row()` greedily consumed tokens for optional columns without
knowing whether they were present in a given row; it now infers the count
of trailing optional columns from the remaining token budget, same as
`naux`/`ncelldim` already did. Full suite green except two pre-existing,
unrelated integration-test failures (xattree mangling an explicit
`multi_package` `name=`, e.g. `"LAK-1"` → `"LAK-10"`).

1. ~~Extend `field()` in `flopy4/mf6/spec.py` with `pk: bool = False`,
   `fk: str | None = None`.~~ **Done** (`f1dd830` / #341).
2. ~~Retype the 5 `prefix=`-using file-reference row columns as `Path`
   fields via `path()`.~~ **Done** (`f1dd830` / #341).
3. ~~Build the *name-based* half of the generalized row-iteration mixin
   (`cellid`, `boundname`, `aux`).~~ **Done** — `flopy4/mf6/row.py`.
4. ~~Add the `pk`/`fk`-driven half of the mixin.~~ **Done** —
   `flopy4/mf6/row.py`; sourced from real dev3 `pk`/`fk` tags via
   `6cdfb2a`'s codegen rewrite.
5. ~~Update `package.py`/`structure.py`/`unstructure.py` to read
   `attrs.fields(RowClass)` instead of `Schema.columns()`.~~ **Done.**
6. ~~Drop the `__{block}_schema__`/`__period_schema__` ClassVar
   aliases.~~ **Done.**
7. ~~Drop `role in ("keystring", "keystring_value", "inline_keyword")`
   entirely.~~ **Done** — superseded by real `Union.arms`-driven detection
   from `6cdfb2a` (see Phase 0.6b/0.7 below); LAK/LKE/LKT/SFR keystring
   period rows still use the flat `(index, keyword, value)` output shape
   for now (typed union-item-class representation is a deferred follow-up,
   see Phase 0.7 status below), but the detection mechanism itself is now
   schema-driven, not a hardcoded `role=`.
8. ~~Delete `flopy4/mf6/schema.py`.~~ **Done.**
9. ~~Codegen (`make.py`, `filters.py`): read `pk`/`fk`/`fk_ref` directly
   off the dev3 DFN attributes.~~ **Done** — landed as part of `6cdfb2a`'s
   full pydantic-native rewrite (Phase 0.6a step 2), not a standalone
   pk/fk-only pass as originally scoped; see that phase for detail.
10. ~~Regenerate all codegen-v2 packages; diff to confirm `Column`/`Schema`
    gone.~~ **Done.**
11. ~~Rewrite tests: delete `test_mf6_schema.py`; fold assertions into
    `test_mf6_row_api.py`.~~ **Done.**
12. ~~Re-run the full suite.~~ **Done**, green modulo the two pre-existing
    unrelated xattree failures noted above.

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

**Status: step 2 (the atomic pydantic-native rewrite + version flip) done,
landed 2026-08-19 in `6cdfb2a`. Step 3 (codec reader path) not started —
confirmed `flopy4/mf6/codec/reader/dfn2lark.py`,
`flopy4/mf6/codec/filters.py`, `flopy4/mf6/codec/reader/transformer/typed.py`,
and `flopy4/mf6/codec/reader/grammar/filters.py` still import legacy
`modflow_devtools.dfn` at `schema_version="2.0.0.dev1"`.** As noted below,
step 3 is decoupled from step 2 with no ordering dependency, so this is
expected, not a regression — it's simply still open. Step 1's devtools-side
`numeric_index` fix landed upstream and was verified: all 5 previously-
missing fields (`buy.irhospec`, `csub.icsubno`, `vsc.iviscspec`,
`prp.irptno`, `ats.iperats`) carry `pk=True`, and LAK's relational case
(`outlets.lakein` → `fk="packagedata.ifno"`) was unaffected. No temporary
override stopgap was needed.

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
2. ~~**Atomic pydantic-native rewrite + version flip.**~~ **Done**,
   `6cdfb2a` (2026-08-19). Also merged in Phase 0.6b + 0.7's scope where the
   runtime already supported it (see those sections) — broader than
   originally scoped for this step alone, but landed atomically as planned:
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
3. **Codec reader path** (decoupled, independent schedule). **Status: not
   started.** Same tree-walk conversion for the reader/grammar chain.
   `field["block"]` isn't a per-field attribute in the new schema (block
   membership is structural via `Block.fields`), but
   `ComponentBase.get_block()` already does this reverse lookup. Own
   independent `schema_version` literal, no ordering dependency on step 2 —
   can land any time, including in parallel with Phase 1.

**Ordering:** step 2 is the only place the devtools-side `numeric_index`
fix matters, and only for the regenerate-and-diff sub-step, not rewrite
correctness (mitigated by the temporary-override fallback if needed). Step
3 has no dependency on step 2. Step 2 blocks Phase 0.6 step 9 specifically
— nothing else. Phase 0.6b is carved out of step 2 and can land any time
after it.

---

## Phase 0.6b — Reflect DFN structure literally instead of custom-flattening

**Status: done (merged into `6cdfb2a`, 2026-08-19) for the scope that
landed — see "Revised plan" and the note at the end of this section for
exactly what shipped vs. what's still deferred.** Carved out
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

**Landed 2026-08-19 in `6cdfb2a`** (the same commit as Phase 0.6a step 2 —
per the merge decision above, these were never separable in practice): the
`filters.py`/`make.py` tree-walk rewrite, OC's rtype table replaced by
reading `rtype.valid` directly from the schema, and LAK/LKE/LKT/SFR-style
keystring period settings now detected from the schema's real `Union.arms`
instead of a hand-maintained override list. **What did *not* land** (per
that commit's own message, and per the "Revised plan" above): the
union-item-class shape itself — real per-arm typed classes — is still not
wired into the generated output. Detection is schema-driven now; the
*generated Python shape* for keystring/union period rows is still the flat
`(index, keyword, value)`-approximation output, same as before, because
`structure.py`/`unstructure.py` only understood that flat vocabulary at
the time. **This blocker is now gone**: Phase 0.6's `Row` migration landed
the next day (`78c506b`, 2026-08-20), so the union-item-class mechanism
(prototyped and validated in a scratchpad script, `composite_v3.py` — not
committed, doesn't survive between sessions, would need re-deriving) is now
a well-scoped, unblocked follow-up phase rather than a hypothetical one.
Not required for Phase 1 (namefile loading doesn't touch period-row
parsing), so it's optional/parallelizable — see "Suggested order" below.

---

## Phase 0.7 — Model DFN `union` fields properly (replaces `keystring`/
`keystring_value`/`inline_keyword`)

**Status (2026-08-20): partially landed, real scope remaining.** The
*detection* half (recognizing `type: union`/`arms` in the schema instead of
a hand-maintained override list) absorbed into and landed with the merged
Phase 0.6a+0.6b effort (`6cdfb2a`) as described there. The *representation*
half — this phase's actual goal, a real discriminated-union Python type
replacing the lossy flat `{keyword, value}` pair, fixing the reproduced
`AUXILIARY` data-loss bug below — has **not** landed; `6cdfb2a` explicitly
kept the flat output shape because `structure.py`/`unstructure.py` didn't
support anything richer at the time. That blocker is gone now that Phase
0.6's `Row` migration landed (`78c506b`, 2026-08-20) — this phase is
unblocked and its design steps (1-6 below) are still accurate as written.
Not required for Phase 1; scoped to 3-4 packages
(`gwf/lak.py`/`gwe/lke.py`/`gwt/lkt.py`/`gwf/sto.py`) and parallelizable
with the namefile-loading phases. Kept here for the scope list and the
`AUXILIARY` regression case, both still relevant and still unfixed.

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

**Status: done (2026-08-20).** `Simulation.load("mfsim.nam")`/`Gwf.load(
"model.nam")` now recursively resolve `packages`/`models`/`exchanges`/
`solutiongroup` rows into real loaded, attached children, with dims
threaded from a `dis`-like sibling to the rest of its block. Landed
alongside two real, previously-latent bugs this work surfaced:

- `Component.load()`/`Context.load()` were calling a dead code path
  (`flopy4.mf6.converter.structure()`, a bare `cattrs.Converter.structure`
  with no hook registered for the abstract `Component` base) — confirmed
  by direct repro (`TypeError: node name must be a string or None`) and by
  the fact that no test exercised it against real files, only a fully
  mocked loader. Fixed by routing `_load_mf6` through the same
  `structure_component()` pipeline `Package.load()` already used
  successfully.
- **False start, corrected the same day**: initially "fixed"
  `binding.py`'s `_get_binding_type` to treat G/A-variant package classes
  (`Chdg`, `Drng`, `Evta`, `Ghbg`, `Rcha`, `Rivg`, `Welg`) as having
  distinct namefile ftypes (`"CHDG6"`, not `"CHD6"`), based on legacy
  flopy's `dfn_file_name`/`_package_type` attributes. This was wrong and
  broke real `mf6` runs ("Model package type not supported [type=CHDG6]")
  — confirmed against the actual MF6 Fortran source (`gwf.f90`'s
  package-type `select case` has no `'CHDG6'`/`'RCHA6'`/etc. arm at all,
  only the base tokens; `chd_create` handles both variants once
  dispatched). Reverted to the original collapsing behavior. Real lesson:
  a DFN's `dfn_file_name` describes the DFN/class identity, not
  necessarily the namefile-level ftype token — verify against the actual
  MF6 source dispatch table, not a generated client library's class
  attributes.
- Because G/A variants genuinely share one namefile ftype, `Union[Chd,
  Chdg]`-shaped fields can't be disambiguated by token alone — resolved by
  peeking the referenced file's own `OPTIONS` block for the
  `READASARRAYS`/`READARRAYGRID` marker keyword (the same signal real MF6
  itself uses) rather than the namefile row.

Target: `component.py`, `converter/ingress/structure.py`, `binding.py`,
`flopy4/mf6/__init__.py`, `context.py`.

1. ~~Add a component-type registry keyed by MF6 file-type token.~~ **Done**
   as `FTYPES`/`get_ftypes()` in `component.py`, built lazily (not eagerly
   in `__attrs_init_subclass__`, to dodge an import-reentrancy failure:
   computing a token needs `binding.py`, whose own import chain can define
   further concrete subclasses before finishing). Model-qualified keys
   (e.g. `"gwf-dis6"`) disambiguate tokens that collide *across* model
   types (every model has its own `Dis` via one shared abstract base);
   G/A-variant collisions *within* one model are a different kind of
   ambiguity, resolved in step 2 instead (a registry entry can only hold
   one class per key).
2. ~~Write a `_resolve_binding` helper.~~ **Done** as `_resolve_bindings()`
   in `structure.py`, using `xattree.get_xatspec(cls).children` to find
   child-Component fields (mirroring `unstructure.py`'s
   `_make_binding_blocks`, the egress side of this same job) rather than
   hand-rolling type introspection from scratch.
3. ~~Route any `block=`-tagged binding-shaped field through
   `_resolve_binding`.~~ **Done** — `structure_component()` gained a
   `workspace` param and merges `_resolve_bindings()`'s result into its
   kwargs before the single `cls(**kwargs)` call, same as every other
   field.
4. ~~Dimension propagation.~~ **Done**, via a small load-order rule local
   to `_resolve_bindings` (not a `dimensions.py` change): within one block,
   `DimensionProvider`-typed rows (the `dis` field) are resolved first, the
   resulting `dims` dict threaded into sibling `Package.load(...,
   dims=dims)` calls. `dimensions.py`'s existing object-graph walk
   (`resolve_dims()`) remains the right tool for *post*-attachment queries;
   it just can't help *during* construction, before children exist to
   walk.
5. ~~Simplify `Component.load()`/`Context.load()`.~~ **Done** — both drop
   the manual child loop entirely (children now arrive already resolved
   and attached from the constructor call).

**Known limitation, not fixed in this pass**: a binding row's `pname` term
isn't threaded through to the loaded child's `.name` (no `name=` kwarg on
`Component.load()`/`Package.load()` today) — loaded children get xattree's
default auto-assigned name. Round-tripping a namefile with hand-picked
custom `pname`s isn't preserved. `Solution.models`/`Exchange.exgmnamea`/
`exgmnameb` *are* threaded through from binding-row terms (real semantic
data, not display names — see `_apply_binding_terms`).

Test coverage: `test/mf6/test_mf6_namefile_load.py` (new) covers recursive
`Simulation.load()`/`Gwf.load()`, dims propagation to griddata siblings,
list-package rows, and G/A-variant disambiguation, via a write-then-load
round trip built on the existing `docs/examples/quickstart.py` pattern.
`test/mf6/test_mf6_component.py` covers the `FTYPES` registry and the
G/A-variant ftype behavior directly.

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

**Updated 2026-08-20.** ~~Phase 0~~ → ~~Phase 0.5~~ → ~~Phase 0.6~~ ⟷
~~Phase 0.6a step 2 + Phase 0.6b (merged)~~ are **all done**. Everything
that was blocking namefile loading has landed:

- Phase 0: one field-metadata convention (`3eda3f9`).
- Phase 0.5: `dfn_type` eliminated (`3eda3f9`).
- Phase 0.6: `Column`/`Schema` deleted, `Row` is the sole list-block schema
  (`f1dd830`, `6cdfb2a`, `78c506b`).
- Phase 0.6a step 2: codegen migrated onto the pydantic-native dev3 DFN
  schema (`6cdfb2a`).
- Phase 0.6b: DFN structure (OC rtypes, keystring/union detection) now read
  from the schema instead of hardcoded tables (`6cdfb2a`).

~~**Phase 1**~~ (generalize structuring to resolve namefile bindings) is
**also done** (2026-08-20) — `Simulation.load()`/`Gwf.load()` recursively
resolve real namefiles now, dims propagation included. See that section
for what landed and two bugs (one real, one a false-start that was found
and reverted the same day) it surfaced along the way.

**Next up: Phase 2** (wire through Model/Simulation, prove end-to-end) —
Phase 1's own tests already exercise a full `Simulation.load()` round
trip on a small model, so Phase 2 is mostly "prove it against a larger/
real-world example (`twri.py`?) and confirm DIS-before-NPF/IC ordering
holds beyond the two-package case," not new mechanism.

**Still open, not blocking Phase 2, land any time / in parallel:**

- Phase 0.6a step 3 (codec reader path off legacy `modflow_devtools.dfn`)
  — not started.
- Phase 0.7 / the deferred union-item-class representation (real typed
  union arms for LAK/LKE/LKT/SFR/STO period rows, fixing the `AUXILIARY`
  data-loss bug) — unblocked now that Phase 0.6 landed, but no code written
  yet; `composite_v3.py`'s prototype logic didn't survive between sessions
  and would need re-deriving.
- Phase 1's known limitation (binding-row `pname` not threaded to a loaded
  child's `.name` — see that section) — small, well-scoped follow-up.
- Phase 3 (namefile grammar refinement) — was already flagged parallelizable.

After Phase 2: Phase 4 (cleanup, close out PR #284, update `docs/dev/`).

**Pre-existing, unrelated to Phase 0/1 work — noticed along the way, not
investigated:** the full suite has 50 pre-existing failures on `HEAD`
(confirmed via `git stash`, i.e. present before *and* after this session's
changes) — 47 in `test_mf6_row_api.py` (`TypeError`/`AttributeError`
patterns suggesting a `Row`-API round-trip regression from the Phase 0.6
migration itself, not yet triaged) plus `test_quickstart_grid`,
`test_gwe_lke_flow_package_auxiliary_name`, and
`test_gwt_lkt_flow_package_auxiliary_name` in `test_mf6_integration.py`
(real-`mf6`-execution failures, the last two plausibly related to the
already-known LAK/LKE/LKT keystring data-loss bug Phase 0.7 is meant to
fix). Worth a dedicated triage pass — `78c506b`'s commit message claimed
"full suite is green except two ... failures," which no longer matches.
