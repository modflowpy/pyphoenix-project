# Open follow-ups

Leftover items from finished plans, now in [`archive/`](archive/). Checked against
develop `a6c52c8` (#415) on 2026-10-07, and again against `e0d94b86`
(#489) on 2026-10-19. Each item names the plan it came from. Newer
follow-ups are in [`followups.md`](followups.md).

## Open

- **mypy and field converters** ([`mypy-converter-plan.md`](archive/mypy-converter-plan.md)).
  Listed as done here before, but it never merged: it's draft PR #433
  (`mypy-converters`), and develop has no `flopy4.mypy_plugin`. The PR
  itself asks whether it's worth it. It predates the field functions
  (#463), which changed how converters are declared, so it would need
  rework. Decide: rework or close.

## DFN questions

None open.

## Done

- **One-row list defaults.** The devtools spec now says a list's default
  holds a single row, repeated to fill the list's shape (branch
  `list-default` on the fork, unmerged). flopy4 already does this.
- **Datetime DFN type.** Not adding one: MF6 treats `start_date_time` as an
  opaque label (list file, NetCDF time units) and never parses it. Typing
  it is flopy4's job; the field takes `str`, `from_time()` converts.
- **Load context** ([`load-context-plan.md`](archive/load-context-plan.md), branch `load-context`).
  `LoadContext` carries the workspace, dims, parent and exchange models
  down the load. Paths resolve against the simulation directory, so
  models in subdirectories load, and the load no longer depends on the
  cwd.
- **Exchanges between grids.** An exchange's cellids, and its GNC's,
  each take their own model's grid width (DIS–DISV etc.), from the
  models the exchange connects.
- **Which model a cellid column refers to.** The DFNs now say it
  (devtools `cellid: true | "1" | "2"`). Codegen emits it as the
  column's `cellid` metadata, `LoadContext.ncelldim` reads it, and
  `Exchange.cellid_models` is gone. (branch `followups`)
- **Time-series names.** Writing a package checks that every name in a
  time-series column (aux and keystring rows included) is defined by
  one of its `Ts` children, as `_check_tas_refs` does for TAS.
  (branch `followups`)
- **Pyright on mixin `self` types.** Pyright 1.1.414 accepts the mixins'
  `self: "X"` annotations, and call sites resolve (`Dis().to_grid()` is a
  `StructuredGrid`). Pyright reports at the `cls` line, not the `def`
  line, so `Tdis.from_timestamps`'s wrapped signature needed a
  `# pyright: ignore` there too. (branch `followups`)
- **SFR period `CROSS_SECTION TAB6 FILEIN`.** The table is an `Sfrtab`
  child, as in `CROSSSECTIONS`. Codegen follows file links into keystring
  arms; period rows load their children once per file, and the children
  walk includes them. It's the only DFN with a file in a period row.
  (branch `sfr-cross-section`)
- **Time series from data.** Decided against accepting a series in a
  time-series column (it widens column types, and built and loaded
  models would differ). Instead, `Ts.from_series` builds a TS6 file from
  a DataFrame, a named Series or a mapping, and `Ts.to_dataframe` gives
  the series back. (branch `ts-from-series`)
- **TS6/TAS6 attributes from plain values.** `Ts(time_series_name=["a"])`
  kept the list, so the writer dropped `ATTRIBUTES` and the name checks
  raised. Single-value records now convert (`Record.from_value`). The TS
  and TAS checks share their name lookup. (branch `followups`)
- **Record fields from plain values** ([`record-values-plan.md`](archive/record-values-plan.md)). Every
  record field converts through `Record.convert` (a bool, the file's
  text, a tuple, a mapping, or a lone value), replacing `from_flag` and
  `from_value`; anything else raises at construction or assignment, and
  the writer raises on a record field holding a non-record.
  (branch `record-convert`)
- **Orphaned `pts.py`.** MF6 removed `sln-pts.dfn` (modflow6 #2912);
  the module and its codegen test entry are gone. It was the only
  generated file with no DFN. (branch `remove-pts`)
- **Dimension providers from DFN scopes** (branch `dims-from-schema`).
  devtools #375 gives each dim a scope. A component with model- or
  simulation-scoped dims gets `DimsProviderMethods` and `shared_dims`
  from codegen, not a hand-kept list; `get_dims` gives only those (DISU's
  `njas` stays its own). `DerivedDim` uses devtools' `dim_value` (#383)
  and flopy4's evaluator is gone.
- **Dimension sync after construction** (branch `dims-from-schema`).
  #407 synced dims on `get_dims`/`resolve_dims`/`write`; assigning a
  dimension that disagrees with its list's rows now raises too. Reading
  the attribute right after an in-place append is still stale until a
  sync.
