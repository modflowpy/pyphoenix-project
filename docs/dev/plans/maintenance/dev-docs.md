# Turning reference notes into developer docs

Some notes here describe how flopy4 works now rather than work to do. They
belong in `docs/dev/` (the "Developer Notes" part of `docs/_toc.yml`),
written for someone new to the codebase. Docs only; one PR is fine.

## Pages

### 1. List fields: `docs/dev/list-fields.md`

From [`list-fields.md`](../lists/list-fields.md), which is already written
for develop: representation, `ItemTable` storage and its three readers,
dimension sync, input forms, views, the row layout, and why rows rather
than columns. Add the `<name>_ts`/`<name>_tas` coordinates (#489) to the
views. If the `Item`/`Record` merge ([`record-unify.md`](../lists/record-unify.md))
lands first, describe the merged codec.

### 2. Mixins and generated classes: `docs/dev/mixins.md`

From [`mixin-fields.md`](../components/mixin-fields.md), which describes
the sync-time scan as it is (#449). Check it against `flopy4/mf6/_sync.py`,
`_mixin_fields.py` and `test/mf6/test_mixin_fields.py`.

### 3. Grid coordinates and selection: `docs/dev/grid-coordinates.md`

From [`rotated-grid-index.md`](../xarray/rotated-grid-index.md): "Framing",
"Coordinates on a DIS array" and "Selection". The user-facing side is the
selection guide (`docs/examples/selection.py`); this page is the design
behind it (why local x/y plus a grid mapping, why `CellIndex`, edge ties,
what isn't indexed). The "Next" list stays in the plan.

### 4. Refresh `docs/dev/load-benchmarks.md`

It opens with the 2026-09-24 `load-baseline` numbers, which predate
#474-#484. Rerun `pixi run -e dev bench` and `bench-report` and replace
them, keeping the methodology (fair flopy3 options, materialize, the file
check).

## Also

- Add the new pages to `docs/_toc.yml`.
- `docs/dev/sdd.md`: link the new pages from "Dimension management",
  "Conversion" and "Xarray conversion", and check its description of lists
  against page 1.

When a page is published, its source note moves to the archive with a
pointer to the page.
