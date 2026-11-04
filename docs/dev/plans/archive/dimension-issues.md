# Dimension follow-ups (issue drafts)

Two open dimension items left over from #167 (the data model refactor).
Each section below is written to be pasted as an issue. Checked against
develop `407102d` on 2026-10-08.

**Status (2026-10-19): done except one item; archived.**

- Issue 1 is done (#442, branch `dims-from-schema`): codegen gives
  `DimsProviderMethods` to components with model- or simulation-scoped
  dims (devtools #375), so there's no hand-kept provider list; `Ncf` and
  package-local dims like `maxbound` aren't providers, so they don't
  collide.
- Issue 2: assigning a dimension that disagrees with its rows raises
  (checked on develop `e0d94b86`: `t.nper = 7` and `a.maxats = 1` with two
  rows both raise `ValueError`). Still open: after an in-place append,
  `t.nper` stays stale until `get_dims()`, and the docs don't say so.
  That item moved to [`followups.md`](../followups.md), item 5.

---

## 1. Scope dimension resolution so any package can provide dimensions

### Current state

Dimension resolution (`DimensionResolverMixin` in `flopy4/dimensions.py`)
walks a component's direct children for `DimensionProvider`s, then its
parent, then its own `dims`. Only four classes are providers, each with a
hand-written `get_dims()`: `Dis`, `Disv`, `Disu` (`grid_dims_methods.py`)
and `Tdis` (`tdis_methods.py`). Codegen config lists which classes get
these methods.

Other packages declare DIMENSIONS fields too, but they don't provide them.
Arrays elsewhere that use those dimensions can't resolve them through the
tree.

### Problem

A generic `Package.get_dims()` that returned every DIMENSIONS field would
make every package a provider. `_get_all_dimensions` raises when two
children of one component provide the same name, and several names repeat:

| Dimension  | Declared by                                   |
| ---------- | --------------------------------------------- |
| `maxbound` | `Api`, `Chdg`, `Drng`, `Ghbg`, `Rivg`, `Welg` |
| `nexg`     | `Gwfgwf`, `Gwegwe`, `Gwtgwt`                  |
| `ncpl`     | `Disv`, `Ncf`                                 |
| `nlay`     | `Dis`, `Disv`                                 |
| `nvert`    | `Disv`, `Disu`                                |
| `nrow`/`ncol` | `Dis`, `Laktab`, `Sfrtab`                  |

Some of these are the same quantity declared twice, like `Ncf`'s `ncpl`,
which repeats the grid's. Others share a name but mean different things,
and one model can hold several of them. A model with a `Chdg` and a `Welg`
has two different `maxbound`s, and a `Laktab`'s `nrow` is a table's row
count, not the grid's.

`maxbound` is also a computed property on list packages, not a field, so
it isn't a dimension anyone else uses.

### Options

1. **Provide only dimensions other components use.** Mark a DIMENSIONS
   field as shared (from the DFN, or derived from which other components'
   arrays reference it). Generic `get_dims()` returns only shared
   fields, and the hand-written providers go away. A package-local
   dimension like `maxbound` stays local.
2. **Scope by name.** Qualify a dimension by its provider (`chdg.maxbound`)
   when it isn't one of a known set of model or simulation dimensions.
   This is more general but changes every lookup.
3. **Keep the provider list in codegen config.** This is the status quo.
   It works, but each new provider needs a config entry and a methods
   mixin.

Option 1 seems smallest. The DFN may already say enough: a dimension
another component uses appears in that component's `shape`.

### Done when

- No hand-written provider list. Providers come from the DFNs.
- `Ncf`'s `ncpl` either agrees with the grid's or raises, instead of
  colliding.
- Two same-named package-local dimensions on one model don't raise.

---

## 2. Linked dimensions after construction

### Current state

A list field's row count sets a linked DIMENSIONS field (TDIS
`perioddata` → `nper`, DISV `vertices` → `nvert`, ATS `perioddata` →
`<=maxats`). This happens at construction, in `Package._init_item_lists`.
After that, `Package._sync_dims` updates the dimension, but only when
something reads dimensions (`get_dims()`, writing). Appending to the list
in place doesn't trigger `on_setattr`, so the sync can't happen on the
change itself.

### Problems

Checked on develop with `Tdis` and `Ats`:

1. **The attribute is stale until something calls `get_dims()`.**
   ```python
   t = Tdis(perioddata=[r1, r2])
   t.perioddata.append(r3)
   t.nper          # 2, though there are three rows
   t.get_dims()    # {'nper': 3}, and t.nper is now 3
   ```
2. **Setting an exact dimension is silently thrown away.**
   ```python
   t = Tdis(perioddata=[r1, r2])
   t.nper = 7      # accepted
   t.get_dims()    # {'nper': 2}; t.nper goes back to 2
   ```
   At construction, `Tdis(nper=7, perioddata=[r1, r2])` raises.
   Assignment should behave the same way.
3. **Setting a bounded dimension too low is caught late.**
   ```python
   a = Ats(perioddata=[row, row])
   a.maxats = 1    # accepted
   ...             # raises later, wherever dimensions are next read
   ```
   The error points to the dimension read, not to the assignment.

### Options

- **Check on assignment.** Add an `on_setattr` hook to linked dimension
  fields that checks the value against the current row count, just as
  construction does. Problems 2 and 3 then raise right away. Codegen
  already knows which fields are linked (`dim` metadata on the list field).
- **Make exact dimensions read-only.** An exact linked dimension (like
  `nper`) is always the row count, so it could be a property, not a field
  the user sets. Problems 1 and 2 go away. This changes the constructor
  (`nper=` would only be checked, never stored) and the generated class
  shape.
- **Observable lists.** Item lists notify their package when they change.
  This fixes problem 1 directly, but it's the most machinery, and it brings
  back the proxying that #167 removed.

Checking on assignment, plus reading through `_sync_dims` (or a property)
wherever the attribute is read, covers all three without new list types.

### Done when

- `t.nper = 7` with two rows raises at the assignment.
- `a.maxats = 1` with two rows raises at the assignment.
- `t.nper` matches `len(t.perioddata)` after an in-place append, or the
  docs say it doesn't until the next dimension read.

### Related

- [`list-dim-default-problem.md`](list-dim-default-problem.md): the construction-time half,
  where an explicit value and a default were indistinguishable. That's
  resolved (`dim_default` metadata).
