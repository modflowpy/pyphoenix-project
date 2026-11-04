# Plan: follow-ups after row layout, boundnames, conditional fields

State as of 2026-10-15: flopy4 `origin/develop` at `995ae0c2`. Merged:
#467 (row layout), #469 (grid dims), #471/#472 (tests), #473 (conditional
fields, the DFN `when` attribute), #470 (boundname fixes: `""` -> `None`,
other empty strings rejected, writer raises on empty).

Rules for every item: one branch and PR each, off a fresh `origin/develop`.
Run only targeted tests locally; CI runs the rest. Never push or touch GitHub
unless asked at the time. Local env:
`.pixi/envs/dev/bin/python`, with `PYTHONPATH` pointing at a devtools
checkout if the pinned devtools (`9a1662ef`) lacks something needed.

Suggested order: 1, 3, 2, 4 (1 and 3 are small; 2 and 4 are large).

**Status (2026-10-19, develop `e0d94b86`):** 1 merged as #478, 3 needed
nothing more (see below). Open: 2 and 4. Both touch the row codec that
#479-#484 since rewrote (`read_rows`, `ItemTable`, one number-conversion
point in #484), so the line numbers below are stale; re-find the spots
before starting.

## 1. Boundnames on the `when` mechanism

**Done:** merged as #478 ("use conditional metadata for boundnames").

#473 says "Boundnames move onto the same mechanism after #470". The DFNs
already say it: devtools `9e45471d` gives every boundname column
`when = "boundnames"` (still `optional`). flopy4 ignores that today:

- Codegen: `make.py` `_is_label` branch (~286) emits
  `string(default=None, empty_is_none=True, optional=True)` with no `when`.
  Pass the DFN field's `when` through (as `filters.attr_column` does for
  other columns via `meta["when"]`). Check the devtools pin has `when` on
  boundnames; bump it if not. `pname` (name files) has no `when`, so
  `_is_label` stays for `empty_is_none`.
- `item.py`: drop the boundname special case.
  - `_has_boundname_field` (~126) and the `bn` loop in `solve` (~602-640):
    the boundname becomes an ordinary conditional last field, present iff
    `boundnames` is in `context.enabled`, absent rows allowed (optional).
  - The Python-input fallback that infers a boundname when the option is
    unset (~638) becomes the generic "conditional=False" retry #473 added.
  - `fields = [... if f.name != "boundname"]` (~428) and `_columns`/
    `to_tokens` boundname-last handling (~759-829): check whether position
    alone now covers it.
- `package.py` `_coerce_item_list` (~457): drop `on.add("boundnames")`;
  `conditional_fields` covers it.
- `structure.py` / `RowContext`: the separate `boundnames` flag goes if
  `enabled` carries it (~58-75, ~1067-1164).
- Regenerate; tests: the boundname round trips from #470 and #473's
  conditional tests must pass unchanged.

## 2. Keep number-like text as text (reader refactor)

**Done locally (2026-11-02):** branch `keep-token-text` (commit
`938a67c6`, worktree `.claude/worktrees/keep-token-text`), not pushed.
Tokens stay text in both transformers and NumberRows; `utils.from_text`
converts by field type while structuring.

Problem: the basic transformer
(`flopy4/mf6/codec/reader/transformer/basic.py`, `TOKEN`) turns tokens that
look like numbers into numbers before the schema is known, so an unquoted
obsname or boundname `1.50` reloads as `1.5`. All loading goes through the
basic transformer (`Package.load` passes no component).

Experiment (local branch `token-text`, uncommitted, worktree
`<devtools scratchpad>/wt-token-text`, on old develop `e8f2b939`):
`TOKEN` returning `str(token)` gave ~848 failed / 653 passed / 29 errors:

- dims and option scalars stay strings (`np.full` in
  `package._broadcast_griddata`; count checks at `package.py` ~65;
  `structure.py` ~345 `nodes // nlay`)
- grid data arrays come out as strings
- ~30 parser tests in `test_mf6_codec.py` assert numbers

Fix: keep tokens as text and convert by field type while structuring.

- One conversion point for scalars, keyed on the field's spec type
  (integer, double, string, keyword, union arms by their own rules).
- Arrays: convert in bulk (`np.array(tokens, dtype=...)` / `np.fromstring`
  style) rather than per token, for speed.
- Row items already convert per field in `item.py` `_convert`; make it take
  text and convert there.
- Update the parser tests to expect strings (the parser no longer types).
- The old workaround (`_TextInt`/`_TextFloat`, `parse_number_text`,
  `token_text`) is on local branch `boundname-text-full`, for reference
  only; don't revive it.
- After this, `package.py` ~572's warning about numeric boundnames stays
  (MF6 itself may read them as cells).

Start a fresh branch off develop; the `token-text` experiment is a
one-liner and can be redone.

## 3. Validate lookup-sized widths

**Done.** `Package` checks lookup-sized widths too: `dim_value(...,
select=...)` in `package.py` (~338-360), column-wise for SFR's 10k rows,
reworked in #481.

Already done: `Package._check_lookup_counts` (#392) checks SFR's ic
with `dim_value(..., select=...)` on construction and load
(`test_sfr_ncon_mismatch`). SFR's ic is the only row-level lookup in the
DFNs. Nothing to do.

An inline array sized by a lookup into another block (LAK/MAW/SFR
`connectiondata` `ic` sized by `packagedata.ncon(ifno)`) isn't checked.
The package checks dim-sized widths already (`dim_input`/`dim_value`,
`package.py`). Add devtools' `dim_value(..., select=...)` there, so
`len(ic) == ncon` for that row's `ifno`. First confirm nothing checks it
today, and find every lookup-sized field in the DFNs. Add the lookup to
`RowContext` if the layout needs it (it shouldn't: these are always the
last field, which takes the rest of the row).

## 4. Merge `Item` into `Record`

**Open.** `class Item(Record)` (`item.py` ~931) still overrides the
row codec. Since #479 list rows can also live as columns in `ItemTable`
(`item_table.py`), so the merge has to cover that path too.

Step 4 of [`record-unify.md`](lists/record-unify.md), now unblocked (cellid and row layout are
in). One codec for row and line records: `Item`'s count-sized arrays,
1-based index/cellid, union columns, time series, trailing boundname,
`_columns` order; `Record`'s `convert` plain forms, nested records, tagged
values. `Item` becomes an alias or goes away. Do after 1 (fewer boundname
special cases to carry) and ideally after 2 (one conversion path). Own
branch, full CI.

## 5. Dimensions after an in-place append

From [`dimension-issues.md`](archive/dimension-issues.md) (issue 2). Assigning a dimension that
disagrees with its list's rows raises, but appending to the list in place
doesn't update the dimension until something reads dims:

```python
t = Tdis(perioddata=[(1.0, 1, 1.0), (2.0, 1, 1.0)])
t.perioddata.append(t.perioddata[0])
t.nper         # 2, until t.get_dims(); then 3
```

Either read linked dims through `_sync_dims` (a property, or on attribute
access), or document that they're current only after a dims read
(`get_dims`, `resolve_dims`, writing). Small; decide which first.

## Local cleanup (ask before deleting)

Still present as of 2026-10-19. Many other worktrees under
`.claude/worktrees/` and the session scratchpads are for branches since
merged (`git worktree list`); worth one pass to prune them.

- `token-text` branch and its worktree: superseded by item 2's fresh branch.
- `boundname-text-full`: reference for item 2's old workaround.
- `row-layout` (worktree `.claude/worktrees/field-functions`, local commit
  `dc64fa2d`): its docstring trim landed in #470.
- `boundname-text` worktree (`<pyphoenix scratchpad>/wt-boundname`):
  merged as #470.
