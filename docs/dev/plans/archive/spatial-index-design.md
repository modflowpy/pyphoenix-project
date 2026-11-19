# Spatial Index Design

## Background

Currently, the `StructuredGrid` class wraps `flopy.discretization.StructuredGrid` and provides xarray coordinate-based indexing using:

- `x` dimension coordinate: 1D array `(ncol,)`, unique x values, one per column
- `y` dimension coordinate: 1D array `(nrow,)`, unique y values, one per row
- `z` non-dimension coordinate: 3D array `(nlay, nrow, ncol)`, cell-specific z values (varies with topography)

The `x`/`y` coordinates use `PandasIndex` and enable e.g. `sel(x=..., y=...)`. The `z` coordinate has no index and acts as an auxiliary coordinate only.

This works well for horizontal spatial queries but doesn't support more advanced queries like vertical (elevation-based) or full 3D spatial queries.

## Dimension and Coordinate Naming Strategy

MF6 uses topology names (`nlay`, `nrow`, `ncol`, `ncpl`). CF conventions expect spatial names (`x`, `y`, `z`). Support both.

Structured grids (DIS) have regular spatial dimensions. Unstructured grids (DISV/DISU) don't.

### Structured Grids (DIS)

Spatial coordinates as primary dimensions, MF6 names as auxiliary:

```python
<xarray.Dataset>
Dimensions:  (x: 100, y: 100, z: 3, time: 10)
Coordinates:
  * x        (x) float64        # spatial coordinate (dimension coord)
  * y        (y) float64        # spatial coordinate (dimension coord)
  * z        (z) float64        # layer elevations (dimension coord)
  * time     (time) float64     # simulation time
    col      (x) int64          # MF6 column index (1-based)
    row      (y) int64          # MF6 row index (1-based)
    layer    (z) int64          # MF6 layer index (1-based)
Data variables:
    head     (time, z, y, x) float64
    ...
```

Why:
- Leverages native xarray `.sel(x=..., y=...)` without custom indexes
- Follows CF conventions
- MF6 indices still accessible as auxiliary coords

Note: Make `z` a 1D dimension coordinate (layer top/midpoint elevations). Store full 3D elevations as auxiliary coords if needed.

### Unstructured Grids (DISV/DISU)

Topology dimensions as primary, spatial coords as auxiliary:

```python
<xarray.Dataset>
Dimensions:  (nlay: 3, ncpl: 1000, time: 10)  # DISV example
Coordinates:
  * nlay     (nlay) int64       # layer index (dimension coord)
  * ncpl     (ncpl) int64       # cells per layer (dimension coord)
  * time     (time) float64     # simulation time
    cell_x   (ncpl) float64     # cell center x coordinate (auxiliary)
    cell_y   (ncpl) float64     # cell center y coordinate (auxiliary)
    cell_z   (nlay, ncpl) float64  # cell center z coordinate (auxiliary)
Data variables:
    head     (time, nlay, ncpl) float64
    ...
```

Why:
- No regular spatial dimensions
- Follows UGRID conventions (xugrid/uxarray pattern)
- Spatial coords require custom indexing

### Unified `.grid` Accessor

Consistent API across both grid types:

```python
# Works for both structured and unstructured grids:
ds.grid.sel(x=1000, y=2000)           # spatial selection
ds.grid.sel(layer=1, row=5, col=10)   # MF6 topology selection (DIS)
ds.grid.sel(layer=1, ncpl=42)         # MF6 topology selection (DISV)
ds.grid.sel(x=1000, y=2000, z=50)     # 3D spatial query
ds.grid.isel(...)                     # always 0-based indexing
ds.grid.plot(...)                     # grid-aware plotting
ds.grid.neighbors(layer=1, row=5, col=10)  # cell connectivity
```

Implementation:
- **DIS**: Spatial selection → native `.sel()`, topology selection → map MF6 coords to spatial
- **DISV/DISU**: Topology selection → native `.sel()`, spatial selection → custom `GeospatialIndex`
- Detect grid type via dimension inspection, dispatch accordingly

### Relationship to Standards

**xugrid/uxarray**: Topology dimensions primary for unstructured grids, spatial coords auxiliary. Moving to custom xarray indexes ([xugrid #35](https://github.com/Deltares/xugrid/issues/35), [PR #373](https://github.com/Deltares/xugrid/pull/373)) instead of wrapper classes.

**CF conventions**: Structured grids use matching dimension/coord names (`x`, `y`, `z`). Unstructured use auxiliary spatial coords. Our approach aligns with both.

**Key insight**: Asymmetry is correct. Structured/unstructured grids have different natural dimension systems. `.grid` accessor unifies the interface.

### Implementation Considerations

#### Z-coordinate for structured grids

Two options:

**1. Layer-representative 1D** (recommended)
- `z = [top1, top2, top3]` or layer midpoints
- Enables native `.sel(z=...)`
- Store full 3D elevations as auxiliary coords

**2. 3D auxiliary** (current)
- `z = (nlay, nrow, ncol)` array
- No native `.sel(z=...)` support
- Requires custom index

#### Grid accessor dispatch

Detect grid type via dimensions:

```python
if {'x', 'y'}.issubset(self.dims):
    return StructuredGridAccessor(self)
elif 'ncpl' in self.dims or 'nlay' in self.dims:
    return UnstructuredGridAccessor(self)
```

Each accessor implements: `.sel()`, `.isel()`, `.plot()`, `.neighbors()`, `.query_ball()`, `.contains()`

#### Coordinate transformation

**Topology → spatial (structured)**:
```python
# ds.grid.sel(layer=2, row=10, col=5)
# → find indices where layer==2, row==10, col==5
# → ds.isel(z=..., y=..., x=...)
```

**Spatial → topology (unstructured)**:
```python
# ds.grid.sel(x=1000, y=2000)
# → spatial_index.query_point(x=1000, y=2000)
# → ds.isel(ncpl=...)
```

## Proposal

Extend `GeospatialIndex` from [flopy3 PR 2654](https://github.com/modflowpy/flopy/pull/2654) to implement `xarray.core.indexes.Index`. Required methods: `sel()`, `isel()`, `equals()`, `union()`, `intersection()`. Start with `.sel()`.

**Primary need**: Unstructured grids (DISV/DISU) where spatial selection can't use native dimension coords. Structured grids (DIS) get basic spatial selection natively, but advanced queries benefit from custom index too.

Integrate with: `StructuredGrid`, `VertexGrid`, `UnstructuredGrid`.

Advanced spatial queries to support:

```python
# Point queries with different semantics
head = ds.grid.sel(x=250, y=650, z=50, method='contains')  # head in cell containing point
head = ds.grid.sel(x=250, y=650, z=50, method='nearest_center')  # head in cell with center nearest to point

# Spatial range queries
nearby = ds.grid.query_ball(point=(1500, 2300, 45), radius=100)  # 3D ball query

# Elevation-based slices
cells = ds.grid.sel(z=slice(40, 60))  # find all cells between elevations 40-60
```

### Point Queries

Use xarray `.sel()` syntax.

#### Open Questions

**1. Z-only queries**

What does `sel(z=50)` mean when z varies in (x, y)? Multiple cells may match.

Options:
- Require x, y when selecting by z
- Return all cells matching z
- Support explicit mode: `sel(z=50, mode='all' | 'first' | 'nearest_to_origin')`

**2. Method parameter**

Two semantics: **containment** vs **nearest center**.

**Containment** (default): Cell that contains the point.
- Use cases: locating wells, boundaries, observation points
- Points outside grid: return `KeyError` or `NaN`
- On boundaries: tie-break to lowest-numbered cell (current flopy 3.x behavior)

**Nearest center**: Cell whose center is closest to point.
- Use cases: out-of-bounds queries, cross-grid comparisons
- Always returns a result, even outside grid bounds
- May return cell that doesn't contain the point

```
┌──────────────────┬──────────────────┐
│                  │                  │
│                  │      ○ ← nearest center
│                  │    ╱             │
│                  │   ╱              │
│           ★ ─────┼──╱               │
│        (query)   │                  │
│                  │                  │
├──────────────────┼──────────────────┤
│                  │                  │
│                  │                  │
└──────────────────┴──────────────────┘

Query point (★):
- contains → left cell
- nearest center → right cell
```

```python
# Default: containment
ds.grid.sel(x=250, y=650, z=50)
ds.grid.sel(x=250, y=650, z=50, method='contains')

# Nearest center
ds.grid.sel(x=250, y=650, z=50, method='nearest_center')
```

Should `method="nearest"` alias one of these, or disallow it to avoid ambiguity?

### Spatial Range Queries

Ball queries can't use `sel()` (only accepts coord names, not arbitrary params).

Use cases: zone of influence, observation network radius, local refinement region.

#### 2D (x, y)

Use geopandas:

```python
cells_gdf = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in zip(...)])
mask = cells_gdf.sindex.query(Point(1500, 2300).buffer(100), predicate='intersects')
```

Expose via accessor to avoid manual `GeoDataFrame` creation.

#### 3D (x, y, z)

Use scipy.spatial.cKDTree (from flopy 3.x `GeospatialIndex`):

```python
tree = cKDTree(np.column_stack([x, y, z]))
indices = tree.query_ball_point((1500, 2300, 45), radius=100)
mask = np.zeros(grid.shape, dtype=bool)
mask.ravel()[indices] = True
```

Expose via accessor:

```python
ds.grid.query_ball(point=(x, y, z), radius=100)
```

### Elevation-Based Slicing

```python
# Extract vertical profile at x=250, y=650.
# For structured grids, this works natively
profile = ds.sel(x=250, y=650, method='nearest')  # returns all z values at (x, y)

# For unstructured grids, use .grid accessor
profile = ds.grid.sel(x=250, y=650)  # spatial query returns vertical profile

# With z-slicing: get only specific elevation range
profile_shallow = ds.grid.sel(x=250, y=650, z=slice(80, 100))

# Select all cells in water table zone (elevation 40-60)
wt_zone = ds.grid.sel(z=slice(40, 60))
```

## References

Several external libraries already have some support for advanced spatial queries:

- **GeoPandas**: 2D spatial queries, already a dependency - use for ball queries, spatial joins
- **scipy.spatial**: 3D KD-tree, likely already in dependency tree - use for 3D ball queries
- **xvec**: xarray vector data extension, wraps GeoPandas - unnecessary if already using GeoPandas
- **rioxarray**: Raster operations only, not applicable for cell center queries
- **rtree/pyvista**: Heavier dependencies, not needed given GeoPandas/scipy coverage

Some specific resources:

- [xarray Custom Index Guide](https://docs.xarray.dev/en/stable/internals/how-to-create-custom-index.html)
- [scipy.spatial.cKDTree](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html) - 3D ball queries
- [GeoPandas Spatial Index](https://geopandas.org/en/stable/docs/reference/api/geopandas.sindex.SpatialIndex.html) - 2D spatial queries
- [GeoPandas sjoin_nearest](https://geopandas.org/en/stable/docs/reference/api/geopandas.sjoin_nearest.html) - Nearest neighbor with max distance
- [xvec](https://xvec.readthedocs.io/) - Vector data cubes for xarray (wraps GeoPandas)

## Future

Some things to consider after an initial implementation:

- Time-varying coordinates: support transient z coordinates (subsidence)
- Multi-grid queries: queries across nested grids
- Spatial aggregations: average within spatial regions
- Coordinate transformations: support for different CRS/projections
