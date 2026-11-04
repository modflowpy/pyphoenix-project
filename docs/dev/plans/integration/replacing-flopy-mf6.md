# Integrating flopy4 into flopy

How hard it will be to replace flopy's mf6 engine with this project's, and
how to go about it. Covers discussions #68 (rollout), #35 (MF6 versions)
and #37 (refactoring 3.x), and issue #113 (flopy3 interfaces).

Facts are against pyphoenix `develop` (`8d25e4b7`) and flopy `develop`
(`aca52382`, 3.13.0.dev0, after 3.12.0); benchmark numbers are from
2026-10-28.

## Summary

- **The surgery is smaller than it looks.** Everything flopy4 needs from
  flopy outside `flopy/mf6` (grids, `ModelTime`, `MfGrdFile`, plotting and
  export through `ModelInterface`/`PackageInterface`) it already imports
  from flopy3 and uses today. The old engine touches the rest of flopy at
  about a dozen places, all known (listed below). What's hard is the
  user-facing API, not the code layout.
- **Don't put the new engine into 3.x**, in place of the old one or beside
  it. The new required dependencies and the Python cap break
  3.x users in a minor release, and the API differences are about
  behaviour, not just names, so adapters can't hide them. Use 3.x instead
  to make the swap cheap (see "3.x work").
- **In 4.x, move the old engine, don't delete it.** Put the new engine at
  `flopy.mf6`, the old one, frozen, at a legacy path (e.g.
  `flopy.mf6.legacy`), and add a thin compatibility layer for the common
  flopy3 idioms. The compat layer either behaves exactly as flopy3 did or
  raises an error naming the replacement. It never gets close and moves on.
- **Tests: re-point, don't rewrite.** The old engine's own tests move with
  it to the legacy path, unchanged. The shared-code tests (grids, plot,
  export, binary files, modpath) must pass against both engines. The
  flopy3 mf6 tests also run against the compat layer as a scoreboard,
  allowed to fail, to measure it. flopy4's ~1190 tests come over as the new
  engine's own suite. The release gate is whether the same models produce
  the same heads and budgets, not whether old tests pass.
- **The best test corpus isn't in flopy.** MF6's autotests (420 files) and
  modflow6-examples (76 scripts) use the flopy3 mf6 API more, and more
  typically, than flopy's own tests. They compare simulation results, and
  MF6's CI is where flopy's versioning hurts most. Make them the
  acceptance tests for the compat layer and for version decoupling.
- **Keep the 4.x branch short.** Finish the core here, upstream every
  change that isn't the swap itself to `develop`, and only then cut the
  branch, once MMP feedback has settled the API. Merge `develop` into it
  weekly.
- **Release shape** (see [`mmp-plan.md`](../../mmp-plan.md)). Alphas and betas, up to and including MMP, ship from this repo as
  `flopy4`, installed from GitHub, so testers can run both engines side by
  side. The 4.x branch ships release candidates `flopy==4.0.0rcN` (pip
  skips pre-releases unless asked), and GA is the last of them.

## Where we stand

### flopy

| | lines of Python |
|---|---|
| `flopy/` | 195k |
| `flopy/mf6/` | 80k |
| `flopy/mf6/modflow/` (generated classes) | 42k |
| `flopy/mf6/` handwritten (data layer, base classes, utils) | 38k |

Where the old engine reaches outside `flopy/mf6`:

- `flopy/plot/map.py`, `crosssection.py`, `plotutil.py`: on
  `p.parent.version == "mf6"`, read `pkg.stress_period_data.array[kper]`,
  `pkg.packagedata.array`, `pkg.connectiondata.array` (recarrays with a
  `cellid` field) and `pkg.package_type`.
- `flopy/modpath/mp7.py`: `isinstance(flowmodel, MFModel)`, `model_type`,
  `get_package("DIS")`, `model_ws`.
- `flopy/utils/gridgen.py`: imports `ModflowGwfdis` to build DIS packages.
- `flopy/utils/binaryfile/reverse.py`: `MFSimulation`, `ModflowTdis`.
- `flopy/discretization/{structured,vertex,unstructured}grid.py`,
  `flopy/utils/zonbud.py`: import `MfGrdFile` from
  `flopy/mf6/utils/binarygrid_util.py`. It doesn't depend on the engine;
  it's just stored in the mf6 directory.

Inside `flopy/mf6/utils`, the modules that work without the engine
(`binarygrid_util`, `mfsimlistfile`, `postprocessing`, `lakpak_utils`,
`mfenums`) can move out of the directory. The ones that need it
(`model_splitter` (4175 lines, 109 references to engine internals),
`output_util`, `mfobservation`, `testutils`, codegen) can't.

### flopy4

- Already a flopy3 client: `flopy4.mf6.adapters.Flopy3Model` /
  `Flopy3Package` implement `ModelInterface`/`PackageInterface` (with
  `.array`) to reuse flopy3's plotting and export. Since #531 that covers
  stress-period list data (fill-forward, aux columns, duplicate cells
  summed or averaged as flopy3 does), `to_geodataframe`, `get_package` by
  name or type, and a grid for every discretization type. Not wrapped:
  packagedata/connectiondata, which only flopy3's `plot_bc` reads for
  SFR/LAK/MAW/UZF. `to_grid()` returns flopy3 grids, and the output
  readers use flopy3 grids. One upstream TODO is open:
  `flopy4/adapters.py:27` (`StructuredGrid` `ia`/`ja`).
- Loads 260 of the 261 models in the devtools registry (`KNOWN_PASSING`
  in `test/mf6/test_mf6_load_all_models.py`; the rest are `xfail`). As of
  2026-10-28 it loaded faster than flopy3 on 127 of the 165 benchmark
  models (median flopy4/flopy3 time ratio 0.44), and slower on large
  inline arrays.
- Not done yet ([`test.md`](../../test.md)): running a model written by flopy3
  and by flopy4 and comparing the results, round-trip tests over the
  corpus, and porting the flopy3 autotests and MF6 examples.
- 1190 test functions (2157 collected with parameters).

### API distance: constructors

flopy3 and flopy4 have 100 component classes in common, with 1101 flopy3
constructor keywords between them (leaving out flopy3 plumbing like
`loading_package` and `pname`):

| | count |
|---|---|
| same name in flopy4 | 836 (76%) |
| `*_filerecord` / `*printrecord` → `*_file` / `*print` | 106 |
| `timeseries` / `timearrayseries` / `observations` → `ts` / `tas` / `obs` children | 66 |
| `dev_*` options (flopy4 codegen leaves them out unless `developmode`) | 36 |
| `maxbound` (derived in flopy4) | 12 |
| `parent_*` (flopy3 plumbing) | 12 |
| other (`perioddata`, `packagedata` on DIS, nam `packages`/`list`, IMS `rcloserecord`, TS records…) | 33 |

Only 20 classes match exactly, but nearly every difference follows a rule
a generator can apply. `LegacyKwargs` (`flopy4/mf6/legacy.py`) already
does this for period data. The constructor gap can be closed with
generated code.

### API distance: everything else

Running a flopy3 quickstart against flopy4:

| flopy3 idiom | flopy4 |
|---|---|
| `MFSimulation(sim_name=, sim_ws=, exe_name=)` | `Simulation(name=, workspace=)` |
| `ModflowGwfdis(gwf, ...)`: the parent positional | `Dis(parent=gwf, ...)`: keyword only |
| `ModflowGwf(sim, modelname=)` | `Gwf(parent=sim, name=)` |
| `stress_period_data=[...]` (a bare list for period 0) | raises (`'list' object has no attribute 'items'`). [`migrating.md`](../../../migrating.md) says a list means period 0, so this looks like a bug. |
| `sim.write_simulation()` / `run_simulation()` | `write()` / `run()` |
| `gwf.modelgrid` | `gwf.grid` |
| `gwf.get_package("chd")`, `sim.get_model()` | `gwf["chd0"]` (`Flopy3Model` has `get_package`) |
| `gwf.output.head()` → `HeadFile` | `gwf.output.head` → `DataArray`, a property. **Same name, different kind of thing.** |
| `npf.k.array`, `.get_data()`, `.set_data()` | `npf.k` is the value itself (a `float` here) |
| `gwf.plot()`, `pkg.export()` | via `Flopy3Model` |
| default filenames `m.chd`, `m_0.chd`, `s.ims` | `m.chd0.chd`, `m.chd1.chd`, `s.ims0.ims` |

Top-level methods are cheap to alias. The data layer is not: flopy3's
`MFArray`/`MFList`/`MFTransientList` objects (storage modes, external
file management, `DataStorageType`, `lazy_io`, `use_pandas`,
`set_record`, `mfstructure` introspection) are an API in themselves, and
reimplementing them on top of flopy4 means rewriting flopy3. Same for
`model_splitter`.

### Who uses the flopy3 mf6 API, and how

| corpus | size | most-used beyond constructors |
|---|---|---|
| flopy `autotest` | 948 tests; 552 in the 41 files touching `flopy.mf6` | `test_mf6.py` and `regression/test_mf6.py` use the data layer heavily; the shared-code tests mostly use mf6 to build fixtures |
| MF6 `autotest` | 420 of 453 test files | `register_ims_package` (340), `modelgrid` (109), `get_model` (86), `output.*` (78), `write_simulation` (77), `MFSimulation.load` (51 files), `run_simulation`, `get_package`; `set_data`/`simulation_data` in only 14 files |
| modflow6-examples | 76 scripts | `.array`, `.get_data()` (partly on `HeadFile`), `output.*`, `simulation_data` (17) |

MF6's tests are mostly "build it with constructors, run it, read
`output`, compare". That's the subset a compat layer can cover exactly.
MF6 also regenerates flopy's classes from its own DFNs (`pixi run
update-flopy`), with `dev_*` options, which is the version coupling #35
wants to remove.

### Dependencies and platforms

| | flopy 3.x | flopy4 |
|---|---|---|
| required | numpy, matplotlib, pandas | + attrs, cattrs, jinja2, lark, xarray*, xugrid (`==0.15.3`), scipy, sparse, pydantic, modflow-devtools (git) |
| numpy | `>=2.2.0` (3.13.0.dev0; `>=1.20.3` through 3.12.0) | `>=2.3.4,<2.6` |
| Python | `>=3.12` (3.13.0.dev0; `>=3.11` through 3.12.0), 3.14 tested | `>=3.11,<3.14` |
| devtools | `>=1.7,<2` (codegen/test), `modflow_devtools.dfn` | unreleased 1.10.0.dev1 from git (PyPI has 1.9.2), `modflow_devtools.dfns` (marked experimental), DFN schema `2.0.0.dev3` |

\* through xugrid; xarray is listed as optional, but `attrs_xarray` and
the array fields need it.

## Question 1: the new engine in 3.x?

**Replacing the old engine: no.** Even with adapters:

- **Dependencies.** Ten or so new required packages, an exact pin, a
  dependency installed from git, and Python 3.14 dropped. (Since flopy
  raised its own floors to Python 3.12 and numpy 2.2, the numpy floor is
  only a minor version apart.) Any one of these breaks
  environments on `pip install -U flopy`, conda-forge and locked-down
  sites especially. In a minor release that breaks semver in spirit, if
  not in letter.
- **Behaviour.** The data layer is where flopy3 scripts live, and its
  semantics (mutable data objects, storage modes, external-file control,
  recarray views) aren't the new design's. An adapter that comes close
  is worse than one that fails: it writes different files and moves on.
- **Files written.** Default names differ, and the formatting differs.
  PEST workflows (pyemu `PstFrom`, hand-made templates) and scripts that
  open input files by name depend on the exact layout.
- **Downstream.** `model_splitter`, pyemu and modflow-setup are built on
  the old internals.

**Shipping it beside the old engine (e.g. `flopy.mf6next` under an
extra): possible, but not recommended.** It gets the new engine to users
early, with no long-lived branch. But it puts code that's still changing
fast on 3.x's release schedule and compatibility promises, means both
engines in every 3.x maintenance release, and needs a second namespace
switch at 4.0. `flopy4` betas from this repo get it to users just as
early, with none of that.

### 3.x work

This is what makes the 4.x swap mechanical. All of it lands on flopy
`develop`, and none of it needs the new engine. It takes up #37's
refactoring list where it helps the swap.

1. **Move engine-agnostic utilities out of `flopy/mf6`.** Move
   `binarygrid_util`, `mfsimlistfile`, `postprocessing`, `lakpak_utils`
   and `mfenums` to e.g. `flopy/utils/mf6/`, with re-exports at the old
   paths. Then `flopy/mf6` holds only the engine and can be moved
   wholesale.
2. **A small neutral protocol for shared code.** Replace the
   `version == "mf6"` branches in plot/modpath with a few methods that
   flopy3's mf6 classes implement now and flopy4's natively later: e.g.
   `boundary_cellids(kper)`, `period_records(kper)` (a recarray or
   DataFrame), `get_dis()`, `model_ws`. Same for `gridgen` (build a
   generic grid spec, not a `ModflowGwfdis`) and `binaryfile/reverse.py`
   (read TDIS with a small reader). This is #113's question, answered on
   the flopy3 side.
3. **Upstream what flopy4 patches**: `StructuredGrid` `ia`/`ja`, and
   anything else the adapters subclass.
4. **Deprecate in 3.x what 4.x won't have**, with warnings that point to
   the replacement: `DataStorageType`, `lazy_io`, `use_pandas`,
   `ExtFileAction` and fine-grained external-file control, `mfstructure`
   introspection, `set_record`, and so on, as was done for `check` (#2357).
   Users see the warnings for a release or two before anything breaks.
5. **Optionally, accept 4.x idioms in 3.x**: `parent=` as a keyword,
   `sim.write()`/`sim.run()`, the `stress_period_data` names (the inverse
   of `legacy.py`), and `*_file` for `*_filerecord`. Then users can write
   code that runs on both, and migrate before they upgrade. It's cheap
   for constructor keywords and top-level methods (codegen templates);
   values are out of scope.
6. **Release modflow-devtools** with both `dfn` (for 3.x) and a stable
   `dfns`, and settle the DFN schema version. This blocks any flopy
   release that includes the new engine.

## Question 2: how to do the replacement

### Layout in 4.x

```
flopy/
  mf6/              <- this project's flopy4/mf6 (generated + handwritten)
    compat/         <- generated flopy3 names: ModflowGwfdis, MFSimulation, ...
    legacy/         <- 3.x's flopy/mf6, frozen (git mv, history kept)
  _core/ or similar <- flopy4's top-level modules (uio, spec, dimensions,
                       attrs_xarray, mixins, protocols) and flopy4/adapters.py
  discretization/, plot/, export/, utils/, modpath/, ...  <- unchanged
```

- `flopy.mf6.ModflowGwfdis` etc. stay importable, served from `compat`.
- `import flopy.mf6.legacy as mf6` gets the old engine back exactly, for
  code that uses the data layer or `model_splitter`. This is TensorFlow's
  `tf.compat.v1`. Freeze it at the last 3.x DFNs: it doesn't follow sync,
  and users who need newer MF6 features migrate. Remove it in 5.0, or
  after a set number of minors.
- The legacy path also means that if pyemu and modflow-setup lag, users
  have a way out: they can switch an import instead of pinning
  `flopy<4`.
- Rename imports (`flopy4.` → `flopy.`) with a script, not by hand. The
  generated modules are regenerated, not edited.
- `flopy4` depends on `flopy>=3.9.5` today. After the merge those are
  ordinary internal imports.

### The compat layer

Generated from the DFNs alongside the classes (so `sync` keeps it
current), plus handwritten pieces for Simulation and Model.
[`aliases-and-codemod.md`](aliases-and-codemod.md) moves most of this into flopy4 itself, as
runtime aliases before MMP. What's left for the 4.x compat layer is the
generated `ModflowXxx` names, and whatever the migration plan classifies
as compat-only.

- **Constructors.** A `ModflowXxx` subclass or factory per component:
  the parent positional, the keyword renames in the table above, flopy3
  value shapes (`head_filerecord="m.hds"`, `saverecord=`, a bare list for
  period 0). It produces a real flopy4 object. `legacy.py` is the
  pattern to extend.
- **Simulation/Model methods**: `write_simulation`, `run_simulation`
  (returning `(success, buff)`), `MFSimulation.load(sim_ws=...)`,
  `get_model`, `get_package`, `register_ims_package`, `modelgrid`,
  `model_ws`, `set_sim_path`, `name_file`. These are mostly aliases.
- **Data access is the hard part.** flopy3's `npf.k` is an object with
  `.array`/`.get_data()`; flopy4's is the value. Either:
  (a) don't support it: `.array` on a value raises with a hint (`npf.k`
  is the array now); or (b) compat classes return a small read-only view
  with `.array`/`.get_data(kper)`. The new classes stay clean, but then
  the same package behaves differently depending on which class built
  it. Probably (a) plus the legacy path, but the scoreboard numbers
  should decide.
- **`gwf.output.head()`**: `head` is a `DataArray` property in flopy4 and
  a method returning `HeadFile` in flopy3. Something callable that also
  acts as a DataArray is possible but too clever. Rename one side (e.g.
  flopy4's `output.head` → `output.heads`, or `output.head()` returning
  the DataArray) so compat can keep the old name.
- **Rule**: same result or a clear error. Every compat class or method
  warns (`FutureWarning`, once per call site) and links to
  [`migrating.md`](../../../migrating.md). The migration plan refines this for the aliases
  in flopy4: "accept" forms don't warn, "deprecate" forms warn with the
  same `FutureWarning`.

### Tests

| tier | what | in 4.x |
|---|---|---|
| A. shared code | grid, plot, export, binary files, gridintersect, modpath, zonbud, utils (~400 tests that never touch mf6, plus the shared-code tests that use mf6 for fixtures) | must pass. Run the mf6 fixtures through both engines (a fixture parameter) |
| B. old engine internals | `test_mf6_set_data_*`, `max_columns`, `header_preservation`, `DataStorageType`, external-file and `lazy_io` tests, `model_splitter`, much of `test_mf6.py` / `regression/test_mf6.py` | re-point to `flopy.mf6.legacy` (an import rewrite); they protect the frozen engine |
| C. compat scoreboard | tier B's end-to-end tests (build/load → write → run → compare), MF6 autotests, modflow6-examples, all against `flopy.mf6` compat | report, don't gate: an `xfail(strict=False)` manifest like `test_mf6_load_all_models.py`. A test that starts passing gets pinned |
| D. new engine | this repo's ~1190 tests, benchmarks | move in, must pass |
| E. equivalence | every registry model: load/write/run with legacy and with new, compare heads and budgets; also compare written input files after normalization (by the option labels, [`layout-logical-decisions.md`](../dfn-spec/layout-logical-decisions.md) "Track A") | **the gate for MMP, and again for 4.0** |

The flopy tests aren't so tied to the old engine that they need
rewriting. They split cleanly, and the ones that are tied (B) should
stay tied, to the legacy path. Tier C, the old tests against the compat
layer, is what #113 suggested ("get all the old tests and examples").
It's useful as measurement, but shouldn't be what decides the release:
a red test there means the compat layer needs work or we should document
a break.

Start E here, before the branch: it's the open item in
[`test.md`](../../test.md), and it finds engine bugs, which the compat layer
can't fix.

## MF6 versions in 4.x

The swap is what makes #35 possible: 3.x can't decouple, because its
classes are generated into the package and regenerating them is a
developer step.

- A 4.x release ships classes synced to the latest MF6 release.
  `flopy mf6 sync <version|develop|path>` regenerates them, plus the
  compat classes (they're generated too, so they're in
  `GENERATED_FILES`). [`mf6-versions.md`](../../../mf6-versions.md) comes over as is, renamed.
- The legacy engine is frozen and doesn't sync. Say so in its docs.
- **MF6's CI** replaces `update-flopy` (`generate_classes --dfnpath ...`)
  with `flopy mf6 sync doc/mf6io/mf6ivar/dfn --developmode`. Sync
  leaves out `dev_*` options by default, which MF6's tests use (36 of
  them in the constructor table); `--developmode` (#522) keeps them. This
  is the first real user of decoupling, and the best test of it.
- `sync` writes into site-packages. That's fine for 4.0. Revisit the
  per-user directory ([`user-dir-classes.md`](../components/user-dir-classes.md)) once `mf6 --spec`
  lands, as that plan says.
- `Simulation.run`'s version check comes over unchanged. Compat's
  `run_simulation` gets it too.

## Order of work

**Phase 0 (here, through MMP):**

1. Fix the bare-list `stress_period_data` bug (open on `8d25e4b7`).
2. Equivalence harness (tier E) over the registry, starting with the
   models that both load.
3. Release modflow-devtools (3.x item 6); drop the git dependency; unpin
   xugrid, or pin it as a range; support Python 3.14; drop 3.11 to match
   flopy, or keep it; decide the numpy
   floor (4.0 can require numpy 2).
4. Settle the open API questions that the compat layer depends on:
   `output.head`, `get_package`/`modelgrid` on Model, `name` vs
   `sim_name`.
5. Survey pyemu, modflow-setup and the MF6 repo's scripts for which
   flopy3 mf6 internals they use, to decide what goes in compat versus
   the legacy path.
6. Shrink the flopy3 gap in flopy4 itself ([`aliases-and-codemod.md`](aliases-and-codemod.md):
   runtime aliases growing out of `flopy4/mf6/legacy.py`, the shared
   generated table, the `flopy4 migrate` codemod), and run its corpus
   scoreboard against MF6's autotests and the examples from here.
   Neither needs flopy's repo. The generated `ModflowXxx` names wait for
   the compat layer in Phase 2.
7. Release `flopy4` alphas and betas from GitHub. MMP is the last beta.

**Phase 1 (flopy `develop`, 3.x):** items 1 to 5 from "3.x work" (item 6,
the devtools release, is in Phase 0). Each is a normal PR and releasable
on its own.

**Phase 2 (cut `4.x` from `develop`, after MMP):**

1. `git mv flopy/mf6 flopy/mf6/legacy` (or wherever it goes), fix the
   imports, rewrite tier B's imports. CI green with only the old engine.
2. Bring flopy4 in (scripted rename) as `flopy.mf6`, with its tests
   (tier D). CI green.
3. Implement the shared-code protocol (from 3.x item 2) for flopy4. Run
   tier A against both engines.
4. Bring the compat layer over (the `ModflowXxx` names, on top of the
   aliases already in flopy4) and start the tier C scoreboard: flopy's
   own tests, plus the MF6 autotests and examples unchanged. Phase 0's
   scoreboard measured the aliases and the codemod, not the compat layer.
5. Release candidates `4.0.0rc1…` once tiers A and D are green on
   `4.x`, from PyPI and conda-forge.

Merge `develop` into `4.x` weekly. Phase 1 keeps conflicts away from
anything but `flopy/mf6`.

**Phase 3:** 4.0 GA, the last release candidate. Cut `v3.x` from `develop` for maintenance and make
`4.x` the new `develop`. Then 3.x gets fixes only, for a fixed time
(map.md says "limited"; pick a date and announce it at 4.0).

## Critical path

The phases above are an order for each piece of work, not one queue. Most
of Phases 0 and 1 can run at the same time.

### Parallel tracks

Start them all at once. Letters match [`mmp-plan.md`](../../mmp-plan.md), which also
has the MMP-only tracks (B to E):

| track | where | items | needed by |
|---|---|---|---|
| **A. Engine correctness** | here | bare-list bug, equivalence harness (tier E), then fixing what it finds | MMP. Longest and least predictable, so first |
| **G. Packaging** | devtools, here | devtools release, drop the git dependency, xugrid range, Python 3.14, numpy floor | the first release candidate (GitHub installs don't need it) |
| **F. 3.x prep** | flopy `develop` | 3.x items 1 to 5 | items 1 and 2 by the branch cut; items 3 to 5 can land later and merge into `4.x` weekly |
| **Questions and survey** | team | open questions, downstream survey | question 3 by MMP; 1, 2 and 6 by the branch cut; the rest as below |

### Before MMP

Tracked in [`mmp-plan.md`](../../mmp-plan.md). From this plan: tier E passes on the
registry corpus, question 3 (`output.head`) is settled and implemented,
since testers write code against it, and the migration scoreboard
([`aliases-and-codemod.md`](aliases-and-codemod.md) step 8) runs from here.

### Before cutting `4.x`

- MMP released, and its feedback worked through.
- Question 2 (compat data access) settled and implemented.
- 3.x item 1 merged: engine-agnostic utilities out of `flopy/mf6` (the
  legacy move depends on it).
- 3.x item 2 merged: the shared-code protocol, implemented by flopy3's
  mf6 classes (Phase 2 step 3 depends on it).
- Question 1: legacy engine or not, and its namespace (Phase 2 step 1).
- Question 6: where flopy4's top-level modules go (Phase 2 step 2).
- Equivalence harness running in CI here, so its results carry over. It
  doesn't have to pass yet.

### Before the first release candidate (`4.0.0rc1`)

- modflow-devtools released, and flopy4 depending on it from PyPI. PyPI
  rejects direct-URL (git) dependencies, so this is a hard blocker.
- xugrid pinned to a range; Python range matching flopy's (`>=3.12`, 3.14
  included).
- Tiers A and D green on `4.x`, and tier E still passing there.
- Tier C scoreboard running on `4.x` with flopy's tests added, so the
  release notes can say how much of the flopy3 API compat covers.
- Downstream survey done, sorted into compat vs. legacy-only.
- MF6's CI running against `4.x` with `flopy mf6 sync --developmode`, at
  least as a non-blocking job.

### Before GA

- 3.x item 4 (deprecations) shipped in a 3.x release, ideally two
  releases before 4.0, so users see the warnings first.
- Question 7 (3.x support window) settled and announced with 4.0.

### The longest chain

Equivalence harness → engine fixes → tier E passes → MMP → API settled →
`4.x` cut → release candidates → GA. The other tracks are shorter and
should finish inside it.

## Sizing

Rough, from the inventory above. "Small" is days, "medium" is weeks,
"large" is a month or more for one person.

| item | size | why |
|---|---|---|
| move engine-agnostic utils out, re-export | small | imports only |
| shared-code protocol (plot, mp7, gridgen, reverse) | medium | about 10 call sites, plus tests |
| 3.x deprecations | small–medium | warnings plus docs |
| 3.x forward-compatible keywords | medium | codegen templates, and 3.x's own tests |
| devtools release, dependency cleanup, Python 3.14 | medium | xugrid and numpy floors may cascade |
| equivalence harness | medium to build; fixing what it finds is open-ended | the biggest unknown |
| legacy move and import rewrite | small | mechanical |
| flopy4 move-in | small–medium | renames and packaging, plus CI time |
| compat constructors (generated) | medium | rules known, 76% free |
| compat Simulation/Model methods | small–medium | mostly aliases |
| compat data access | unknown until decided | (a) small, (b) large |
| MF6 CI switch to sync | small (`developmode` sync exists, #522) | |
| `model_splitter` for the new engine | large | 4175 lines on old internals; legacy-only in 4.0 is fine |

The risks are in the engine itself: whether flopy4 writes models that
run and give the same answers across the whole corpus (tier E). The code
move isn't a risk.

## Open questions

1. Legacy engine in 4.x: whether, its namespace, and how long it stays.
   Probably `flopy.mf6.legacy`, until 5.0.
2. Compat data access: (a) raise with a hint, or (b) views.
3. `output.head`: which side renames.
4. Whether to accept 4.x keywords in 3.x (3.x item 5).
5. numpy floor and Python range for 4.0. flopy `develop` is at Python
   `>=3.12` and numpy `>=2.2`; the question is whether flopy4 needs more
   than that.
6. Where flopy4's top-level modules (`uio`, `spec`, `dimensions`, ...) go:
   `flopy._core`, or under `flopy.mf6` if nothing else will use them.
   NFR-4 (one API for MF6 and older MODFLOW programs) says somewhere
   shared.
7. How long 3.x is maintained after 4.0.
