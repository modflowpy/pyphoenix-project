# DISV: status after #391

Re-evaluated against `origin/develop` at `98f53b9` (2026-10-02). #391 ("generate
dis packages") did the work this plan proposed, so there is nothing left to
plan for the core fix.

## What #391 delivered (verified)

- `Disv` (gwf/gwt/gwe/prt) is generated from the DFNs; `DisBase` is gone.
- Stored data matches the DFN: `vertices: list[Vertices]`, `cell2d:
  list[Cell2d]`. No duplicate `iv/xv/yv` arrays or `cell2ddata`.
- Indices are stored 0-based and renumbered at the I/O boundary: `Item` now
  handles an index *array* (`icvert`, `array=True, index=True`) and a count
  column (`ncvert`, `count="ncvert"`), which was the `Item` extension I had
  proposed.
- Methods live in mixins (`DisvMethods`, `GridDimsMethods`), registered like
  `TdisMethods`; derived dimensions use the new `DerivedDim` descriptor; the NCF
  child is a `subpackage(file_field="ncf_file")`, which was the blocker I had
  flagged for the mixin approach.
- The original bugs are fixed. On `develop`: write a `Disv`, `Disv.load` it, and
  `to_grid()` works, re-writing keeps the `CELL2D` block, and `vertices`/`cell2d`
  round-trip.

## What is still open

1. **Equality across a round trip.** A hand-built `Disv` and the same grid
   loaded from its written file compare unequal. The only differing field is
   `cell2d`: built `Cell2d(ncvert=None)` vs loaded `Cell2d(ncvert=3)`.
   `ncvert` is a count column derived from `len(icvert)`, so it shouldn't be an
   independent stored value. Options: normalize `ncvert` in post-init (or a
   converter) to `len(icvert)`; or exclude it from comparison with `eq=False`.
   I'd normalize it so the stored value is always consistent.
2. **Dropped API.** `iv=`, `xv=`, `yv=` and `cell2ddata=` constructor inputs,
   the read-only `iv/xv/yv` views, and `Cell2dRecord` no longer exist. If you
   want any of them back for convenience, it's a small addition to
   `DisvMethods`. Otherwise this is a deliberate break and worth noting in
   release notes.
3. **Array-equality branch conflicts.** `fix/array-equality` conflicts with
   `develop` in `spec.py` and the four `disv.py` files (`merge-tree` check). The
   `disv.py` edits (`eq=ARRAY_EQ` on `iv/xv/yv`) are obsolete (those fields are
   gone) and should be dropped; `spec.py` needs a manual merge. After the rebase
   I need to re-check that every array field still has `shape` metadata
   (#391 flattened shapes and changed arrays to `IntArrayLike`/`FloatArrayLike`),
   since the default comparer keys on it.
4. **#380 (draft)** still edits the four `disv.py` files and adds `Cell2d` /
   derive-on-load code that #391 supersedes; it needs a substantial rebase or
   a rewrite of its DISV parts. It also adds `grb_filerecord` to DIS/DISV;
   #391 already renamed these to `*_file`.
5. **Structured `Dis`/`Disu`** were generated in the same PR, so the earlier
   "do `Dis` as a follow-up" question is moot.

## Status (2026-10-05)

- Item 1 (`ncvert` equality): `fix/disv-ncvert` fills count columns from the
  array they count, and keeps them in step on reassignment (`on_setattr` hook
  from `spec.field(count=...)`). Counts that name a package dimension
  (GNC, EVT) are skipped. Pushed; no PR yet.
- Item 2 (dropped API): `fix/disv-legacy-api` restores `iv`/`xv`/`yv`/
  `cell2ddata` inputs (via a metaclass on `DisvMethods`), read-only views and
  `Cell2dRecord`. Pushed; no PR yet. The views are read-only.
- Item 3 (array equality): merged as #394; `fix/array-equality` is obsolete.
- Item 4 (#380): still needs a rebase or rewrite of its DISV parts.
- Not started: reconcile list-length dimensions (`nvert`, `ncpl`, `nper`) from
  row counts at `get_dims()` and write time, since mutating a list can't
  trigger an `on_setattr` hook.
