# Input loader roadmap

**Archived 2026-10-19.** Superseded: stage 0 merged as #482 (benchmarks), stage 4 as #474-#484 (see [`typed-loader-perf.md`](../loading/typed-loader-perf.md)). Stages 2-3 (typed wiring) are in [`typed-loader-wiring.md`](../loading/typed-loader-wiring.md), not started.

Status as of 2026-09-24: what's done, what we learned, and how the remaining
loader work is staged. This is the index. Details live in the docs and plans
linked below.

## Where things are

**Branches on the fork (`origin` = wpbonelli/pyphoenix-project), no PRs:**

| branch | contents | status |
|---|---|---|
| `typed-remarks` (off `develop`) | parse-stage benchmark, basic vs. typed; [`typed-grammar-remarks.md`](typed-grammar-remarks.md) (remarks and performance analysis). Uses the old names (`bench`, `test_mf6_reader_benchmark.py`, `--bench-manifest`); `load-baseline` renames them. | superseded by `load-baseline` for review |
| `load-baseline` (on `typed-remarks`) | both benchmark suites under their final names: `bench-parse` (`test_mf6_parse_benchmark.py`, flopy4 basic vs. typed parsers) and `bench-load` (`test_mf6_load_benchmark.py`, flopy3 vs. flopy4 full load, 165 pinned models); `bench` runs both. `docs/dev/load-benchmarks.md` | ready for review; contains `typed-remarks` |
| `typed-no-remarks` | experiment: remark support removed from the typed grammar | reference only, never merge; lacks the later doc commits |

**Worktrees:** `~/dev/pyphoenix-typed-remarks`,
`~/dev/pyphoenix-load-baseline`.

**Plans (untracked, project root):**
- [`load-baseline-plan.md`](load-baseline-plan.md): done.
- [`typed-loader-wiring.md`](../loading/typed-loader-wiring.md): not started. Stages 2-3 below.
- [`typed-grammar-trailing-remarks.md`](typed-grammar-trailing-remarks.md): the original open question, since
  answered.
- [`optimization-plan.md`](optimization-plan.md): basic-loader performance steps. Not started;
  stage 4 below.

## What we learned

1. **Trailing remarks are load-bearing.** Removing them breaks 357 more
   corpus files (47 → 404 failures), ~90% of them MF2005-style labels on
   array control lines (`CONSTANT 100.0 DELR`). They cost nothing
   measurable at parse time, only ~0.5 s of one-time grammar build. So
   any case for dropping them rests on grammar complexity, not speed.
2. **The typed loader isn't faster, and moving logic into the grammar
   won't make it so.**
   - Typed parse is ~1.07x basic; parse + transform is ~1.25x.
   - ~87% of a basic `Simulation.load` is Lark (lex, parse, tree); the
     structuring the typed grammar was meant to absorb is ≤13%.
   - Pure-Python grammar rules cost the same interpreter time as
     post-processing, plus tree overhead.
   - The headroom is bulk numeric data. Extracting it in C is 10-30x
     faster than Lark's lexer alone.
3. **flopy4-basic vs. flopy3** (load + materialize, 165 models, equal work
   verified per model):
   - 14.44 s vs. 17.01 s overall, but one model (henrytidal) accounts for
     ~10 s of flopy3's time. Without it, flopy4 is slower (9.99 s vs.
     6.24 s), though it wins on 127 of 165 models (less fixed cost).
   - ~5x slower on large inline arrays (Lark cost per token).
   - ~3x faster on `OPEN/CLOSE` arrays (read with numpy). This is
     independent evidence for point 2's numpy idea.
   - ~2.5x slower cold start, mostly imports: flopy3 for grids (~0.64 s)
     and xugrid (~0.45 s).
   - 74 models are excluded for unequal work (TS/OBS child files, DISU,
     LAK tables). They need a new baseline when flopy4 supports them.
4. **The typed transformer has real bugs** that the parse-only corpus
   test couldn't see, including silent data loss (TDIS
   `START_DATE_TIME` → `'1997'`). The typed loader isn't wired into
   `Simulation.load` / `Package.load` at all.

## Staging

**Stage 0: land the measurement baseline.**
- One PR from `load-baseline`, which includes `typed-remarks`. It's tests
  and docs only, with no production code change.
- Everything after this is measured against it.
- `typed-no-remarks` stays on the fork as a reference.

**Stage 1: small independent PRs off `develop`** (any order, in parallel
with other work):
- Typed transformer silent-loss fixes (wiring plan step 3a): the
  `START_DATE_TIME` truncation, remark tokens in data rows, the
  `layered`/`netcdf` slot mix-up, and integer arrays parsed as doubles.
  Each gets a regression test.
- Cold-start imports: make the flopy3-for-grids and xugrid imports lazy
  (optimization plan step 1).
- Grammar/DFN drift: regenerate against a pinned DFN version and remove
  the 17 orphaned grammars, as its own labelled change.

**Stage 2: typed wiring, the parts that don't touch the converter**
(wiring plan steps 1, 5, 2, 3b):
1. `ReadContext` switch (`basic` / `typed` / `typed-fallback`) plus the
   parity test. At first the parity test reports how many models match;
   that number is the progress metric.
2. Runtime schema from generated classes (option b): audit what the
   transformer needs, then prototype b1 (read class metadata) against b2
   (codegen emits a per-component transformer) on 2-3 components. Review
   the choice before committing to one.
3. Specify the typed output representation: numpy not xarray, no `Tree`s
   left in the output, real list-block names.

**Stage 3: typed structuring** (wiring plan step 4), **after the converter
simplification lands**.
- `structure.py` is also being reworked on `pyphoenix-simplify-converter`,
  which is itself waiting on `roundtrip-fixes`. Build the shared
  per-field-kind back end on the simplified converter, or fold it into
  that work.
- Then one PR per block kind: options/dimensions → lists/periods →
  griddata → name-file bindings. Parity should rise with each.
- Then add a `reader` parameter to `bench-load` for the first full
  three-way comparison (flopy3 / basic / typed).

**Stage 4: performance, in parallel with stages 2-3** (details in
[`optimization-plan.md`](optimization-plan.md)). These target the **basic** loader users run today,
so they don't wait on the typed wiring. Each is one PR, with `bench-load`
numbers before and after and a clean value-snapshot check:
0. Value-snapshot check (prerequisite).
1. Lazy imports (cold start).
2. Tolerant bulk external-array reader, with a count check.
3. Bulk numeric-run token in `basic.lark`, covering inline arrays and
   all-numeric list rows (the big one; estimated ~2x faster than flopy3
   overall).
4. Lists with words (boundnames, keywords), if still worth it after step 3.
5. Lark inline transformer / `cache=True`, for whatever still goes
   through Lark.

The typed grammar gets the same bulk token when it's wired in. After
that, revisit remarks with the cheaper rest-of-line remark terminal; by then
remark use can be counted, so a deprecation argument has data.

## Deferred: lazy external arrays (and an xarray backend)

**The idea.** Read externally stored array data only when it's accessed,
not at load time. Today flopy4 reads every `OPEN/CLOSE` array eagerly. In
the load-baseline corpus that's 18 models and 12.6 MB of array files,
sometimes most of a model's bytes. Laziness would make those loads nearly
free, and users who touch only some arrays would never pay for the rest.

**Evidence it matters:**
- flopy3 already defers `OPEN/CLOSE` array reads until `get_data()`. That
  is one reason the benchmark has to materialize everything to compare
  fairly.
- Unlike flopy3, which re-reads the file on *every* access with no
  caching, flopy4 should read once and cache.

**Shape of it:**
- Binary `OPEN/CLOSE ... (BINARY)` arrays: memory-map the file
  (`np.memmap`, after the MF6 binary header) and wrap it as a lazily
  indexed array. Slices never touch the rest of the file.
- Text `OPEN/CLOSE` arrays: can't be indexed without parsing, so defer the
  whole read to first access. That's a `dask.delayed` read wrapped in a
  `dask.array`, or a small lazy array type. Read once, then cache.
- The object model holds these lazy arrays in place of numpy arrays. Shape
  and dtype are known at load from dims and the field type, so validation
  that needs only shape still works without reading.
- Writing: an unmodified lazy array can be written back as the same
  `OPEN/CLOSE` reference without being read (flopy3's `lazy_io` does the
  same). That's a round-trip win too.
- Inline arrays (inside the package file) stay eager: they have to be
  parsed to get past them anyway.

**Things to settle first:**
- Which consumers assume a concrete `np.ndarray`: converters, `to_xarray`,
  writers, validation. The converter simplification is the natural time to
  find out.
- File-change semantics: what happens if the external file changes between
  load and first access? Probably document "read at first access" and move
  on.
- Benchmark impact: `bench-load`'s "load + materialize" stage stays the
  fair comparison. A "load only" number will drop sharply and shouldn't be
  quoted alone.

**Xarray backend.** An `engine="mf6"` backend (`open_dataset` /
`open_datatree` → `load(...).to_xarray()`) is cheap given the existing
`to_xarray()` methods, but adds no speed and is a lossy view of input
files (options, records, bindings). If done, keep it a thin wrapper that
the reader never depends on. Lazy external arrays, built into the loader,
are the part of that idea worth pursuing, and a backend would get them for
free. Not on the critical path; revisit after stage 3.

## Open decisions (yours)

- Stage 0 as one PR or two (`typed-remarks`, then `load-baseline`).
- Stage 3: wait on the converter simplification, or merge the two.
- When the `roundtrip-fixes` PR goes up; the converter simplification is
  blocked on it.
- flopy3 `lazy_io=True`: add it as an extra benchmark column? It would
  change the henrytidal picture.
