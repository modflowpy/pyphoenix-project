# Spatial Index Design

## Background

Currently, the `StructuredGrid` class wraps `flopy.discretization.StructuredGrid` and provides xarray coordinate-based indexing using:

- `x` dimension coordinate: 1D array `(ncol,)`, unique x values, one per column
- `y` dimension coordinate: 1D array `(nrow,)`, unique y values, one per row
- `z` non-dimension coordinate: 3D array `(nlay, nrow, ncol)`, cell-specific z values (varies with topography)

The `x`/`y` coordinates use `PandasIndex` and enable e.g. `sel(x=..., y=...)`. The `z` coordinate has no index and acts as an auxiliary coordinate only.

This works well for horizontal spatial queries but doesn't support more advanced queries like vertical (elevation-based) or full 3D spatial queries.

## Proposal

Extend (or compose) the `GeospatialIndex` class under development in [flopy3 PR 2654](https://github.com/modflowpy/flopy/pull/2654) to extend `xarray.core.indexes.Index`. This requires implementing a set of required methods: `sel()`, `isel()`, `equals()`, `union()`, `intersection()`, etc. (We may want to start with `.sel()` and work up from there.)

Compose this with the `StructuredGrid` (and eventually `VertexGrid` and `UnstructuredGrid`?) classes. (This document only considers the structured case for now.)

Ultimately this should allow advanced spatial queries that aren't currently supported:

```python
# Point queries with different semantics
head = grid.head.sel(x=250, y=650, z=50, method='contains')  # head in cell containing point
head = grid.head.sel(x=250, y=650, z=50, method='nearest_center')  # head in cell with center nearest to point

# Spatial range queries
# TODO

# Elevation-based slices
cells = grid.botm.sel(z=slice(40, 60))  # find all cells between elevations 40-60
```

### Point Queries

Probably the most natural way to expose point queries is xarray `.sel()` syntax.

#### Questions

There are several potential sources of semantic ambiguity with point queries.

1. Z-only queries

What does `sel(z=50)` mean when z varies in (x, y)? Multiple cells may have z ≈ 50 at different locations.

Possible solutions include:

- Require x, y when selecting by z: `sel(x=250, y=650, z=50)`
- Return all cells matching z: `sel(z=50)` → all cells with z ≈ 50
- Support explicit mode: `sel(z=50, mode='all' | 'first' | 'nearest_to_origin')`

2. Method parameter

What does `method='nearest'` mean for point queries (if we want it to mean anything at all, or rather require different values for `method`)? Two possible meanings are "containment" and "nearest center".

With **containment** semantics we ask which cell which contains the query point. This should probably be the default.

The main use case here is probably locating features. For instance:

- Which cell should contain this pumping well at (x,y,z)?
- Which cell does this constant head boundary go in?
- Which cell contains this observation point?

There is no meaningful value for points outside grid bounds, and the result is ambiguous for points exactly on cell boundaries, necessitating a tie-breaking strategy (currently flopy 3.x returns the lowest-numbered cell).

With **nearest center** semantics we ask for the cell whose center point is closest to the query point.

Potential use cases for nearest center queries:

- Out-of-bounds queries: extrapolate to nearest cell when point is outside domain, e.g. with noisy field data from GPS coordinates we might still want to associate a point with the "closest" cell.
- Cross-grid comparisons: Associate a set of points with the "closest" cells from grid A and grid B

A nearest center query can always return a result, even if the point is beyond the grid bounds. It's also a bit more intuitively consistent with xarray's `method='nearest'` convention, but it may return a cell that doesn't contain the point (why containment should probably be the default).

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

We could consider supporting the following:

```python
# Default: containment semantics
grid.head.sel(x=250, y=650, z=50) # equivalent below
grid.head.sel(x=250, y=650, z=50, method='contains')

# Opt into nearest center query
grid.head.sel(x=250, y=650, z=50, method='nearest_center')
```

Should we support `method="nearest"` for compatibility with the xarray convention? If so, which should it alias, "contains" or "nearest_center"? Maybe this is not worth the ambiguity and we should disallow it?

What happens when a point is outside the grid? With `method="contains"`, presumably raise `KeyError` or return `NaN`. With `method="nearest_center"`, we can return the cell with the nearest center by default, possibly providing some kind of option to toggle whether an error should be raised (though I don't think we can do this within the `.sel()` paradigm, I think its signature is fixed).

### Spatial Range Queries

Ball queries ("find all cells within radius R of point P") cannot be implemented via `sel()` since xarray's `sel()` only accepts coordinate names as arguments, not arbitrary parameters like `spatial_distance=(x, y, z, r)`.

Use cases might include: zone of influence around pumping well, observation network radius, local refinement region, etc.

#### 2D (x, y)

We can support this out of the box with geopandas (already a dependency):

```python
from shapely.geometry import Point
import geopandas as gpd

# Create GeoDataFrame from cell centers
points = [Point(x, y) for x, y in zip(grid.x.values, grid.y.values)]
cells_gdf = gpd.GeoDataFrame(geometry=points)

# Ball query
query_point = Point(1500, 2300).buffer(100)  # 100m radius
mask = cells_gdf.intersects(query_point)
nearby_heads = grid.head.where(mask)
```

Alternative using geopandas spatial index:

```python
# More efficient for large grids
nearby_indices = cells_gdf.sindex.query(query_point, predicate='intersects')
```

Perhaps consider exposing this via an accessor so the user doesn't have to explicitly create a `GeoDataFrame`.

#### 3D (x, y, z)

Given the geospatial index soon to be merged into flopy 3.x,  we can use the pre-built scipy.spatial.cKDTree it provides:

```python
from scipy.spatial import cKDTree

# Build KD-tree from 3D cell centers
centers_3d = np.column_stack([
    grid.x.values.ravel(),
    grid.y.values.ravel(),
    grid.z.values.ravel()
])
tree = cKDTree(centers_3d)

# Ball query
query_point = (1500, 2300, 45)
radius = 100
indices = tree.query_ball_point(query_point, radius)

# Create mask and apply
mask = np.zeros(grid.shape, dtype=bool)
mask.ravel()[indices] = True
nearby_cells = grid.head.where(mask)
```

Consider also exposing this via an xarray accessor, e.g.

```python
cells = grid.head.spatial.query_ball(point=(x, y, z), radius=100)
```

Probably also worth a method on the `Grid` classes:

```python
# Add method to StructuredGrid class
mask = grid.query_ball(point=(x, y, z), radius=100)
cells = grid.head.where(mask)
```

### Elevation-Based Slicing

```python
# Extract vertical profile at x=250, y=650.
# Currently works - returns all z values at that (x, y)
profile = grid.head.sel(x=250, y=650, method='nearest')

# With z-slicing: get only specific elevation range
profile_shallow = grid.head.sel(x=250, y=650, z=slice(80, 100))

# Select all cells in water table zone (elevation 40-60)
wt_zone = grid.head.sel(z=slice(40, 60))
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
