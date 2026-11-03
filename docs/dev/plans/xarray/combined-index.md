# Combined grid index: rebuilding on `CellIndex`

Status: **deferred.** Revisit if DISV needs its own index anyway (see
[`package.md`](package.md), "xugrid").

`flopy4/mf6/indexes.py`, an early xarray index prototype, was deleted in
#510. This covers what it would take to bring back a combined index on top
of `CellIndex`, and how that compares to what we do now. It
builds on [`rotated-grid-index.md`](rotated-grid-index.md) ("Why not an index (yet)"), which
already prototyped a z index.

## What `indexes.py` did

- `alias(ds, "nlay", "lay")`: a `PandasIndex` over `RangeIndex(n)`, giving a
  dim named after its size (`nlay`) a label coordinate (`lay`). This was for
  when array dims were `nlay`/`nrow`/`ncol`/`nper`.
- `MetaIndex`: wraps several indexes as one. `create_variables` and `sel`
  delegate to each child and merge the results with `merge_sel_results`.
- `grid_index`/`time_index`: build those for `lay`/`row`/`col` and `kper`.

None of it is needed now. Dims are `layer`/`row`/`col` (#469), and selecting
by position is `isel`. It also doesn't fit the current xarray `Index` API:
`from_variables` has no keyword-only `options`, and it returns a dict
instead of an `Index`.

The thing to take from it is the shape, one index delegating to child
indexes, not the code.

## Why a plain meta-index adds nothing today

`MetaIndex.sel` asks each child separately and merges what they return.
xarray already does exactly that across separate indexes. `da.sel(x=..., y=...)`
sends `x` to the `CellIndex` on `col` and `y` to the one on `row`, then merges
the two dim indexers. Wrapping the two `CellIndex`es in a `MetaIndex` would
behave the same, with more code.

A combined index only helps when the children **depend on each other**: one
label's answer depends on what another label chose. On a DIS grid, z is the
case that needs it. The layer containing z depends on which `(row, col)` x/y
picked (see the `ZIndex` prototype in [`rotated-grid-index.md`](rotated-grid-index.md)). Merging
independent answers gives wrong results for scalar x/y and raises
`IndexError` for lists.

So "rebuild the combined index" really means a **`GridIndex` owning `x`,
`y`, and optionally `z`/`z_top`/`z_bot`**, which answers all three labels in
one `sel` call.

## What a `GridIndex` on `CellIndex` would need

### Structure

- `class GridIndex(xr.Index)` holding:
  - `xindex: CellIndex | None` (on `col`)
  - `yindex: CellIndex | None` (on `row`)
  - `z_top`/`z_bot`: `Variable`s on `(layer, row, col)`, or `None` for
    arrays without z (1-layer arrays, RCHA/EVTA; see [`rch-evt-layer.md`](rch-evt-layer.md)).
  - `z` (centres), which it owns so that `sel(z=...)` reaches it, but which
    it answers by containment over the bounds, not by centre.
- Composition, not inheritance: x and y keep all their behaviour from
  `CellIndex`, and `GridIndex` delegates per dim, as `MetaIndex` did.

### Methods

- **`from_variables(cls, variables, *, options)`**: build the children with
  `CellIndex.from_variables({"x": ...}, options={"bounds": options["x_bounds"]})`
  and the same for y. Keep z bounds as variables. Accept any subset of the
  coordinates.
- **`create_variables`**: the children's variables, plus `z`/`z_top`/`z_bot`
  wrapped as index variables.
- **`sel(labels, method=None, tolerance=None)`**, the reason this exists:
  1. Split `labels` into x, y and z.
  2. Ask `xindex.sel`/`yindex.sel` for the `col`/`row` indexers. They handle
     containment, edge ties, slices and `method="nearest"` as now.
  3. If z is given: `isel` the z bounds by those indexers, then call
     `vertical.layer_at(z, z_top_sel, z_bot_sel)` to get the layer per chosen
     vertical column. Raise `KeyError` where no layer contains z, to match
     `.grid.sel`.
  4. Return one `IndexSelResult`. For points (DataArray labels sharing a
     dim), all three indexers are vectorized over the points dim. For scalar
     x/y with scalar z, they're ints. For z alone, `layer` is a `(row, col)`
     indexer (the horizontal slice, as `sel_z`).
  - `method`/`tolerance` apply to x/y only. z is always containment, as now.
- **`isel(indexers)`**:
  - Delegate `col`/`row` to the children.
  - `isel` the z bounds on `layer`/`row`/`col`.
  - When a dim becomes scalar, drop that part and keep the rest. This is the
    main thing to verify: with one index across three dims, returning `None`
    drops the **whole** index, so `isel(layer=0)` would also lose x/y
    selection. Prototype what xarray does when `isel` returns an index that
    no longer owns some of its coordinates.
- **`join`/`reindex_like`/`equals`**: delegate per dim to the children
  (keeps #486's edge checks), and compare the z bounds.
- **`concat`**:
  - Along `col`/`row`: delegate.
  - Along `layer`: concatenate the z bounds.
  - Along anything else (e.g. `time`): the index is unchanged.
- **`roll`, `__getitem__`, `_replace`, `copy`, `__repr__`**, pickling: as
  `CellIndex` does.

### Wiring

- `index_xy` sets one `GridIndex` with
  `obj.set_xindex(["x", "y", "z", "z_top", "z_bot"], GridIndex, x_bounds=..., y_bounds=...)`
  instead of two `CellIndex`es, falling back to x/y only when z isn't there.
- `CellIndex` stays, as the child and for any 1-D-only use.
- `.grid.sel(..., z=...)` and `sel_world(x, y, z)` keep working. They can
  move to plain `sel` once it gives the same answers.
- Reopening from netCDF drops the index either way. `index_xy` rebuilds it
  (rotated-grid plan, Next item 2).

### Tests

- Re-run every `CellIndex` test (`test/mf6/test_mf6_component.py`, around
  `:2686`) against `GridIndex`: containment, ties, outside → `KeyError`,
  slices, nearest, align/concat edges, roll.
- Then add:
  - `sel(z=)` alone vs `sel_z`
  - `sel(x=, y=, z=)` vs `.grid.sel` for scalars and point DataArrays
  - `isel(layer=k)` then `sel(x=, y=)`
  - arrays without z
  - chunked (dask) arrays
- Pin xarray. Multi-coordinate custom indexes and `IndexSelResult` are
  public but still changing.

### Rough size

`CellIndex` is about 130 lines, because most of an `Index` subclass is
keeping state right through `isel`/`join`/`concat`/`roll`. A `GridIndex`
that delegates x/y is probably 150–250 more, mostly the z bookkeeping, plus a
test file of about the same size as `CellIndex`'s. DISV isn't covered: it has
no `CellIndex`, and horizontal containment there goes through xugrid.

## Current approach vs a custom combined index

**Current:** one `CellIndex` per horizontal coordinate. z, world coordinates
and their combinations are free functions in `utils/grid.py` and
`utils/vertical.py`, on the `.grid` accessor.

| | Current (per-coordinate `CellIndex` + accessor) | Combined `GridIndex` |
|---|---|---|
| x/y containment | `da.sel(x=, y=)` | Same |
| z | `.grid.sel(z=)`, `.grid.sel_z`, `.grid.mask_z`; `da.sel(z=)` raises `KeyError` | `da.sel(z=)` and `da.sel(x=, y=, z=)` |
| World coordinates on a rotated grid | `.grid.sel_world`, which converts and then calls `sel` | Unchanged; still an accessor function (world x/y aren't 1-D) |
| Discoverability | Users have to know `.grid` exists (covered in the selection guide) | Plain `sel`, what xarray users try first |
| Code to maintain | `CellIndex` plus small functions over plain coordinates | `CellIndex` plus a three-dim index whose state must survive every xarray operation |
| Behaviour through `isel`/`concat`/`align`/arithmetic | z coordinates are unindexed, so xarray handles them as ordinary coordinates; nothing to get wrong | Every operation goes through our code; partial `isel` across three dims is the risk |
| xarray API exposure | One-dim `PandasIndex` subclass (fairly stable) | Multi-coordinate custom `Index` (experimental, evolving) |
| Failure modes | A missing accessor call gives a clear `KeyError: no index for 'z'` | A bookkeeping bug gives silently wrong cells |
| Arrays without z, DISV | Same functions, branch on what's present | Needs an "x/y only" mode; DISV still separate |
| netCDF round trip | `index_xy` re-attaches the indexes | Same |
| Capability | Everything | Nothing new; a nicer spelling of the same selections |

**Recommendation:** keep the current approach. A combined index only adds
the `da.sel(z=...)` spelling, and in exchange takes on the hardest part of
custom xarray indexes: keeping state right across several dims through
partial `isel`. Revisit it if:

- users ask for plain `sel(z=...)`; or
- the DISV/xugrid work ends up needing its own index anyway, so one design
  can cover both; or
- xarray settles its multi-coordinate index API (and ideally gains a
  documented way to keep part of an index through `isel`).

Unrelated to the index design: `alias` was 0-based (`RangeIndex(n)`), the
same as `isel` now. Keep selection 0-based everywhere and convert only at
the MF6 file boundary. One 1-based exception already exists:
`StructuredGrid.to_xarray` gives `layer` a 1..nlay coordinate
(`utils/grid.py:504`, and `:657`, `:1171`), so `ds.sel(layer=1)` there means
`isel(layer=0)`. This is the file boundary, not an exception: those
datasets are what `NetCDFModel` writes as MF6 netCDF input. They match
MF6's own netCDF export, which defines a `layer` int variable of `1..nlay`
with the same attrs (`DisNCStructured.f90`, `DisNCMesh.f90`, `DisvNCMesh.f90`,
modflow6 @ 48f34498f3). Keep it.

Bug found along the way: `vertical.sel_z` replaces `layer` with the chosen
**positions** (`vertical.py:99`). On a dataset with 1-based `layer` labels
(e.g. MF6 netCDF output opened with `xr.open_dataset`), the result's
`layer` is off by one: selecting z in the second layer returns its value
with `layer=1`. It should keep the labels when `layer` has them
(`obj[dim].values[idx]`), and positions only when it has none.
