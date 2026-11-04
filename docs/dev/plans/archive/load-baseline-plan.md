# Plan: baseline input-load benchmarks, flopy3 vs. flopy4

**Archived 2026-10-19.** Superseded: the `load-baseline` branch was folded into the benchmark suite merged as #482 (`benchmarks/`, `docs/dev/load-benchmarks.md`).

Goal: a baseline for simulation *input* loading that later loader changes
can be measured against. Compare flopy3 (`flopy.mf6.MFSimulation.load`),
the flopy4 basic loader, and the flopy4 typed loader, as far as each can
honestly be compared today.

## Context (read first)

- Work in the existing worktree `~/dev/pyphoenix-typed-remarks`, on a new
  branch off `typed-remarks` (e.g. `load-baseline`). Put any new worktree
  under `~/dev/`, never `/tmp`.
- Read [`typed-grammar-remarks.md`](typed-grammar-remarks.md) on `typed-remarks`, especially
  "Why the typed loader isn't faster (yet)". Then read
  `test/mf6/test_mf6_reader_benchmark.py`, the reader benchmark to extend.
  It's opt-in (`--benchmark-enable`), uses `pixi run -e dev bench`, and has
  `--bench-manifest` for pinning a corpus.
- Run everything with `pixi run -e dev ...`, never `uv run`. flopy 3.11.0
  is already a core dependency (`flopy>=3.9.5,<4`).
- Verify with `pixi run -e dev smoke`, not the full suite.
- Sign commits (`Co-Authored-By:` trailer). Don't push, open PRs, or touch
  GitHub unless the user asks.

## What can be compared, and at which level

| level | flopy3 | flopy4 basic | flopy4 typed |
|---|---|---|---|
| full simulation load | `MFSimulation.load` | `Simulation.load` | **not possible yet** |
| parse stage (`loads`) | n/a | yes (existing) | yes (existing) |

Typed `loads` output isn't wired into `structure.py`, so there's no full
typed load. Don't fake one; for example, don't add the basic structure time
to typed `loads`. Report typed at the parse stage only, and state the gap
in the results. When typed is wired in, it gets a column in the first row.

## Steps

1. **Pick the model corpus.** Start from `KNOWN_PASSING`
   (`test/mf6/test_mf6_load_all_models.py`). Keep only models that *both*
   flopy3 and flopy4 load without error. Record the exclusions and why
   (flopy3 errors vs. flopy4 errors) in the results doc.
   - Pin the set with a model-level manifest, either by extending
     `--bench-manifest` or adding a sibling option, so later runs time
     identical input.
   - First time one full round of each loader. If flopy3 over the whole
     corpus is too slow for 3+ rounds, also define a smaller fixed subset
     for routine runs: the ~10 largest models by input bytes plus a spread
     of small ones. Keep the full corpus as an occasional run.
2. **Make the two loaders do comparable work.** This is the step most
   likely to go wrong.
   - flopy3: `MFSimulation.load(sim_ws=..., verbosity_level=0,
     lazy_io=False, verify_data=False)`, with `use_pandas` at its default
     (record it). Check whether flopy3 defers reading any data until access
     (external `OPEN/CLOSE` arrays, `lazy_io`, pandas-backed lists).
   - flopy4: `Simulation.load(path)`. It reads `OPEN/CLOSE` arrays eagerly
     today; confirm that.
   - If either defers work, benchmark two stages: `load`, and
     `load + materialize`. The second touches every package's array and list
     data, e.g. by summing every numeric array. Only the second is a fair
     comparison when laziness differs. Write down exactly what
     "materialize" touches for each loader.
   - Silence output on both: flopy3 via `verbosity_level=0`; flopy4 by
     disabling logging and warnings, as the corpus fixture already does.
     Printing isn't what we're measuring.
3. **Separate warm from cold.**
   - The warm benchmark (in-process, parsers/grammars already built, same
     pattern as the existing corpus fixture) is the main number.
   - Add a small cold-start measurement: a fresh `subprocess` per loader
     that imports it and loads one mid-size model. It captures import time
     plus flopy4's grammar build, which matters for CLI use. A handful of
     repetitions is enough; this doesn't need pytest-benchmark precision.
4. **Implement** as a new module next to the existing one, e.g.
   `test/mf6/test_mf6_load_benchmark.py`. Reuse the opt-in gate, the
   `slow` mark, the `dfn_path` fixture, `copy_to`, and pytest-benchmark
   groups (`sim-load`, `sim-load-materialize`). In `extra_info`, record
   `n_models`, total input bytes, and the flopy version. pytest-benchmark
   already saves the commit and machine info. Copy each model workspace
   once per session, outside the timed region. Have the `bench` pixi task
   run both modules, or add a `bench-load` task.
5. **Record the baseline** in a short results section: add it to
   [`typed-grammar-remarks.md`](typed-grammar-remarks.md), or split out
   `docs/dev/load-benchmarks.md` and link it from there. Include:
   - the corpus and exclusions;
   - flopy3 vs. flopy4-basic full-load times, with and without
     materialize if both stages were needed;
   - the existing basic vs. typed `loads` numbers alongside, labelled as
     parse-stage only;
   - cold-start numbers;
   - the exact commands to reproduce.
   Add a short per-model breakdown for the largest few models, where
   differences show most. Give absolute times and ratios.

## Done when

- `pixi run -e dev bench` (or `bench-load`) produces saved, comparable
  flopy3 and flopy4 full-load numbers on a pinned model set.
- The laziness question is answered in writing, and the benchmark times
  equivalent work.
- The results doc states the baseline and what isn't measured yet (a full
  typed load).
- `pixi run -e dev smoke` still passes, and the new benchmarks are skipped
  in it.
