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
step 4 of [`record-unify.md`](../lists/record-unify.md).

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
- **Editing:** warn when an edit shifts positions that MVR or SPC rows refer to
  in that period: inserting, deleting or reordering rows, or changing a grid
  package's active cells.

Small to medium.

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

## mypy and field converters

From [`mypy-converter-plan.md`](../archive/mypy-converter-plan.md). This
never merged: it's draft PR #433 (`mypy-converters`), which is still open,
and develop has no `flopy4.mypy_plugin`. The PR itself asks whether it's
worth doing. It predates the field functions (#463), which changed how
converters are declared, so it would need rework. Decide whether to rework
it or close it.
