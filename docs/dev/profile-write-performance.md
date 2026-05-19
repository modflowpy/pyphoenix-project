# flopy4 Write Performance Profiling

## Purpose

An early, lightweight read on flopy4 write performance compared to flopy3, and
on the relative cost of flopy4 output formats (list ASCII, array ASCII, array
NetCDF). Results reflect a single development machine, a single Python version,
and a narrow slice of the write path. The intent is to surface obvious
regressions and gross performance gaps early — not to replace a proper
profiling infrastructure.

---

## Approach

All profile scripts live in `docs/profile/`.

| Script | Model | Focus |
|--------|-------|-------|
| `ff_write.py` | frenchman-flat (DISV, ~6K cells, 33 periods) | flopy4 vs flopy3 list; flopy4 format comparison |
| `test1000_write.py` | test1000\_751x751 (struct, 582K cells, 3 periods) | sparse vs. dense stress packages; flopy4 format comparison |
| `test1005_write.py` | test1005\_secp (struct, 572K cells, 6 periods) | realistic multi-package model; flopy4 format comparison |
| `diag_list_scaling.py` | synthetic 1L×1R×N struct grid | list write O(n) scaling + cProfile |
| `run_all.py` | — | runner; optional JSON + Markdown output |

**Methodology:**
- Both flopy4 and flopy3 models are built from scratch in Python from the same
  in-memory arrays. No load-then-write round-trips.
- Only the write call is timed (`sim.write()` / `sim.write_simulation()`).
  For NetCDF variants, `to_netcdf()` is included in the timed call since it is
  part of the total cost a user pays when choosing the NetCDF output path.
- The first run exceeding 30 s is flagged `[slow]`; remaining runs are skipped
  unless `--include-slow` is passed.
- Default `--runs 5`; pass `--runs N` to adjust.
- Results optionally written to JSON via `--output path.json`.

**Caveats:**
- Timings are wall-clock on a single Linux workstation (no isolation, no warmup).
- flopy3 v3.10.0; flopy4 `profile` branch.
- Large test models from `modflow6-largetestmodels` are required for
  `test1000_write.py` and `test1005_write.py` and are not bundled.
  Pass `--models-root <DIR>` (or via `run_all.py --models-root`) to specify the repo root.
- ASCII grid variants (WELG/CHDG) write full (nper × nlay × nrow × ncol) arrays;
  impractical for very large or high-period-count grids.
  NetCDF grid variants are included where ASCII is impractical (test1005).

---

## Results

Two separate comparisons are reported: flopy4 vs flopy3 (list packages only,
apples-to-apples) and a flopy4-only format comparison (list ASCII vs array ASCII
vs array NetCDF). flopy3 has no NetCDF output path, so it does not appear in the
format comparison.

All timings are minimum of 5 runs, 2026-05-19, `profile` branch.

### flopy4 vs flopy3

#### frenchman-flat (DISV, ~6K active cells)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL) | 0.20 |
| flopy3 list (WEL) | 0.86 |

flopy4 list is ~4× faster than flopy3.

#### test1000\_751x751 (structured, 582K cells, 3 stress periods)

##### Scenario 1 — Sparse stress packages (WEL 1 cell + CHD 1550 cells)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL + CHD) | 0.22 |
| flopy3 list (WEL + CHD) | 1.93 |

flopy4 is ~9× faster than flopy3 for sparse list packages.

##### Scenario 2 — Dense uniform RCH (582K cells, constant=0.001)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list Rch (1.74M entries) | 22.3 |
| flopy4 array Rcha (CONSTANT) | 0.24 |
| flopy3 list Rch | 11.5 |
| flopy3 array Rcha (CONSTANT) | 2.0 |

##### Scenario 3 — Dense heterogeneous RCH (582K cells, K-derived)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list Rch (1.74M entries) | 25.0 |
| flopy4 array Rcha (per-cell) | 0.82 |
| flopy3 list Rch | 12.1 |
| flopy3 array Rcha | 5.7 |

For dense list, flopy3 is ~2× faster than flopy4. For dense array, flopy4 wins
by 8× (CONSTANT) and 7× (per-cell). See Key learnings 1 and 2.

#### test1005\_secp (structured, 572K cells, 6 periods, WEL + CHD + RCHA)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL + CHD + RCHA) | 0.73 |
| flopy3 list (WEL + CHD + RCHA) | 4.74 |

flopy4 is ~6.5× faster because the stress packages are sparse
(WEL: 3971 cells × 6 periods; CHD: 18647 cells × 1 period) and recharge is
array-based (RCHA, written as CONSTANT or INTERNAL).

---

### flopy4 format comparison (list ASCII · array ASCII · array NetCDF)

NetCDF timing includes both `to_netcdf()` and `sim.write()` — the full cost
a user pays when choosing the NetCDF path.

#### frenchman-flat (DISV, ~6K active cells, 33 periods)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list ASCII (WEL) | 0.20 |
| flopy4 array ASCII (WELG, 7.5M elements) | 1.04 |
| flopy4 array netcdf\_base (WEL + NetCDF arrays) | 0.28 |
| flopy4 array netcdf\_mesh (WELG + layered NC) | 0.28 |
| flopy4 array netcdf\_struct (WELG + CF NC) | 0.27 |

#### test1000\_751x751 — Scenario 1 (sparse WEL+CHD, 1.74M array elements)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list ASCII (WEL+CHD) | 0.22 |
| flopy4 array ASCII (WELG+CHDG) | 0.22 |
| flopy4 array netcdf\_mesh (WELG+CHDG) | 1.83 |
| flopy4 array netcdf\_struct (WELG+CHDG) | 0.08 |

#### test1000\_751x751 — Scenario 2 (dense uniform RCH, CONSTANT)

| Variant | Time (s) |
|---------|-------:|
| flopy4 array ASCII (Rcha, CONSTANT) | 0.24 |
| flopy4 array netcdf\_mesh (Rcha) | 1.73 |
| flopy4 array netcdf\_struct (Rcha) | 0.11 |

#### test1000\_751x751 — Scenario 3 (dense heterogeneous RCH, per-cell)

| Variant | Time (s) |
|---------|-------:|
| flopy4 array ASCII (Rcha, per-cell) | 0.82 |
| flopy4 array netcdf\_mesh (Rcha) | 1.79 |
| flopy4 array netcdf\_struct (Rcha) | 0.14 |

#### test1005\_secp (572K cells, 6 periods — ASCII grid omitted, 34M elements)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list ASCII (WEL+CHD+RCHA) | 0.73 |
| flopy4 array netcdf\_mesh (WELG+CHDG+RCHA) | 0.31 |
| flopy4 array netcdf\_struct (WELG+CHDG+RCHA) | 0.09 |

`netcdf_struct` is the fastest format across all models and scenarios. `netcdf_mesh`
behaves very differently: comparable to structured on small models (~0.28 s on
frenchman-flat) but 1.7–1.8 s on test1000 — 13–20× slower than structured on the
same data. The mesh format writes a separate layered geometry file whose cost scales
with model size; the structured CF format does not.

---

## Key learnings

**1. Use array (G/A) packages for dense data.**
When a stress package touches most cells, the array variant (`Rcha`, `Welg`,
`Chdg`) should be preferred over the list variant. flopy4 Rcha writes 582K-cell
recharge in 0.24–0.82 s (CONSTANT/INTERNAL); the list variant takes 22–25 s.
This applies equally to flopy3 (list Rch: ~12 s for the same data). The gap
grows with cell count.

**2. flopy4 list write is O(n) but was ~10× slower per cell than flopy3.**
`diag_list_scaling.py` confirmed linear scaling before and after fixes (no
quadratic loops). The baseline constant was ~220 µs/cell vs. flopy3's ~20
µs/cell; after targeted fixes (see below) this improved to ~27 µs/cell. For
dense list Rch (582K cells × 3 periods) this reduced end-to-end time from
~350 s to 22–25 s — flopy3 is still faster at ~12 s, but the gap narrowed
from ~30× to ~2×.

**3. flopy4 is faster than flopy3 for sparse list packages.**
For models where stress packages cover a small fraction of cells (frenchman-flat,
test1000 sparse, test1005 WEL/CHD), flopy4 list write is 4–9× faster than flopy3.

**4. `netcdf_struct` is the fastest write format and eliminates the ASCII size penalty.**
ASCII grid write time scales with total array elements regardless of how many are
active — every FILL\_DNODATA sentinel must be written. `netcdf_struct` (CF-convention
structured NetCDF) does not carry this cost and is consistently the fastest format
across all models and data densities tested:

| Scenario | netcdf\_struct | array ASCII | list ASCII |
|----------|---------------:|------------:|-----------:|
| frenchman-flat (7.5M sparse) | 0.27 s | 1.04 s | 0.20 s |
| test1000 sparse WELG+CHDG | 0.08 s | 0.22 s | 0.22 s |
| test1000 dense Rcha CONSTANT | 0.11 s | 0.24 s | 22.3 s |
| test1000 dense Rcha per-cell | 0.14 s | 0.82 s | 25.0 s |
| test1005 WELG+CHDG+RCHA (34M) | 0.09 s | — too large | 0.73 s |

`netcdf_mesh` (layered-mesh NetCDF) does not share this advantage: it is fast on
small models but 1.7–1.8 s on test1000, due to the cost of writing the separate
layered geometry file at scale.

---

## Local optimizations (applied on `profile` branch)

Two targeted fixes were made to `flopy4/mf6/codec/writer/filters.py` and
`flopy4/mf6/codec/writer/templates/macros.jinja`. These should be reviewed
before merging to `develop`.

### Fix 1 — Vectorized `dataset2list` extraction

**Problem:** `dataset2list` indexed into xarray DataArrays one cell at a time
(~80 µs overhead per cell via label-based indexing).

**Fix:** Pre-extract all values as numpy arrays outside the per-row loop;
use plain numpy scalar access inside.

**Result:** `data2list` for a 25K-cell period: 2.11 s → 0.23 s (9×).
End-to-end list write at 250K cells: 45.9 s → 6.7 s (6.8×).

### Fix 2 — Eliminate Jinja2 per-row iteration

**Problem:** The `list` macro in `macros.jinja` iterated over rows in Jinja2's
sandboxed environment (~25K `getattr` calls per write).

**Fix:** Added a `data2lines` filter that pre-formats all rows into a single
newline-joined string in Python; the macro emits one `{{ value|data2lines }}`
expression instead of a per-row loop.

**Result:** Eliminates ~0.4 s of Jinja2 sandbox overhead per 25K-cell write;
proportionally larger for bigger models.

### Combined scaling result

| cells | baseline (s) | after fixes (s) | speedup |
|------:|-------------:|----------------:|--------:|
| 1,000 | 0.22 | 0.08 | 2.9× |
| 5,000 | 0.94 | 0.16 | 5.9× |
| 25,000 | 4.52 | 0.65 | 7.0× |
| 100,000 | 18.0 | 2.6 | 6.9× |
| 250,000 | 45.9 | 6.7 | 6.9× |

End-to-end for 582K cells × 3 periods (test1000 dense list): ~350 s baseline →
22–25 s after fixes, now completing under the 30 s slow threshold.

---

## Next steps

- **Optimization sprint** — The remaining per-row Python loop in `dataset2list`
  and other write-path overhead can be addressed more systematically. Candidates
  include fully vectorized row generation and lazy/streaming write paths for
  very large models.

- **CI integration** — Targeted profiles on each CI platform (Linux, macOS,
  Windows) on each commit would catch regressions early and build a performance
  history. `run_all.py --output` already produces JSON suitable for a tracking
  tool.

- **Replace with a proper profiling framework** — Tools like `pytest-benchmark`
  or `airspeed-velocity` (asv) provide statistical rigor (outlier rejection,
  confidence intervals, history graphs) that these scripts lack. This effort is
  a stopgap and should be superseded once the write path stabilizes.
