# Plan: input-load optimizations (basic loader first)

**Archived 2026-10-19.** Superseded by [`typed-loader-perf.md`](../loading/typed-loader-perf.md) and merged as #474, #479, #481, #483 and #484. Lazy imports, bulk numeric runs and bulk external arrays are all in.

Goal: make flopy4 simulation loading faster than flopy3 across the board, by
taking per-token Python work out of the hot paths. Each step is measured
against the committed baseline and checked for unchanged results.

Written 2026-09-29. It applies to the **basic** loader, which users run
today. None of it waits on the typed-loader wiring
([`typed-loader-wiring.md`](../loading/typed-loader-wiring.md)); the typed grammar gets the same bulk-token
idea when it's wired in. Index of related work: [`loader-roadmap.md`](loader-roadmap.md).

## Background (read first)

- `docs/dev/load-benchmarks.md` (branch `load-baseline`): the flopy3 vs.
  flopy4 baseline, and "Why array reading differs: Python work per token,
  per line, or per file".
- [`typed-grammar-remarks.md`](typed-grammar-remarks.md), "Why the typed loader isn't faster
  (yet)": where parse time goes, and the original data-block idea.

**`develop` has moved since the baseline.** The numbers below were measured
at `fe5423c`. Since then:
- #370 ("fix number parsing") changed both grammars. `basic.lark` now lexes
  every whitespace-separated token as one generic `TOKEN`, and
  `BasicTransformer` decides per token whether it's a number. `typed.lark`'s
  number terminals now only match whole tokens.
- #373 ("fix support for trailing text") changed `structure.py`.
- #369 added a round-trip test (`test/mf6/test_mf6_io_roundtrip.py`).

So **re-run `bench-load` and `bench-parse` on current `develop` first**,
and use that as the "before" for step 1. The per-token cost and the
flopy3/flopy4 ratios may have shifted.

The core finding: speed tracks how much Python work runs per value.
Per-token work (Lark: lex, parse, a tree node, a callback per number) is
slowest, per-line work (flopy3's loops) is in between, and a whole-file or
whole-block pass in C is fastest. flopy4 is per-token for all inline data
today, and per-file only for `OPEN/CLOSE` arrays, which is the one place it
clearly beats flopy3.

## Where time goes now (measured)

| | flopy3 | flopy4 basic | notes |
|---|---|---|---|
| corpus, load + read all data (165 models) | 17.0 s | 14.4 s | one outlier is ~10 s of flopy3's time |
| same, without henrytidal | 6.2 s | 10.0 s | |
| cold start (fresh interpreter) | 0.94 s | 2.41 s | flopy4: 1.52 s imports, of which flopy3 ~0.64 s, xugrid ~0.45 s |

- **Corpus inline tokens:** 1.44 M in total, split 59.5% array data, 38.6%
  list rows, 1.9% other. External (`OPEN/CLOSE`) data is excluded.
- **Lark costs ~7-10 µs per token**, about 11.5 s of the 14.4 s. A bulk
  numpy read costs ~0.25-0.4 µs per value, including tolerance for
  comments and delimiters.
- **Lists: parsing dominates, not structuring.** On mv_disv_xt3d's DISV the
  split is 1.61 s parse vs. 0.08 s structure; on henrytidal it's GHB 1.64 s
  vs. 0.19 s and DRN 0.57 s vs. 0.08 s.
  - So building one `Item` per row is *not* the next bottleneck after a
    bulk list parse, at least until parsing is 5-10x faster. (This corrects
    an earlier assumption that bulk lists needed a column-oriented object
    model first.)

## Ground rules

- Work in a new worktree under `~/dev/` (never `/tmp`), off `develop` once
  `load-baseline` has merged, or off `load-baseline` (rebased onto current
  `develop`) until then.
- Run everything with `pixi run -e dev ...`. Verify with
  `pixi run -e dev smoke`, not the full suite, unless asked. Sign commits
  with the session's trailers. No pushes, PRs or GitHub actions unless the
  user asks.
- **One PR per step.** Each PR description gives:
  - `pixi run -e dev bench-load --benchmark-compare` before and after
    (`bench-parse` too for grammar changes);
  - the result of the snapshot check (step 0).
- **Coordinate on `structure.py`.** Steps 3 and 4 touch its array and list
  consumers (`_read_control_record`, `_numeric_prefix`, `_parse_rows`). The
  converter simplification (`~/dev/pyphoenix-simplify-converter`) is
  reworking the same file. Check its state first and keep these changes
  small and local.

## Steps

### 0. Snapshot check (prerequisite)

A benchmark proves speed, not correctness. Before any optimization, add a
way to show that loaded values are unchanged:

- A script (or `slow`-marked test) that loads every `KNOWN_PASSING` model
  and writes a canonical snapshot per model: every scalar, array
  (dtype + values) and list field, walked the same way as
  `materialize_flopy4` in `test/mf6/test_mf6_load_benchmark.py`. Save it to
  an `.npz`/JSON pair per model under a scratch directory.
- A compare mode that diffs two snapshot directories exactly: dtype
  included, arrays compared with `np.array_equal`.
- Take one snapshot on the base branch and one on each step's branch. Any
  diff must be explained in the PR (e.g. a value that was previously a
  string and is now numeric).
- The round-trip test from #369 (`test/mf6/test_mf6_io_roundtrip.py`) has
  since landed on `develop`, and there's the planned typed-vs-basic parity
  test ([`typed-loader-wiring.md`](../loading/typed-loader-wiring.md), step 5). Check whether the round-trip
  test's comparison can be reused for the snapshot compare before writing a
  new one. Note that a round trip alone doesn't prove values are unchanged:
  a value misread the same way on both loads still round-trips.

### 1. Lazy imports (cold start)

- Profile with `pixi run -e dev python -X importtime -c "import
  flopy4.mf6.simulation" 2> imports.txt` and sort by cumulative time.
- Known module-level offenders (found by grep; confirm with the profile):
  - `flopy4/adapters.py`: `import xugrid as xu`,
    `from flopy.discretization.structuredgrid import StructuredGrid`;
  - `flopy4/mf6/adapters.py`: several `flopy.*` imports (grid, modeltime,
    export, plot);
  - `flopy4/mf6/gwt/__init__.py`:
    `from flopy.discretization.structuredgrid import StructuredGrid`.
- Move these into the functions that use them, or behind a lazy accessor.
  Keep `TYPE_CHECKING` imports for annotations. Check that loading a
  simulation never needs them.
- Target: flopy4's import time drops by roughly the ~1.1 s of flopy3 +
  xugrid. Measure with `test_cold_start`, or directly with
  `python test/mf6/test_mf6_load_benchmark.py cold flopy4-basic WS`.
- Low risk and independent of everything else, so this can go first.

### 2. Harden the external-array reader

`_read_open_close_values` (`structure.py`) is fast but fails on any `#`
comment or stray text in an external file. Make it tolerant without losing
the bulk path:

```python
COMMENT = re.compile(r"[#!][^\n]*")
TABLE = str.maketrans({",": " ", ";": " ", "\t": " ", "'": None, '"': None, "d": "e", "D": "e"})
values = np.array(COMMENT.sub("", text).translate(TABLE).split(), dtype=dtype)
```

- Measured on VilhelmsenGF's external files: 0.062 s vs. 0.042 s today,
  still ~2x faster than flopy3's loop (0.134 s).
- **Check what MF6 accepts first.** The tolerated set above was a
  synthetic stress test, not MF6's spec. Only accept what MF6's own reader
  accepts; e.g. confirm whether `!` comments, `;` and quoted numbers are
  valid in external arrays, and drop what isn't.
- **Count check.** Take the expected length from dims. Too few values is
  an error ("expected N values for <field>, got M"); extra trailing values
  are ignored, matching MF6.
- **The same helper serves step 3,** so write it as a reusable function:
  text in, flat ndarray out, with an optional expected count.
- **Tests:** unit tests with comments, commas, `D` exponents, and too-few
  values, plus the snapshot check.

### 3. Bulk numeric runs in the basic grammar (the big one)

**Idea.** Lex a run of consecutive numeric-only lines as a single token and
convert it with step 2's helper, instead of one Lark token per number.

**Grammar** (`flopy4/mf6/codec/reader/grammar/basic.lark`):
- Since #370 the grammar has a single generic `TOKEN` terminal, and
  `BasicTransformer` decides per token whether it's a number. Add a
  terminal matching one or more lines that contain only numbers and
  separators, roughly `/(?:[ \t]*[-+.\d][-+.\deEdD, \t]*(?:\r?\n|$))+/`.
  Refine it so it can't swallow a line that starts with a keyword.
- Lines with any word stop the run and go through the existing per-token
  path. That covers control records, list rows with boundnames, and data
  rows with trailing remarks (`0 0 0 ... row 1`).
- **Don't rely on longest match.** Per #370's own finding, Lark's lexer
  takes the first matching terminal, not the longest; that's what split
  ISO datetimes. So give the run terminal an explicit priority over
  `TOKEN` (e.g. `DATA_RUN.2`), and test the edge cases directly:
  - a lone number on a line of its own;
  - a numeric line followed by a keyword line;
  - `CONSTANT` values and dimension scalars (these sit on lines with
    keywords, so they should be unaffected);
  - ISO datetimes, `D` exponents, signed numbers: the #370 regression
    tests in `test_mf6_codec.py` / `test_mf6_reader.py` must still pass.

**The design issue:** the basic grammar has no types, so the terminal
captures **both** inline array data and rectangular list rows (e.g.
all-numeric stress-period rows). The token value must keep row boundaries:
- In the transformer, produce `(values: flat ndarray, row_lengths: int
  array)`. Row lengths come from the run's lines, e.g. `[len(l.split()) for
  l in lines]` (C-level splits, one Python iteration per line), or
  vectorized from newline positions.
- If all row lengths are equal, the consumer can reshape to 2-D directly.
- Parse to float64 and cast in structuring, where the field's dtype is
  known. That covers integer arrays, and cellid/integer list columns.
  Check that every numeric form `flopy4.utils.parse_number` accepts today
  still parses (e.g. `D` exponents).

**Consumers** (`structure.py`):
- **Arrays:** `_read_control_record` and `_numeric_prefix` currently
  extend a Python list row by row. Accept a bulk token by concatenating
  arrays and trimming to `length`, keeping the "values can wrap over many
  lines" behavior.
- **Lists:** `_parse_rows` builds one `Item` per row from token lists.
  Feed it rows split from the bulk token (`np.split(values,
  cumsum(row_lengths))`, or 2-D slices when rectangular). Per-row `Item`
  construction stays, since it's ~5-15% of list cost (measured).
- **Anything else** that iterates block rows and could now see a bulk
  token must be checked, e.g. `_resolve_open_close_rows` and the Pass 1
  scalar loop. Keep the token confined to data blocks (griddata, period,
  packagedata-style), or make the transformer fall back to per-row lists
  outside them.

**Expected effect.** These are estimates from token shares × measured
per-token costs, not measurements. The step's PR must replace them with
`bench-load` numbers.

| | flopy3 | flopy4 now | flopy4 after arrays | after arrays + numeric lists |
|---|---|---|---|---|
| corpus | 17.0 s | 14.4 s | ~8 s (6.5-9.5) | ~4-5 s |
| corpus without henrytidal | 6.2 s | 10.0 s | ~3.5 s | ~2.5 s |
| Keating (98% array) | 0.38 s | 0.67 s | ~0.1 s | ~0.1 s |
| mv_disv_xt3d (54% array, 46% list) | 0.56 s | 2.74 s | ~1.3 s | ~0.3 s, if DISV rows are numeric-only |

- Small models gain less: they're dominated by fixed per-file overhead.
- DISV `cell2d` rows are variable-length, not rectangular, and
  `vertices` rows are rectangular. Both are numeric, so both should take
  the bulk path with row lengths.

**Validation:** the snapshot check (no diffs), smoke, the load-all-models
test, and `bench-load` / `bench-parse` compares. Also compare the
`KNOWN_PASSING` count before and after: the grammar change mustn't make
any model stop loading.

### 4. Lists that aren't all-numeric

After step 3, the remaining per-token lists are rows with words: boundnames,
keywords, `OC` records, name-file bindings. **Measure first.** After step
3, check with a per-package split (parse vs. structure; see
`load-benchmarks.md` for how it was measured) whether these still matter.

If they do:
- **Per-block regex, built from the list's column dtypes**, run in C over
  the block text. It needs the component's field types, which the basic
  path gets in structuring, not parsing. So this likely belongs in
  `structure.py`, fed the block's raw text rather than tokens, or waits
  for the typed grammar, where types are available at parse time.
- **Or `pandas.read_csv(sep=r"\s+", comment="#")`** on the block text, like
  flopy3's `MFPandasList`. flopy3 pays a fixed cost per block with it
  (henrytidal: ~1,900 blocks), so batch the blocks, or use it only for
  large ones.

### 5. Cheaper Lark for whatever still goes through it

After steps 3-4, Lark handles mostly structure: keywords, options, control
lines. Measure whether these are still worth it:
- **Inline transformer.** Pass `transformer=BasicTransformer()` to the LALR
  `Lark(...)` in `parser.py`, so callbacks run during the parse and no tree
  is built. Check that terminal callbacks (`TOKEN` since #370, and `CNAME`)
  still apply in that mode.
- **`cache=True`**, to save grammar analysis between processes. It matters
  mostly for the typed loader's ~1.7 s of grammar construction, and for
  cold start.
- **`debug=True`** is set on both parsers. Check whether it costs anything
  outside development.

### 6. Deferred: lazy external arrays

See [`loader-roadmap.md`](loader-roadmap.md), "Deferred: lazy external arrays". This changes
what the object model holds, not how fast parsing is, so it's out of scope
here. Revisit after the converter simplification.

## Benchmark infrastructure: one approach, and a weekly CI job

This isn't a speed-up itself, but it's what makes the steps above
trustworthy over time. It can proceed in parallel with steps 1-3, since
each step only needs the local `bench-load` compare.

### Today: two systems

| | `docs/profile/` (on `develop`, #317) | `test/mf6/test_mf6_{parse,load}_benchmark.py` (`load-baseline`) |
|---|---|---|
| covers | writing input files (frenchman-flat, test1000, test1005, chunked dask streaming, list scaling); reading output (HDS/CBC, lazy vs. eager, chunk sweeps) | parsing and loading input files (flopy4 basic vs. typed; flopy3 vs. flopy4) |
| harness | argparse scripts with their own timer (`_timer.py`: min/mean over N runs, skip slow variants after one run) | pytest-benchmark, opt-in via `--benchmark-enable` |
| run | `python docs/profile/run_all.py [--runs N] [--memory] [--models-root DIR]` | `pixi run -e dev bench` / `bench-parse` / `bench-load` |
| results | custom JSON plus a Markdown report, **committed** in `docs/profile/results/` | pytest-benchmark JSON in `.benchmarks/` (git-ignored), compared with `--benchmark-compare` |
| extras | tracemalloc peak memory (`--memory`), cProfile (`--profile`) | equal-work check, pinned corpora, cold start in a fresh process |
| large models | `modflow6-largetestmodels` via `--models-root` / `MODFLOW6_LARGE_MODELS` | not used |
| its own tests | `docs/profile/test_profile_scripts.py` (outside `testpaths`, so not in normal runs) | skipped unless benchmarking is enabled |

Both compare flopy3 and flopy4 variants, and both use min-of-N timing. They
differ in harness, result format, where results live, and how they're run.

### Target: one consistent approach

**One harness: pytest-benchmark.**
- It's already a dependency. It gives saved JSON, `--benchmark-compare`,
  the `pytest-benchmark compare` CLI for reports, machine and commit info
  in every save, and `--benchmark-cprofile`, which replaces the old
  `--profile` flag.
- Memory has no built-in equivalent. Add a small fixture that runs the
  target once under `tracemalloc` (as `_timer.profile_memory` does) and
  records peak MiB in `extra_info`, enabled by an option such as
  `--bench-memory`.

**One layout.** Move all benchmarks to `test/bench/`, one module per
operation:

| module | operation | parametrized by |
|---|---|---|
| `test_bench_parse.py` | input text → Python (flopy4 parsers only) | `basic`, `typed` |
| `test_bench_load.py` | input files → objects, full simulations | `flopy3`, `flopy4-basic`, later `flopy4-typed` |
| `test_bench_write.py` | objects → input files | `flopy3`, `flopy4`, and flopy4 output variants (ASCII list, grid, NetCDF) |
| `test_bench_output.py` | MF6 output (HDS/CBC) → arrays | `flopy3`, `flopy4-lazy`, `flopy4-eager`, chunk sizes |

- A shared `test/bench/conftest.py` holds the opt-in gate, `quiet`,
  corpus fixtures and manifests, the large-model fixture (skipped unless
  `MODFLOW6_LARGE_MODELS` is set), and the memory fixture.
- A module that also needs a fresh-process script (like the load
  benchmark's file check and cold start) keeps the three-part layout:
  stdlib-only helpers, then the script entry point, then the benchmarks.

**One naming scheme.**
- Test functions are named for the operation and stage: `test_load`,
  `test_load_materialize`, `test_write_list`, `test_read_hds_eager`, and
  so on.
- The first parameter is always the implementation ID: `flopy3`,
  `flopy4-basic`, `flopy4-typed`, `flopy4-netcdf`, ...
- `benchmark.group` is the stage (e.g. `load-materialize`), so each group
  table compares implementations side by side.
- `extra_info` always records the workload: bytes, files or models,
  elements, and flopy's version.

**One way to run.**
- `pixi run -e dev bench` runs everything available locally. Per-area
  tasks are `bench-parse`, `bench-load`, `bench-write` and `bench-output`.
- Rounds come from one option, e.g. `--bench-rounds N` (default 3), so CI
  can raise it without code changes.
- Keep the old slow-variant guard: a variant whose first run exceeds a
  threshold runs once, unless `--bench-include-slow` is passed.

**Results aren't committed.**
- Delete `docs/profile/results/` once the migration is done. History lives
  in CI (below).
- A dated summary with numbers belongs in the relevant doc
  (`docs/dev/load-benchmarks.md`, and a write/output counterpart ported
  from the old `profile-write-performance.md`, removed from `docs/dev` in
  #322 but still in history at `5119a70`).

**Migration.**
1. Move the two existing modules to `test/bench/` under the new names, and
   factor their shared pieces into `conftest.py`.
2. Port the `docs/profile` scripts one at a time: `ff_write`,
   `test1000_write`, `test1005_write`, `chunked_profile`,
   `diag_list_scaling` → `test_bench_write.py`; `ff_read` →
   `test_bench_output.py`. Run old and new side by side on one machine and
   check the numbers agree (within noise) before deleting each script.
3. Remove `docs/profile/` (scripts, `_timer.py`, `run_all.py`,
   `test_profile_scripts.py`, `results/`) and point anything that
   referenced it at the new tasks.

### Weekly CI job

**Workflow:** `.github/workflows/benchmark.yml`.
- Triggers:
  - `schedule` (weekly, e.g. Sunday night UTC);
  - `workflow_dispatch`, with an optional `ref` input to benchmark a
    branch on demand;
  - optionally, a PR label such as `benchmark`, for changes to the reader
    or converter.
- It should never run on every push. The full set takes ~10 minutes
  locally and more on CI runners.
- One runner type (`ubuntu-latest`) and one Python version. Cross-OS
  numbers aren't comparable, and the question is the trend on one
  platform.

**Steps:**
1. Checkout; setup pixi (`dev` environment, same versions as `ci.yml`).
2. `pixi run mf sync`, as in `ci.yml`, for the models registry.
3. Cache the downloaded models and DFNs across runs with `actions/cache`,
   so setup time doesn't vary.
4. Install MF6 (`modflowpy/install-modflow-action`) if the output
   benchmarks need to run a simulation first.
5. Large models: clone or download `modflow6-largetestmodels` (cached)
   and set `MODFLOW6_LARGE_MODELS`. This is the full set, as wanted, but
   it's the slowest step. Check its size and cache it.
6. Run the full set:
   `pixi run bench --bench-rounds 5 --benchmark-json bench.json`.
7. Upload `bench.json` as an artifact (90-day retention).
8. Append it to a long-term history (below).

**Noise.** GitHub-hosted runners are shared VMs, and the CPU model can
differ from week to week. Two kinds of noise need different fixes:
- **Jitter within a run:** handled by rounds. Use 5 rounds plus one warm-up
  (vs. 3 locally), and compare the **min**, which is the most robust
  statistic for "how fast can this code go". Keep the mean and stddev in
  the JSON for diagnosing.
- **Differences between runs** (different CPUs or neighbors each week):
  rounds don't fix this. Two mitigations:
  1. **Ratios within a run.** flopy3 runs in the same job on the same
     machine, so `flopy4 / flopy3` per group is largely
     machine-independent. Make that the headline trend metric, rather
     than absolute seconds.
  2. **A reference ref in the same job,** when a precise comparison is
     needed: benchmark both the previous week's `develop` commit (or the
     last release tag) and `HEAD` in one job, and report `HEAD / ref`.
     This doubles the time, so use it for `workflow_dispatch` comparisons,
     not every week.
- Record the CPU model (`lscpu` / `/proc/cpuinfo`) in the saved JSON, so
  a jump that coincides with a hardware change can be told apart from a
  regression.
- If noise stays a problem, a self-hosted runner on fixed hardware is the
  real fix. That's a project decision.

**History and alerts.**
- [`benchmark-action/github-action-benchmark`](https://github.com/benchmark-action/github-action-benchmark)
  reads pytest-benchmark JSON (`tool: 'pytest'`; verify against its
  current docs). It stores a history, renders trend charts, and can post
  an alert when a benchmark crosses a threshold vs. the previous run.
- Docs deploy via `actions/deploy-pages`, not a `gh-pages` branch. So
  point the action at a dedicated data branch (e.g. `bench-data`) rather
  than `gh-pages`, and either publish the chart page from the docs build
  or just link the data.
- Alert threshold: generous (e.g. 30% slower), since weekly runs land on
  different hardware. Treat alerts as "look at this", not failures. Alert
  on the flopy4/flopy3 ratio as well as absolute time, if the action
  allows; otherwise compute it in a small post-processing step.
- The job never fails the build for a slowdown. It fails only if a
  benchmark itself errors, which is how rot gets caught, e.g. a pinned
  model that no longer loads, or an equal-work check that no longer holds.

**Keeping benchmarks from rotting between weekly runs.** Normal CI skips
the benchmarks entirely. Add a cheap check to `ci.yml`'s test job that
runs the benchmark modules once with `--benchmark-disable` on a tiny
subset (e.g. `-k "largest1 or cold_start"` plus a 5-model manifest). That
proves the code still runs, without timing anything.

### Order

1. Merge `load-baseline` (stage 0 of the roadmap).
2. The weekly CI job for the existing parse/load benchmarks. It's useful
   immediately, and it records a "before" history for the optimization
   steps.
3. Unify the layout (`test/bench/`, shared conftest, `--bench-rounds`).
4. Port the `docs/profile` scripts, then delete them.

## Not in this plan

- **The typed grammar.** It gets the same bulk terminal when it's wired in
  ([`typed-grammar-remarks.md`](typed-grammar-remarks.md), "Ideas", item 2). With types available,
  the terminal can target arrays exactly and carry each list's column
  dtypes.
- **Speeding up flopy3.** Worth noting in discussion #55 that a whole-file
  fast path plus read caching would fix its external-array cost. That's not
  our work.
- **Adding a flopy3 `lazy_io=True` column** to the benchmark. That's an
  open decision in the roadmap.

## Done when

- Steps 1-3 are merged, each with before/after `bench-load` numbers and a
  clean snapshot check in its PR.
- `load-benchmarks.md` has a new results section with measured numbers
  replacing this plan's estimates, and flopy4 vs. flopy3 per regime (inline
  arrays, external arrays, simple lists, complex lists, cold start).
- Steps 4-5 are either done or recorded as measured and not worth it, with
  the numbers.
