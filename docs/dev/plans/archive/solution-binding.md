# Solution–model binding

How solutions (IMS, EMS) and exchanges are associated with the models they
solve or connect. Fixes #285 (and covers flopy#2355).

## Status

- **PR #496, `solution-models`** (on `develop` 3813b016): solutions hold
  their models. Open.
- **`exchange-models`** (cb41db42, based on `solution-models`): exchanges
  hold their models the same way. Pushed; open its PR against
  `solution-models`, retarget to `develop` once #496 merges.

## Background

- **#285**: support `Ims(models=[gwf])` alongside `Ims(models=["gwf"])`, and
  let the solver take over the models' association with the simulation.
- **flopy#2354 / flopy#2355** (mbakker7): flopy3's
  `sim.register_ims_package(ims, model_list=[gwf.name])` is hard to teach.
  He suggests `ModflowIms(sim, model=gwf)`, or `ModflowIms(model=gwf)` with
  the sim inferred. One solution solving many models is real (LGR,
  parallel, flow + transport), so the relation is many-to-one.
- **The bug**: `Ims(models=[gwf])` was accepted, but `sim.write()` put the
  model's repr in `mfsim.nam`, because `Binding.from_component` wrote
  `tuple(component.models)` unconverted.

## Design, as built

### Reference fields

`Solution.models` (`list[Model | str]`) and `Exchange.exgmnamea` /
`exgmnameb` (`Model | str | None`) are declared with `reference()`
(`metadata={"reference": True}`). A reference field:

- isn't a child field: walkers (`_children`, writing, `to_dict`, parent
  assignment) skip it, so a solution never takes over its models' parent or
  name;
- is stored as model names in xarray, and its repr and eq go by name;
- holds objects or names. Names are resolved at write time,
  case-insensitively as MF6 does, so default names (given on attach) and
  renames are followed for objects. A name doesn't follow a rename.
- A single model is wrapped in a list (`Ims(models=gwf)`).

The simulation owns its models; solutions and exchanges only refer to them,
as `mfsim.nam` does (models declared in MODELS, named again in
SOLUTIONGROUP / EXCHANGES).

### Ways to associate (user's view)

1. **Default**: one solution listing no models solves every model in the
   sim, including ones added later. `Simulation(models=[gwf],
   solutiongroup=[Ims()])`, `Ims(parent=sim)`.
2. **By object**: `Ims(models=[gwf, gwt])`, bottom-up
   (`Simulation(solutiongroup=[ims])`) or top-down (`Ims(parent=sim, ...)`).
3. **By name**: `Ims(models=["flow"])`; the model needn't exist yet. Mixed
   lists work.
4. **Join through models**: `Ims(models=[gwf])` with no parent, where `gwf`
   is already in a sim, joins that sim's `solutiongroup` (at construction).
   Error if the models are in different sims. Exchanges do the same
   (`Component._references_parent`).
5. **Later changes**: `ims.models.append(gwt)`, `ims.models = [...]`,
   `sim.solutiongroup.append(ims)`, `sim["ims0"] = ims`.
6. **Loading**: solutions and exchanges hold the loaded model objects.
7. **Lookup**: `gwf.solution` (read-only, `None` if unsolved or no sim). No
   stored back-pointer and no `Gwf(solution=...)`.

### Write-time checks (`SimulationMethods._solution_models`)

Errors start with "Invalid solution group: ...".

- every model a solution lists is in the sim (catches stale names and
  removed objects);
- every model is solved by exactly one solution; with two or more
  solutions the default doesn't apply, so each must list its models;
- EMS solves PRT only, IMS everything else;
- exchanges: both models present, and of the exchange's model types.

Loading more than one SOLUTIONGROUP is an error (multiple groups aren't
supported; `mxiter` and the hardcoded `SOLUTIONGROUP 1` are unchanged).

### Copying and pickling

- `deepcopy` copies what a component owns and shares what it refers to:
  copying a sim gives a sim whose solutions refer to the copied models;
  copying a lone `Ims` keeps referring to the original models. References
  are resolved after the outermost copy, so order doesn't matter
  (`deepcopy([ims, gwf])` works).
- `pickle` stores references as names; `Simulation.__setstate__` resolves
  them, as loading does.
- `copy.copy` stays shallow.

### Filenames

Solutions use #495's uniform default, `{sim}.{name}.{ext}`
(`sim.ims0.ims`), like any list-field child (`model.wel0.wel`). Decided:
no `{model}.ims` default and no dropping the `0` for a lone solution.

- flopy#2355 doesn't ask for `{model}.ims`. Its `gwf.name + '.ims'` is
  flopy3 code, setting a filename by hand so two solutions' files don't
  collide. What it asks is that flopy take care of the filename, which the
  uniform rule does: names are unique among siblings.
- `{model}.ims` would be the only default based on a reference (which can
  change) rather than the owner, with fallbacks for zero or several models.
- Dropping the `0` would break "once assigned, a name stays": adding a
  second solution would rename the first, or name them inconsistently.
  2cbc0da7 drops the name only when it's the extension (single-child
  fields: `model.dis`), never a list index.

## Done since the first push

- **CI failures on #496** (`test_mf6_sync`, `test_mixin_fields`):
  `SimulationMethods.__setstate__: no Model.lower`. The mixin gap check
  (`flopy4/mf6/_mixin_fields.py`) had two bugs, now fixed (add09054):
  - comprehension variables were bound once per method, so two
    comprehensions using `m` over different fields were conflated. They're
    now scoped to their comprehension (`_scoped`);
  - a field holding a plain type besides components (`list[Model | str]`)
    was checked as if every item were a component. Past such a field
    (`_open`), an attribute only some types have isn't reported.
- **Examples** (0a6d5a23): `period-data` and `selection` pass `models=[gwf]`
  instead of a name, like the other examples.
- **Stale example outputs** (8eb40524): `docs/examples/period-data/` is
  gitignored like the other examples' output dirs, but its outputs had been
  committed and went stale with #495's naming. Untracked them.
- `exchange-models` rebased onto the above (452b9e51) and pushed.

## Open

- **Other model-name fields**, as a separate issue: MVR `mname1` / `mname2`
  (`flopy4/mf6/gwf/mvr.py`) and HPC `partitions` (`flopy4/mf6/utl/hpc.py`).
  The same reference mechanism would apply, but they're inside record/list
  fields, so it's more involved.
- **Comment on #285 / flopy#2355** with the design, to close them (only
  when asked).
