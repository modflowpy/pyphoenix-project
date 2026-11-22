# dev3 migration: gaps and overrides hit

**Status (2026-09-17): fully resolved.** Gaps #2 and #3 below got fixed
upstream, and the flopy4-side stopgap layer this doc tracked
(`overrides.py`/`dfn_overrides.toml`) has since been deleted entirely
(`f3cd6f6`/#353, `e3075da`/#354 — "no more overrides"). Gap #1
(`Array.repeat`) turned out not to be a devtools bug at all -- devtools
investigated it and found dev3's existing `shape=[]` self-sizing-array
semantics already cover what `repeat` would have expressed, and removed
the dead `repeat` mechanism rather than populate it (see
`~/dev/modflow-devtools/todo.md`, 2026-08-18 entry, checked off). The
remaining flopy4-side codegen/runtime work for self-sizing arrays --
covering both real patterns hiding behind dev3's one `shape == []`
representation, see gap #1 below -- is now implemented and tested
(`filters.py`, `make.py`, `record.py`, `structure.py`, `unstructure.py`,
`spec.py`, `basic.lark`, `macros.jinja`; `test/mf6/test_mf6_codec.py`).
Kept for the design-decision rationale in the second section, which
explains several non-obvious pieces of the current DFN-interpretation code
(e.g. why `role="feature_id"` is Integer-only, why keystring period lists
have two record shapes) that aren't reconstructible from the code alone.

**One new, unrelated bug surfaced along the way, since fixed** (found
2026-09-17, fixed 2026-09-17): `structure_component`'s Pass 1
(`converter/ingress/structure.py`) matched a row's leading token against
top-level field names *before* checking the inner-record-keyword lookup
(`inner_class_fields`). For utl-tas this meant `time_series_namerecord`'s
keyword `NAME` collided with `Package.name` (silently overwriting the
package's own instance name with the record's data) and `sfacrecord`'s own
field name (`sfac`, after `_strip_record_words` drops "record") collided
with its own inner record's trigger keyword. Fixed with two changes: (1)
`all_fields` now only indexes fields carrying `block` metadata, so
identity/bookkeeping attributes with no block metadata (`Component.name`,
`filename`, ...) can never shadow a same-named block keyword; (2) whenever
a matched field's type resolves to an inner Record class
(`_inner_class_type`), it's always dispatched through `from_tokens()`
rather than falling into the generic scalar/list branch, so a field whose
own name coincides with its record's trigger keyword still works. Along
the way, `record.py`'s `from_tokens` also turned out to assume every token
was a string (`tokens[i].upper()`), which crashed the first time this path
was actually exercised with a numeric-valued record (`loads()` already
parses numeric tokens to `int`/`float`) — fixed with `str(tokens[i])`.
Verified against a real MF6-written `.tas` file and
`test_load_tas_inner_classes_name_collision` (no longer `xfail`).

Working doc from `filters.py`/`make.py` rewrite. Two kinds of items:
**devtools-side gaps** (already logged in `devtools/todo.md`, need an
upstream fix) and **flopy4-side local overrides** (stopgaps in
`dfn_overrides.toml` that should come out once the upstream fix lands).

## Devtools-side gaps

1. ~~`Array.repeat` never populated by migration.~~ **Reclassified — not a
   devtools bug, and turned out to be two distinct flopy4-side patterns
   hiding behind one dev3 shape.** v1's `repeating: true` (affecting
   `utl-tas.tas_array`, `prt-oc.times`, `prt-prp.times`) looked like it
   needed a migration path into a `repeat` field, same bug class as
   `layered` (which *was* fixed, in f3ae0f4). Devtools investigated instead
   of migrating it: all 3 fields also carry v1 `shape (any1d)`, which the
   mapper already collapses to dev3's `shape=[]` — matching `dfnspec.md`'s
   self-sizing-array semantics, with no sibling count field for `repeat` to
   reference. `Array.repeat` was removed from `schema.py`/`dfnspec.md`/
   `schema.json` rather than backfilled (see `~/dev/modflow-devtools/
   todo.md`, 2026-08-18 entry, checked off 2026-09-17).

   Implementing the flopy4 side revealed dev3's `shape == []` actually
   covers **two unrelated wire-format patterns**, not one:

   - **Trailing-tokens record children** (`utl-tas.time_series_name`/
     `sfacval`, `prt-oc.track_timesrecord`/`prt-prp.release_timesrecord`'s
     `times`): plain `NAME v1 v2 ...`/`SFAC v1 v2 ...` syntax, consumed
     until the record runs out of tokens -- true "self-sizing" in the
     "MF6 reads until it runs out" sense. Fixed generally: `filters.py`'s
     `is_record_list_field`/`_record_child_supported`/
     `can_generate_record_class`, `make.py`'s `_build_record_class_specs`
     (emits `list[str]`/`list[float]` children), and `record.py`'s
     `to_tokens`/`from_tokens` (a `list[...]`-typed field consumes/emits
     all remaining tokens instead of exactly one). Verified against the
     whole dev3 corpus: flips exactly `time_series_namerecord`, `sfacrecord`,
     `track_timesrecord`, `release_timesrecord`, plus utl-ts's 3 records
     (not currently generated, but ready once utl-ts's other blockers
     clear) — nothing else in ~250 Record fields.
   - **`tas_array` itself**: not self-sizing in that sense at all -- a
     griddata-style `Array` field (U2DREL CONSTANT/INTERNAL/OPEN-CLOSE
     control-record syntax, sized by the grid) whose own block (`time`)
     repeats per distinct header value (`BEGIN TIME <t> ... END TIME`,
     found via a real MF6-written `.tas` fixture -- analogous to
     `BEGIN PERIOD <kper>` but keyed by a float time, not an int period
     index). Required four pieces: `filters.py`'s `is_readarray_field` +
     `make.py`'s time-array-series field spec (`Optional[dict[float,
     FloatArrayLike]]`, paralleling `stress_period_data`'s `dict[int,
     ...]` -- `time_from_model_start` isn't a stored field, same as `kper`
     isn't, it's carried by the dict's keys); `basic.lark`'s block-header
     grammar (`block_name: CNAME [INT]` → `[NUMBER]`, a safe superset since
     Lark's `NUMBER` already includes `INT`, verified against the full
     suite); a new ingress pass in `structure.py` (parses repeating
     `<block> <t>` blocks via the existing `_read_control_record`/
     `_griddata_flat_length` griddata primitives, needs `dims`); a new
     egress path in `unstructure.py` plus a `macros.jinja` `array_bare`
     macro (the block's content is the bare control record with no
     field-name token first -- `just_data true` in the v1 DFN, unlike a
     griddata field's `<NAME>\n  CONSTANT ...`). `spec.py`'s `to_field_type`
     also needed a `dict[K, V]` unwrap case (resolves dtype from the dict's
     value type) since existing period/griddata array fields never wrap in
     a dict.

   Both verified via round-trip tests in `test/mf6/test_mf6_codec.py`
   (`test_dumps_tas_inner_classes*`, `test_tas_array_roundtrip`,
   `test_tas_array_constant_roundtrip`) and against a real MF6-written
   `.tas` file. No upstream dependency for either.

2. ~~`numeric_index` → `pk`/`fk` backfill (a838d84) covered 6 fields, but
   44 have the same gap.~~ **Resolved upstream, comprehensively — superset
   fix, not a per-field audit.** A full recursive corpus scan (v1
   `numeric_index: true` vs dev3 leaf fields, including inside
   `List.item`/`Record`/`Union` nesting — a flat scan finds 0) had turned up
   44 fields with no `pk`/`fk` in dev3; only `gwf-lak.iconn` was confirmed to
   break a real test and got a local flopy4-side `pk = true` override.
   Devtools resolved the whole class by decomposing `pk`/`fk`'s conflated
   "needs 1-based/0-based conversion" + "is a relational key" concerns into a
   dedicated `index` attribute (`index-node-attributes-plan.md`, Phase 1):
   `Integer.index`/`Array.index` (the latter gated to `dtype == "integer"`),
   set mechanically (`index = numeric_index`) for *every* `Integer`/
   `Array(dtype="integer")` field in `migrate_to_v2_0_0_dev2.py` — applies
   unconditionally, not just where `pk`/`fk` are absent, so it's a superset
   of the 44-field gap rather than an audit of it. Verified: `gwf-lak.iconn`
   now comes through as `index=True` with no flopy4-side override needed
   (the override is gone, per the top status line).

3. ~~Bare `optional` attribute (no value) in v1 DFNs isn't migrated as
   `true`.~~ **Resolved upstream, generically — not a per-field patch.**
   v1 syntax allows a valueless `optional` line (vs. `optional true`/
   `optional false`) meaning "true"; the migration used to default it to
   `false` instead (30 occurrences across 12 v1 DFN files, only 3 fields ×
   6 packages confirmed breaking a real test at the time). Fixed at the
   shared parsing utility (`try_parse_bool`: an empty string now parses as
   `True`, not falling through to `default`), so it applies to every
   `optional`-parsing call site at once, not just the confirmed-broken
   printrecord fields. Verified live (2026-09-18): `gwf-oc`'s
   `formatrecord.{columns,width,digits}` now migrate as `optional=True`
   with no flopy4-side override present anywhere in the repo.

## Flopy4-side local overrides (`flopy4/mf6/utils/codegen/dfn_overrides.toml`)

**No longer exists** (`overrides.py`/`dfn_overrides.toml` deleted,
`f3cd6f6`/#353, `e3075da`/#354) — both stopgaps below were superseded by
the upstream fixes for gap #2 and #3 and removed along with the file.
Kept here for history only.

- `["gwf-lak".iconn] pk = true` — gap #2, confirmed via a real MF6 write
  failure (`iconn FOR LAKE 1 MUST BE > 1 and <= 9`) before the patch.
- `["<pkg>".columns/width/digits] optional = true` for `chf-oc`, `gwe-oc`,
  `gwf-oc`, `gwt-oc`, `olf-oc`, `gwt-ist` — gap #3, the printrecord family's
  `formatrecord.{columns,width,digits}`.

## Flopy4-side design decisions (not devtools bugs — schema is correct,
## flopy4 needed to interpret it more carefully than a first pass did)

- **`role="feature_id"` (0-based↔1-based conversion) must be Integer-only.**
  A `pk`/`fk` on a `String` field (e.g. MVR's `pname`, a package *name*
  reference) isn't a numeric index — applying the conversion crashed on
  `int("wel0")`. Fixed by gating `is_index` on `isinstance(col, Integer)`.
- **Keystring-shaped period lists have two real record shapes, not one.**
  LAK: `item` is a single-field Record wrapping the Union (index embedded
  per-arm, e.g. `lakeno`/`outletno`). LKE/LKT/SFR: `item` is a Record with
  an index field *and* a sibling Union field. Both needed detecting via
  `find_keystring_union`, not just the single-field-wrapper case.
- **Not every keystring union has an index column.** PRP's `releasesetting`
  (ALL/FIRST/LAST/FREQUENCY/STEPS) has no per-row index anywhere (confirmed
  via v1 DFN: bare `recarray releasesetting`, no feature-id field) — unlike
  LAK/LKE/SFR. Emitting a fabricated "number" column there was wrong.
  `_keystring_has_index` checks both the outer-sibling and per-arm-embedded
  cases before deciding whether to include it.
- **A bare Union arm (no data payload, e.g. OC's `ocsetting` ALL/FIRST/LAST)
  needs `Literal["ARM"]`, not generic `bool`** — a plain bool erases *which*
  of several mutually-exclusive flags was set.
- **`STO.storage` (period) is a bare scalar directly in the period block**,
  not a `List` — but still needs the same per-period `dict[int, ...]`
  fill-forward treatment as any other period field. Only `List` fields were
  getting that wrapping initially; bare period scalars needed the same path.
- **Nested records, one level deep, are a single recurring pattern, not
  arbitrary depth.** The `head/temperature/concentration/qoutflow/cim
  printrecord` family (6 fields) all wrap one `formatrecord: Record{columns,
  width, digits, format}`. Implemented via one level of recursive flattening
  in `_build_inner_class_spec`, replacing the old `extra_children` TOML
  override mechanism (now empty/unused) which had gone stale (wrong
  `optional` values baked in from an earlier, incorrect guess).
- **`is_file_record` (Record wrapping a File child, e.g. `ts_filerecord`)
  and a bare `File` field with no wrapping Record (e.g. `prt-fmi.packagedata`'s
  `gwfhead`/`gwfbudget`/`gwfgrid`) are different shapes** — both need
  `path()` codegen, but only one has a `Record` to unwrap.

## Explicitly out of scope for this pass (deferred, not forgotten)

- **Union-item-class shape** (real per-arm typed classes instead of the
  generic `(keyword, value)` approximation) — prototyped and validated
  (`composite_v3.py`, a scratchpad script that didn't survive between
  sessions). At the time this doc was written, `structure.py`/
  `unstructure.py` only understood the flat `Schema`/`Column`/`role=`
  vocabulary, so this was deferred pending Phase 0.6's `Row` migration.
  **Update (2026-08-20): Phase 0.6 has since landed** (`78c506b`) — `Row`
  is now the sole list-block schema, so this blocker is gone. Still not
  wired in; see Phase 0.7 in [`mf6-object-model-plan.md`](mf6-object-model-plan.md) for current status.
- ~~`utl-tas.TimeSeriesName`/`Sfac`~~ — **resolved**, see gap #1 above.
