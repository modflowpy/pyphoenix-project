# Backlog

Small open items that don't belong to a live plan, checked against
develop `8d25e4b7`. Earlier lists, with the items since done, are in the
archive: [`followups-after-row-layout.md`](../archive/followups-after-row-layout.md),
[`open-followups.md`](../archive/open-followups.md) and
[`dead-code-audit.md`](../archive/dead-code-audit.md).

## Merge `Item` into `Record`

`class Item(Record)` (`flopy4/mf6/item.py`) still overrides the row codec.
Since #479, list rows can also be stored as columns in `ItemTable`
(`item_table.py`), so the merge has to cover that path too. The design is
in [`record-unify.md`](../lists/record-unify.md).

Merging gives one codec for row and line records. It has to carry over:
- from `Item`: count-sized arrays, 1-based index and cellid, union columns,
  time series, the trailing boundname, `_columns` order;
- from `Record`: the plain forms `convert` accepts, nested records, tagged
  values.

`Item` then becomes an alias or goes away. Large; its own branch, with full
CI.

## Bound references and periods

A list or grid entry's bound number is a position within one period (see
[`overview.md`](../dfn-spec/overview.md#what-can-be-referred-to)), and flopy4
doesn't treat it that way yet:

- **Checks:** `_role_keys` (`flopy4/mf6/keys.py`) checks a `<=dim` key against
  the dimension, or the longest list in any period. An MVR or SPC row that
  names a position with no entry in its own period passes. It should check
  against the referring row's period, once the period's rows can be found.
  It should warn, not raise, as `_check_periods` does for harmless input. From
  reading MF6, not a run, a number is only checked against `maxbound`
  (`Mover.f90`, `prepare`; `check_flow_package` in `TspSpc.f90`), so such a row
  does nothing. A row's own period is the simple check. It misses an MVR row
  carried into a later period where the target has fewer entries, and no check
  can tell that a position now names a different entry.
- **Editing:** warn when an edit shifts positions that MVR or SPC rows refer to
  in that period: inserting, deleting or reordering rows, or changing a grid
  package's active cells. `PeriodRows` sees a whole period being assigned, but
  not an in-place edit of its rows, and grid arrays can be edited in place too.
  So decide first whether this is worth a proxy, or should be a documented
  hazard.

Small to medium, without a proxy.

## Link check for `docs/dev`

From the [plan audit](plan-audit.md#s5-broken-or-stale-references). A check of
relative links and anchors would stop dead ones coming back. It doesn't catch
references to quoted section names or "step N". It needs a home: CI runs only
for `main` and `develop`, ignores `**.md` changes, and `develop` has no
`docs/dev/plans`, so a job there would miss most of the docs. A job on
`dev-plans` or a pre-commit hook would cover them. Small; decide where first.

## Dimensions after an in-place append

From [`dimension-issues.md`](../archive/dimension-issues.md) (issue 2).
Assigning a dimension that disagrees with its list's rows raises. But
appending to the list in place doesn't update the dimension until
something reads dims:

```python
t = Tdis(perioddata=[(1.0, 1, 1.0), (2.0, 1, 1.0)])
t.perioddata.append(t.perioddata[0])
t.nper         # 2, until t.get_dims(); then 3
```

There are two options:
- read linked dims through `_sync_dims`, as a property or on attribute
  access;
- or document that they're current only after a dims read (`get_dims`,
  `resolve_dims`, writing).

Small; decide which first.

## `sel_z` and layer labels

`vertical.sel_z` replaces `layer` with the chosen positions
(`flopy4/mf6/utils/vertical.py:99`). On a dataset with 1-based `layer`
labels (MF6 netCDF output opened with `xr.open_dataset`), the result's
`layer` is off by one. It should keep the labels when `layer` has them
(`obj[dim].values[idx]`), and positions only when it has none. Small.

## flopy3 adapter: lists besides stress period data

From [`dead-code-audit.md`](../archive/dead-code-audit.md). #531 wrapped
stress period data for flopy3's `DataListInterface`, but not `packagedata`
or `connectiondata`, which flopy3's SFR/LAK/MAW/UZF `plot_bc` reads. Do it
here, or through the neutral protocol in flopy3 (3.x item 2 of
[`replacing-flopy-mf6.md`](../integration/replacing-flopy-mf6.md)).

## Record strings drop unknown tokens

A record given as a string keeps the tokens it recognizes and drops the rest,
with no error, so a bad string can switch on a solver option:

```python
Gwf(newtonoptions="garbage").newtonoptions  # Newtonoptions(under_relaxation=None): Newton on
Npf(xt3doptions="garbage").xt3doptions      # Xt3doptions(rhs=None): XT3D on
Npf(rewet="garbage")                        # raises: the token has to fill a float
```

`Record.convert` passes strings to `Record.from_tokens`
(`flopy4/mf6/record.py`). It should raise on tokens it can't place. The file
loader may also use `from_tokens`, so check what it relies on first. Tuples
have a similar gap: `Ts.Sfac.convert(("a", "b"))` keeps strings in a float
array. Small. Do this soon, because it can silently change a model's results.

## Pyright sees constructors as `Any`

`LegacyKwargs.__call__` (`flopy4/mf6/legacy.py`, #503) is typed `-> Any`, and
Pyright uses a metaclass `__call__` in place of `__init__`. So it doesn't check
`Component` constructor calls, and `Npf()` is `Any`. Put `__call__` behind
`if not TYPE_CHECKING:`, and check `_LegacyInputs` in `disv_methods.py` too.

This brings back Pyright's false errors on plain values like
`Npf(rewet=(1.0, 1, 0))`, until the stubs in
[`constructor-stubs.md`](../components/constructor-stubs.md) land. It's step 1
of that plan, and ships ahead of the rest. Small. Do this soon.
