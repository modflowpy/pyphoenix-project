# Grid coordinates, rotation and spatial selection

This plan is the current version of two earlier ones:

- **The spatial index design** (`docs/dev/spatial-index-design.md` on `origin/xarray-index`, Nov 2025–Feb 2026), with upstream #207 (structured grid index), #208 (`.grid` accessor) and #120 (closed background). It proposed spatial dims for DIS, a `.grid` accessor, a custom `GeospatialIndex` (from flopy PR 2654), containment-vs-nearest point queries, z and ball queries.
- **The rotated-grid selection plan** (this file's earlier form): local x/y plus a grid mapping for rotated DIS, world coordinates as an overlay.

The "Where the old design stands" section below records what was kept, changed or dropped from the first.

## Framing

Keep the grid geometry pure and treat world coordinates as an overlay:

- Index in the grid's own frame. `x`/`y` are 1-D on `col`/`row`, always indexed, rotated or not.
- The rotation lives in the CRS (or, without one, in grid-mapping metadata), not in the coordinate values.
- World coordinates for a rotated grid are derived, 2-D, auxiliary, and unindexed.

This is the CF `rotated_latitude_longitude` pattern: 1-D `rlon`/`rlat` dimension coordinates in the rotated frame, a `grid_mapping` variable describing the transform, and 2-D `lon`/`lat` auxiliary coordinates.

It's also what MF6 and our own writer already do:

- `DisNCStructured` writes zero-based local x/y for rotated grids. When a CRS is configured, it wraps it in a derived projected CRS (EPSG:9624 affine) encoding xorigin/yorigin/angrot.
- `StructuredGrid._structured_dataset` (`flopy4/mf6/utils/grid.py`) mirrors that, using `wrap_rotated_crs` in `flopy4/mf6/utils/crs.py`.

So "`x`/`y` are coordinates in the grid's CRS" holds everywhere:
- **Unrotated:** the grid CRS is the base CRS, so `x`/`y` are world coordinates (offset by the origin).
- **Rotated:** the grid CRS is the derived CRS, so `x`/`y` are local and zero-based.

No renaming of `x`/`y` is needed.

## Where the old design stands

| Topic | Old design | Now | Status |
|---|---|---|---|
| DIS dims | `x`/`y`/`z` as dims, `col`/`row`/`layer` auxiliary | Reversed: dims `layer`/`row`/`col`, `x`/`y` 1-D indexed coords | Changed (#469). Stock xarray covers it with `set_xindex`. |
| Layer/row/col selection (#207's original ask) | Custom index mapping nodes to l/r/c | Dim names plus `isel` (0-based) | Done (#469). 1-based `sel` by MF6 numbers is still open; see accessor. |
| Rotation | Not covered | Local x/y, `projection` grid mapping, `x_world`/`y_world`, `sel_world` | Done (#485) |
| Custom index | `GeospatialIndex` as an xarray `Index` | `CellIndex` (a `PandasIndex` subclass with cell edges) for DIS; xugrid for DISV/DISU | Changed |
| Point semantics | Containment by default, `nearest_center` opt-in, `nearest` ambiguous | `sel` without a method is containment; `method="nearest"` is the nearest centre | Done (#485); answers the old open question by making `nearest` mean nearest centre |
| Edge ties | Lowest-numbered cell (flopy3) | Lowest-numbered: west (lower col), north (lower row) | Decided, matches flopy3. Keep DISV consistent if possible. |
| `.grid` accessor (#208) | The single entry point; DISV redirects to `.ugrid` | `.grid.sel_world`, plus `sel`/`sel_z`/`mask_z` on `z-attach` | Started (#487); `sel`/`sel_z`/`mask_z` in #490; see Next for the rest |
| CRS | "Future" | `crs_wkt`/`grid_mapping_name` on `projection` | Done (#485) |
| `z` selection, vertical profiles | 1-D layer-representative `z` or 3-D aux + custom index; open questions on z-only `sel` | One cell per vertical column: `sel_world(x, y, z)`, `sel_z`, `mask_z` over `z_top`/`z_bot` coords on all layered arrays | Functions merged (#488); attaching and accessor in #490 (`z-attach`). Plain `.sel(z=...)` needs a custom index (see Why not an index). DISU and `z_bnds` open |
| Ball/range queries | `query_ball` via cKDTree (3-D) / geopandas (2-D) | None | Open, accessor methods |
| DISV/DISU spatial selection | `GeospatialIndex` | Output is `UgridDataArray` (`ugrid.sel`); inputs have unindexed x/y on `cell`/`node` | Open |
| Quasi-3D `laycbd` z centres (comment on #207) | Needed for non-MF6 grids | Ignored | Open, only matters if non-MF6 grids are supported |

## Coordinates on a DIS array

| coord | dims | index | rotated | unrotated | status |
|---|---|---|---|---|---|
| `x` | `col` | `CellIndex` | local, zero-based | world | #469; `CellIndex` #485 |
| `y` | `row` | `CellIndex` | local, zero-based | world | #469; `CellIndex` #485 |
| `dx`/`dy` | scalar if uniform, else `col`/`row` | none | cell sizes (`dy` negative) | same | output since #469; package arrays and `StructuredGrid` #485 |
| `projection` (scalar) | — | none | grid mapping | grid mapping | #469; `crs_wkt` #485 |
| `x_world`/`y_world` | `(row, col)` | none | `to_world(...)` | omitted (same as `x`/`y`) | #485 |
| `z` | `(layer, row, col)` | none | cell-centre elevation | same | `StructuredGrid` only before; all layered arrays on `z-attach`, computed from the bounds |
| `z_top`/`z_bot` | `(layer, row, col)` | none | cell top and bottom | same | `z-attach` |

- `projection`'s value is `1`. Its attrs are `xorigin`/`yorigin`/`angrot` always, plus `crs_wkt` (wrapped by `wrap_rotated_crs` when rotated) and `grid_mapping_name` with a CRS. Gridded variables name it in their `grid_mapping` attr, set by `index_xy`.
- `xorigin`/`yorigin`/`angrot` stay: they're non-standard, but they're the only record of placement without a CRS.
- The netCDF heads reader keeps the file's CRS attrs on `projection`; the grb still gives the placement.
- The z coordinates come from the discretization's `top`/`botm` (package arrays, `StructuredGrid`/`VertexGrid`) or the grb's TOP/BOTM (heads, budgets), via `vertical.z_coords`. DIS/DISV `top` (size-1 `layer`) gets layer 0's, since it's the top layer's cells' tops. Other arrays with one layer's worth of values, such as RCHA/EVTA's, don't get them unless the model has one layer, since their layer depends on `irch`/`ievt` (see `rch-evt-layer-plan.md`). Each has a `long_name` ("cell top elevation" etc.). DISV arrays get the same three on `(layer, cell)`.

## Selection

### `CellIndex` (DIS, all grids)

A `PandasIndex` over the centres that also keeps each cell's `(lower, upper)` edges, built by `index_xy` from `dx`/`dy`, or midway between centres without them.

- `sel` with no `method`: the cell containing the point. Scalar and point-wise (DataArray) labels both work.
  - A point on an edge goes to the lower-numbered cell (west/north), as in flopy3.
  - Points outside raise `KeyError`.
  - The edges are widened by `tolerance`, a billionth of the axis's extent by default, so rotation rounding doesn't push an edge point outside.
- With `method=`, or a slice: selection by centre, as with `PandasIndex`.
- The index is kept by `isel` (slices and arrays), `roll`, pickle, deepcopy, `chunk`, `concat` along non-grid dims, and arithmetic between same-grid arrays.
- Aligning (`xr.align` inner/outer, `a + b`) and `concat` along `col`/`row` keep each cell's edges (#486). Aligning grids with a cell at the same centre but different edges raises `ValueError`.

Why a `PandasIndex` subclass rather than the alternatives considered earlier:
- `pd.IntervalIndex`: prints and plots as intervals, doesn't serialise to netCDF, and has no `method="nearest"`.
- Float centres alone: the nearest centre can be a neighbouring cell when `delr`/`delc` vary.

### `sel_world` (rotated DIS)

```python
def sel_world(obj, x, y, z=None, **kwargs):
    # rotated: to_local(...) through projection, then sel; otherwise just sel
    # with z: then sel_z(..., outside="raise") on the vertical column
```

- On a rotated grid it converts to local coordinates through `to_local` (the inverse of `to_world`), then calls `sel`, so it gets containment from `CellIndex`. It no longer needs its own tolerance.
- Scalar and point-wise inputs. **Slices don't work**: a world box isn't a local box on a rotated grid, and `to_local` can't take a slice. For box selection, mask on `x_world`/`y_world` (`where`) in the accessor.

### DISV/DISU

Unchanged.
- MF6's mesh exports write world-coordinate vertices, and so do our grb readers since #469.
- Output is a `UgridDataArray`, so containing-face selection is xugrid's `ugrid.sel` / `sel_points`. That needs `numba_celltree`, which isn't in the dev env.
- Input arrays on `cell`/`node` have unindexed x/y. Wrap them as `UgridDataArray`, or give them an `NDPointIndex` (nearest centre only). Not decided.

## Alternatives considered

- **`xarray.indexes.NDPointIndex`** (KD-tree on 2-D world centres): nearest centre only, wrong next to a wide cell, lost on any `isel`. No for DIS; maybe for DISV/DISU inputs.
- **Custom `CoordinateTransformIndex` on world coordinates** (x/y world-valued, 2-D when rotated): an experimental xarray API, x/y changing shape with rotation, no slicing on rotated grids, and disagreement with MF6's netCDF. The overlay plus `CellIndex` gives the same selection.
- **`GeospatialIndex` as an xarray `Index`** (the old design): it isn't needed for DIS. It might still be the way to do DISV/DISU inputs, or ball queries, if xugrid doesn't fit.
- **Prior art:** rasterix `RasterIndex` is affine-only (uniform spacing). rioxarray keeps the transform/CRS in `spatial_ref` with 1-D x/y, the convention followed here. xproj records the CRS but doesn't transform.

## Known limitations

- Arithmetic between differently placed grids keeps the first's `projection` (xarray compares the value, always 1, not the attrs) and drops whichever world coordinate differs. Documented in `index_xy`.
- Arrays reopened from netCDF have their coordinates but not their indexes; they need `index_xy`. The z coordinates come back as they are, since they're unindexed.

## z selection

### Status

- **#488 (`z-select`, merged 2026-10-17):** `flopy4/mf6/utils/vertical.py` with `layer_at`, `sel_z`, `mask_z`, over `z_top`/`z_bot` coordinates or bounds passed in.
- **`z-attach` (PR #490; checked 2026-10-19):**
  - `vertical.z_coords(top, botm, dims)` builds `z`, `z_top` and `z_bot`. It replaces #488's `layer_bounds`.
  - Attaches them to package arrays, `StructuredGrid`/`VertexGrid` and their arrays, and DIS/DISV heads and budgets.
  - Adds `z=` to `sel_world`, and `sel_z`/`mask_z` to `.grid`.
  - Tested on a rotated DIS grid, a `VertexGrid`, and real DIS/DISV heads.
  - Also on the branch since: DIS/DISV `top` gets its layer's elevations; `long_name`s on the z coordinates; `.grid.sel`, `sel`'s indexers plus `z`; world-x/y slices and lists on a rotated grid raise, pointing to masking on `x_world`/`y_world` or point DataArrays; and the selection guide (Next item 6).
- **Open:** `z_bnds` in netCDF (with the `x_bnds`/`y_bnds` work), and DISU.

A **vertical column** is the cells at one `(row, col)`, or one DISV `cell`, through all layers. ("Column" alone is ambiguous next to the `col` dim.)

### The old open question goes away

The old design asked what `sel(z=50)` means when z varies across (row, col), since there could be many matches. Within one vertical column, though, layers stack without overlapping, so **at most one cell contains a given elevation**. Two answers follow:

- **With x/y:** the point is in one vertical column, so z picks at most one layer and the result is one cell, the same as horizontal containment.
- **z alone:** one cell per vertical column, so the result is a (row, col) map, a horizontal slice at that elevation. Vertical columns where z is above the top or below the bottom are NaN. This is the useful "head at elevation 50" map, without interpolation.

So z needs neither a layer-representative 1-D z (which is wrong wherever layers aren't flat) nor a "return all matches" mode.

### Why not an index (yet)

xarray's `sel` passes each keyword to the index owning that coordinate. `x` and `y` have `CellIndex`es, on `col` and `row`; `z` has none, and the default `PandasIndex` only takes 1-D coordinates, while `z` is on `(layer, row, col)`. So `head.sel(z=...)` raises `KeyError: no index found for coordinate 'z'`, alone, with `x`/`y`, or even on one vertical column. (On one column, `set_xindex("z")` works, but `method="nearest"` then means the nearest centre, not the containing cell.)

So z selection is free functions over `z_top`/`z_bot`, on the accessor:
`.grid.sel(..., z=...)` (`sel`'s indexers, then `sel_z` on what's left), `.grid.sel_world(x, y, z)`, `.grid.sel_z`, `.grid.mask_z`.

**A custom index could make plain `.sel(z=...)` work.** This section used to say it couldn't, because neither result is a rectangular subset. That's wrong: `Index.sel` can return a vectorized indexer. Prototyped on xarray 2025.12 (2026-10-19):

```python
class ZIndex(xr.Index):
    # owns z_top and z_bot: da.set_xindex(["z_top", "z_bot"], ZIndex)
    @classmethod
    def from_variables(cls, variables, *, options):
        return cls(xr.DataArray(variables["z_top"]), xr.DataArray(variables["z_bot"]))

    def sel(self, labels, **kwargs):
        idx, found = layer_at(labels["z_top"], self.z_top, self.z_bot, "layer")
        return IndexSelResult({"layer": idx.variable})  # a layer per (row, col)
```

- **z alone works:** `da.sel(z_top=12.0)` gives the horizontal slice on `(row, col)`, a different layer per column, the same as `sel_z`.
- **z with x/y doesn't:** xarray asks each index separately and merges their dim indexers. The z index picks a layer for every column of the whole grid, not knowing which column x/y chose. Then:
  - scalar x/y give a wrong result on `(row, col)`;
  - lists raise `IndexError: Dimensions of indexers mismatch`.

So a working `.sel(x=, y=, z=)` needs **one index owning `x`, `y`, `z`, `z_top` and `z_bot`**, which sees all three labels in one `sel` call: horizontal containment first, as `CellIndex` does, then the layer in the chosen columns. It would replace the two `CellIndex`es on DIS arrays. Work and open questions:

- **Keyword:** users want `sel(z=...)`, so the index owns `z` too (the centres) and answers `z` labels with containment over its bounds, not with the centres.
- **Partial selections:** `sel(x=...)` alone, `sel(y=..., z=...)`, slices of x/y (containment for scalars, by centre for slices, as now), and `method="nearest"` (x/y only).
- **Everything `CellIndex` keeps working through:** `isel` (slices, arrays, and a single layer, after which z is 2-D), `align`/`concat` along `col`/`row` with edges (#486), `roll`, pickle, `chunk`, arithmetic.
- **Arrays without z:** 1-layer arrays and RCHA/EVTA (see `rch-evt-layer-plan.md`) still need x/y selection, so the index must work with or without the z coordinates, or there are two index types.
- **DISV:** no `CellIndex`; horizontal selection goes through xugrid. The index would need a cell-containment structure for `(cell)` too, or z stays accessor-only on DISV.
- **netCDF:** like `CellIndex`, it isn't saved; reopened arrays need `index_xy` (Next item 2).
- **Experimental API:** custom indexes over several coordinates and `IndexSelResult` are public but still evolving in xarray. Pin and test.
- **Payoff:** `.sel(x=, y=, z=)` and `.sel(z=)` read naturally, but they add no capability over `.grid.sel`. Do it only if users ask for plain `sel`, or with the DISV/xugrid work if that needs its own index anyway.

### Data: z bounds on arrays

Containment needs each cell's top and bottom, not its centre, so two unindexed coords sit alongside `z`:

- `z_top` and `z_bot` on `(layer, row, col)` (DIS) or `(layer, cell)` (DISV), with `z_top[0] = top`, `z_top[k] = botm[k-1]` and `z_bot = botm`.
- Why two coords rather than a CF `z_bnds`: a DataArray's coords can only use the array's own dims, so a `(layer, row, col, bnd)` coordinate can't be attached to a `(layer, row, col)` array. Write them out as `z_bnds` with `z:bounds = "z_bnds"` when saving to netCDF (with the `x_bnds`/`y_bnds` work), and read them back into the two coords.
- Sources: `Dis`/`Disv` `top`/`botm` for package arrays, and the grb's TOP/BOTM for heads/budget arrays (`get_coords` and the heads reader).
- They're plain numpy, 2× the size of one layer stack. That's small next to a time series. `z` (the centres) is computed from them, so the two can't disagree.
- They follow `isel(layer=...)` and `sel(x=, y=)` for free, since they share the array's dims. So after a horizontal point selection, a column keeps its own bounds.

### API

On `.grid`:

- **`sel(indexers=None, method=None, tolerance=None, drop=False, **indexers_kwargs)`:** `sel` with `z` taken out first, then `sel_z(..., outside="raise")` on the result: the cell containing z in each vertical column the other indexers leave. x/y are in the grid's frame, as with `sel`; `method`/`tolerance` apply only to the other indexers. `sel_world` is this after converting world x/y.
- **`sel_world(x, y, z=None, **kwargs)`:** an optional `z` added to the existing method. It selects horizontally as now, then picks the layer whose `z_bot <= z <= z_top`. With DataArray x/y/z sharing a dim, it works point-wise: horizontal `sel` gives `(point, layer)`, then the layer is chosen per point by vectorized `isel`. With `method="nearest"`, only the horizontal pick is nearest; z is always containment. A nearest-in-z without bounds is the cell-centre `z`, which isn't what anyone asking for an elevation means.
- **`sel_z(z, outside="nan")`:** the horizontal slice. It returns the array with `layer` replaced by the containing layer per vertical column: `(…, row, col)` for DIS, `(…, cell)` for DISV, with NaN where no cell contains z (`outside="raise"` raises `KeyError` instead). The chosen layer is kept as a `layer` coord, so users can see where it came from. `z` can also be a DataArray, on the vertical columns' dims (e.g. a surface) or on a points dim.
- **`mask_z(zmin=None, zmax=None, how="overlap")`:** a boolean on `(layer, row, col)` for use in `where`; a missing end is open. `how` is `"overlap"` (the cell intersects the range; the default, since "which cells touch the water-table zone" is the usual question), `"within"` (the cell is entirely in the range), or `"center"` (`z` is in the range). Thickness-weighted fractions are out of scope.
- **Vertical profile:** no new method. `sel_world(x, y)` already returns the `(…, layer)` column, and with `z`/`z_top`/`z_bot` attached it carries its elevations, which is what a profile plot needs. A `plot_profile` helper can come later.

### Rules

- **Ties:** a z exactly on a layer interface goes to the upper (lower-numbered) layer, matching flopy3's `StructuredGrid.intersect` (it scans layers from the top, inclusive at both ends, and takes the first match) and our horizontal rule. The model top and bottom are inclusive.
- **Outside:** for a point outside, `sel_world` raises `KeyError`, as horizontal selection does. `sel_z` gives NaN for those vertical columns. Point-wise selection with some points outside raises too. A `drop`/NaN option can be added if anyone asks.
- **idomain:** selection is geometric. Inactive (0) and vertical pass-through (-1) cells are found like any other, and their values are whatever the array holds (NaN/1e30 in heads). Zero-thickness cells never win a tie against the cell above them, because the upper cell matches first.
- **Not covered:** dry or saturated-thickness selection (a water-table-aware z) is hydraulics, not geometry. Make it a separate method if wanted. Transient z (CSUB subsidence) is out of scope; bounds are static.
- **Rotation:** z isn't rotated, so this composes with `sel_world`'s local/world conversion unchanged.
- **Units:** z is in model length units. There's no vertical CRS handling.

### DISV and DISU

- **DISV:** the same, on `(layer, cell)`. The horizontal step goes through xugrid (see DISV/DISU), and the z step is identical, so write the layer pick once over a trailing `layer` dim.
- **DISU:** nodes have their own top/bot and there's no layer dim, so "the vertical column" is the set of nodes whose footprints contain the point. A point query is the horizontal containment and then `bot <= z <= top` among those nodes. `sel_z`/`mask_z` become masks over nodes. Defer this until DISU horizontal selection exists.

## Done

1. **#469:** layer/row/col dims, local 1-D `x`/`y` for rotated DIS, the `projection` coordinate, grb readers that honour `angrot`.
2. **#485 (`rotated-world`):**
   - `x_world`/`y_world`, `to_local`, `sel_world`.
   - `crs_wkt`/`grid_mapping_name` on `projection`; the heads reader keeps the file's CRS.
   - `CellIndex` containment selection on all DIS arrays; `dx`/`dy` on package arrays and `StructuredGrid`.
3. **#486 (`cellindex-align`):** `CellIndex` keeps cell edges through `align` and `concat` along `col`/`row`.
4. **#487 (`grid-accessor`):** the `.grid` accessor, with `sel_world`.
5. **#488 (`z-select`):** z-selection functions. **#490 (`z-attach`)** attaches them and adds them to the accessor; see z selection.

## Next

In the order I'd take them:

1. **DISV/DISU spatial selection.**
   - Add `numba_celltree` to the pixi dev env.
   - Test `ugrid.sel` / `sel_points` on the `UgridDataArray`s from our grb and heads readers, which now carry `z`/`z_top`/`z_bot` (check `ugrid.sel` keeps them, so `sel_z` works after it).
   - Check xugrid's behaviour for a point on an edge between faces: can DISV match DIS ties (lower-numbered cell), or does it need a wrapper?
   - Decide what DISV/DISU *input* arrays get (a `UgridDataArray` wrapper or `NDPointIndex`), and how `.grid` dispatches on dims: `row`/`col` structured, `cell`/`node` or a `UgridDataArray` unstructured, redirecting to `.ugrid` where it can.
2. **Accessor leftovers (#208):**
   - 1-based selection by MF6 cell numbers (cellids from list packages), since dims carry no labels. Not as `ds.grid.sel(layer=1, ...)`: `grid.sel` is now `sel` plus `z`, 0-based like `sel`. A separate method, e.g. `ds.grid.sel_cell(layer=1, row=5, col=10)` or `ds.grid.sel_cell(cellid)`.
   - `index_xy` for arrays reopened from netCDF (e.g. `ds.grid.index()`, or doing it on access).
   - A world-box selection that masks on `x_world`/`y_world` for rotated grids.
   - Whether to expose the old `method="contains" | "nearest_center"` names, or just document `sel`'s `None`/`"nearest"`.
   - Possibly `ds.grid.crs` (from `projection.crs_wkt`), `plot`, `plot_profile`, `neighbors`.
3. **netCDF bounds:** write `x_bnds`/`y_bnds` from `CellIndex` and `z_bnds` from `z_top`/`z_bot` (with `bounds` attrs), and read them back, so MF6 netCDF can be indexed without a grb. This is the writer and the heads reader.
4. **Ball/range queries:** `query_ball` via `scipy.spatial.cKDTree` on centres (3-D, using `z` now that layered arrays carry it) and geopandas (2-D), as free functions with accessor methods. On rotated grids they read `x_world`/`y_world`.
5. **Budget-reader coordinates for faces.**
   - Now: flows indexed by the cell they leave (DIS right/front/lower, DISV lower) carry that cell's x/y/z coordinates, as in DIS since #469; DISV horizontal flows, on mesh edges, carry none.
   - DISV edges: x/y from UGRID edge coordinates (xugrid's edge midpoints), and a vertical extent from the two cells on either side, `z_top = min` of their tops and `z_bot = max` of their bottoms (one cell on the grid boundary), from `edge_face_connectivity`. Then `mask_z`/`sel_z` work on edges.
   - Keep the cell-based convention for cell-indexed flows, so budgets line up with heads cell for cell, and document it: a lower flow crosses the face at the cell's `z_bot`, so `sel_z(z)` on lower flows gives the lower-face flow of the cell containing z, not the flow through a face at z.
   - After DISV selection, since both use xugrid's edge connectivity.
6. **Selection vignette.** Drafted on `z-attach` (`df8e4d93`) as `docs/examples/selection.py` + `.ipynb`, covering the points below; review it with that PR. Original outline: `docs/guide/selection.py` (jupytext, paired `.ipynb`, under the Guide part of `_toc.yml`), on a small rotated DIS model with heads:
   1. Scalar `sel`/`sel_world`: containment, ties to the lower-numbered cell, outside raises `KeyError`.
   2. Lists vs DataArrays on a shared `point` dim: the outer product vs one cell per point, side by side, with result shapes. Lists silently give the outer product, which is the subtle part.
   3. With `z`: a vertical column per point, then a cell per point; a scalar `z` with point x/y.
   4. `sel_z` as a horizontal slice, and `mask_z` with `where`.
   5. Rotated grids: why world slices don't work, and masking on `x_world`/`y_world` instead.
7. **The `projection` attrs limitation** (see Known limitations).
8. **Quasi-3D `laycbd`** z centres, only if non-MF6 grids are in scope.
9. **Upstream housekeeping** (don't post without asking):
   - Rescope or close #207: layer/row/col and z are done; DISV is what's left.
   - Close draft #278 (`xarray-index`, the old spatial index design), which this plan replaces.
   - Point #208 at this plan.
   - Supersede or delete `docs/dev/spatial-index-design.md` on `xarray-index`, or replace it with a version of this plan under `docs/dev/`.

### Parallel work

- `z-attach` touches `grid.py`, `package.py`, `adapters.py`, the heads and budget readers, and the accessor. Until it merges, avoid starting work in those files.
- **Can start now:** the DISV/xugrid groundwork (env and tests only), `query_ball` as free functions in their own module, and drafting the upstream housekeeping text.
- **After `z-attach` merges:** the accessor leftovers, netCDF bounds, and the `projection` fix. The DISV input/dispatch decision can then go in alongside the accessor leftovers.
