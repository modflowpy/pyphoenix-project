# Cellid arrays: what changes for flopy4

modflow-devtools branch `cellid-node-arrays` (wpbonelli fork)
changes how every cellid column is represented in the dev2/dev3 DFN spec. Not
yet merged upstream. flopy4 depends on `modflow-devtools` from MODFLOW-ORG
`main` (`pyproject.toml`), so nothing changes here until it merges. To try it
earlier, install that branch into the env, after which `LocalDfnRegistry`
migrates v1 DFNs with the new rules. This replaces the locally patched spec
that put `node` on `cellidsj`.

## The schema change

There's now one encoding for a cellid:

```
Array(dtype="integer", shape=["ncelldim", ...], index=True, cellid=True)
```

- The first shape axis is always `ncelldim`: one cellid's components (3 for DIS,
  2 for DISV, 1 for DISU). Shapes list the fastest-varying axis first, as grid
  arrays already do (`botm` is `["ncol", "nrow", "nlay"]`).
- Any further axes count cellids. These columns are still written inline on the
  row, one cellid after another.
- `Integer.node` is **removed**. The attribute is now `cellid`, on `Array` only,
  and requires integer dtype, `index=True`, a leading `ncelldim`, and a
  list-item context.
- The leading `ncelldim` isn't resolved as a dim in the component's scope. Its
  value depends on the grid the column refers to. Exchanges don't see
  `ncelldim` at all, since their parent is the simulation.

| column | before | after |
|---|---|---|
| stress `cellid`, HFB `cellid1`/`cellid2`, CSUB, PRP, ... | `Array(shape=["ncelldim"])` | same, plus `index`, `cellid` |
| exchange `cellidm1`/`cellidm2` | `Integer(index, node)` | `Array(shape=["ncelldim"], index, cellid)` |
| GNC `cellidn`/`cellidm` | `Integer(index, node)` | `Array(shape=["ncelldim"], index, cellid)` |
| GNC `cellidsj` | `Array(shape=["numalphaj"], index)` | `Array(shape=["ncelldim", "numalphaj"], index, cellid)` |

44 components change. Every stress-package `cellid` gains `index` and `cellid`;
the exchanges and GNC change type.

## What happens in flopy4

From reading the code. Not yet run against the branch.

### Breaks: GNC `cellidsj` (codegen `filters.py` and `make.py`)

Even with cellid detection fixed (next section), the column-role chain in
`make.py` (~L227-256) only treats a 1-element shape as
`counted`. `cellidsj` now has a 2-element shape, so it falls through to
`elif col.is_cellid` and becomes `role="cellid"` with
`shape="ncelldim,numalphaj"`. In other words, it's read as **one** cellid. The
generated `gwf/gnc.py`, now
`cellidsj: ... = field(array=True, cellid=True, count="numalphaj")`, would
regress. The GNC tests in `test/mf6/test_mf6_codec.py` (~L420-443) should catch
it.

Fix: for a `cellid` column, use `shape[1:]` as the count shape. If it's empty,
the column is one cellid (`role="cellid"`). If it's one dim, the column is
`role="counted"` with `count=shape[1]` and `cellid=True`, i.e. the existing
counted-cellid path, unchanged downstream. Read and write (`item.py`
`from_tokens`/`to_tokens`, `cellid` + `array` metadata) already handle a
counted cellid column.

### Breaks: cellid detection (`filters.py` `_fields_to_columns`, ~L952)

```python
is_cellid=(isinstance(col, Array) and list(col.shape or []) == ["ncelldim"])
or bool(getattr(col, "node", False)),
```

The shape check still catches the single cellids, which are now `["ncelldim"]`
arrays. But the `node` fallback matches nothing now, so `cellidsj` (shape
`["ncelldim", "numalphaj"]`) is **not detected as a cellid at all**. It has to
become `isinstance(col, Array) and col.cellid`, which covers every cellid. The
`getattr` and its comment ("only Integer has `node` yet") go away, and
`ColumnSpec.is_cellid`'s comment needs updating. This fix has to land together
with the `make.py` fix above, or `cellidsj` falls through to a non-cellid role.

### Unaffected

- **`index` on cellid columns.** It's newly set, but `is_cellid` is checked
  before `is_index` in `make.py`, and `cellid` metadata is checked before
  `index` in `item.py`. So there's no double 1-based offset. Worth a quick look
  at any other place that reads `is_index` without checking `is_cellid` first.
- **Stress packages.** Their shape didn't change, so their generated classes
  should come out the same.
- **ncelldim inference** (`item.ncelldim_from_dims` / `infer_ncelldim`) is
  unchanged. Cellid width is still taken from the grid at read time.

### Still open (not addressed by this change)

- **Exchanges** (`EXG_TIER` in `test_mf6_codegen.py` excludes gwfgwf etc.).
  Their cellid columns now look like any other cellid, which helps. But each
  column needs its own model's `ncelldim`, and the spec still doesn't say which
  model a column refers to. flopy4 has to hard-code it: in `exg-*`, `cellidm1`
  is model 1 and `cellidm2` is model 2. In GNC under an exchange, `cellidn` and
  `cellidsj` are model 1 and `cellidm` is model 2. A later schema addition
  (e.g. `cellid: "1" | "2"`) may make this explicit.
- **PRP** (`test_prt_basic` docstring). PRP's `cellid` column is a plain
  `["ncelldim"]` cellid in a list item, now marked `cellid`. The
  "(nreleasepts, ncelldim)" limitation is flopy4-side, and this change doesn't
  touch it.
- **Multi-dimensional inline arrays.** `cellidsj` is the first array with more
  than one dimension inside a list item. Other code that assumes inline arrays
  are 1-D (e.g. `len(shape) == 1` checks) should be audited, not just the role
  chain.

## Checklist after the devtools change lands

1. Bump or refresh `modflow-devtools`, then regenerate (`make.py`).
2. Switch `is_cellid` to `Array.cellid` (required, not optional), and drop the
   stale `getattr`/comments.
3. Fix the `make.py` role chain for `cellid` arrays (count from `shape[1:]`).
4. Diff the regenerated packages. Only `gwf/gnc.py`, and the exchange classes
   if generated, should change. Anything else is unexpected.
5. Run the codec/codegen tests, especially GNC.
6. Drop the locally patched spec.
