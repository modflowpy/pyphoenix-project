# flopy3 → flopy4 migration: aliases first, then a codemod

Written 2026-11-03 against pyphoenix `develop` (`8d25e4b7`). Prompted by
mjreno's flopy4 round-trip PRs on MF6 (MODFLOW-ORG/modflow6#3048, #3057,
#3067). Counts of flopy3 keywords and of MF6 autotest usage are from
[`replacing-flopy-mf6.md`](replacing-flopy-mf6.md), not recounted here.

## Summary

- **The MF6 PRs don't need flopy4 build code.** #3067 builds each model
  with flopy3, loads the written input with `Simulation.load`, writes it
  back with `sim.write()`, reruns mf6 and compares. That covers the
  loader and writer across 334 test files. Duplicating 334 `build_models`
  functions in flopy4 to also cover the constructors would double the
  maintenance for little gain.
- **Shrink the gap before building the tool.** Many differences between
  the flopy3 and flopy4 APIs come from implementation details (attrs'
  `kw_only`, DFN field names), not from design decisions. Accepting the
  flopy3 forms at runtime (Part 1) makes most flopy3 scripts run
  unchanged, with warnings, and leaves the codemod much less to do.
- **The codemod applies the runtime aliases statically.** Each alias is a
  table entry: the flopy3 form, the flopy4 form and a converter. The
  runtime shim and the codemod (Part 2) both read the same table, so a
  rewrite the codemod can't make (the value is a variable, or built in a
  loop) can be left alone, and the code still runs. The codemod only
  needs `# TODO(flopy4)` comments for differences that have no alias.
- **Migration becomes two steps:** first make it run (upgrade, fix
  warnings as convenient), then make it idiomatic (`flopy4 migrate`).
  Neither step requires the other.

## Part 1: make the gap smaller

Each flopy3 → flopy4 difference falls into one of three groups:

- **Accept**: take the flopy3 form for good, with no warning. The
  difference was accidental, and the flopy3 form costs nothing.
- **Deprecate**: take the flopy3 form with a `FutureWarning` that names
  the replacement. Not `DeprecationWarning`: Python hides that outside
  `__main__` and tests, so script users wouldn't see it. The 4.x compat
  layer uses the same class. The new form is better, but the old one is easy
  to convert.
- **Break**: the meaning changed. Raise an error with a hint, or document
  the change. The codemod flags these and doesn't rewrite them.

### Constructors

| flopy3 | flopy4 today | proposal | why |
|---|---|---|---|
| parent positional: `ModflowGwfdis(gwf, ...)` | `parent=` keyword only | **accept** | `kw_only=True` exists so attrs allows optional base fields before required subclass fields (`component.py:235`), not to stop positional use. `LegacyKwargs.__call__` can move one positional argument to `parent=` before attrs sees it. `Dis(gwf, nlay=3)` reads fine. |
| bare list `stress_period_data=[...]` | raises `'list' object has no attribute 'items'` | **accept (bug fix)** | [`migrating.md`](../../../migrating.md) already says a list means period 0. |
| `*_filerecord` / `*printrecord` (106 keywords), e.g. `head_filerecord="m.hds"` or `[("m.hds",)]` | `head_file=` | **deprecate** | `head_file` is better. Convert each flopy3 value shape (a string, a 1-tuple, a list of 1-tuples) to a path. These are generated `Legacy` entries like the period-data ones. |
| `perioddata`, `steady_state`/`transient`, `saverecord`/`printrecord`, ... | `stress_period_data` | **deprecate** (done) | Already `LegacyKwargs` (`legacy.py`, from `_LEGACY_PERIOD_KWARGS` in `utils/codegen/make.py`). |
| `timeseries=`, `timearrayseries=`, `observations=` (66 keywords) | `ts` / `tas` / `obs` children | **deprecate** | flopy3 accepts a dict (`{"filename": ..., "timeseries": ..., ...}`) or a file name. The common shapes convert. Raise on any other shape. |
| `maxbound=` (12) | derived from the data | **accept, check it** | Drop it if it agrees with the data, raise if it doesn't. A warning only adds noise: the value is redundant, not wrong. |
| `pname=` | `name=` | **accept** | A synonym. |
| `parent_*`, `loading_package` (12) | — | **accept, ignore** | flopy3 plumbing. Ignore with no warning, or with a warning if it was set to anything but the default. |
| `dev_*` options (36) | only with `developmode` | **break, clearly** | Raise an error saying "regenerate with `flopy4 mf6 sync --developmode`". MF6 is the main user, and its CI now has the switch. |
| nam `packages=`, IMS `rcloserecord`, TS records, other leftovers (33) | various | **case by case** | Classify in step 1 below. Most of them are likely to be "deprecate". |

### Simulation and Model

| flopy3 | flopy4 today | proposal | why |
|---|---|---|---|
| `MFSimulation(sim_name=, sim_ws=, exe_name=)` | `Simulation(name=, workspace=)` | **deprecate** `sim_name`/`sim_ws`; **accept** `exe_name` | `exe_name` is useful: store it as the default executable for `run()`, instead of only accepting `run(exe=)`. |
| `ModflowGwf(sim, modelname=, model_nam_file=)` | `Gwf(parent=sim, name=)` | **deprecate** `modelname` | |
| `MFSimulation.load(sim_ws=...)` | `Simulation.load(path_to_mfsim.nam)` | **accept a directory** | If the path is a directory, look for `mfsim.nam` in it. That's a good change regardless of migration. Keep `sim_ws=` as a deprecated keyword. |
| `write_simulation()` / `run_simulation()` | `write()` / `run()` returning `None` | **deprecate** both | `run_simulation` returns `(success, buff)` as in flopy3, and `run` keeps its own return type. |
| `get_package(name or type)`, `get_model(name)`, `get_package_list()` | `gwf["chd0"]` only | **accept, add to core** | They're useful lookups, not leftovers. `Flopy3Model` (`flopy4/mf6/adapters.py:163-169`) already has `get_package` and `get_package_list`, so move the logic into `ModelMethods` and `SimulationMethods`, and add `get_model`. |
| `gwf.modelgrid` | `gwf.grid` (`model_methods.py:11`) | **accept** `modelgrid` | It's the same object. Many plotting and export functions in flopy are written against `modelgrid`. |
| `sim.register_ims_package(ims, [names])` | `ims.models = [...]` | **deprecate** | 340 MF6 test files use it. The method is one line. |
| default file names: `m.chd`, then `m_0.chd`, ... | `m.chd0.chd`, `m.chd1.chd`; `s.ims0.ims` | **reconsider** | Leaving the first instance unsuffixed (`m.chd`, then `m.chd1.chd`) matches flopy3 in the common one-instance case, and it's tidier. Tests and scripts that reference files by name (observation and budget checks) then keep working. This changes file names in flopy4's own tests, so decide early. |

### Data access and output: decide, don't alias

These are the "break" group. Aliases here would hide a real change in
meaning.

- **`npf.k.array` / `.get_data()` / `.set_data()`.** [`replacing-flopy-mf6.md`](replacing-flopy-mf6.md)
  Decision 2 leans toward (a): `npf.k` is the value itself, and
  `.array` raises with a hint. That group keeps the rule "same result or
  a clear error". One cheap middle ground: `get_data()` with no
  arguments on an array value could return the array, but numpy arrays
  can't take new methods, so it would need a wrapper. Don't do this.
- **`gwf.output.head()`.** flopy4's `output.head` is a `DataArray`
  property (`gwf_methods.py:31`); flopy3's is a method returning
  `HeadFile`. Same name, different thing. Pick one before release
  ([`replacing-flopy-mf6.md`](replacing-flopy-mf6.md) suggests options). If `head` stays a
  property, calling it fails with `'DataArray' object is not callable`,
  which is confusing. A wrapper that raises with a migration hint when
  called would make that error clearer.

### What the changes buy

After Part 1, a typical MF6 autotest `build_models` (constructors,
`register_ims_package`, `write_simulation`) should run against flopy4
with only `ModflowXxx` → `xxx.Xxx` class names changed. The class names
are the one difference that stays. Generated `ModflowXxx` aliases belong
to the flopy 4.x compat layer ([`replacing-flopy-mf6.md`](replacing-flopy-mf6.md)), not to
flopy4 itself, because they'd double the namespace.

## Part 2: the codemod

### Interface

- Library: `flopy4.migrate.transform(source: str, *, path=None) -> Result`,
  where `Result` holds `code: str` and `diagnostics: list[Diagnostic]`
  (a line, a rule id, a message, and whether the code was rewritten or
  only flagged).
- Script: `flopy4 migrate PATH... [--diff | --write] [--select RULES]
  [--check]` through `flopy4/cli.py`. `--check` exits non-zero if
  anything would change (for CI). The default is `--diff`. The script
  never writes files unless asked.
- Built on libcst, so comments and formatting outside the rewritten
  nodes stay as they were. libcst becomes an optional dependency
  (a `migrate` extra).

### Rules

Each rule is one transformation. Order matters only where noted.

1. **Imports.** `import flopy` and `flopy.mf6.X` → `from flopy4.mf6 import
   gwf, gwt, ...` with the modules used. Leave every non-mf6 use of
   `flopy` alone (`flopy.utils`, `flopy.plot`, `flopy.discretization`).
2. **Class names.** `ModflowGwfdis` → `gwf.Dis`, `MFSimulation` →
   `Simulation`, `ModflowTdis` → `Tdis`, and so on. The table is
   generated from the DFNs: flopy3's name is `Modflow` + component name
   with the hyphen removed. Use module-qualified names, because `Dis`
   and others repeat across model types.
3. **Parent keyword.** A positional first argument → `parent=`. Optional
   once Part 1 accepts a positional parent. Keep it as a style rule,
   off by default.
4. **Keyword renames** with no change to the value: from the generated
   `Legacy` tables (`*_filerecord` → `*_file` where the value is a
   literal string, `sim_ws` → `workspace`, `modelname` → `name`, ...).
5. **Keyword reshapes.** STO's `steady_state`/`transient`, OC's
   `saverecord`/`printrecord`, filerecord tuples. Rewrite when every
   value involved is a literal (a dict, list or tuple of constants).
   Otherwise leave it alone and add an info diagnostic: the runtime
   alias handles it.
6. **Method renames.** `write_simulation()` → `write()`; `run_simulation()`
   → `run()`, but only when the return value is unused. If it is used
   (`success, buff = sim.run_simulation()`), leave it and flag it.
7. **Flags with no rewrite**, for the "break" group: `.array`,
   `.get_data`, `.set_data`, `output.head()` / `.budget()`,
   `simulation_data`, `dev_*` keywords, `model_splitter`. These get a
   `# TODO(flopy4): ...` comment linking to [`migrating.md`](../../../migrating.md), or only
   a diagnostic with `--no-comments`.

### Knowing what a name refers to

Rules 6 and 7 need to know that `sim` is a simulation and `gwf` a model.
libcst's scope provider plus a simple per-function pass covers the
common cases: track assignments from constructor calls (`gwf =
ModflowGwf(...)`) and from `MFSimulation.load(...)`, `sim.get_model(...)`.
Don't do cross-function type inference. When the type of a name is
unknown, match method names that only exist on one kind of object
(`write_simulation` is always a simulation), and flag the rest instead
of guessing.

### Generated tables, one source of truth

Extend `_legacy_kwargs` in `flopy4/mf6/utils/codegen/make.py` so that
`sync` writes one data module (say `flopy4/mf6/_legacy_table.py`) with,
for each component: flopy3's class name, keyword renames, and named
converters. Both `LegacyKwargs` (runtime) and the codemod read it. A test
checks that every `Legacy` entry has a codemod rule, or is marked
runtime-only on purpose.

### Testing

- **Unit:** each rule gets before/after source snippets, plus an
  idempotence check: running the codemod on its own output changes
  nothing.
- **Corpus:** run the codemod on each MF6 autotest's `build_models`
  (local modflow6 checkout, not vendored), then run the result and
  compare heads and budgets against the flopy3 build, using the existing
  framework comparison. Report the share that run with only rules 1–2
  (imports and class names; flopy4 has no `ModflowXxx` names, so nothing
  runs fully unchanged before 4.x), run after the full codemod, and
  remain flagged. Use it as a scoreboard (xfail
  manifest), not a gate, as with the compat tier in
  [`replacing-flopy-mf6.md`](replacing-flopy-mf6.md).
- **Examples:** the 76 modflow6-examples scripts as a second corpus. They
  use more `.array` / `.get_data()`, so expect more flags.

## Steps

1. **Classify every difference.** Generate the full keyword diff (all
   1101 keywords across the 100 shared classes) and the method diff, and
   label each accept / deprecate / break. Resolve the 33 "other"
   keywords. Include the data-shape changes from
   [`layout-logical-decisions.md`](../dfn-spec/layout-logical-decisions.md) (STO `sc=`: accept; UZF placeholder
   columns: deprecate). Write the result into [`migrating.md`](../../../migrating.md) as the reference
   table. *No code changes.*
2. **Decisions that block Part 1:** default file naming, `output.head`
   (property or method), data access (Decision 2). Step 3 can start
   without them, but its scoreboard numbers inform them.
3. **Bug fix:** bare-list `stress_period_data` (independent, do first).
4. **Part 1 runtime aliases**, in order of MF6 autotest usage:
   positional parent, `register_ims_package`, `write_simulation` /
   `run_simulation`, `Simulation.load` from a directory, `get_model` /
   `get_package`, `modelgrid`, `sim_ws` / `sim_name` / `modelname` /
   `exe_name`, `*_filerecord`, `maxbound`, `ts` / `obs` keywords.
5. **Generated table** shared by runtime and codemod.
6. **Codemod rules 1, 2, 4, 6** (mechanical renames), CLI and library
   entry points, unit tests.
7. **Rules 5 and 7** (reshapes and flags), name tracking.
8. **Corpus scoreboard** over MF6 autotests, then modflow6-examples.
   Runs in flopy4's CI against a modflow6 checkout; nothing changes in
   MF6's repo. Doubles as readiness tracking for MF6's switch during the
   4.x release candidates (see "MF6's test suite").
9. **Docs:** a "Migrating" page that leads with "your code probably
   runs; here's what the warnings mean; `flopy4 migrate` fixes them".

Steps 3–4 alone already make the MF6 test corpus mostly runnable against
flopy4. If that turns out to be enough for MF6's needs, the codemod
becomes a convenience for users, not a prerequisite.

## Rough effort

| step | size |
|---|---|
| 1. classification | 1–2 days, mostly generated |
| 3. bare-list fix | hours |
| 4. runtime aliases | ~1 week, mostly generated `Legacy` entries plus a handful of methods |
| 5–6. table and mechanical codemod | ~1 week |
| 7. reshapes, flags, name tracking | ~1 week |
| 8. corpus scoreboard | a few days, then ongoing tail work |

## Open questions

- Should "accept" aliases stay permanently, or warn eventually? This
  plan says permanently for positional parent, `get_package` /
  `get_model`, `modelgrid`, `exe_name` and loading from a directory;
  they're good API, not leftovers.
- Should the codemod live in flopy4 or in flopy 4.x next to the compat
  layer? In flopy4 for now; it moves with everything else at the merge.
- When a flopy4 change breaks MF6's optional `fp4` jobs, who fixes it,
  and how fast? Still open. It matters more once MF6's build code moves
  to flopy4.

## MF6's test suite

Settled 2026-11-03:

- The round-trip PRs (#3048, #3057, #3067) are worth having for both
  sides: flopy4 gets IO coverage across MF6's corpus, MF6 gets its NetCDF
  input tested. Keep them as they are.
- MF6 will switch its tests' build code to flopy4 eventually: probably
  while flopy 4.x is in release candidates, after MMP and before GA. Not
  before then, because the API (including the Part 1 changes here) is
  still moving.
- Until then, constructor coverage stays on flopy4's side: step 8 runs
  the codemod over a modflow6 checkout in flopy4's CI, and MF6's
  `build_models` stay flopy3.
- When MF6 switches, step 8's scoreboard shows how much of the suite the
  codemod converts cleanly, and the conversion uses the codemod, not
  hand edits.
- For teaching the new style, port a dozen modflow6-examples by hand
  rather than adding flopy4 builds to the autotests.
