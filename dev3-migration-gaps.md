# dev3 migration: gaps and overrides hit

Working doc from `filters.py`/`make.py` rewrite. Two kinds of items:
**devtools-side gaps** (already logged in `devtools/todo.md`, need an
upstream fix) and **flopy4-side local overrides** (stopgaps in
`dfn_overrides.toml` that should come out once the upstream fix lands).

## Devtools-side gaps

1. **`Array.repeat` never populated by migration.** v1's `repeating: true`
   has no migration path into `repeat` at all — same bug class as `layered`
   (which *was* fixed, in f3ae0f4). Affects 3 fields: `utl-tas.tas_array`,
   `prt-oc.times`, `prt-prp.times`. Flopy4 impact: these render as TODOs
   (unshaped/variadic arrays in a leaf position aren't modeled yet).

2. **`numeric_index` → `pk`/`fk` backfill (a838d84) covered 6 fields, but
   44 have the same gap.** A full recursive corpus scan (v1 `numeric_index:
   true` vs dev3 leaf fields, including inside `List.item`/`Record`/`Union`
   nesting — a flat scan finds 0) turns up 44 fields with no `pk`/`fk` in
   dev3. Most are local sequence/vertex/connection numbers (not full
   table-wide primary keys), e.g. `icell1d`/`icell2d`/`iv` (DISU/DISV vertex
   indices), `icon`/`iconr`/`idv` (MAW/SFR connection numbers), `cellidm1`/
   `cellidm2` (exchange cellid refs), `idcxs`, `bndno`. Only `gwf-lak.iconn`
   is confirmed to break a real (pre-existing) test so far — patched locally
   (see below). The other 43 are unaudited case-by-case.

3. **Bare `optional` attribute (no value) in v1 DFNs isn't migrated as
   `true`.** v1 syntax allows a valueless `optional` line (vs. `optional
   true`/`optional false`) meaning "true" — the migration defaults it to
   `false` instead. 30 occurrences across 12 v1 DFN files. Confirmed to
   break real tests for 3 fields × 6 packages (see override below);
   remaining occurrences in the other 6 files are unaudited.

## Flopy4-side local overrides (`flopy4/mf6/utils/codegen/dfn_overrides.toml`)

Stopgaps for gap #2 and #3 above, scoped to what's confirmed to break a real
test — not exhaustive fixes of either pattern.

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
  wired in; see Phase 0.7 in `mf6-object-model-plan.md` for current status.
- **`utl-tas.TimeSeriesName`/`Sfac`** — same root cause as devtools gap #1
  above (`Array.repeat`); test skipped with a clear reason rather than
  worked around.
