# Benchmark infrastructure plan

**Archived 2026-10-19.** Done: merged as #482 ("benchmarking infra"), with the suite in `benchmarks/`, tiers, `bench-memory`, `bench-profile` and `bench-report`; `docs/profile/` is gone. The "Later" items (history across commits, CI regression checks, typed-loader benchmarks) are not started.

This plan merges our three benchmark approaches into one suite that can be checked in:

- the `origin/load-baseline` pytest-benchmark suite;
- `docs/profile/`;
- the scratchpad harness behind [`io-benchmark-results.md`](io-benchmark-results.md).

The suite will live in a top-level `benchmarks/` directory, run on pytest-benchmark.

## Decisions

- **pytest-benchmark is the engine, not asv.** asv is too heavyweight.
  - pytest-benchmark is already a dependency, and `load-baseline` uses it.
  - Its JSON output is what other tools read, so we can add these later without touching the benchmarks:
    - history across commits (github-action-benchmark or Bencher);
    - regression checks in CI (pytest-codspeed accepts the same `benchmark` fixture).
  - The fair-comparison logic is specific to this project, so we write it either way.
- **Memory comes from pytest-memray, not RSS.**
  - memray counts only what is allocated during the test, numpy included, so it gives each model's own footprint without the import baseline.
  - It slows things down, so it runs in its own session (`bench-memory`) and never alongside the timing runs.
- **The subprocess worker is kept only for:**
  - cold start;
  - the memory cost of importing each library, which memray can't see.
- **Large models are their own tier.** They run only with `--bench-tier large`, and the registry downloads them on first use.
- **Results stay out of git.**
  - `.benchmarks/` is gitignored.
  - A Markdown report generated from a saved run is committed only when it's worth keeping.
  - `docs/profile/results/` goes.
- **No CI gating for now.** Shared runners are too noisy for absolute times. Revisit later with codspeed or a manual or nightly workflow.

## What to keep from each source

### `origin/load-baseline` (this is the base)

The branch is unmerged and dated 2026-09-24. Its commits are b00ac6ba, 5bae03a6, 8f7e4c25 and e4d095e3, plus the parse-benchmark commits af3b2ff0 and c101c031.

Files:

- `test/mf6/test_mf6_load_benchmark.py`
- `test/mf6/test_mf6_parse_benchmark.py`
- `test/mf6/load_benchmark_models.txt` (~180 models)
- `docs/dev/load-benchmarks.md`
- the `bench-load` task, defined in `pyproject.toml` on that branch

What to keep:

- **Fixed flopy3 options:** `FLOPY3_OPTIONS = {verbosity_level: 0, lazy_io: False, verify_data: False, use_pandas: True}`.
- **`load_only_for(dfn_names)`:** limits flopy3's `load_only` to the package types flopy4 actually loaded.
  - It finds those types with `load_flopy4_recording`, which patches `Package.load`.
  - It handles the cases where several flopy4 components share one flopy3 type: `rcha`/`evta`, the `*g` packages and exchanges.
- **`check`:** in a subprocess, an audit hook confirms both libraries opened the same set of files. A model that fails the check is left out.
- **`touch(x)`:** the materialize step, which sums every array and list.
  - It's needed because flopy3 doesn't read OPEN/CLOSE arrays at load time.
  - flopy3 then rereads them on every `get_data()`, without caching.
- **Benchmarks:**
  - `test_load`
  - `test_load_materialize` (the fair one)
  - `test_load_materialize_largest`
  - `test_cold_start`
  - the basic vs. typed parse benchmark
- **The opt-in skip, and the pinned manifest** (`--bench-load-manifest`). The manifest fails loudly if a listed model stops loading or stops doing the same work in both libraries.
- **The module layout.**
  - The top of the module imports only the standard library, and the script entry point exits before pytest is imported.
  - This keeps the cold-start timing free of pytest's import cost (~0.1 s).

### Scratchpad harness (this session)

The scripts are in `/private/tmp/claude-502/-Users-wbonelli-dev-pyphoenix-project/0c2187ab-eda9-4492-9ae6-11e169356e97/scratchpad/`:

- `bench/worker.py`
- `bench/run.sh`
- `bench/summarize.py`
- `size_corpus.py`

What to keep:

- Write benchmarks that write into a fresh empty directory each round.
  - flopy4: set `sim.workspace = out`, then call `sim.write()`.
  - flopy3: `set_sim_path(out)`, then `write_simulation(silent=True)`.
- Record bytes written, and keep a round-trip check: reload the written output and compare arrays.
- Keep the size-ranged, tagged model selection. It's the basis for the tiers below.
- Drop its flopy3 setup (default options, no `load_only`) and `run.sh`.

### `docs/profile/` (on develop)

Files:

- `run_all.py`
- `ff_read.py`, `ff_write.py`
- `test1000_write.py`, `test1005_write.py`
- `chunked_profile.py`
- `diag_list_scaling.py`
- `_timer.py`
- `test_profile_scripts.py`
- `results/`

What to keep and what to drop:

- Keep the scenario scripts as profiling tools, moved to `benchmarks/profile/`.
- Keep the git commit and timestamp in every result, and Markdown report generation.
- Drop `run_all.py`, `_timer.py` and `results/`.
- Check whether `test_profile_scripts.py` is still worth keeping after the move.

## Layout

```
benchmarks/
  conftest.py      # --bench-tier, --bench-manifest, model fixtures, opt-in skip
  models.toml      # tiers + tags per model
  _ops.py          # per library: load / materialize / write; stdlib-only at module level
  _check.py        # file-equivalence (audit hook), round-trip compare
  _worker.py       # subprocess entry: cold start, import memory
  test_load.py     # load, load+materialize (from load-baseline)
  test_write.py    # write; bytes written in extra_info
  test_parse.py    # basic vs. typed (from load-baseline)
  test_memory.py   # pytest-memray peak per (library, model, op); run in its own session
  report.py        # pytest-benchmark JSON (one run or two to compare) -> Markdown
  profile/         # scenario scripts moved from docs/profile/
```

- `_ops.py` is the only place load, materialize and write are defined. Every benchmark and the worker go through it, so flopy3's options can't drift between benchmarks.
- The equivalence and round-trip checks run once per model per session, as session fixtures. A model that fails is reported and left out, so it can't skew the comparison silently.
- Each model's tags, input size and bytes written go into `extra_info`, so `report.py` can group results by data shape.

## Tiers

Models come from the modflow-devtools registry. All are in `KNOWN_PASSING`.

- **smoke** (about 5 tiny models, under a minute):
  - test001a_Tharmonic
  - test006_gwf3_disv_ext
  - test028_sfr
  - test045_lake4ss_dev
  - test120_mv_dis-lgr
- **standard** (the default): the smoke tier, plus:
  - test016_Keating_dev
  - test033_wtdecay
  - test019_VilhelmsenGF
- **large** (opt-in, downloaded on first use):
  - test1000_751x751
  - test016_Keating_disu_mfusg
  - test1005_secp
  - test1002_biscqtg_disv_dev
  - test1001_Peterson
- **full**: the ~180-model manifest from `load-baseline`.

Each model gets tags for its data shape:

- `array`: secp, Peterson, Keating_disu_mfusg, 751x751
- `list`: biscqtg
- `exg`: dis-lgr
- `openclose`: disv_ext, VilhelmsenGF, wtdecay
- `sfr`, `lak`: package-specific cases

## pixi tasks

- `bench`: the standard tier, with autosave.
- `bench-large`: the large tier.
- `bench-full`: the full manifest.
- `bench-compare`: compare against the last saved run.
- `bench-memory`: a pytest-memray session.
- `bench-report`: write the Markdown report.

## Steps

1. **Port `load-baseline`.** On a local branch off develop:
   - bring in the benchmark files from `load-baseline` (cherry-pick, or check them out);
   - move them into `benchmarks/`;
   - split out `_ops.py` and `_check.py`;
   - check that `bench` runs.
2. **Write benchmarks.** Add `test_write.py`, bytes written and the round-trip check.
3. **Tiers.** Add `models.toml` and the `--bench-tier` option.
4. **Memory.**
   - Add pytest-memray to the dev environment, then add `test_memory.py` and the `bench-memory` task.
   - Have `_worker.py` handle cold start and import memory.
5. **Report.**
   - Add `report.py`.
   - Rerun the standard and large tiers with the fair flopy3 options.
   - Regenerate [`io-benchmark-results.md`](io-benchmark-results.md) from those runs.
6. **Profiling scripts.**
   - Move the `docs/profile/` scripts into `benchmarks/profile/`.
   - Remove `run_all.py`, `_timer.py` and `results/`.
   - Update any docs that point to them.

Run checks through `pixi run -e dev`: the smoke tests, plus the benchmark files that changed. Don't run the full test suite.

## Later

- History across commits with github-action-benchmark or Bencher. Both read pytest-benchmark JSON.
- CI regression checks with pytest-codspeed. Note that its instruction counts mostly ignore time spent waiting on IO.
- Typed-loader benchmarks once the typed loader is wired into structuring: add `flopy4-typed` to `LOADERS`.
