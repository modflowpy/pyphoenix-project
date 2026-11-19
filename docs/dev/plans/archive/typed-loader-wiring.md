# Plan: wire the typed loader in alongside the basic one

Goal: make the flopy4 typed loader (per-component Lark grammar plus
`TypedTransformer`) a complete, selectable alternative to the basic loader
for `Simulation.load` / `Package.load`. Switching between them should be
trivial. Parity should be verified on the real corpus, and full-load
performance should be measurable for both.

Written 2026-09-24. Background: [`typed-grammar-remarks.md`](../archive/typed-grammar-remarks.md) on
branch `typed-remarks`, particularly "Why the typed loader isn't faster
(yet)". Once the `load-baseline` branch lands, it provides the flopy3 vs.
flopy4 full-load benchmark this plan extends in step 6.

## Ground rules for whoever implements this

- Work in a new git worktree under `~/dev/` (never `/tmp`), branched from
  `develop` or from whichever of `typed-remarks` / `load-baseline` has
  merged by then. Rebase the benchmark bits in as needed.
- Run everything via `pixi run -e dev ...` (never `uv run`). Verify with
  `pixi run -e dev smoke`, not the full suite, unless asked.
- Sign commits with the session's `Co-Authored-By:` trailer. Don't push,
  open PRs, or touch GitHub unless the user asks.
- Justify generality (new IR layers, recursion) with verified facts from
  the DFN schema or corpus, not intuition.
- Local DFNs: `~/dev/modflow6/doc/mf6io/mf6ivar/dfn` (the `dfn_path` test
  fixture finds them).

## Status (2026-10-19)

**Not started, and not yet decided.** `Package.load` still passes no
component, so only the basic reader runs; `loads_typed` is used by the
corpus tests (`_check_typed_grammar` in `test_mf6_load_all_models.py`)
and the parse benchmarks. After #474-#484 the basic reader is 2-5x faster
than flopy3 and typed parse is slower than basic ([`typed-loader-perf.md`](../archive/typed-loader-perf.md)),
so the case for wiring typed in is validation and error messages, not
speed. Decide whether to do it before starting.

What changed since the state below was written:

- **Step 2 is done, differently** (#455, [`class-driven-reader-plan.md`](../archive/class-driven-reader-plan.md)).
  The typed transformer reads the parse tree alone: generated rules are
  named for what they are (`grammar/names.py`), so it needs neither DFNs
  nor class metadata. `codec/reader/dfns.py`, `dfn_path` and the runtime
  fetch are gone. Option (b1)/(b2) below no longer applies.
- **Version drift is handled by sync** (#437, #455): grammars are
  checked in and regenerated with the classes in one staged swap, stale
  ones removed.
- **Step 3a, rechecked 2026-10-19** with `loads_typed` on develop
  `e0d94b86`:
  - `START_DATE_TIME`: fixed, the full timestamp comes through.
  - TDIS perioddata remarks: still kept as data
    (`[1.0, 1, 1.0, 'Items:', 'PERLEN', 'NSTP', 'TSMULT']`), still under
    `stress_period_data`.
  - Name files: blocks now come back as rows keyed by block
    (`models`, `solutiongroup 1`), but the rows are still under
    `stress_period_data`.
  - LAYERED arrays: the `layered` marker is still in the `netcdf` slot.
  - NPF `icelltype`: still parsed as double (`1.0`).
- Benchmarks (step 6) now live in `benchmarks/` (#482), whose
  `test_parse.py` already compares basic and typed parse.

## Current state (verified 2026-09-24)

**One seam, one consumer.**
- `Package.load` (`flopy4/mf6/package.py`) calls `codec.reader.load(fp)`
  without passing `component=`, so the basic loader always runs.
- The raw result goes to `structure_component`
  (`flopy4/mf6/converter/ingress/structure.py`). It only understands the
  basic shape `{BLOCK: [token rows]}`, and does all typing in four passes:
  scalars, block item lists, periods (including READARRAY), and griddata.
- `Simulation.load` / `Model.load` go through `Component._load` →
  `structure_component` → `_resolve_bindings`, which loads each child with
  `target_cls.load(workspace / fname, dims=..., name=...)`. The `format=`
  argument isn't passed down to children.
- `_resolve_open_close_rows` also calls `codec.reader.loads` (basic) to
  read externally redirected list rows.

**Typed output is a different representation, with bugs.** Observed on
`mf6/test/test001a_Tharmonic`. Reproduce by printing `loads_basic(text)`
next to `loads_typed(text, dfn_name, dfn_path=...)` for each file
`_collect_package_files` returns
(`test/mf6/test_mf6_typed_grammar_corpus.py`):

| file | typed output problem |
|---|---|
| tdis options | `START_DATE_TIME 1997-07-16T19:20:30.45+01:00` → `'1997'`: the rest is swallowed as a trailing remark. **Silent data loss.** |
| tdis perioddata | the row keeps remark tokens as data: `[1.0, 1, 1.0, 'Items:', 'PERLEN', 'NSTP', 'TSMULT']`, and is wrapped in an untransformed `Tree('perioddatadata', ...)` |
| sim/gwf name files | `models` / `packages` / `solutiongroup` blocks come back as raw `Tree('<block>data', ...)`, all under the key `stress_period_data`. Bindings can't be resolved from this. |
| dis/npf LAYERED arrays | the `layered` marker lands in the `netcdf` slot: `'netcdf': Tree('typed__layered', [])` (`layered_array`'s `items[0]` is the `layered` result, not `netcdf`) |
| npf `icelltype` | integer array comes out as `1.0`, because `constant:` always parses `double` |
| ic `strt` INTERNAL | flat `DataArray (dim_0: 10)`: the transformer has no grid dims, so it can't shape arrays |
| chd period | rows are raw token lists (cellid not split, no `Item`s), which is fine as input to `_parse_rows` |
| ims (legacy `XMD` block) | hard parse failure. Basic parses it and structuring ignores it. |

The good parts: options come out as `{'save_flows': True}`, OC records as
`{'rtype': 'HEAD', 'ocsetting': 'all'}`, and array control records are
already interpreted.

**DFNs at runtime.** `get_typed_transformer` needs DFN `Component`
specs. With no `dfn_path`, `flopy4/mf6/codec/reader/dfns.py` fetches them
over the network (`RemoteDfnRegistry` at `_contract.MF6_VERSION`). flopy4
ships no DFNs.

**Version drift.** Regenerating grammars from newer local DFNs changed 5
committed grammars (the *g packages gained `maxbound`; utl-ts changed), and
17 committed grammars have no matching local DFN. Nothing checks that
grammars, transformer DFNs and generated classes agree.

## Decisions already made

- **Switch:** a read context (context variable), not a keyword argument
  threaded through every layer. See step 1.
- **Schema source at runtime (step 2): option (b).** Drive the typed
  transformer from the generated Python classes' metadata, not DFNs loaded
  at runtime. DFNs stay a build-time input to codegen (classes and
  grammars), and there's one source of truth at runtime.

## Steps

Recommended order: 1 → 5 → 3a → 2 → 3b → 4 (incrementally) → 6. Steps 1
and 5 make every later step measurable. Fix the silent-loss bugs (3a)
before anything relies on typed output.

### 1. Reader switch

- Add a `ReadContext`, modelled on `flopy4/mf6/write_context.py`'s
  `WriteContext`: a context manager backed by a `contextvars.ContextVar`,
  with `ReadContext.current()`. Field: `reader: Literal["basic", "typed",
  "typed-fallback"] = "basic"`.
- `Simulation.load(path, reader=...)` (and `Model`/`Package.load`) take an
  optional `reader=` that just enters the context for the duration, as a
  convenience. Children inherit it, since the context is ambient.
- Branch in `Package.load` (and the `Component._load` path for name files):
  - `basic`: `loads_basic` → `structure_component` (unchanged).
  - `typed`: `loads_typed(text, cls.dfn_name)` → `structure_typed` (step 4).
    Failures raise.
  - `typed-fallback`: try typed; on a parse/structure error, log a warning
    naming the file and the error, then use basic. For real-world use while
    typed is incomplete. Tests and benchmarks use strict `typed`.
- `_resolve_open_close_rows` keeps using basic for now; revisit in step 4.
- Default stays `basic` until parity (step 5) is essentially clean.

### 2. Runtime schema from generated classes (option b)

1. **Audit** what `TypedTransformer` reads from the DFN today:
   - `dfn.blocks`;
   - `get_fields(recurse=True)`;
   - `valid_as_union`;
   - `isinstance` checks on `Keyword` / `Record` / `Union`;
   - record child order, and which children are keywords;
   - `tagged`, `optional`, union arm names.

   For each, check whether the generated classes already carry it. Known
   so far:
   - Available: block, shape, layered, optional, tagged metadata
     (`flopy4/mf6/spec.py` `field()`); records as inner `Record` classes
     with `_keyword` / `_extra_tokens`; union arms as inner `Item` classes
     with `_keyword`.
   - Lossy: `Oc.Save.rtype` is `Union[float, str]`, not a keyword.
     Check whether keyword children of records are recoverable.
2. **Close the gaps in codegen** (`flopy4/mf6/utils/codegen/`), not by
   hand. Add metadata where the audit finds it missing.
3. **Choose the mechanism** and record the choice in the doc:
   - (b1) `TypedTransformer` takes the component class and reads its attrs
     metadata;
   - (b2) codegen emits a per-component transformer, or a table of
     callbacks, next to each grammar.

   b2 also sets up Lark's inline-transformer option (see the perf doc),
   since explicit per-rule callbacks avoid `__default__`. Prototype on 2-3
   components (e.g. gwf-oc, gwf-npf, sim-nam) before committing to one.
4. Remove the runtime DFN fetch from the typed path.
   `get_typed_transformer(name, dfn_path)` becomes keyed by class (or
   name). `dfns.py` goes away or becomes test-only.
5. **Consistency guard:** make codegen produce grammars and classes from
   the same DFN set in one run, and add a test that every generated class's
   `dfn_name` has a grammar generated from the same DFN version. For
   example, stamp the DFN version/commit into each generated file's header
   and compare. Resolve the current drift (5 changed, 17 orphaned
   grammars) as a separate, clearly labelled commit.

### 3. Fix and pin the typed transformer's output

**3a (first):** fix the silent-loss bugs:
- `START_DATE_TIME` truncation;
- remark tokens leaking into data rows;
- the `layered` / `netcdf` slot mix-up;
- integer arrays parsed as doubles. `constant:` should use the field's
  dtype: generate `constant_int` / `constant_double` variants, or pass the
  dtype through.

Add a regression test for each, next to the existing typed grammar tests
in `test/mf6/test_mf6_reader.py`.

**3b:** define the typed output representation and write it down (a short
section in the doc, or the transformer's module docstring), then make the
transformer match it:
- Blocks are keyed by lowercase name, with indexed blocks as `"period 1"`,
  as today.
- Scalars and records are keyed by field name, with records as dicts of
  their non-keyword children.
- List blocks are keyed by their real field name (not
  `stress_period_data` everywhere); rows are token lists. Transform the
  `<block>data` rules so no `Tree` survives. Add an assertion or test that
  output contains no `lark.Tree`.
- Arrays are `{"control": {...}, "data": np.ndarray | Path | scalar,
  "layered": bool}` with **numpy, not xarray**. Shape and dims are applied
  in structuring, which knows the grid. Drop `try_create_dataarray`.
- Decide what to do with unknown or legacy blocks such as IMS `XMD`.
  Recommendation: the grammar accepts any unknown `BEGIN x ... END x`
  generically and the transformer drops it with a warning, matching the
  basic path's behavior.

### 4. `structure_typed`

- **Refactor first**: split `structure_component` so the per-field-kind
  logic takes already-parsed inputs:
  - scalar/record assignment;
  - item-list rows (`_parse_rows`);
  - period grouping (`_group_repeating_rows`);
  - griddata (`_parse_griddata_block` → take control record plus values);
  - READARRAY period arrays;
  - repeating arrays;
  - bindings (`_resolve_bindings`).

  Then the basic front end (token rows) and the typed front end (typed
  output) both feed the same back end. Don't fork a second converter.
  Keep `pixi run -e dev smoke` and the load-all-models test green through
  the refactor, before any typed code exists.
- **Then add typed front-end handlers one block kind at a time**, each
  verified by step 5's parity test under strict `typed`:
  1. options/dimensions (names → attrs field names/aliases; records need a
     from-dict constructor next to `Record.from_tokens`);
  2. list blocks and periods (typed rows → `_parse_rows`);
  3. griddata and READARRAY periods (reshape to dims, LAYERED stacking,
     `FACTOR`, `OPEN/CLOSE` and `(BINARY)` reads via the existing helpers);
  4. name-file bindings (`_resolve_bindings` from typed binding rows),
     which completes `Simulation.load` under `typed`.
- Until all four are done, `typed-fallback` gives a usable mixed path.

### 5. Parity test (the acceptance test)

- New test (e.g. `test/mf6/test_mf6_reader_parity.py`), marked `slow`,
  parametrized over `KNOWN_PASSING`. It loads each model with
  `reader="basic"` and `reader="typed"` and compares the results field by
  field: scalars equal, arrays `np.array_equal` (dtype included), item
  lists equal, children recursively.
- Keep a **per-file** known-differences list with reasons, finer-grained
  than `KNOWN_TYPED_GAPS`' per-component skips. A difference not on the
  list fails.
- Where typed is right and basic is wrong, record it rather than
  "fixing" typed to match. One suspect case: basic keeps
  `CONSTANT -10.00000000` as the string `'-10.00000000'` in dis
  griddata. Check what structuring does with it.
- Write this early (right after step 1). It will fail almost everywhere at
  first. That's the point: it becomes the progress metric. Report
  `n_models_identical / n_models` in the test output or a small script.

### 6. Benchmarks

- Add a `reader` parameter (`basic`, `typed`) to the full-load benchmark
  from `load-baseline` (flopy3 is the third column there), pinned to the
  models that load under both readers.
- Keep the parse-stage benchmark (`test_mf6_parse_benchmark.py`, `bench-parse`) as is.
  With typed arrays as numpy (step 3b), expect the typed transform stage
  to get cheaper. Measure it.
- Record the first full-load typed vs. basic vs. flopy3 comparison in the
  doc, with the caveat about which models were included.

## Done when

- `Simulation.load(path, reader="typed")` loads the models it covers
  without fallback. `reader="typed-fallback"` loads everything basic does.
  The default is still `basic`.
- The parity test passes, with a short per-file known-differences list
  whose every entry has a reason.
- No runtime DFN fetch on the typed path. A test guards grammar/class/DFN
  version agreement.
- The typed output representation is documented, and contains no `Tree`s
  and no xarray.
- Full-load benchmark numbers for typed vs. basic vs. flopy3 are in the
  doc.

## Out of scope here (tracked in the perf doc)

These are perf ideas to try after parity, since each changes grammar or
transformer internals the parity test should guard:
- inline Lark transformer;
- `cache=True` grammar caching;
- numpy-parsed numeric data-block terminals;
- a cheaper trailing-remark terminal.
