# Simulation load benchmarks: flopy3 vs. flopy4

A baseline for simulation *input* loading, for later loader changes to be
measured against. Measured 2026-09-24 at commit `5bae03a` (on the unmerged
`load-baseline` branch), on an Intel Core Ultra 7 155H (WSL2, CPython
3.11.16), with flopy 3.11.0. flopy4 has changed a lot since, so treat the
numbers as history; the analysis of how each library reads data still holds.

The benchmarks now live in `benchmarks/` and run with `pixi run -e dev bench`.
They also time writing (`test_write.py`), recording bytes written, after
checking that each library's output reloads intact (a round-trip check).

The models come in tiers, listed in `benchmarks/models.toml`: `smoke` (a few
tiny models), `standard` (the default) and `large` (opt-in, downloaded on
first use). A fourth tier, `full`, is the 165-model manifest this baseline
used, `benchmarks/models-full.txt`. Every tier pins its models: a model that
fails either check fails the run rather than dropping out, so a regression
can't quietly shrink what's compared. The numbers below are from the full
manifest.

## What's compared, and at which level

| level | flopy3 | flopy4 basic | flopy4 typed | suite |
|---|---|---|---|---|
| full simulation load | `MFSimulation.load` | `Simulation.load` | **not possible yet** | `test_load.py` |
| parse stage (parse + transform) | n/a | yes | yes | `test_parse.py` |

Typed parser output isn't wired into `structure.py`, so there's no full typed
load to time. The typed loader appears here at the parse stage only. It gets a
column in the first row once it's wired in.

There are two benchmark modules, both opt-in pytest-benchmark modules under
`benchmarks/` (`pixi run -e dev bench` runs both):

| | parse | load |
|---|---|---|
| module | `test_parse.py` | `test_load.py` |
| question | is one flopy4 parser faster than the other? | how fast is loading for a user, vs. flopy3? |
| compares | flopy4 basic vs. typed parser | flopy3 vs. flopy4 (basic) |
| unit of work (full tier) | 2,149 package files' text, pre-read into memory | 165 whole simulations, from disk |
| benchmarks | `test_parse`, `test_parse_transform`, `test_typed_grammar_build` | `test_load`, `test_load_materialize`, `test_load_materialize_largest`, `test_cold_start` |
| pinning | the tier's models, or `--bench-parse-manifest` (file list) | always: the tier, or `--bench-manifest` |
| equal-work check | both grammars parse the file | both loaders open exactly the same files |
| runtime (full tier) | ~4 min | ~6.5 min |

Use the parse benchmarks for grammar/transformer changes and the load
benchmarks for anything user-visible.

## The loaders don't do the same work by default

This was settled by recording every file each loader opens (a `sys` audit hook
on `open`), both during load and during a later "materialize" pass. It was
cross-checked against flopy3's source.

### flopy3

`MFSimulation.load(verbosity_level=0, lazy_io=False, verify_data=False)`, with
`use_pandas=True` (the default).

- **Internal data** (inline arrays and lists) is parsed at load.
- **`OPEN/CLOSE` arrays are not read at load.** `_load_layer` hands the
  control line to `process_open_close_line`, which stores the file path, not
  the data. `get_data()` reads the file on every call, and nothing caches it.
  In the benchmark corpus, 18 models have 56 array files (12.6 MB of the
  31.8 MB total) that flopy3 opens only when their data is accessed.
- **`OPEN/CLOSE` lists are read at load, but only as a side effect.**
  `lazy_io=False` leaves `auto_set_sizes` on. `MFPackage.load` then calls
  `_update_size_defs`, which calls `get_data()` on every list to size
  `maxbound`. That reads the external file, converts the DataFrame to a
  recarray, and throws both away. Access reads the file again.
  - `lazy_io=True` turns `auto_set_sizes` off, and then flopy3 reads no
    external list files at load. It isn't benchmarked.
  - `lazy_io` doesn't otherwise make array reading lazier. Arrays are
    deferred either way.
- **flopy3 loads more than flopy4 does.** It reads packages flopy4 has no
  component for (DISU, MAW, SFR, UZF, HFB, GNC, GWF-GWF exchanges, ...) and
  child files (TS, TAS, OBS, LAK tables).

### flopy4

`Simulation.load(path)`, the basic loader.

- Everything it reads, it reads at load, `OPEN/CLOSE` arrays and lists
  included (`_read_open_close_values`, `_resolve_open_close_rows`). No model
  opened any file during materialize.
- It silently skips packages and child files it has no component for. It
  records a `ts_file`/`obs_file` path without opening it.

### Equalizing the work

- flopy3 gets `load_only`, set to the package types flopy4 actually loaded
  for that model (recorded by wrapping `Package.load`). flopy3 always loads
  the discretization, TDIS and namefiles regardless.
- Two stages are timed. `test_load` is load only. `test_load_materialize`
  is load, then touch everything. Only the second is like-for-like, because
  flopy3 defers `OPEN/CLOSE` arrays.
- "Materialize" means:
  - **flopy3:** for every package in `sim.sim_package_list` and every model's
    `packagelist`, and every dataset in every block:
    - `get_dataframe()` for pandas-backed lists (their native form;
      `get_data()` would add a recarray conversion);
    - `get_data()` for `MFArray`, `MFTransientArray`, `MFList` and
      `MFTransientList`.

    Then sum every numeric array, column or field. Scalars aren't touched,
    since they're always parsed at load.
  - **flopy4:** walk the component tree (attrs fields and `__dict__`, into
    records, dicts and lists), summing every numeric value.
- A model is in the corpus only if both loaders, after load and materialize,
  opened **exactly the same set of files**. That check runs once per session,
  in a subprocess, so the audit hook never runs in the timed process.
- As a spot check that flopy4 doesn't read a file and then drop its data:
  across the 165 corpus models, every one of the 1,874 non-transient griddata
  arrays that flopy3 holds data for is non-`None` on the matching flopy4
  package. (This used a scratch script and isn't part of the benchmark.) The
  one model where flopy4 did drop griddata, `test006_gwf3_disv_ext`, is
  excluded by the file check anyway.

The two loaders still keep data differently. For example, flopy4 sometimes
keeps a `CONSTANT` array as a scalar where flopy3's `get_data()` builds the
full array. They also hold lists differently: a DataFrame in flopy3, lists of
attrs records in flopy4. These differences are part of what's timed.

## Corpus

This is the 239 `KNOWN_PASSING` models (`test_mf6_load_all_models.py`) minus
the 74 where the file sets differ. That leaves **165 models, 31.8 MB** of input
files. All 239 load without error under both loaders, so every exclusion is
about unequal work, not failures. The list is pinned in
`benchmarks/models-full.txt`.

| excluded | reason |
|---|---|
| 44 | flopy3 reads TS/TAS and/or OBS child files that flopy4 doesn't load (24 with TS/TAS, 20 OBS only) |
| 17 | DISU models: flopy4 has no DISU component, and flopy3 always loads the discretization |
| 10 | flopy3 reads LAK table files (`utl-laktab` children), mostly alongside TS/OBS |
| 1 | `test005_advgw_tidal`: TS/OBS files, plus an `OPEN/CLOSE` file referenced from an OBS file |
| 1 | `test006_gwf3_disv_ext`: DISV `DIMENSIONS` is `OPEN/CLOSE`, so flopy4 can't size the grid. It leaves `top`/`botm`/`idomain` as `None` and doesn't read `CELL2D` |
| 1 | `test051_uzfp2_openclose`: flopy4 reads OC per-period `OPEN/CLOSE` files, but flopy3 never opens them, even on access |

## Results

These are warm runs, in-process, after one untimed warm-up round. Figures are
the minimum of 3 rounds, from the load benchmarks with the pinned
manifest. An earlier run agreed within 2% on the corpus figures and within
5% on the per-model ones.

### Whole corpus (165 models, 31.8 MB)

| stage | flopy3 | flopy4 basic | flopy3 / flopy4 |
|---|---|---|---|
| `test_load` (not like-for-like) | 15.56 s | 13.72 s | 1.13 |
| **`test_load_materialize`** | **17.01 s** | **14.44 s** | **1.18** |

The corpus total is misleading on its own. One model,
`test205_gwtbuy-henrytidal`, accounts for ~10 s of flopy3's 17 s.

A scratch script timed each model separately: warm, load + materialize, best
of 3. It showed:

- The totals were 16.10 s for flopy3 and 13.26 s for flopy4. Without
  henrytidal, they're **6.24 s and 9.99 s**, so flopy4 is slower on the rest.
- flopy4 is faster on 127 of the 165 models, which are mostly small ones.
  - For the 127 models under 50 ms with both loaders, the median is 20.4 ms
    for flopy3 and 8.2 ms for flopy4. flopy3 has more fixed overhead per
    model.
  - The median per-model ratio (flopy4 / flopy3) is 0.44. The 10th
    percentile is 0.31 and the 90th is 3.09.

### Largest models (load + materialize)

| model | input | flopy3 | flopy4 | flopy4 / flopy3 |
|---|---|---|---|---|
| `test019_VilhelmsenGF` | 10.8 MB | 0.392 s | 0.141 s | 0.36 |
| `test120_mv_disv_xt3d` | 3.8 MB | 0.556 s | 2.736 s | 4.92 |
| `test205_gwtbuy-henrytidal` | 3.1 MB | 9.969 s | 3.354 s | 0.34 |
| `test016_Keating_dev` | 1.5 MB | 0.385 s | 0.675 s | 1.75 |
| `test016_Keating` | 1.5 MB | 0.382 s | 0.666 s | 1.74 |

Each model shows a different regime:

- **VilhelmsenGF.** Almost all of its bytes are `OPEN/CLOSE` array files.
  flopy4 reads these with `np.array(text.split())`, entirely in C. flopy3
  reads them on access, with a per-line Python loop and no caching (see
  [below](#why-array-reading-differs-python-work-per-token-per-line-or-per-file)).
- **mv_disv_xt3d and Keating.** Large *internal* arrays. flopy4's Lark path
  costs per token in pure Python.
  flopy3 reads the same data faster, because its per-line loop does less
  Python work per value than Lark's per-token path.
- **henrytidal.** It has ~970 stress periods of GHB and DRN list data (1,939
  period blocks), and flopy3 pays a fixed pandas cost per block. cProfile
  shows two main costs:
  - `_read_text_data`, with `_decrement_id_fields` inside it;
  - `_update_size_defs` (`auto_set_sizes`), which converts each block's
    DataFrame to a recarray just to count rows. This was about 30% of
    flopy3's profiled load.

### Why array reading differs: Python work per token, per line, or per file

This comes from follow-up measurements after the baseline (2026-09-24,
scratch scripts, flopy 3.11.0). It explains the first two regimes above.

**flopy3 reads every text array, inline or external, with one per-line
Python loop.** `MFFileAccessArray.read_text_data_from_file`
(`flopy/mf6/data/mffileaccess.py`) serves both cases: `INTERNAL` arrays pass
the open package file handle, and `OPEN/CLOSE` arrays open the external
file. For each line it:

1. calls `fd.readline()`;
2. tokenizes with `PyListUtil.split_data_line`, a Python function that also
   detects the delimiter. For the first 15 lines of each file it runs
   `shlex.split` and retries the line with every candidate delimiter, then
   falls back to `str.split`. A comment line restarts that detection;
3. calls `MFComment.is_comment`;
4. appends the tokens to one Python list of strings.

Numpy is used once, at the end: `np.fromiter(data_raw, dtype=...)`. Binary
external arrays are different, and are read with `np.fromfile`, but no
corpus model has one.

**flopy4 does different amounts of Python work per value, depending on
where the array is:**

| array location | flopy4 | flopy3 | Python work per… | result |
|---|---|---|---|---|
| inline (`INTERNAL`) | Lark: lex, parse, build a tree node for every number, then a transformer callback | the per-line loop | token (flopy4) vs. line (flopy3) | **flopy3 faster**: 1.75x on Keating, 4.9x on mv_disv_xt3d |
| external (`OPEN/CLOSE`, text) | `read_text().split()` then `np.array(tokens, dtype)`, entirely in C (`structure.py`, `_read_open_close_values`) | the same per-line loop, and no caching (see below) | file (flopy4) vs. line (flopy3) | **flopy4 faster**: 2.8x on VilhelmsenGF |

The ordering is the same in both rows: per-token Python costs more than
per-line Python, which costs more than a whole-file pass in C.
It's also why reading inline data blocks as single tokens with numpy
should pay off.

**Measured on VilhelmsenGF's external files** (25 files, 9.5 MB, 96k
lines with ~7-10 values each; same in-memory text, best of 5, no
profiler):

| reader | time |
|---|---|
| flopy4 (`split` + `np.array`) | 0.044 s |
| flopy3's loop (`split_data_line` + `is_comment` + `np.fromiter`) | 0.133 s (3.1x) |
| of which `split_data_line` alone | 0.089 s |

- Under cProfile, the loop's cost is the per-line calls, not `shlex`.
  `split_data_line` runs once per line (203k calls over the load +
  materialize), and `shlex` is only ~7% of its time, because it runs only
  on each file's first lines. Short lines are the worst case, since the
  fixed per-line cost is shared by fewer values.
- **flopy3 also re-reads files.** It doesn't cache external array data:
  each `get_data()` reads the file again. During one load + materialize,
  `read_text_data_from_file` ran 54 times for the 25 files, roughly
  doubling flopy3's cost on top of the 3x.
- flopy3 could close most of this gap cheaply. It could try a whole-file
  split and a single numpy conversion, falling back to the line loop only
  on failure, and cache what it reads.

**Tolerance is cheap when done in bulk.** flopy4's current reader is
faster partly because it tolerates less: a `#` comment or any stray text
in an external array file makes it fail (no corpus file has one). A
tolerant bulk reader keeps nearly all of the speed:

```python
COMMENT = re.compile(r"[#!][^\n]*")
TABLE = str.maketrans({",": " ", ";": " ", "\t": " ", "'": None, '"': None, "d": "e", "D": "e"})
values = np.array(COMMENT.sub("", text).translate(TABLE).split(), dtype=np.float64)
```

On the same 25 files:

| reader | clean files | "messy" files |
|---|---|---|
| flopy4 current | 0.042 s | fails on `#` |
| tolerant bulk (above) | 0.062 s | 0.067 s |
| flopy3's loop | 0.134 s | fails (`IndexError`) |

- The messy files are a synthetic stress test made from the real ones:
  - a comment line every 50 lines;
  - trailing `!` remarks;
  - random `,` / `;` / tab delimiters;
  - 5% quoted values;
  - 30% `D` exponents.
- The tolerant reader returns exactly the values the current reader gets
  from the clean files.
- These features were not checked against what MF6 itself accepts in an
  external array file. Semicolons, `!` comments and quoted numbers may not
  be valid MF6, so flopy3 failing on them is not a flopy3 bug.
- Adding tolerance costs ~1.5x and stays ~2x faster than flopy3's loop,
  because every extra step is another whole-file pass in C.
- Still missing from the tolerant reader, relative to flopy3:
  - stopping at the expected number of values, which needs a count check
    against the grid dims (that also gives a better error message);
  - per-line truncation for LAYERED arrays;
  - handling text after the values that isn't marked as a comment.

### Cold start

Each round runs a fresh interpreter that imports the loader, then loads and
materializes `test050_circle_island` (0.55 MB DISV). The measurement is
wall time, minimum of 5 rounds. The breakdown columns come from inside the
child process, in its last round.

| | wall | import | load | materialize |
|---|---|---|---|---|
| flopy3 | 0.94 s | 0.54 s | 0.24 s | 0.05 s |
| flopy4 basic | 2.41 s | 1.52 s | 0.56 s | 0.03 s |

- flopy4's import dominates its cold start. `python -X importtime` puts
  ~0.64 s of it in importing flopy3 itself (`flopy.discretization`, for
  grids) and ~0.45 s in `xugrid`.
- flopy3's DFN structure build happens on first load, inside its "load"
  column.

### Parse stage, basic vs. typed

These come from the parse benchmarks, run in the same session. The corpus is 2,149 package files (21.6 MB) that both
grammars parse, and figures are the minimum of 3 rounds.

This is **parse stage only**. It's a different corpus and a different unit of
work from the full loads above, so don't compare the two tables' times
directly.

| stage | basic | typed | typed / basic |
|---|---|---|---|
| parse | 12.62 s | 13.28 s | 1.05 |
| parse + transform | 14.37 s | 17.81 s | 1.24 |
| typed grammar build (30 components, once per process) | | 1.74 s | |

## Not measured yet

- **A full typed load**, which doesn't exist yet (see above).
- **The 74 excluded models.** flopy4 skips DISU, TS/OBS and other child
  files. Once it loads them, those models can join the corpus, but that
  changes the pinned set, so it needs a fresh baseline.
- **flopy3 with `lazy_io=True`.** That turns off `auto_set_sizes`, which
  would likely help henrytidal-style inputs a lot.

## Reproducing

```shell
# all benchmarks (opt-in), on the standard tier (benchmarks/models.toml)
pixi run -e dev bench
pixi run -e dev bench --bench-tier smoke            # under a minute
pixi run -e dev bench-large                         # the large tier
pixi run -e dev bench-full                          # benchmarks/models-full.txt
pixi run -e dev bench --benchmark-compare           # vs. the last saved run
pixi run -e dev bench -k test_load                  # load only
pixi run -e dev bench -k test_parse                 # parse only
pixi run -e dev bench -k test_write                 # write only

# benchmark the models listed in a file instead of a tier. If the file
# doesn't exist, discover the models from KNOWN_PASSING: the ones that pass
# the equal-work check are written to it, and the others listed at the end
pixi run -e dev bench --bench-manifest /path/to/new-models.txt

# the file-set check or the cold start by hand, for one or more workspaces
pixi run -e dev python benchmarks/_check.py WS [WS ...]
pixi run -e dev python benchmarks/_worker.py cold flopy4 WS
```

Saved runs go to `.benchmarks/`, which is git-ignored. Benchmark names
changed since this baseline was recorded (e.g. `flopy4-basic` → `flopy4`),
so `--benchmark-compare` against an older save won't match names; rerun to
get a fresh save. Each benchmark's
`extra_info` records:

- `models` (the tier or manifest), `n_models`, `n_bytes`, `n_excluded`, the
  flopy version and the flopy3 load options;
- the model name and its `models.toml` tags, for the per-model and
  cold-start groups;
- `n_files_written` and `n_bytes_written`, for the write groups.

The per-model distribution and the griddata coverage check came from scratch
scripts. Both are easy to reconstruct from `benchmarks/_ops.py`:

- the distribution loops over the manifest, timing
  `materialize_*(load_*(ws))` best-of-3 per loader;
- the coverage check matches packages by filename and compares
  `MFArray.has_data()` with the flopy4 attribute.
