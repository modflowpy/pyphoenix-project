# flopy4 Write Performance Profiling

## Purpose

An early, lightweight read on flopy4 write performance compared to flopy3.
This is **not** a rigorous benchmark suite — results reflect a single development
machine, a single Python version, and a narrow slice of the write path.
The intent is to surface obvious regressions and gross performance gaps early,
not to replace a proper profiling infrastructure.

A more rigorous approach (multi-platform CI benchmarks, statistical sampling,
tools like `pytest-benchmark` or `airspeed-velocity`) should supersede this
work when the library is closer to production maturity.

---

## Approach

All profile scripts live in `docs/profile/`.

| Script | Model | Focus |
|--------|-------|-------|
| `ff_write.py` | frenchman-flat (DISV, ~6K cells, 33 periods) | flopy4 list vs. flopy3 list; flopy4 grid ASCII variant |
| `test1000_write.py` | test1000\_751x751 (struct, 582K cells, 3 periods) | sparse vs. dense stress packages |
| `test1005_write.py` | test1005\_secp (struct, 572K cells, 6 periods) | realistic multi-package model |
| `diag_list_scaling.py` | synthetic 1L×1R×N struct grid | list write O(n) scaling + cProfile |
| `run_all.py` | — | runner; optional JSON + Markdown output |

**Methodology:**
- Both flopy4 and flopy3 models are built from scratch in Python from the same
  in-memory arrays. No load-then-write round-trips.
- Only the write call is timed (`sim.write()` / `sim.write_simulation()`).
- The first run exceeding 30 s is flagged `[slow]`; remaining runs are skipped
  unless `--include-slow` is passed.
- Default `--runs 5`; pass `--runs N` to adjust.
- Results optionally written to JSON via `--output path.json`.

**Key assumptions / caveats:**
- Timings are wall-clock on a single Linux workstation (no isolation, no warmup).
- flopy3 v3.10.0; flopy4 `profile` branch.
- Large test models from `modflow6-largetestmodels` are required for
  `test1000_write.py` and `test1005_write.py` and are not bundled.
  Pass `--models-root <DIR>` (or via `run_all.py --models-root`) to specify
  the repo root; without it those scripts exit with a clear error.
- Grid-based (WELG/CHDG) variants write full (nper × nlay × nrow × ncol) ASCII
  arrays; impractical for very large or high-period-count grids.

---

## Results (single-run baseline, 2026-05-18, `profile` branch)

### frenchman-flat (DISV, ~6K active cells)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL) | 0.31 |
| flopy4 grid ASCII (WELG, 7.5M elements) | 1.15 |
| flopy3 list (WEL) | 0.90 |

flopy4 list is ~3× faster than flopy3. The grid ASCII variant is included to
show the cost of writing full (nper × nlay × nrow × ncol) arrays when the
stress package is very sparse — here it is slower than both list variants.

### test1000\_751x751 (structured, 582K cells, 3 stress periods)

#### Scenario 1 — Sparse stress packages (WEL 1 cell + CHD 1550 cells)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL + CHD) | 0.25 |
| flopy4 grid ASCII (WELG + CHDG, 1.74M entries) | 0.24 |
| flopy3 list (WEL + CHD) | 1.90 |

flopy4 is ~8× faster than flopy3 for sparse list packages.

#### Scenario 2 — Dense uniform RCH (582K cells, constant=0.001)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list Rch (1.74M entries) | 348 ⚠ slow |
| flopy4 array Rcha (CONSTANT) | 0.25 |
| flopy3 list Rch | 12.2 |
| flopy3 array Rcha (CONSTANT) | 2.0 |

#### Scenario 3 — Dense heterogeneous RCH (582K cells, K-derived)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list Rch (1.74M entries) | 346 ⚠ slow |
| flopy4 array Rcha (per-cell) | 0.87 |
| flopy3 list Rch | 11.8 |
| flopy3 array Rcha | 5.7 |

### test1005\_secp (structured, 572K cells, 6 periods, WEL + CHD + RCHA)

| Variant | Time (s) |
|---------|-------:|
| flopy4 list (WEL + CHD + RCHA) | 0.67 |
| flopy3 list (WEL + CHD + RCHA) | 4.43 |

flopy4 is ~6.6× faster here because the stress packages are sparse
(WEL: 3971 cells × 6 periods; CHD: 18647 cells × 1 period) and the
recharge is array-based (RCHA, written as CONSTANT or INTERNAL).

---

## Key learnings

**1. Array (G/A) packages are the right choice for dense data.**
When a stress package touches most cells, the array variant (`Rcha`, `Welg`,
`Chdg`) should be used over the list variant (`Rch`, `Wel`, `Chd`).
flopy4 Rcha writes 582K-cell recharge in 0.25–0.87 s (CONSTANT/INTERNAL);
the list variant took 348 s. This is not a flopy4-specific rule — flopy3's list
Rch also takes 12 s for the same data. The performance difference between
list and array grows with cell count.

**2. flopy4 list write was O(n) but with ~10× worse constant than flopy3.**
`diag_list_scaling.py` confirmed linear scaling for both before and after fixes
(no quadratic loops). The baseline constant was ~220 µs/cell vs. flopy3's
~20 µs/cell. After targeted fixes (see below), this improved to ~27 µs/cell.

**3. flopy4 is faster than flopy3 for sparse packages.**
For models where stress packages cover a small fraction of cells (frenchman-flat,
test1005 WEL/CHD), flopy4 list write is 3–8× faster than flopy3.

---

## Local optimizations (applied on `profile` branch)

Two targeted fixes were made to `flopy4/mf6/codec/writer/filters.py` and
`flopy4/mf6/codec/writer/templates/macros.jinja` during profiling.
These are not part of a formal optimization sprint and should be reviewed
before merging to `develop`.

### Fix 1 — Vectorized `dataset2list` extraction (`filters.py`)

**Problem:** `dataset2list` indexed into xarray DataArrays one cell at a time
via label-based indexing (`da[tuple(idx[i] for idx in indices)]`), which carries
~80 µs of xarray overhead per cell.

**Fix:** Pre-extract all values from each data variable as numpy arrays outside
the per-row loop (`da.values[tuple(indices)]`), then use plain numpy scalar
access inside the loop.

**Result:** `data2list` for a 25K-cell period Dataset: 2.11 s → 0.23 s (9×).
End-to-end list write: 250K cells, 45.9 s → 6.7 s (6.8×).

### Fix 2 — Eliminate Jinja2 per-row iteration (`macros.jinja` + `filters.py`)

**Problem:** The `list` macro in `macros.jinja` iterated over list rows in
Jinja2's sandboxed environment, triggering ~25K `getattr` calls per write
for attribute access through the sandbox.

**Fix:** Added a `data2lines` filter that pre-formats all rows into a single
newline-joined string in Python. The `list` macro now emits one `{{ value|data2lines }}`
expression instead of a per-row loop.

**Result:** Eliminates ~0.4 s of Jinja2 sandbox overhead per 25K-cell write;
proportionally larger gain for bigger models.

### Combined scaling result

| cells | baseline (s) | after fixes (s) | speedup |
|------:|-------------:|----------------:|--------:|
| 1,000 | 0.22 | 0.08 | 2.9× |
| 5,000 | 0.94 | 0.16 | 5.9× |
| 25,000 | 4.52 | 0.65 | 7.0× |
| 100,000 | 18.0 | 2.6 | 6.9× |
| 250,000 | 45.9 | 6.7 | 6.9× |

Extrapolating to 582K cells × 3 periods: ~47 s (vs. baseline ~350 s).
Still above the 30 s slow threshold; further optimization is deferred to
a dedicated sprint.

---

## Next steps

- **Optimization sprint** — The remaining per-row Python loop in `dataset2list`
  and other write-path overhead can be attacked more systematically. Candidate
  approaches include fully vectorized row generation (bypassing Python loops
  entirely) and lazy/streaming write paths for very large models.

- **CI integration** — Running targeted profiles on each CI platform (Linux,
  macOS, Windows) on each commit would catch regressions early and build a
  performance history. Platform differences in I/O and Python overhead are
  significant enough that cross-platform data is worth collecting.
  `run_all.py --output` already produces JSON suitable for ingestion by a
  tracking tool.

- **flopy4-specific output format profiling** — `ff_write.py` already
  collects timing data for flopy4-only output formats (grid ASCII, NetCDF
  base, NetCDF mesh, NetCDF structured) on the frenchman-flat model. These
  results are not included here because there is no flopy3 equivalent to
  compare against. A future profiling effort should treat these as their own
  category: flopy4 format vs. format comparisons (e.g. list vs. grid ASCII
  vs. NetCDF) across model sizes and package densities.

- **Replace with a proper profiling framework** — Tools like
  `pytest-benchmark` or `airspeed-velocity` (asv) provide statistical
  rigor (multiple runs, outlier rejection, confidence intervals, history
  graphs) that these scripts lack. This effort is a stopgap; the scripts
  here should be replaced or wrapped by such a framework once the write
  path is more stable.
