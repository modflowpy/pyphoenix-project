# Datetime period keys (#518), then `create_tdis` (#226)

Status: **in progress** (#518, #226).

## Goal

Let period-keyed package data (fill-forward fields: CHD/WEL/... lists,
RCHA/WELG/... arrays, OC) be keyed by datetimes as well as 0-based period
indices, e.g.

```python
chd = Chd(stress_period_data={
    "2000-01-01": [((0, 0, 0), 1.0)],
    pd.Timestamp("2000-03-01"): [((0, 0, 0), 2.0)],
})
```

and then let a simulation build its TDIS from the datetimes its packages use
(imod-python's `create_time_discretization`), the time half of #226.

## Current state

- `Package._check_periods()` (`flopy4/mf6/package.py`, run from
  `Package.write`) raises on any non-integer, negative, or >= NPER period
  key. Before it, a datetime key was silently dropped on write, and keys
  past NPER were written as PERIOD blocks MF6 never reads.
- Keys are stored as given; nothing normalizes them at construction.
- `Tdis.from_timestamps` / `Time.from_timestamps` build a TDIS from N
  timestamps -> N-1 periods (the last timestamp is the end time).
- `Tdis.start_date_time` is an ISO string; `time_units` may be None.

## Design

**Keep datetime keys as given, resolve to period indices late.** TDIS stays
the one source of truth for what period n means. `create_tdis` doesn't
rewrite package keys; it only builds a TDIS that the keys line up with.
Datetime keys therefore also work without `create_tdis`, against a
hand-built TDIS with `start_date_time` set.

### Key normalization (construction / reassignment)

- Accept `datetime.datetime`, `datetime.date`, `np.datetime64`,
  `pd.Timestamp`, and ISO strings; normalize all to `pd.Timestamp` (a
  sortable, hashable, `==`-sane type with nanosecond precision).
- Integers (`int`, `np.integer`, not `bool`) stay as `int`.
- Strings: parse with `pd.Timestamp`; reject digit-only strings (`"0"`,
  `"3"`) with an error rather than guess between "period 0" and a date.
- **No mixing** ints and datetimes within one package (all its
  fill-forward fields together, e.g. RIVG's stage/cond/rbot), raising at
  construction. Fill-forward order and "which period is first" are
  ambiguous otherwise. Different packages in one simulation may differ.
- Hook: wherever fill-forward dicts are coerced, i.e. `_coerce_list_field`
  (lists, `PeriodRows`) and `_init_period_arrays` (arrays, including the
  dense `(nper, ...)` split in `period_arrays.split_periods`, which already
  produces ints). One helper, e.g. `period_arrays.normalize_period_key`.
- Audit `int(kper)` casts (`period_arrays.py:182`) so a datetime can never
  be coerced to an integer silently.

### Resolution against TDIS

- New `Tdis.period_index(t) -> int` (in `TdisMethods`), and a vectorized
  `period_starts() -> pd.DatetimeIndex`: `start_date_time` plus the
  cumulative sum of `perlen` in `time_units`.
- Errors when: `start_date_time` is unset; `time_units` is None/"unknown";
  `t` isn't exactly a period start (say which periods it falls between);
  `t` is at or after the end of the last period. "years" is 365.25 days
  (check against MF6 docs before committing to that).
- `Package._period_index(key) -> int`: ints pass through; datetimes go
  through the TDIS found via the package's parent chain (the simulation).
  No TDIS reachable -> error naming the package and key.

### Write path

- `_check_periods` widens: datetimes are valid iff they resolve via
  `_period_index`; then the existing negative / >= NPER checks apply to
  the resolved index.
- `_unstructure_package` (`converter/egress/unstructure.py`) maps every
  fill-forward key through `value._period_index` before collecting into
  `spd_period` / `readarray_period`, so the `kper + 1` block numbering and
  sort are on ints. Two datetime keys resolving to the same period (only
  possible with sub-second differences) -> error.
- `external.py` names external files `_p{kper + 1}`; it must see the
  resolved index too.
- `_normalize_kper`'s `"*"` wildcard is unreachable after the write-time
  check (nothing produces it); delete it in this change.

### `Simulation.create_tdis` (#226)

```python
sim.create_tdis(end="2001-01-01", nstp=1, tsmult=1.0)
```

- Collect datetime keys from every package in every model (and exchanges),
  plus `end`, and build `self.tdis = Tdis.from_timestamps(...)` with
  `time_units="days"`, `start_date_time` = earliest key.
- `end` is required (keys give period starts only), must be after the
  latest key.
- Integer-keyed packages are allowed alongside but contribute no times;
  warn if the resulting NPER is below one past their largest key, since
  their meaning changes with the new TDIS.
- Optionally accept extra `times=` to split periods with no stress change
  (imod allows this, e.g. for output timing).
- Time-series (TS6/TAS6) times are numeric offsets from simulation start,
  not period keys; out of scope.

### Dense / xarray views (follow-up)

`Package.period_array`, `period_lists` dense tables and `to_xarray` derive
NPER from `resolve_dims("nper")` or `max(keys) + 1` and sort keys. With
datetime keys:

- with a TDIS: resolve keys to indices first, then as today; optionally add
  a `time` coordinate from `period_starts()`;
- without: sort the timestamps and index them 0..n-1, `time` coordinate
  from the keys.

Separate PR; the write path doesn't depend on it.

## Steps

1. Key normalization + no-mixing check, with construction tests (each
   accepted type, digit-only string rejected, mixed keys rejected).
2. `Tdis.period_starts` / `period_index`, with unit tests (units, off-grid
   date, past end, missing start date).
3. Write-path resolution (`_period_index`, `_check_periods`,
   `_unstructure_package`, external file naming), drop the `"*"` wildcard.
   Tests: datetime-keyed CHD and RCHA write the same files as their
   int-keyed equivalents; off-grid and no-TDIS cases raise.
4. `Simulation.create_tdis`, with tests mirroring the imod 1D transport
   example (packages first, TDIS last), and an mf6 run of one example if
   the binary is available.
5. Follow-up PR: dense / xarray views with datetime keys.
6. Docs: a short example in the user guide; update #226 / #518.

## Open questions

- `datetime.date` vs `datetime.datetime`: treat a date as midnight?
  (Probably yes, as pandas does.)
- Should `create_tdis` also be callable on a model-free basis
  (`Tdis.from_packages(*pkgs, end=...)`), with the simulation method as a
  wrapper? Useful for tests and for building one TDIS for several sims.
- Round-trip: a loaded simulation always has int keys. Do we ever want to
  offer "re-key by date" (`pkg.with_datetime_keys()`)? Not needed now.
