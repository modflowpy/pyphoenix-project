# Period lists in xarray

Plan for giving list packages' stress period data an xarray form, generically,
with no per-package code. Starts from commit `e87c53e` ("put list packages'
stress period data on the grid"), which exists only on `ts-ref` (local and
`origin/ts-ref`).

## Starting point: e87c53e

- New `flopy4/mf6/period_lists.py` (276 lines), `Package.to_xarray()` branch,
  new `Package.from_xarray()`, `test/mf6/test_mf6_period_lists.py` (12 tests).
- Puts each value column on the dense grid, `(per, ...grid)`, a variable per
  aux name, `FILL_DNODATA` where a period has no boundary, carrying periods
  forward as MF6 does. `from_xarray` writes a period block only where a period
  differs from the one before.
- Already structural, not name-based: the cell is found from `cellid`
  metadata, or through an `fk` to a table with one cellid (UZF's `ifno` ->
  packagedata).
- Raises (pointing to `to_dataframe()`) for: two rows in one cell, time-series
  values, keystring rows (SFR, LAK, MAW, TVK), two cellids (HFB), no cellid
  (MVR, STO). Drops boundnames with a warning.
- Builds dense `(per, grid)` arrays eagerly via `period_arrays.dense`.
- Array columns (EVT's `pxdp`, `petm`, length `nseg - 1`) get an extra dim,
  named with a placeholder `<column>_dim0`.
- Branch state: `ts-ref`'s other commits (`f9caa23`, `9428067`, `f3ad6f3`)
  landed in develop via squash merges (#450, #456). `e87c53e` merges cleanly
  onto develop `22e1fd9`; its dependencies (`period_arrays.dense`,
  `FILL_DNODATA`, `TimeSeriesRef`, `_row_dict`) are all on develop. Not yet
  tested against #454/#455.

## Design

### Index dim from the row's key

| Row key | Index dim | Examples |
|---|---|---|
| one `cellid` | grid: `(layer, row, col)` / `(layer, cell)` / `(node,)` | CHD, WEL, DRN, TVK |
| `fk` to another table's `pk` | that table's sizing dim, e.g. `(per, nreaches)` | UZF, SFR, LAK, MAW, LKT |
| anything else (two cellids, no key) | `entry` dim, period and key columns as coordinates | HFB, MVR |

All from metadata: `cellid`, `fk`, `pk`, `union`, `array`, `time_series`,
`dim`, `shape`.

### Dim naming

Name dims after the DFN sizing dimension, which the user sees, not a field
name, which they don't.

- fk-keyed rows: `fk="packagedata.ifno"` names the `packagedata` field, whose
  `dim=` metadata gives the dim (`nreaches` for SFR, `nuzfcells` for UZF,
  `nlakes`, `nmawwells`, ...).
- Array columns: name the extra dim from the column's `shape` metadata, not
  `<column>_dim0`.
- Grid dims (decided 2026-10-14): the exception, named for the grid's axes,
  `(layer, row, col)`, `(layer, cell)`, `(node,)`, since they're typed in
  selections constantly and xarray has no dim aliases. DFN sizing names only
  in `constants.GRID_DIMS`, for size lookup. No index coordinates (positions
  are the indices; `k` clashes with NPF's/TVK's `k`). Sparse cellid columns
  `cellid_layer`, ...; sparse dim `entry` (not `row`). `cell`, not `node`,
  for DISV: UGRID's node is a vertex. Branches: `grid-dims` (#469:
  `to_dataarray`; DIS output readers to `row`/`col` with indexed x/y and no
  1-based layer coord; DISV output keeps xugrid's face dim), `period-lists`,
  `grid-coords` (`utils/grid.py`, `grid.dims`). `disv-j` abandoned.

### Dense by default, sparse opt-in

- `to_xarray()` is dense along the key dim: the grid for cellid-keyed rows,
  the feature dim for fk-keyed rows (one slot per feature, missing where a
  period doesn't set it). Grid projection of fk-keyed rows (through
  packagedata's cellid) is a separate opt-in view.
- Rows with no dense form (HFB, MVR) fall back to the row form, the same
  output as sparse. No raising.
- `to_xarray(sparse=True)`: lossless `(per, row)` form for any package, cellid
  (or other key) as a coordinate.
- Two rows in one cell: `to_xarray(duplicates="raise" | "sum" | "first")`.
  Default `"raise"` (lossless), and the error offers `sparse=True` or
  `duplicates="sum"`. `"sum"`/`"first"` are documented as lossy (merged
  rows lose boundnames; `from_xarray` won't round-trip). No per-column
  "additive" knowledge: the reduction is the user's choice.
- Array columns stay a dim (ordered, like quantities); aux stays a variable
  per name (named, unlike quantities). Flattening to `pxdp_1..n` is the
  flopy3 adapter's job.

### Keystring (union) rows

Pivot `(key, setting, value)` rows into one variable per setting:
`status(per, nreaches)`, `inflow(per, nreaches)`, ... (members from `union`
metadata). Text settings become string variables. Missing means not set this
period. Settings persist per setting in MF6 (not replaced as a block), so
carry forward per setting; the union-ness of the row says which semantics
applies.

### Lossless extras

- Boundnames: a string coordinate on the key dim (dense) or row dim (sparse).
- Time-series values: numeric variable with NaN where a series applies, plus a
  `<column>_ts` string coordinate/variable holding series names, mirroring
  period arrays' `<name>_tas`. Evaluation (see tas-interpolation-plan.md) can
  later fill values as a separate opt-in step.

### Memory

Don't build `(nper, grid)` per column eagerly. Store only periods with blocks
and fill forward, as period arrays do, or build lazily (dask).

## Steps

1. Rebase `e87c53e` onto develop in a new worktree, branch `period-lists`:
   `git rebase --onto origin/develop f3ad6f3 <branch>` (don't touch `ts-ref`
   or the main checkout, which is on `ts-ref`).
2. Rename DISV dim `face` -> `j` in `Package.to_dataarray`, its dask test, and
   `_GRIDS`. Possibly a small separate PR first.
3. Rework `period_lists`:
   - key dim from `cellid` / `fk`->`dim` / row fallback;
   - pivot keystring rows, per-setting carry-forward;
   - boundnames and TS names as coordinates;
   - sizing-dim names (fk features, array columns);
   - periods-with-blocks storage or lazy build;
   - `sparse=True`;
   - `duplicates=` reduction;
   - `from_xarray` inverse for each form.
4. Tests: rework existing; add SFR/LAK/MAW (keystring, feature dims), UZF
   (feature dim + grid view), HFB/MVR (row fallback), boundnames, TS values,
   two-rows-in-a-cell raise, `duplicates="sum"`/`"first"`, sparse round
   trips, multi-value aux with boundnames.
5. Verify: `pixi run -e dev pytest test/mf6/test_mf6_period_lists.py` plus
   other touched files, ruff, mypy. Push and open a PR only when asked.
6. After merge: delete `ts-ref` locally and on the fork.

## Follow-ups

- Fill in `Flopy3ListData` (empty stub in `flopy4/mf6/adapters.py`) over the
  new Dataset: `to_array(kper, mask)` -> `{column: grid}` with
  `duplicates="sum"`, extra dims flattened to `<col>_1..n`;
  `masked_4D_arrays_itr`; wire into `Flopy3Package`. See
  `.claude/worktrees/list-to-xarray/209-ideas.txt`.
- `list-to-xarray` branch: `0348be2` is superseded by this work (drop it);
  `99077f9` landed separately as branch `trailing-none-boundname`.

- `attrs_to_dataset` still puts rows as objects into the dataset's attrs.
- Once TS evaluation exists, optionally fill evaluated values instead of NaN.

## Status (2026-10-19)

- **Merged as #476** ("support xarray conversion for list-based stress
  packages"), from branch `period-lists`. #489 (`series-nan`) then made
  time-series placeholders `NaN` in the xarray form, with the series name
  in a `<name>_ts` / `<name>_tas` coordinate (`None` where a period has no
  series), and fixed the netCDF round trip of those names.
- DISV's within-layer dim stays `cell`; the `disv-j` rename (#461) was
  closed 2026-10-18.
- Still open, from the follow-ups above:
  - `Flopy3ListData` in `flopy4/mf6/adapters.py` is still an empty stub.
  - `attrs_to_dataset` still puts rows as objects into the dataset's
    attrs.
  - Lazy/periods-only storage (the dense form is eager).
  - `auxiliary` as an int count when rows give aux values without names.
  - Filling evaluated series values instead of NaN, once TS/TAS
    evaluation exists ([`tas-interpolation.md`](../xarray/tas-interpolation.md)).
- Local cleanup (ask first): branches/worktrees `period-lists`,
  `list-to-xarray`, `disv-j` are merged or closed.

## Status (2026-10-13)

- Branch `period-lists` (worktree `.claude/worktrees/period-lists`), local
  only: `08aff59` (rebased e87c53e), `da83387` (DISV `j`), `b0dd085`
  (rework). `disv-j` holds the rename alone, off develop.
- Done: steps 1-4 except lazy/periods-only storage (dense form is eager;
  documented). Grid dim names in `constants.GRID_DIMS`.
- Fallback dim names where the DFN has no sizing dim: the key field
  (LKT/LKE `ifno`/`lakeno`, SPC `bndno`) and setting indexes (`idv`, `icon`).
- Open: `auxiliary` becomes an
  int count when rows give aux values without names.
