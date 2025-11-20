# Array Converter Design Document

## Overview

Design for refactoring `flopy4.mf6.converter.structure.structure_array()` to support multiple sparse/dense array formats from flopy 3.x while returning xarray DataArrays with proper metadata.

## Current State

**Location**: `flopy4/mf6/converter/structure.py:13`

**Current Capabilities**:
- Handles dict-based sparse arrays with stress period keys: `{0: {cellid: value}, 1: {...}}`
- Returns numpy arrays or sparse COO arrays based on size threshold
- Resolves dimensions from model context

**Current Limitations**:
- Does NOT return `xr.DataArray` (returns raw numpy/sparse)
- Only supports dictionary input
- Limited to very specific dict format
- No support for list-based formats
- No duck array pass-through
- No grid reshaping (structured ↔ unstructured)

## Requirements

### Supported Input Formats

#### 1. Stress Period Dictionary (with fill-forward)
```python
# Sparse stress period specification - each fills forward
{0: data1, 5: data2, 10: data3}
# SP 0-4 use data1, SP 5-9 use data2, SP 10+ use data3

# Single entry fills to all periods
{0: data1}  # All stress periods use data1
```

#### 2. Layer Dictionary
```python
# Simple layered values
{0: 100.0, 1: 90.0, 2: 85.0}

# With metadata
{0: {'data': array1, 'factor': 1.0, 'iprn': 1},
 1: {'data': array2, 'factor': 1.0, 'iprn': 1}}
```

#### 3. Mixed Dict Value Types
```python
# Values can be different types in same dict
{
    0: xr.DataArray(..., dims=['nlay', 'nrow', 'ncol']),  # xarray
    5: np.array([[100.0], [90.0]]),                       # numpy
    10: [[95.0], [85.0]],                                 # list
    15: 0.004                                             # scalar
}
```

#### 4. List-Based Formats
```python
# Simple list (layers/periods)
[100.0, 90.0, 85.0]

# Nested lists (structured)
[[100.0], [90.0, 90.0, 90.0, ...]]

# Fully nested (layer → row → col)
[[[1.0, 2.0], [3.0, 4.0]], [[5.0, 6.0], [7.0, 8.0]]]
```

#### 5. Duck Arrays (xarray, numpy, sparse)
```python
# xarray with named dimensions
xr.DataArray(data, dims=['nper', 'nodes'])

# numpy array (validated by shape only)
np.array(shape=(10, 1000))

# sparse array
sparse.COO(coords, data, shape=shape)
```

#### 6. Scalars
```python
# Constant value (broadcast to full shape)
0.004
```

#### 7. External File Metadata
```python
{'filename': 'strt.txt', 'factor': 1.0, 'data': [...], 'binary': True}
```

#### 8. DataFrame (from stress_period_data property)
```python
# Structured grid format (from package.stress_period_data)
pd.DataFrame({
    'kper': [0, 0, 1, 1],
    'layer': [0, 1, 0, 1],
    'row': [0, 9, 0, 9],
    'col': [0, 9, 0, 9],
    'head': [10.0, 5.0, 11.0, 6.0]
})

# Unstructured grid format
pd.DataFrame({
    'kper': [0, 0, 1],
    'node': [0, 99, 0],
    'head': [20.0, 15.0, 21.0]
})

# Enables round-trip: package → stress_period_data → new package
```

### Key Features

#### Fill-Forward Logic
Sparse dictionary keys fill forward to next key or end of simulation:
- `{0: data1, 5: data2}` → SP 0-4 use `data1`, SP 5+ use `data2`
- Mimics MF6 behavior: specifying only SP 0 applies to all periods

#### Grid Reshaping (Structured ↔ Unstructured)
Most component fields use flat `nodes` dimension for grid-agnostic design:
- User provides: `(nlay, nrow, ncol)` structured
- Component expects: `(nodes,)` flat where `nodes = nlay * nrow * ncol`
- Function must reshape: `data.reshape(-1)` or `data.ravel()`

**Supported conversions**:
1. `(nlay, nrow, ncol)` → `(nodes,)`
2. `(nper, nlay, nrow, ncol)` → `(nper, nodes)`

#### Time Dimension Fill-Forward
Arrays without `nper` dimension apply to all stress periods:

**Case A: Has `nper` dimension**
```python
xr.DataArray(shape=(10, 1000), dims=['nper', 'nodes'])
# All 10 stress periods explicitly specified
```

**Case B: No `nper` dimension**
```python
xr.DataArray(shape=(1000,), dims=['nodes'])
# Broadcast to all stress periods: (nper, 1000)
```

#### Duck Array Validation

**Correct dimension names** (from Tdis/Dis components):
- Time: `nper` (not `time`)
- Structured: `nlay`, `nrow`, `ncol` (not `layer`, `row`, `col`)
- Unstructured: `nodes` (flat)

**Validation rules**:
- xarray: Check dimension names match expected
- numpy: Check shape matches expected (no named dims)
- Handle structured→flat reshaping automatically
- Raise clear errors on mismatches

### Output Format

**Primary**: `xr.DataArray` with:
- Proper dimensions from field spec (`nper`, `nodes`, etc.)
- Coordinates resolved from model context (Tdis, Dis)
- Attributes for metadata (factor, iprn, etc.)
- Underlying storage: sparse COO or dense numpy

**Fallback**: Raw arrays via `return_xarray=False` flag

## Implementation Strategy

### Function Signature
```python
def structure_array(
    value: dict | list | xr.DataArray | np.ndarray | float | int,
    self_,
    field,
    *,
    return_xarray: bool = True,
    sparse_threshold: int | None = None
) -> xr.DataArray | np.ndarray | sparse.COO:
    """
    Convert various array representations to structured xarray DataArrays.

    Parameters
    ----------
    value : dict | list | xr.DataArray | np.ndarray | float | int
        Input data in any supported format
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default
    return_xarray : bool, default True
        If True, return xr.DataArray; otherwise return raw array
    sparse_threshold : int | None
        Override default sparse threshold for COO vs dense

    Returns
    -------
    xr.DataArray | np.ndarray | sparse.COO
        Structured array with proper shape and metadata
    """
```

### Core Helper Functions

#### 1. Dimension Resolution
```python
def _resolve_dimensions(self_, field) -> tuple[list[str], list[int], dict]:
    """
    Get expected dims, shape, and resolved dimension values.

    Returns
    -------
    dims : list[str]
        Dimension names (e.g., ['nper', 'nodes'])
    shape : list[int]
        Resolved shape (e.g., [10, 1000])
    dim_dict : dict
        Dimension values (e.g., {'nper': 10, 'nodes': 1000})
    """
```

#### 2. Grid Reshape Detection
```python
def _detect_grid_reshape(
    value_shape: tuple,
    expected_dims: list[str],
    dim_dict: dict
) -> tuple[bool, tuple | None]:
    """
    Check if structured↔flat conversion needed.

    Returns
    -------
    needs_reshape : bool
        True if reshape required
    target_shape : tuple | None
        Target shape for reshape, or None
    """
```

#### 3. Grid Reshaping
```python
def _reshape_grid(
    data: np.ndarray | xr.DataArray,
    target_shape: tuple,
    source_dims: list[str] | None = None,
    target_dims: list[str] | None = None
) -> np.ndarray | xr.DataArray:
    """
    Perform structured↔flat grid conversion.

    Handles:
    - (nlay, nrow, ncol) → (nodes,)
    - (nper, nlay, nrow, ncol) → (nper, nodes)
    - Preserves xarray metadata if input is xarray
    """
```

#### 4. Duck Array Validation
```python
def _validate_duck_array(
    value: xr.DataArray | np.ndarray,
    expected_dims: list[str],
    expected_shape: tuple,
    dim_dict: dict
) -> xr.DataArray | np.ndarray:
    """
    Validate and optionally reshape duck arrays.

    - xarray: check dimension names, apply grid reshape if needed
    - numpy: check shape, apply reshape if needed
    - Raise clear errors on incompatibilities
    """
```

#### 5. Time Fill-Forward
```python
def _fill_forward_time(
    data: np.ndarray | xr.DataArray,
    dims: list[str],
    nper: int
) -> np.ndarray | xr.DataArray:
    """
    Add nper dimension if missing (broadcast to all periods).

    If 'nper' in dims but not in data:
        Broadcast data to (nper, *data.shape)
    Else:
        Return as-is
    """
```

#### 6. DataFrame Parser
```python
def _parse_dataframe(
    df: pd.DataFrame,
    field_name: str,
    dim_dict: dict
) -> dict[int, dict]:
    """
    Parse pandas DataFrame to dict format compatible with stress period data.

    Handles both structured (layer/row/col) and unstructured (node) coordinates.
    Enables round-trip: package → stress_period_data → new package

    Returns
    -------
    parsed : dict[int, dict]
        Dict with stress period keys mapping to cellid dicts
        Example: {0: {(0, 0, 0): 10.0, (1, 9, 9): 5.0}, ...}
    """
```

#### 7. Dict Format Parser
```python
def _parse_dict_format(
    value: dict,
    expected_dims: list[str],
    expected_shape: tuple,
    dim_dict: dict,
    field
) -> dict[int, np.ndarray]:
    """
    Parse dict format with fill-forward logic.

    Returns
    -------
    parsed : dict[int, np.ndarray]
        Dict with integer keys (period/layer) and normalized arrays

    Handles:
    - Mixed value types (xarray, numpy, list, scalar)
    - Metadata dicts ({'data': ..., 'factor': ...})
    - External file dicts ({'filename': ...})
    - Each value independently validated/reshaped
    """
```

#### 8. List Format Parser
```python
def _parse_list_format(
    value: list,
    expected_dims: list[str],
    expected_shape: tuple,
    field
) -> np.ndarray:
    """
    Parse nested list formats to numpy array.

    Handles:
    - Simple lists: [100.0, 90.0]
    - Nested lists: [[...], [...]]
    - Validates shape matches expected
    """
```

#### 9. xarray Wrapper
```python
def _to_xarray(
    data: np.ndarray | sparse.COO,
    dims: list[str],
    coords: dict,
    attrs: dict
) -> xr.DataArray:
    """
    Wrap array in xarray DataArray with metadata.

    Parameters
    ----------
    data : np.ndarray | sparse.COO
        Underlying array data
    dims : list[str]
        Dimension names
    coords : dict
        Coordinate arrays for each dimension
    attrs : dict
        Metadata attributes (factor, iprn, etc.)
    """
```

## Implementation Flow

```
structure_array(value, self_, field)
    │
    ├─→ _resolve_dimensions() → dims, shape, dim_dict
    │
    ├─→ Detect input type:
    │   ├─→ DataFrame → _parse_dataframe() → dict
    │   │                └─→ Continue processing as dict below
    │   │
    │   ├─→ dict → _parse_dict_format()
    │   │         ├─→ For each value:
    │   │         │   ├─→ xarray/numpy → _validate_duck_array()
    │   │         │   ├─→ list → _parse_list_format()
    │   │         │   └─→ scalar → broadcast
    │   │         └─→ Apply fill-forward logic
    │   │
    │   ├─→ list → _parse_list_format()
    │   │
    │   ├─→ xarray/numpy → _validate_duck_array()
    │   │                  └─→ _reshape_grid() if needed
    │   │
    │   └─→ scalar → broadcast to shape
    │
    ├─→ _fill_forward_time() if nper in dims
    │
    ├─→ Apply sparse/dense threshold logic
    │   ├─→ Large: build sparse COO
    │   └─→ Small: build dense numpy
    │
    └─→ _to_xarray() if return_xarray=True
        └─→ Return xr.DataArray or raw array
```

## Testing Strategy

### Test Cases (in `tests/test_converter_structure.py`)

1. **Dict formats**:
   - Stress period dict with nested lists
   - Stress period dict with tuples
   - Stress period dict with scalars
   - Fill-forward logic (sparse keys)
   - Layered dict with metadata
   - Mixed value types in dict

2. **List formats**:
   - Simple list
   - Nested lists (2D, 3D)
   - Shape validation

3. **Duck arrays**:
   - xarray with correct dims
   - xarray needing reshape
   - numpy arrays
   - sparse arrays

4. **Grid reshaping**:
   - Structured → flat (3D → 1D)
   - Structured → flat with time (4D → 2D)

5. **Time handling**:
   - Array with nper dimension
   - Array without nper (fill-forward)
   - Dict with sparse periods

6. **External files**:
   - Metadata dict format

7. **xarray output**:
   - Dimension names
   - Coordinate values
   - Attributes
   - Sparse vs dense backing

8. **Edge cases**:
   - Empty dicts/lists
   - Single values
   - Dimension resolution failures

9. **DataFrame integration**:
   - Round-trip structured grid: dict → stress_period_data → DataFrame → dict
   - Round-trip unstructured grid: dict → stress_period_data → DataFrame → dict
   - DataFrame with star key handling
   - Verify data preservation across round-trip

## Backward Compatibility

- `return_xarray=False` as default (backward compatible)
- `return_xarray=True` returns xarray DataArrays (new behavior)
- Existing dict format continues to work
- Update existing tests to validate xarray output

## Benefits

1. **Unified interface**: Single function for all flopy 3.x formats
2. **Better metadata**: xarray preserves dimensions, coordinates, attributes
3. **Grid agnostic**: Automatic structured↔unstructured conversion
4. **Type safety**: Clear return types for static analysis
5. **Interoperability**: xarray works with pandas, dask, netCDF, zarr
6. **Round-trip support**: DataFrame integration enables package → stress_period_data → new package
7. **Future-proof**: Easy to extend with new formats
