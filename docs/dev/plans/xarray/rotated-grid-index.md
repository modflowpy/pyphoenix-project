# Grid coordinates, rotation and spatial selection

How grid arrays carry coordinates, how rotation is represented, and how
selection works, as built in #469-#490, plus what's left. This replaces
the earlier spatial index design
([`spatial-index-design.md`](../archive/spatial-index-design.md), #278,
with #207, #208 and #120). From that design, the `.grid` accessor and
containment-by-default point queries were kept; spatial dims for DIS were
reversed (dims are `layer`/`row`/`col`), and the custom `GeospatialIndex`
was replaced by `CellIndex` on DIS and xugrid on DISV/DISU.

## Framing

The grid geometry stays pure, and world coordinates are an overlay:

- Index in the grid's own frame. `x`/`y` are 1-D on `col`/`row`, always
  indexed, rotated or not.
- Rotation lives in the CRS (or, without one, in grid-mapping metadata),
  not in the coordinate values.
- World coordinates for a rotated grid are derived, 2-D, auxiliary and
  unindexed.

This is CF's `rotated_latitude_longitude` pattern: 1-D `rlon`/`rlat` in
the rotated frame, a `grid_mapping` variable for the transform, 2-D
`lon`/`lat` auxiliary coordinates. It's also what MF6 does:
`DisNCStructured` writes zero-based local x/y for rotated grids, wrapping
a configured CRS in a derived projected CRS (EPSG:9624 affine) that
encodes xorigin/yorigin/angrot. `StructuredGrid._structured_dataset`
(`utils/grid.py`) mirrors that with `wrap_rotated_crs` (`utils/crs.py`).

So `x`/`y` are always coordinates in the grid's CRS: world coordinates
when unrotated (the grid CRS is the base CRS), local and zero-based when
rotated (it's the derived CRS).

## Coordinates on a DIS array

| coord | dims | index | rotated | unrotated |
|---|---|---|---|---|
| `x` | `col` | `CellIndex` | local, zero-based | world |
| `y` | `row` | `CellIndex` | local, zero-based | world |
| `dx`/`dy` | scalar if uniform, else `col`/`row` | none | cell sizes (`dy` negative) | same |
| `projection` (scalar) | — | none | grid mapping | grid mapping |
| `x_world`/`y_world` | `(row, col)` | none | `to_world(...)` | omitted (same as `x`/`y`) |
| `z` | `(layer, row, col)` | none | cell-centre elevation | same |
| `z_top`/`z_bot` | `(layer, row, col)` | none | cell top and bottom | same |

- `projection`'s value is `1`. Its attrs are `xorigin`/`yorigin`/`angrot`
  always, plus `crs_wkt` (wrapped when rotated) and `grid_mapping_name`
  with a CRS. Gridded variables name it in `grid_mapping`, set by
  `index_xy`. `xorigin`/`yorigin`/`angrot` aren't standard, but without a
  CRS they're the only record of placement.
- The netCDF heads reader keeps the file's CRS attrs on `projection`; the
  GRB still gives the placement.
- z coordinates come from `top`/`botm` (package arrays,
  `StructuredGrid`/`VertexGrid`) or the GRB's TOP/BOTM (heads, budgets),
  via `vertical.z_coords`, with `z_top[0] = top`, `z_top[k] = botm[k-1]`,
  `z_bot = botm`. DIS/DISV `top` (size-1 `layer`) gets layer 0's. Other
  one-layer arrays such as RCHA/EVTA don't get them unless the model has
  one layer, since their layer depends on `irch`/`ievt`
  ([`rch-evt-layer.md`](rch-evt-layer.md)). DISV arrays get the same three
  on `(layer, cell)`.
- Two coords rather than CF `z_bnds`, because a DataArray's coords can only
  use its own dims, so a `(layer, row, col, bnd)` coord can't attach. They
  follow `isel` and `sel(x=, y=)` for free, and `z` is computed from them.
  On netCDF they'd be written as `z_bnds` and read back (Next 3).

## Selection

### `CellIndex`

A `PandasIndex` over the centres that also keeps each cell's
`(lower, upper)` edges, built by `index_xy` from `dx`/`dy`, or midway
between centres without them.

- `sel` without `method` gives the cell containing the point, for scalar
  and point-wise (DataArray) labels. A point on an edge goes to the
  lower-numbered cell (west, north), as in flopy3. Points outside raise
  `KeyError`. Edges are widened by `tolerance` (a billionth of the axis's
  extent by default) so rotation rounding doesn't push an edge point out.
- With `method=` or a slice, selection is by centre, as with `PandasIndex`.
- Kept through `isel`, `roll`, pickle, deepcopy, `chunk`, `concat` along
  non-grid dims, and same-grid arithmetic. `align` and `concat` along
  `col`/`row` keep each cell's edges (#486); grids with a cell at the same
  centre but different edges raise `ValueError`.

Why not `pd.IntervalIndex`: it prints and plots as intervals, doesn't
serialise to netCDF, and has no `method="nearest"`. Why not float centres
alone: the nearest centre can be a neighbouring cell when `delr`/`delc`
vary.

### `sel_world` (rotated DIS)

Converts world x/y to local through `to_local` (the inverse of
`to_world`), then calls `sel`, so it gets containment from `CellIndex`.
Scalar and point-wise inputs only: a world box isn't a local box on a
rotated grid, so slices raise and point to masking on
`x_world`/`y_world`.

### z

Within one vertical column (the cells at one `(row, col)`, or one DISV
`cell`, through all layers) layers don't overlap, so at most one cell
contains a given elevation. So:

- with x/y, z picks at most one layer, and the result is one cell;
- z alone gives one cell per vertical column: a horizontal slice at that
  elevation, NaN where z is above the top or below the bottom.

Neither needs a layer-representative 1-D z or a "return all matches" mode.

The functions are in `utils/vertical.py` (`layer_at`, `sel_z`, `mask_z`),
on the accessor:

- **`.grid.sel(..., z=...)`:** `sel` with z taken out, then
  `sel_z(..., outside="raise")` on the result. `method`/`tolerance` apply
  only to the other indexers.
- **`.grid.sel_world(x, y, z=None)`:** horizontal, then the layer with
  `z_bot <= z <= z_top`. Point-wise with DataArray x/y/z on a shared dim.
  With `method="nearest"` only the horizontal pick is nearest; z is always
  containment.
- **`.grid.sel_z(z, outside="nan")`:** replaces `layer` with the containing
  layer per vertical column, kept as a `layer` coord. `z` can be a
  DataArray on the column dims (a surface) or on a points dim.
- **`.grid.mask_z(zmin=None, zmax=None, how="overlap")`:** a boolean on the
  cell dims for `where`. `how` is `"overlap"` (default), `"within"` or
  `"center"`.
- A vertical profile is `sel_world(x, y)`, which returns the `(…, layer)`
  column with its elevations.

Rules:

- A z on an interface goes to the upper layer, matching flopy3's
  `StructuredGrid.intersect` and the horizontal rule. Model top and bottom
  are inclusive.
- `sel_world` raises `KeyError` for a point outside; `sel_z` gives NaN.
- Selection is geometric: inactive and pass-through cells are found like
  any other. Zero-thickness cells never win a tie against the cell above.
- Not covered: water-table-aware selection (hydraulics, not geometry) and
  transient z (CSUB).
- z isn't rotated, so it composes with `sel_world` unchanged. It's in model
  length units, with no vertical CRS.

#### Why not an index

`sel` passes each keyword to the index owning that coordinate. `z` has
none, and `PandasIndex` takes only 1-D coordinates, so `head.sel(z=...)`
raises `KeyError`. A custom index can return a vectorized indexer, and a
prototype `ZIndex` owning `z_top`/`z_bot` (xarray 2025.12) makes
`da.sel(z_top=12.0)` give the horizontal slice. But with x/y it doesn't
work: xarray asks each index separately and merges the results, so the z
index picks a layer for every column without knowing which column x/y
chose. Scalar x/y give a wrong `(row, col)` result; lists raise
`IndexError`.

A working `.sel(x=, y=, z=)` needs one index owning `x`, `y`, `z`, `z_top`
and `z_bot`, replacing the two `CellIndex`es; see
[`combined-index.md`](combined-index.md). It adds no capability over
`.grid.sel`.

### DISV and DISU

- MF6's mesh exports and our GRB readers write world-coordinate vertices.
- Output is a `UgridDataArray`, so containing-face selection is xugrid's
  `ugrid.sel`/`sel_points`, which needs `numba_celltree` (not in the dev
  env).
- Input arrays on `cell`/`node` have unindexed x/y. Wrap them as
  `UgridDataArray` or give them an `NDPointIndex` (nearest centre only);
  see [`overview.md`](overview.md) on xugrid.
- z on DISV is the same as DIS on `(layer, cell)`, after the horizontal
  step through xugrid, so the layer pick should be written once over a
  trailing `layer` dim.
- DISU nodes have their own top/bot and no layer dim: a point query is
  horizontal containment, then `bot <= z <= top` among those nodes, and
  `sel_z`/`mask_z` become masks over nodes. After DISU horizontal
  selection exists.

### Alternatives

- **`NDPointIndex`** (KD-tree on 2-D world centres): nearest centre only,
  wrong next to a wide cell, lost on any `isel`. Not for DIS; maybe for
  DISV/DISU inputs.
- **`CoordinateTransformIndex` on world coordinates:** experimental API,
  x/y changing shape with rotation, no slicing on rotated grids, and
  disagreement with MF6's netCDF.
- **`GeospatialIndex`** (the old design): not needed for DIS; possibly for
  DISV/DISU inputs or ball queries if xugrid doesn't fit.
- **Prior art:** rasterix `RasterIndex` is affine-only. rioxarray keeps the
  transform and CRS in `spatial_ref` with 1-D x/y, the convention followed
  here. xproj records the CRS but doesn't transform.

### Known limitations

- Arithmetic between differently placed grids keeps the first's
  `projection` (xarray compares the value, always 1, not the attrs) and
  drops whichever world coordinate differs. Documented in `index_xy`.
- Arrays reopened from netCDF have coordinates but not indexes; they need
  `index_xy`.

## Next

Roughly in order:

1. **DISV/DISU selection.** Add `numba_celltree` to the dev env. Test
   `ugrid.sel`/`sel_points` on our GRB and heads readers' output, checking
   that `z`/`z_top`/`z_bot` survive so `sel_z` works after it. Check
   xugrid's edge ties against DIS's. Decide what input arrays get, and how
   `.grid` dispatches on dims (`row`/`col` structured; `cell`/`node` or a
   `UgridDataArray` unstructured, redirecting to `.ugrid` where it can).
2. **Accessor leftovers (#208):**
   - 1-based selection by MF6 cell numbers, as a separate method (e.g.
     `sel_cell(layer=1, row=5, col=10)` or `sel_cell(cellid)`), since
     `grid.sel` is 0-based like `sel`.
   - `index_xy` for arrays reopened from netCDF (`ds.grid.index()`, or on
     access).
   - A world-box selection masking on `x_world`/`y_world`.
   - Possibly `ds.grid.crs`, `plot`, `plot_profile`, `neighbors`.
3. **netCDF bounds:** write `x_bnds`/`y_bnds` from `CellIndex` and `z_bnds`
   from `z_top`/`z_bot`, and read them back, so MF6 netCDF can be indexed
   without a GRB.
4. **Ball/range queries:** `query_ball` via `cKDTree` on centres (3-D) and
   geopandas (2-D), as free functions with accessor methods, reading
   `x_world`/`y_world` on rotated grids.
5. **Budget coordinates for faces.** Cell-indexed flows (DIS right, front,
   lower; DISV lower) carry the cell they leave's x/y/z, which keeps
   budgets aligned with heads; document that `sel_z(z)` on lower flows
   gives the lower-face flow of the cell containing z. DISV horizontal
   flows, on mesh edges, carry none: give them x/y from xugrid's edge
   midpoints and a vertical extent from the two adjacent cells
   (`z_top = min` of tops, `z_bot = max` of bottoms) via
   `edge_face_connectivity`. After DISV selection.
6. **The `projection` attrs limitation** above.
7. **Quasi-3D `laycbd`** z centres, only if non-MF6 grids are in scope.
8. **Upstream:** rescope or close #207 (DISV is what's left), close draft
   #278, and point #208 here.
