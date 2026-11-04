# Plan: turn reference notes into developer docs

Written 2026-10-19, against develop `e0d94b86`. Not started.

Some notes under `docs/dev/plans/` describe how flopy4 works now, rather
than work still to do. They belong in `docs/dev/` (the "Developer Notes"
part of `docs/_toc.yml`), rewritten for someone new to the codebase.
This plan lists the sources and what each page should say. One PR for all
of it is fine; it's docs only.

## Pages

### 1. List fields: `docs/dev/list-fields.md`

Source: [`design.md`](lists/design.md), plus the "Row layout" section of
[`record-unify.md`](lists/record-unify.md).

- Rewrite for the current state, not the August design:
  - fields declared with `list_()` (#463), period lists as
    `_stress_period_data` with a `stress_period_data` alias, fill-forward;
  - item classes (`Item`/`Record`, slots since #481), union arms;
  - storage: `ItemTable` (#479) keeps tabular rows as numpy columns, each
    Item a view; the three readers (`read_rows`, `Item.from_rows`,
    `Item.from_tokens`) as in `item_table.py`'s module docstring;
  - row layout: one positional rule, widths from package context, a
    boundname present iff the option (or `when`, #478) says so, no value
    sniffing; Python input flat or tupled;
  - views: `Package.to_xarray` for period lists (#476), the
    `<name>_ts`/`<name>_tas` coordinates (#489), DataFrames.
- Drop the "fan-out problem" history to a short paragraph, and drop the
  `period_as_dataset` sketch, which didn't land.
- Keep "Rationale for list over DataFrame"; it's still the argument.
- If the `Item`/`Record` merge ([`followups.md`](followups.md) item 4) lands first,
  describe the merged codec instead.

### 2. Mixins and generated classes: `docs/dev/mixins.md`

Source: [`mixin-fields.md`](components/mixin-fields.md).

- Mostly current (#447, #449). Trim the history ("as first merged ...")
  to what the check does now: sync reads each mixin's field paths, checks
  them against the generated classes, warns, and `flopy4 mf6 status`
  reports gaps per method.
- Item 3 of "What `mixin-requires` adds" had lost the end of a sentence;
  it was completed from context when the note moved here. Check that
  paragraph against the code (`flopy4/mf6/_sync.py`,
  `test/mf6/test_mixin_fields.py`).
- Keep "Still not caught" and "Why not type checking instead?".

### 3. Grid coordinates and selection: `docs/dev/grid-coordinates.md`

Source: [`rotated-grid-index.md`](xarray/rotated-grid-index.md), sections "Framing",
"Coordinates on a DIS array", "Selection", "Known limitations" and
"Alternatives considered".

- Write after `z-attach` merges, so the z coordinates and the `.grid`
  accessor are described as they are. The user-facing side is the
  selection guide on that branch (`docs/examples/selection.py`); this
  page is the design behind it (why local x/y plus a grid mapping, why
  `CellIndex`, edge ties, what isn't indexed).
- The plan's "Next" list stays in the plan, not the page.
- Then do the plan's housekeeping item: replace
  [`spatial-index-design.md`](archive/spatial-index-design.md) on `xarray-index` (#278) with a link
  to this page.

### 4. Refresh `docs/dev/load-benchmarks.md`

It still opens with the 2026-09-24 `load-baseline` numbers. #482 updated
the usage, but the results predate #474-#484. Rerun
`pixi run -e dev bench` and `bench-report`, and replace the numbers (the
archived [`io-benchmark-results.md`](archive/io-benchmark-results.md) is the same kind of table, also stale).
Keep the methodology (fair flopy3 options, materialize, the file check).

## Also fix while there

- `docs/_toc.yml` lists `dev/protocols-plan` and
  `dev/array-converter-design`, which don't exist in `docs/dev/`. Remove
  them, and add the new pages.
- `docs/dev/sdd.md`: link the new pages from "Dimension management",
  "Conversion" and "Xarray conversion", and check that its description of
  lists matches page 1.

## Not moving

- [`open-followups.md`](open-followups.md) and the `*-plan.md` files stay local: they track
  work, not how the code works.
- Archived docs stay in `archive/`.

## Done when

- The pages above build in the docs (`docs/_toc.yml`), and
  [`design.md`](lists/design.md) and [`mixin-fields.md`](components/mixin-fields.md) move to `archive/`
  with a pointer to their page.
