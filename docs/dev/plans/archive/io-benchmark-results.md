# flopy4 vs. flopy3 IO benchmark (2026-10-16)

**Archived 2026-10-19.** Stale: measured at `6b233ddb`, before #482-#484. Regenerate from the suite with `pixi run -e dev bench-report`.

Load and write times for flopy4 (`develop` @ `6b233ddb`, after #479 "more IO
optimizations") and flopy3 3.11.0, on 13 test models from 5 KB to 84 MB.

## Summary

- **Load:** flopy4 is 1.4–13× faster, mostly 2.5–5×. On biscqtg
  (1.27M list rows) it drops from 10.8 s to 2.3 s. The 751x751 grid gains
  least, at 1.4×.
- **Write:** flopy4 is 2.3–9.5× faster from about 1 MB up. On the tiniest
  model it's slightly slower (11 ms vs. 9 ms).
- **Memory:** flopy4 uses more on every model. Its import alone costs
  ~120 MB more (~295 vs. ~175 MB), and on biscqtg it peaks at 1.16 GB vs.
  0.60 GB. This is the main follow-up.
- **Startup:** importing flopy4 takes ~2.2 s vs. ~0.8 s for flopy3, and its
  first load adds ~0.3 s to build the parser. Both are left out of the
  table.
- **Output:** flopy4 writes ~half the bytes of flopy3 and the same number of
  files. The difference is formatting: flopy3 pads every value to 8 decimals,
  and flopy4 writes compact values. Reloading flopy4's output for secp,
  751x751 and Peterson gives float arrays that match the source exactly.

## Results

Times are median seconds. "flopy3 load" includes reading all data (see
Method). "Memory" is the process's peak RSS in MB, including import and
warm-up.

| model | input MB | flopy3 load | flopy4 load | load × | flopy3 write | flopy4 write | write × | memory fp3 / fp4 | reps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| test001a_Tharmonic | 0.005 | 0.010 | 0.003 | 2.9× | 0.009 | 0.011 | 0.8× | 175 / 298 | 5 |
| test006_gwf3_disv_ext | 0.015 | 0.035 | 0.005 | 6.6× | 0.019 | 0.015 | 1.3× | 175 / 295 | 5 |
| test028_sfr | 0.38 | 0.033 | 0.009 | 3.5× | 0.024 | 0.021 | 1.1× | 178 / 297 | 5 |
| test045_lake4ss_dev | 0.50 | 0.033 | 0.011 | 3.1× | 0.031 | 0.019 | 1.7× | 175 / 296 | 5 |
| test120_mv_dis-lgr | 1.6 | 0.070 | 0.017 | 4.0× | 0.092 | 0.033 | 2.8× | 178 / 300 | 3 |
| test016_Keating_dev | 3.3 | 0.355 | 0.028 | 12.8× | 0.101 | 0.044 | 2.3× | 185 / 311 | 3 |
| test033_wtdecay | 6.9 | 0.068 | 0.013 | 5.1× | 0.173 | 0.018 | 9.5× | 181 / 304 | 3 |
| test019_VilhelmsenGF | 10.8 | 0.368 | 0.129 | 2.9× | 1.84 | 0.26 | 7.0× | 300 / 476 | 2 |
| test1000_751x751 | 33 | 0.323 | 0.224 | 1.4× | 1.21 | 0.22 | 5.4× | 290 / 430 | 1 |
| test016_Keating_disu_mfusg | 55 | 2.16 | 0.86 | 2.5× | 1.93 | 0.81 | 2.4× | 320 / 479 | 1 |
| test1005_secp | 66 | 2.49 | 0.83 | 3.0× | 3.92 | 0.68 | 5.8× | 332 / 605 | 1 |
| test1002_biscqtg_disv_dev | 77 | 10.79 | 2.30 | 4.7× | 7.65 | 3.12 | 2.5× | 596 / 1161 | 1 |
| test1001_Peterson | 84 | 2.89 | 1.23 | 2.3× | 5.84 | 1.05 | 5.6× | 492 / 672 | 1 |

flopy3's load time split into the load call itself and the data-reading pass:

| model | `MFSimulation.load` | read all data |
|---|---:|---:|
| test033_wtdecay | 0.013 | 0.055 |
| test019_VilhelmsenGF | 0.054 | 0.314 |
| test1002_biscqtg_disv_dev | 8.837 | 1.956 |

For the other models the data-reading pass takes under 0.1 s.

Bytes written:

| model | flopy3 MB | flopy4 MB |
|---|---:|---:|
| test1000_751x751 | 19.8 | 9.4 |
| test016_Keating_disu_mfusg | 17.0 | 7.4 |
| test1005_secp | 65.6 | 27.0 |
| test1002_biscqtg_disv_dev | 58.6 | 57.4 |
| test1001_Peterson | 80.4 | 36.1 |

## Method

- **Models:** from the modflow-devtools registry, all in `KNOWN_PASSING`
  (`test/mf6/test_mf6_load_all_models.py`). They were picked to cover:
  - the size range from 5 KB to 84 MB;
  - array-heavy models (secp, Peterson, Keating_disu_mfusg, 751x751);
  - list-heavy models (biscqtg);
  - multiple models with exchanges (dis-lgr);
  - package-specific cases (SFR, LAK);
  - OPEN/CLOSE external files (disv_ext, VilhelmsenGF, wtdecay).

  Input MB is the total size of each model's copied files.
- **Isolation:** each (library, model) pair runs in its own Python process,
  one after another.
- **Warm-up:** each process first loads `test001b_Tlogarithmic`, so import
  and parser building are excluded from the timings.
- **Each repeat:** load from the source directory, then write to a fresh
  empty directory.
- **flopy3:**
  - Loading uses `MFSimulation.load(sim_ws=..., verbosity_level=0)` with
    default options.
  - flopy3 doesn't read OPEN/CLOSE files until data is accessed, so its load
    time adds a pass that calls `get_data()` on every `data_list` item of
    every simulation and model package.
  - Writing uses `set_sim_path(out)` then `write_simulation(silent=True)`.
- **flopy4:**
  - Loading uses `Simulation.load(ws / "mfsim.nam")`, which reads all data
    into numpy arrays at load time.
  - Writing sets `sim.workspace = out`, then calls `sim.write()`.
- **Environment:** Apple M2 Max (12 cores), 32 GB RAM, macOS 26.7.1,
  Python 3.11.16, numpy 2.4.6, lark 1.3.1, pixi `dev` env.

### Caveats

- The five largest models ran once each, so treat their numbers as rough
  (about ±10%).
- The data-reading pass doesn't cover flopy3's child packages (OBS, TS), so
  flopy3's load time is slightly understated.
- flopy3 used its default load options, not the
  `lazy_io=False, verify_data=False` that the `load-baseline` branch used,
  so these numbers aren't directly comparable with that branch's.
- Write speed partly reflects how much is written: flopy3 writes about 2×
  the bytes.
- The memory figures are each process's peak, not the model's own
  footprint. They include the ~175 MB (flopy3) or ~295 MB (flopy4) baseline
  from import and warm-up.

## Reproducing

The scripts live outside the repo, in the session scratchpad:

- `size_corpus.py` copies the `KNOWN_PASSING` models and ranks them by size.
- `bench/worker.py` times one library on one model.
- `bench/run.sh` takes a list of `model:reps` arguments and runs both
  libraries on each.
- `bench/summarize.py` builds the tables.

If you check them in, use the benchmark infrastructure in the follow-up
below rather than copying them as-is.

## Other benchmark tooling in the repo

- **`docs/profile/` (on develop):**
  - `run_all.py` runs the profile scripts, with `--runs`, `--memory`,
    `--report`, `--flopy4-only` and `--include-slow` options.
  - The scripts cover Frenchman Flat read and write, and write scenarios for
    `test1000_751x751` and `test1005_secp`.
  - Results are saved in `docs/profile/results/`.
- **`origin/load-baseline` branch (not merged, 2026-09-24):**
  - An opt-in pytest-benchmark suite, `pixi run -e dev bench-load`, with
    `--benchmark-compare`.
  - It uses a fixed list of about 180 models
    (`test/mf6/load_benchmark_models.txt`).
  - Its tests:
    - `test_load`: load only.
    - `test_load_materialize`: load, then fetch and sum every array and
      list.
    - `test_load_materialize_largest`: the same, per model, for the largest
      models.
    - `test_cold_start`: a fresh interpreter per round.
    - A basic vs. typed parser benchmark (`test_mf6_parse_benchmark.py`).
  - `docs/dev/load-benchmarks.md` describes how each library reads data.
    flopy3 doesn't read OPEN/CLOSE arrays at load time and rereads them on
    every `get_data()`.
  - It measures loading only, not writing.
