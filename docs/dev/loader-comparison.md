# flopy4's two loaders, compared

Phase C of the [converter simplification plan](converter-simplification-plan.md):
the basic loader (Track A: one generic grammar, block structure read from
the stored DFNs at runtime) against the typed loader (Track B: a grammar
generated per component, values read by the classes' fields alone). Both
stay, with `loader="basic" | "typed"` (the tests' `--loader`) choosing
between them; deleting one is a separate decision.

Measured 2026-10-21 at `721503fe`, on an Apple M2 Max (macOS, CPython
3.11.16), standard benchmark tier (9 models, 15.1 MB of input).

## Summary

| | basic | typed |
|---|---|---|
| correctness (round-trip suite, load snapshots) | passes | passes but `test1001_Peterson`, a basic-loader bug |
| load + materialize, all models | 0.254 s | 0.318 s (1.25×) |
| peak memory, load | — | 0.97–1.81× basic's; most models within 3%, two 1.7–1.8× |
| cold start, first load | 0.265 s | 0.32–0.33 s with the grammar cache warm, 0.62 s without |
| malformed files | lenient: loads most, warning or silently | strict: a missing `END` or wrong value type raises, with line and column |
| code only it needs | ~450 lines (~570 with the DFN accessor egress shares), plus 129 stored DFNs (1.4 MB) | ~1,300 lines with the grammar templates, plus 129 generated grammars (6,581 lines) |

**Recommendation:** keep basic as the default and typed as the opt-in.
The basic loader is faster, smaller and lighter on memory; the typed
loader's advantages are stricter errors and no DFN at runtime, and the
first can be had in the basic loader for less (see "Errors"). Before
deciding to delete either, look into the typed loader's memory on
`test016_Keating_dev` and `test045_lake4ss_dev`, which wasn't investigated
here, and fix the error-reporting gaps both share.

## Correctness

Both pass the round-trip suite (load → write → load over the corpus) and
produce the same load snapshots, but one: under `--loader typed`, 257 of
258 load snapshots pass. `test1001_Peterson` differs in IMS's
`rclose_option`, a string written `50000.000`: the typed loader keeps the
word, the basic loader reads it as the number `50000.0`. The basic
loader's is the bug (its parse reads numbers before the converter knows
the field), and the snapshot pins it. `test060_gms_ets` loads under
neither. Rerun at `721503fe`:

    pixi run -e dev pytest test/mf6/test_mf6_io_roundtrip.py \
        test/mf6/test_mf6_load_all_models.py --loader typed

## Load time and memory

`pixi run -e dev bench -k load` and `pixi run -e dev bench-memory -k
test_load`, which now run `flopy4-typed` beside `flopy3` and `flopy4`
(`benchmarks/_ops.py`, `LOADS`); `benchmarks/report.py` has a "Loaders,
basic vs. typed" section. Times are the minimum of 3 rounds; memory is
peak heap (memray). Ratios are typed / basic.

| benchmark | basic | typed | × |
|---|---:|---:|---:|
| load, all models | 0.205 s | 0.273 s | 1.33 |
| load + materialize, all models | 0.254 s | 0.318 s | 1.25 |

| model | input MB | load+mat basic | typed | × | load memory, MiB | × |
|---|---:|---:|---:|---:|---:|---:|
| test001a_Tharmonic | 0.003 | 0.00309 | 0.00433 | 1.40 | 0.167 / 0.162 | 0.97 |
| test001a_Tharmonic_extlist | 0.003 | 0.00328 | 0.00464 | 1.42 | 0.077 / 0.096 | 1.26 |
| test028_sfr | 0.021 | 0.00994 | 0.0122 | 1.23 | 0.269 / 0.277 | 1.03 |
| test045_lake4ss_dev | 0.299 | 0.0100 | 0.0149 | 1.48 | 0.500 / 0.841 | 1.68 |
| test050_circle_island | 0.551 | 0.0584 | 0.0769 | 1.32 | 4.33 / 4.24 | 0.98 |
| test120_mv_dis-lgr | 0.735 | 0.0162 | 0.0243 | 1.50 | 1.17 / 1.43 | 1.22 |
| test033_wtdecay | 1.18 | 0.0121 | 0.0154 | 1.27 | 3.59 / 3.61 | 1.01 |
| test016_Keating_dev | 1.47 | 0.0265 | 0.0450 | 1.70 | 2.85 / 5.15 | 1.81 |
| test019_VilhelmsenGF | 10.8 | 0.110 | 0.117 | 1.06 | 36.2 / 36.3 | 1.00 |

The typed loader is slower on every model, by 6% (the largest, where
reading array values dominates and both share the code) to 70%. Peak
memory is about the same where arrays dominate, and up to 1.8× where
they don't. Against flopy3, flopy4 stays ahead with either loader: typed
load + materialize is 3.3× faster over the tier (basic, 4.2×).

## Cold start

A fresh interpreter importing flopy4, then loading and materializing
`test050_circle_island` (`benchmarks/_worker.py cold`), three alternating
runs each. The import is the same for both (~0.8 s); the first load:

| | first load |
|---|---:|
| basic | 0.265–0.268 s |
| typed, grammar cache warm (the usual case) | 0.321–0.332 s |
| typed, no cache (`FLOPY4_CACHE_DIR=`) | 0.617–0.635 s |

The basic loader's first load includes loading the 10 DFNs this
simulation needs and building codegen's spec of each class for
`attr_names`; the typed loader's, reading (or building) a parser per
component. With no cache, the typed loader builds each grammar, which
happens once per machine and lark/Python version. In the benchmark run's
`test_cold_start` (wall time, five rounds), flopy3 took 1.04 s, flopy4
1.16 s basic and 1.24 s typed.

## Errors

Seven malformed copies of `test001a_Tharmonic`, one fault each, loaded
with both loaders:

| fault | basic | typed |
|---|---|---|
| missing `END OPTIONS` (CHD) | loads; warns "no field takes OPTIONS entry BEGIN" | `UnexpectedToken` at the `MAXBOUND` line, line and column, the tokens expected |
| misspelled keyword (`PRINT_FLOWZ`) | loads; warns "no field takes OPTIONS entry PRINT_FLOWZ" | the same |
| wrong value type (`MAXBOUND two`) | loads silently | `UnexpectedToken` at `two`, line and column, expecting an integer |
| short list row (CHD, no head) | `ValueError: StressPeriodData: can't read a row from [1, 1, 10]` | the same |
| bad OPEN/CLOSE path (NPF `K`) | `FileNotFoundError` naming the path | the same |
| short array (IC `STRT`, 9 values for 10 cells) | loads silently | the same |
| unknown block (`DIMENSIONZ`) | loads; warns "ignoring unknown block" | the same |

- The typed loader catches two faults the basic one doesn't, and says
  where. The basic loader's missing `END` happens to load the right
  values here; MF6 would stop.
- Neither loader's errors name the file. The typed loader's give a line
  and column in a file the message doesn't name; the basic loader's give
  neither.
- Both accept a short array. A `LAYERED` field with fewer values than a
  layer has is filled by repeating them (`np.resize`, there to repeat a
  record across layers when there are fewer records than layers); a
  non-layered one keeps its 9 values for the 10 cells.
- The basic loader ignores a `MAXBOUND` it can't read because MAXBOUND is
  computed; a wrong-typed value in a field it keeps would fail where the
  converter casts it.

The script that made these isn't checked in; each fault is a one-line
edit of the file named. The follow-ups are in the plan's "Later".

## Code size

Code lines (no blanks, comments or docstrings), from parse to component
kwargs. `structure.py`'s functions are split by what the typed loader
imports from it, directly or through what it calls.

| | lines |
|---|---:|
| **basic only** | |
| `basic.lark` | 40 |
| basic transformer | 67 |
| `structure.py`: `_Load`, the array and row readers, block grouping | ~340 |
| DFN accessor in `spec.py` (also egress's; see below) | ~120 |
| stored DFNs, `flopy4/mf6/dfns` | 129 files, 1.4 MB |
| **typed only** | |
| `typed.lark` | 144 |
| grammar generation (`grammar/__init__.py`, `filters.py`, `names.py`, `dfn2lark.py`) | 260 |
| grammar templates (Jinja) | 335 |
| typed transformer | 298 |
| `ingress/typed.py` | 276 |
| generated grammars | 129 files, 6,581 lines (536 KB) |
| **shared** | |
| `structure.py`: `ComponentLoad`, bindings, array files, children | ~410 |
| `transformer/rows.py` | 97 |
| `parser.py` (both parsers, the typed parsers' disk cache) | 108 |

Egress (S2) reads block structure through the DFN accessor too, so the
stored DFNs and the accessor stay while either egress or the basic
loader needs them. Deleting the basic loader would mean egress reading
the classes' fields instead (plan, Phase C).
