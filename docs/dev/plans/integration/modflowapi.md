# Folding modflowapi into flopy4

Run MF6 in process through XMI from flopy4's own components, with
modflowapi's API, so one tool covers building a simulation and stepping
through it. From the `plan-api` branch (Feb 2026). The full drafts are on
the `dev-plans-full` branch (`modflowapi.md`, `xmi-api.md`).

## The gap

- **modflowapi** ([repo](https://github.com/MODFLOW-ORG/modflowapi)) gives
  runtime access but no construction. `ModflowApi` wraps libmf6 through
  xmipy's `XmiWrapper` (`initialize`/`update`/`finalize`).
  `ApiSimulation.load(mf6)` parses the XMI variable names into
  `ApiSimulation`/`ApiModel`/`ApiPackage` objects.
- **flopy4** builds, writes and loads simulations, and runs them as a
  subprocess (`Simulation.run`), with no runtime access.

```python
# modflowapi today
mf6 = ModflowApi("libmf6", working_directory="./sim")
mf6.initialize()
sim = ApiSimulation.load(mf6)
while not mf6.finalized:
    mf6.update()
    print(sim.kper, sim.models[0].X.max())
mf6.finalize()
```

## Design

- **A plugin subpackage, `flopy4/mf6/xmi/`.** `Simulation`, `Model` and
  `Package` stay free of XMI code. XMI behaviour comes from mixins combined
  with the base classes: `XmiSimulation`, `XmiGwf`, `XmiGwt`, `XmiGwe`,
  `XmiPackage`.
- **Explicit classes, not auto-enhancement.** A user picks `XmiSimulation`
  to get XMI. Turning a plain `Simulation` into one when it runs
  (`sim.run(executor="xmi")`) would be convenient but surprising, and hard
  to type-check. `XmiSimulation.run()` defaults to XMI.
- **Follow modflowapi's API closely.** It's what users already know, and
  what they turned out to need. Stepping is the primary workflow; `run_xmi()`
  (run to the end, with callbacks) is a convenience.
  - **Simulation:** `initialize_xmi(lib_path=None)`, `update()`,
    `finalize()`, `finalized`; time `kper`, `kstp`, `nstp`, `nper`, `totim`,
    `delt`; `model_names`, `models`, `get_model(name)`; solver control
    `iteration` and `allow_convergence` (settable); later solutions,
    exchanges, ATS.
  - **Model:** `kper`/`kstp`/`totim` from the simulation; `shape`, `size`,
    `nodetouser`, `usertonode`; `X`, the solution (heads, concentrations,
    temperatures), readable and settable; `get_package(name)`.
  - **Package:** what modflowapi's `ApiPackage` subclasses expose, e.g. stress
    package values to change between steps.
- **Variables by address.** Components read and write XMI variables by
  address (`SIM/TDIS/KPER`, `GWF_1/X`), caching addresses discovered at
  initialization, which is modflowapi's `ApiSimulation.load` logic.
- **xmipy as an optional extra** (`flopy4[xmi]`), not a required dependency.
- **Same model, two modes.** One loaded simulation can run as a subprocess
  for production and through XMI for debugging or coupling, from the same
  input files and the same engine, so results can be compared directly.

## Phases

- **A. Wrap modflowapi.** Implement the flopy4 API by delegating to
  `ModflowApi`/`ApiSimulation`/`ApiModel`. Ships quickly and pins the API.
- **B. Port to xmipy directly**, with the API unchanged: variable discovery
  first, then simulation and model properties, package access, and solver
  control.
- **C. modflowapi 2.0 wraps flopy4.** `ModflowApi`, `ApiSimulation` and
  `ApiModel` become thin wrappers with deprecation warnings, so existing
  scripts keep working. After a transition (about a year), archive
  modflowapi, its README pointing to flopy4.

Tests: mixins against a mocked XMI; integration against a real libmf6 with
existing MF6 test simulations, comparing heads with subprocess runs; and
modflowapi's own examples, ported.

## Open questions

- Name collisions between XMI properties and fields (`kper`, `X`):
  unprefixed names (natural, need a review), an `xmi_` prefix, or a
  namespace (`sim.xmi.kper`).
- Whether `get_model(name)` returns the tree's model object, enhanced, or a
  wrapper; and whether `sim["gwf"].X` works as well as `get_model`.
- Which package properties need XMI access, following modflowapi's
  `ApiPackage` implementations, and how errors are reported.
- How long the modflowapi compatibility layer lasts, and agreement with
  modflowapi's maintainers (USGS, Deltares) before any of it.
- How this fits the executor abstraction in
  [`python-models.md`](python-models.md), which runs MF6 through
  `sim.run(executor=...)` rather than separate classes.
