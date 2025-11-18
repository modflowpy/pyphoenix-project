# Custom Spatial Index for Structured Grids

**Status**: Future Enhancement
**Created**: 2025-11-18
**Related**: Issue #207 - Grid Coordinate Indexing

## Background

Currently, the `StructuredGrid` wrapper provides xarray coordinate-based indexing using:
- **x, y coordinates**: 1D with `PandasIndex` - enables `sel(x=..., y=...)`
- **z coordinate**: 3D non-dimension coordinate - attached to data but not indexed

This works well for horizontal spatial queries but doesn't support vertical (elevation-based) or full 3D spatial queries.

## Motivation

Enable advanced spatial queries that aren't currently supported:

```python
# Vertical slicing by elevation
cells = grid.botm.sel(z=slice(40, 60))  # All cells between elevations 40-60

# 3D nearest-neighbor lookup
value = grid.head.sel(x=250, y=650, z=50, method='nearest')  # Nearest cell to 3D point

# Spatial range queries
cells = grid.idomain.sel(spatial_distance=(x0, y0, z0, radius))  # Within distance
```

## Current Implementation

### Coordinate Structure
- `x`: 1D array `(ncol,)` - unique x values, one per column
- `y`: 1D array `(nrow,)` - unique y values, one per row
- `z`: 3D array `(nlay, nrow, ncol)` - cell-specific z values (varies with topography)

### Indexing
- x, y use `PandasIndex` for fast 1D lookups
- z has no index - acts as auxiliary coordinate only

### Limitations
1. Cannot select by elevation: `sel(z=50)` not supported
2. No 3D spatial nearest-neighbor queries
3. No elevation-based slicing
4. Complex spatial queries require manual iteration

## Proposed Solution: Custom Spatial Index

### Architecture

Create a `StructuredGridSpatialIndex` class that:
- Extends `xarray.core.indexes.Index`
- Handles mixed regular (x, y) and irregular (z) coordinates
- Provides efficient spatial lookups

### Key Components

```python
class StructuredGridSpatialIndex(Index):
    """
    Custom index for structured grids with x, y, z coordinates.

    Handles:
    - Regular 2D grid (x, y) with known spacing
    - Irregular 3D coordinate (z) varying by cell
    """

    def __init__(self, x, y, z, grid_shape):
        """
        Parameters
        ----------
        x : ndarray (ncol,)
            X coordinates (column centers)
        y : ndarray (nrow,)
            Y coordinates (row centers)
        z : ndarray (nlay, nrow, ncol)
            Z coordinates (cell centers, varies spatially)
        grid_shape : tuple
            (nlay, nrow, ncol)
        """
        self.x = x
        self.y = y
        self.z = z
        self.nlay, self.nrow, self.ncol = grid_shape

        # Build spatial index for fast lookups
        self._spatial_index = self._build_spatial_index()

    def _build_spatial_index(self):
        """
        Build spatial index structure.

        Options:
        1. KD-tree for 3D point cloud (all cell centers)
        2. Layered 2D R-trees (one per layer) + z-lookup
        3. Hybrid: regular grid for x,y + interval tree for z
        """
        pass

    def sel(self, labels, method=None, tolerance=None):
        """
        Select by spatial coordinates.

        Supports:
        - Individual coordinates: x=250, y=650, z=50
        - Ranges: z=slice(40, 60)
        - Method: 'nearest', 'pad', 'backfill'
        """
        pass
```

### Implementation Challenges

#### 1. **Semantic Ambiguity**

**Problem**: What does `sel(z=50)` mean when z varies in (x, y)?
- Multiple cells may have z ≈ 50 at different locations
- Need to define unambiguous behavior

**Solutions**:
- Require x, y when selecting by z: `sel(x=250, y=650, z=50)`
- Return all cells matching z: `sel(z=50)` → all cells with z ≈ 50
- Support explicit mode: `sel(z=50, mode='all' | 'first' | 'nearest_to_origin')`

#### 2. **Mixed Dimensionality**

**Problem**: x, y are regular grid (1D), z is irregular (3D)
- Standard spatial indexes assume uniform dimensionality
- Need hybrid approach

**Solution**:
- Use regular grid index for x, y (simple array lookups)
- Build spatial structure only for z within (x, y) cells
- Layered approach: find (i, j) from (x, y), then find k from z[i, j]

#### 3. **Performance**

**Problem**: Large grids (millions of cells) need efficient indexing
- Full KD-tree over all cells: O(n log n) build, O(log n) query
- May be slow for very large grids

**Solution**:
- Exploit regular grid structure for x, y (O(1) lookups)
- Only index z values within columns: O(nlay) per (x, y) location
- Consider approximate spatial hashing for very large grids

#### 4. **xarray Integration**

**Problem**: Custom indexes need to integrate with xarray's indexing machinery
- Implement required Index methods: `sel()`, `isel()`, `equals()`, `union()`, `intersection()`
- Handle coordinate alignment and broadcasting
- Support both positional and label-based indexing

**Solution**:
- Start with minimal Index subclass
- Implement only `sel()` initially
- Extend as needed based on use cases

### Spatial Index Options

#### Option 1: Full 3D KD-Tree
```python
from scipy.spatial import cKDTree

# Build point cloud of all cell centers
points = []
for k in range(nlay):
    for i in range(nrow):
        for j in range(ncol):
            points.append([x[j], y[i], z[k, i, j]])
tree = cKDTree(np.array(points))

# Query nearest
distance, idx = tree.query([x_query, y_query, z_query])
```

**Pros**: Simple, general-purpose, handles all 3D queries
**Cons**: Memory intensive, doesn't exploit regular grid structure

#### Option 2: Layered 2D + Z-Lookup (Recommended)
```python
# Exploit regular x, y grid
j = np.searchsorted(x, x_query)  # O(log ncol)
i = np.searchsorted(y, y_query)  # O(log nrow)

# Search z within this column
z_column = z[:, i, j]  # (nlay,)
k = np.argmin(np.abs(z_column - z_query))  # O(nlay)
```

**Pros**: Fast, memory-efficient, exploits structure
**Cons**: Assumes x, y selection first, more complex code

#### Option 3: Spatial Hash Grid
```python
# Divide 3D space into voxels
voxel_size = (dx, dy, dz)
hash_table = defaultdict(list)

for cell in cells:
    voxel = compute_voxel(cell.center, voxel_size)
    hash_table[voxel].append(cell)

# Query by looking in nearby voxels
```

**Pros**: Good for range queries, tunable precision
**Cons**: Complex, may need multiple voxel sizes

### Recommended Implementation

**Phase 1: Layered Index (Quick Win)**
- Implement Option 2 (layered 2D + z-lookup)
- Support `sel(x=..., y=..., z=..., method='nearest')`
- Require x, y to be specified when using z
- Fast and efficient for typical use cases

**Phase 2: Enhanced Queries**
- Support z-based slicing: `sel(z=slice(40, 60))`
- Returns all cells in elevation range
- Useful for vertical cross-sections

**Phase 3: Full 3D Index (If Needed)**
- Implement Option 1 (KD-tree) for complex queries
- Support queries without x, y specification
- Enable spatial range searches

## Example Usage

### Basic 3D Point Query
```python
# Current: must use layer index
head_value = grid.head.isel(k=0, i=5, j=3)

# With custom index: use physical coordinates
head_value = grid.head.sel(x=250, y=650, z=50, method='nearest')
```

### Elevation-Based Slicing
```python
# Select all cells in water table zone (elevation 40-60)
wt_zone = grid.head.sel(z=slice(40, 60))
# Returns: DataArray with only cells in that elevation range
```

### Vertical Cross-Section
```python
# Extract vertical profile at x=250, y=650
profile = grid.head.sel(x=250, y=650, method='nearest')
# Currently works - returns all z values at that (x, y)

# With z-slicing: get only specific elevation range
profile_shallow = grid.head.sel(x=250, y=650, z=slice(80, 100))
```

### 3D Spatial Query
```python
# Find all cells within 100m of well location (in 3D)
well_location = (x=1500, y=2300, z=45)
nearby_cells = grid.idomain.sel(
    spatial_distance=(well_location, 100),
    method='all'
)
```

## Implementation Steps

1. **Create Index Class** (`flopy4/mf6/utils/spatial_index.py`)
   - Subclass `xarray.core.indexes.Index`
   - Implement basic structure

2. **Implement Layered Lookup**
   - Start with Option 2 (regular grid + z-lookup)
   - Handle x, y, z coordinate queries

3. **Integrate with StructuredGrid**
   - Modify `_compute_world_coordinates()` to create spatial index
   - Register index with xarray dataset

4. **Add Tests**
   - Test 3D nearest-neighbor queries
   - Test elevation slicing
   - Test edge cases (out of bounds, etc.)

5. **Documentation**
   - Update user guide with spatial query examples
   - Document query semantics and limitations

## Alternative Approaches

### A. Lazy Evaluation
Instead of pre-building index, compute on-demand:
```python
def find_cell_at(grid, x, y, z):
    """Find cell nearest to (x, y, z) - computed on demand."""
    # No pre-built index, just search
```
**Pros**: No upfront cost
**Cons**: Slow for repeated queries

### B. External Spatial Library
Use existing spatial indexing libraries:
- `rtree` - R-tree spatial index
- `shapely` + `geopandas` - full GIS capabilities
- `pyvista` - 3D visualization and queries

**Pros**: Mature, well-tested
**Cons**: Heavy dependencies, may not integrate cleanly

## Success Criteria

The custom index implementation should:
1. ✓ Support `sel(x=..., y=..., z=..., method='nearest')`
2. ✓ Provide O(log n) query performance
3. ✓ Handle variable topography correctly
4. ✓ Integrate seamlessly with existing xarray operations
5. ✓ Have comprehensive test coverage
6. ✓ Be documented with clear usage examples

## Open Questions

1. **Should z-only queries be supported?** (`sel(z=50)` without x, y)
   - If yes, what should the semantics be?
   - Return all cells at that elevation?

2. **How to handle edge cases?**
   - Query point outside grid bounds
   - Multiple cells at exact same (x, y, z)
   - Inactive cells (idomain=0)

3. **Performance targets?**
   - What grid sizes should we optimize for?
   - Acceptable query time for interactive use?

4. **Integration with visualization?**
   - Should spatial index power plotting functions?
   - Integration with vtk/pyvista for 3D viz?

## References

- xarray Custom Index Guide: https://docs.xarray.dev/en/stable/internals/how-to-create-custom-index.html
- scipy.spatial.cKDTree: https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html
- rtree Documentation: https://rtree.readthedocs.io/
- Current Implementation: `flopy4/mf6/utils/grid.py:60-110`

## Future Enhancements

Beyond initial implementation:
- **Time-varying coordinates**: Support transient z coordinates (subsidence)
- **Unstructured grids**: Extend to DISV, DISU discretizations
- **Multi-grid queries**: Queries across nested grids
- **Spatial aggregation**: Average within spatial regions
- **Coordinate transformations**: Support for different CRS/projections
