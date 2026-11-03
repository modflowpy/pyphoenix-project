# Evaluate time-array series in the period view

Status: ready, not started (rechecked 2026-10-19 against develop `e0d94b86`:
no `Tas.average`, `step_array` or `dense_steps` yet; `period_array`,
`period_arrays.dense` and `_check_tas_refs` are where the plan expects).
Since written, #489 marks series values `NaN` in the xarray view with the
series name in a `<name>_tas` coordinate; a step view could fill those.
Written 2026-10-07, against develop `a6c52c8`. MF6 semantics checked
in `../modflow6` (`src/Utilities/TimeSeries/TimeArraySeries.f90`,
`TimeArraySeriesManager.f90`). Decisions are under "Decisions".

## Problem

A period array (RCHA's `recharge`, EVTA's, SPCA's) can come from a
time-array series: `recharge={0: TimeArraySeriesRef("rch")}`.
`Package.period_array()` and `period_arrays.dense()` raise on these
because they can't compute the values. So anything that wants the values
in effect can't use a model that has them: plots, adapters, and analysis.

## What's available

- The series is already loaded with the reference. RCHA, EVTA and SPCA
  have `tas: list[Tas]` children (`TAS6 FILEIN`), and each `Tas` holds
  `time_series_name`, `interpolation_method`, `sfac` and
  `tas_array: {time: array}`.
- `Package._check_tas_refs` already matches references to series by name.
- `Time` (`flopy4/mf6/utils/time.py`, a flopy `ModelTime`) gives each
  step's end time as `totim`; a step starts at the previous one's end, or
  at 0. `Simulation.time` builds it from TDIS.

## MF6 semantics (checked)

- **Only STEPWISE and LINEAR.** `tas_init` rejects anything else
  ("Unknown interpolation method"). The DFN (`utl-tas.dfn`) lists
  `linearend` as valid, but MF6 doesn't accept it for array series.
- **Evaluated once per time step, as an average.** `tasmgr_ad` calls
  `GetAverageValues(begintime=totimc, endtime=totimc+delt)`. That is the
  integral of the interpolant over the step, divided by `delt`. A
  zero-length step takes the value at that time.
  - **STEPWISE:** the integrand holds each array until the next time. If
    a series time falls inside a step, the step gets the time-weighted
    mix of both arrays, not the value at the step's start.
  - **LINEAR:** the integrand interpolates linearly between times, so the
    step gets the trapezoid average.
- **SFAC is applied when the array is read**, so it scales every value.
- **Series times are simulation time** (`totim`), starting at 0.
- **Coverage:**
  - If the series ends before a step ends, MF6 stops with "Error
    encountered while performing integration". This is true for STEPWISE
    too.
  - If the step starts before the series' first time,
    `get_latest_preceding_node` finds no record, and the integral stays
    zero with no error. The step gets zeros.

## Design

1. **`TimeArraySeriesRef.resolve(package) -> Tas`** finds the series by
   name (case-insensitive) among `package.tas`, and raises as
   `_check_tas_refs` does if none matches. The reference stays a name;
   resolving it when used keeps it valid if `tas` is edited.
2. **`Tas.average(t0, t1) -> np.ndarray`** gives MF6's step value: the
   integral of the interpolant over `[t0, t1]` divided by `t1 - t0`, or
   the value at `t0` when they're equal. SFAC is applied.
   - It lives in a method-only mixin (`TasMethods`, listed in `MIXINS`),
     with the integration as plain functions so they can be tested on
     their own.
   - It raises if the series ends before `t1`, as MF6 does.
   - It returns zeros with a warning if `t0` is before the first time.
     MF6 does this silently; the warning flags what's likely an input
     mistake.
   - It raises on a method other than STEPWISE or LINEAR, naming the
     method.
3. **A step view, as its own method.** `Package.step_array(name,
   time=None)` returns `(nstp_total, ...)`: one array per time step, the
   values MF6 applies.
   - Plain period arrays repeat their period's value across its steps,
     with carry-forward as today.
   - A period given by a reference is evaluated per step with
     `Tas.average`. A reference carried forward keeps being evaluated at
     each later step.
   - Aux arrays work the same way, per name: `{name: (nstp_total, ...)}`,
     as `period_array` gives `{name: (nper, ...)}`.
   - Values stay in input units, as in `period_array`. MF6 also converts
     RCH/EVT fluxes to flows (cell area) and applies `auxmultname` after
     substitution. The view does neither.
4. **The period view is unchanged.** `period_array` keeps its signature
   and its `(nper, ...)` shape. A period from a time-array series has no
   single value in MF6, so it still raises for one. The error now points
   to `step_array`. No averaged or derived value is invented.
5. **Where the time steps come from.** `step_array` takes an optional
   `time: Time`.
   - Without it, the package finds TDIS through its parents (the
     simulation's `tdis`) if it's attached to one.
   - Pass `time` for a package that isn't attached.
   - Raise if both are present, so it's never ambiguous which time
     discretization applies.
   - Raise if neither is present.
6. **`period_arrays.dense_steps()`**, next to `dense()`, takes the step
   bounds and a resolver (a callable from a reference to a `Tas`).
   `dense()` keeps raising on references.
7. **NetCDF export is a non-goal.** Exported files keep the reference in
   the package file, since MF6 reads the series itself.

## Steps

1. Add `Tas.average` and its integration functions. Unit tests against
   hand-worked values:
   - STEPWISE and LINEAR over a step that lies within one interval;
   - a step spanning a series time (the mix for STEPWISE, piecewise
     trapezoids for LINEAR);
   - a zero-length step;
   - SFAC;
   - the series ending early (raises), and starting late (zeros, warns);
   - an unsupported method (raises).
2. Add `TimeArraySeriesRef.resolve`, and have `_check_tas_refs` use it.
3. Add the time lookup (`time=` or TDIS through the parents, raising on
   both or on neither).
4. Add `dense_steps` and `Package.step_array`, aux included. Update the
   period view's error message.
5. **Test against MF6:**
   - Run test027 (`TimeseriesTest`), read the RCH budget per step from
     the CBC file, and compare it with `step_array("recharge")` times
     cell area.
   - Add a small synthetic model per method with a series time inside a
     multi-step period, so the STEPWISE mix is exercised.
   - Cover an aux array from a series, and SPCA's `concentration`, in
     the unit tests. MF6's budget doesn't show aux, so these aren't
     compared against a run.
6. **Upstream:** report that `utl-tas.dfn` lists `linearend`, which MF6
   rejects for array series. Either the DFN or the Fortran should change.

## Decisions

- **Time source:** the package's TDIS if it's attached to a simulation,
  or an explicit `time`. Both present raises.
- **No period average.** The step view gives MF6's values. The period
  view gives exact values or raises; it never returns a derived summary.
- **Aux and SPCA are in scope.** MF6 accepts a series for RCHA
  `recharge`/`aux`, EVTA `rate`/`aux` and SPCA
  `concentration`/`temperature` (the DFNs' `time_series true`; aux
  through `aux_tasnames` in `Mf6FileLayerArray.f90`). flopy4 already
  types all of them `... | TimeArraySeriesRef`, and `split_tas` already
  handles aux. EVTA `surface`/`depth` can't come from a series.
- **A separate `step_array`, not a `by=` keyword.** A keyword would make
  `period_array`'s shape depend on an argument, and `time=` would apply
  to only one of its modes.
- **Warn on zeros before the series starts.** MF6 is silent; the warning
  is flopy4's addition, since it most likely marks an input mistake.

## Follow-on: time series in period lists

Not started (added 2026-10-18). The same gap exists for TS6 in list-based
packages. A row value can come from a series, `TimeSeriesRef("headseries")`,
and `to_xarray` holds it as NaN, with the series name in the `<name>_ts`
coordinate. So the values in effect aren't available for these either. This
follows the TAS work and reuses its time lookup (design 5) and step
bounds.

MF6 semantics (checked in `TimeSeries.f90` and `TimeSeriesManager.f90`):

- **STEPWISE, LINEAR and LINEAREND.** Unlike TAS, LINEAREND is accepted.
  STEPWISE and LINEAR give the step average, as with TAS. LINEAREND gives
  the value at the step's end (`get_value_at_time(time1)`).
- **Per-series method and SFAC.** `METHODS`/`SFACS` set them per name, and
  `METHOD`/`SFAC` set them for all names. SFAC is applied when each record
  is read.
- **DNODATA in a TS file is a gap.** That record is skipped for that series
  only, so the series interpolates across it.
- **Names are case-insensitive** (`UPCASE` on lookup).
- **No extension past the end.** `extendTsToEndOfSimulation` defaults to
  false, and no package sets it. A series that ends before a step ends is
  an error, as with TAS.
- **Aux values can come from a series too** (`auxvarTsLinks`), so the
  evaluation covers aux columns.

Sketch:

1. `TimeSeriesRef.resolve(package) -> (Ts, index)` finds the series among
   `package.ts` by name. It shares the name lookup with the TS name check.
2. `Ts.average(name, t0, t1) -> float` gives MF6's step value for one
   series, reusing the TAS integration functions on scalars, with
   LINEAREND added.
3. A step view of a period list, with one value per step for each row
   given by a series. Rows with plain values repeat their period's value,
   as `step_array` does. Whether this is a dense per-step dataset or rows
   per step is open. It should match whatever `step_array` settles on.
4. The period view is unchanged, as for TAS (design 4).
5. Test against test027 and the test001e TS models' CBC budgets per step.
