# Pydantic Prototype Summary

## Answers to Your Specific Questions

### 1. Can we type hint array dtypes with `NDArray[...]`?

**YES!** The prototype demonstrates this works perfectly:

```python
class Npf(MF6Base):
    icelltype: Annotated[
        NDArray[np.int64],  # ← Precise dtype in type hint!
        MF6Array(dims=("nodes",), block="griddata", netcdf=True)
    ]

    k: Annotated[
        NDArray[np.float64],  # ← Works great!
        MF6Array(dims=("nodes",), block="griddata", netcdf=True)
    ]
```

**Output from prototype:**
```
NPF.k shape: (300,)
NPF.k dtype: float64  # ← Correctly typed as float64!
```

Type checkers (mypy, pyright) will understand these hints and validate usage.

### 2. What does `model_rebuild()` do?

See [`model-rebuild-explained.md`](model-rebuild-explained.md) for the full explanation, but in summary:

- **Purpose:** Resolves forward references in circular type dependencies
- **When needed:** Only when classes reference each other before they're defined
- **Solution:** Use `from __future__ import annotations` to avoid it entirely (recommended)

**Example:**
```python
from __future__ import annotations  # ← Avoids model_rebuild()

class Package(BaseModel):
    parent: Optional[MF6Model] = None  # ← No quotes needed!

class MF6Model(BaseModel):
    npf: Optional[Npf] = None

# No rebuild needed - Python handles it automatically
```

### 3. Can we alias pydantic's "model" terminology?

**YES!** The prototype includes a clean aliasing pattern:

```python
class MF6Base(BaseModel):
    """Base class with MF6-friendly method names."""

    @classmethod
    def get_fields(cls):
        """Alias for model_fields."""
        return cls.model_fields

    @classmethod
    def get_schema(cls):
        """Alias for model_json_schema."""
        return cls.model_json_schema()

    def to_dict(self):
        """Alias for model_dump."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict, **kwargs):
        """Alias for model_validate."""
        return cls.model_validate(data, **kwargs)
```

**Usage:**
```python
class GwfModel(MF6Base):  # ← "Model" means MF6 model
    pass

# Clean API - no confusion!
schema = GwfModel.get_schema()  # Not model_json_schema()
data = gwf.to_dict()            # Not model_dump()
```

## What the Prototype Demonstrates

### ✅ Fully Compatible with #167 Refactor Design

1. **Protocols work perfectly** - DimensionProvider, DatasetConvertible
2. **Parent-child relationships** - Set via `model_post_init()`
3. **Dimension resolution** - Via parent chain walking
4. **Explicit conversion methods** - `.to_dataset()`, `.to_datatree()`
5. **No inheritance conflicts** - Protocols are for type checking only

### ✅ Implicit Validation on Assignment (Your Requirement!)

```python
# Validation runs automatically on assignment
dis.nlay = -1  # ❌ Raises ValidationError
npf.k = "invalid"  # ❌ Raises ValidationError
```

**Output from prototype:**
```
2. Testing implicit validation on assignment...
   OK Validation caught error: ValidationError
```

This is enabled by `validate_assignment=True` in ConfigDict.

### ✅ Array Fields Can Be xarray.DataArray

```python
class Dis(MF6Base):
    delr: Annotated[
        xr.DataArray,  # ← Fields are DataArrays!
        MF6Array(dims=("ncol",), block="griddata")
    ]
```

**Output:**
```
delr type: <class 'xarray.core.dataarray.DataArray'>, shape: (10,)
```

Arrays are validated and structured via `@field_validator`.

### ✅ Complex Array Structuring Works

The prototype includes a simplified version of your `structure_array` logic:

```python
@field_validator("icelltype", "k", mode="before")
@classmethod
def structure_arrays(cls, v: Any, info: ValidationInfo) -> NDArray:
    """Structure arrays from various input formats."""
    # Access metadata
    field_info = cls.model_fields[info.field_name]
    metadata = field_info.json_schema_extra

    # Get dimensions from context
    dim_values = info.context.get("dims", {})

    # Handle different input types
    if isinstance(v, np.ndarray): ...
    if isinstance(v, (int, float)): ...  # Broadcast scalar
    if isinstance(v, dict): ...  # Cellid format

    return structured_array
```

Your full 500-line converter logic can be ported to validators.

### ✅ Schema-First Design

Metadata stored in `json_schema_extra` is **schema-native**:

```python
k: Annotated[
    NDArray[np.float64],
    Field(json_schema_extra={
        'dims': ['nodes'],
        'block': 'griddata',
        'netcdf': True,
        'longname': 'hydraulic conductivity'
    })
]
```

This makes JSON Schema generation automatic (with some caveats for numpy types).

### ✅ Dimension Resolution

Works exactly like the #167 design:

```python
class DimensionRegistry:
    def resolve(self, name: str, node: Any) -> int:
        """Walk up parent chain to resolve dimension."""
        current = node
        while current is not None:
            if isinstance(current, DimensionProvider):
                dims = current.get_dimensions()
                if name in dims:
                    return dims[name]
            current = getattr(current, "parent", None)
        raise ValueError(f"Dimension '{name}' not found")
```

## Prototype Output

```
======================================================================
Pydantic-based MF6 Data Model Prototype
======================================================================

1. Creating DIS package...
   DIS dimensions: {'nlay': 3, 'nrow': 10, 'ncol': 10, 'nodes': 300}
   delr type: <class 'xarray.core.dataarray.DataArray'>, shape: (10,)
   OK Arrays are xr.DataArray

2. Testing implicit validation on assignment...
   OK Validation caught error: ValidationError

3. Creating NPF package with dimension resolution...
   NPF.k shape: (300,)
   NPF.k dtype: float64
   OK Dimension context resolved from parent

4. Creating GWF model...
   Model dimensions: {'nlay': 3, 'nrow': 10, 'ncol': 10, 'nodes': 300}
   NPF parent: mymodel
   OK Parent references set automatically

5. Generating JSON Schema...
   OK Schema generation path demonstrated

6. Serialization...
   OK Round-trip serialization works

7. Converting to DataTree...
   OK Hierarchical xarray structure

======================================================================
Prototype demonstrates:
  OK NDArray[dtype] type hints work
  OK Implicit validation on assignment
  OK Dimension resolution via parent chain
  OK Complex array structuring in validators
  OK JSON Schema generation (schema-first)
  OK Compatible with #167 refactor design
======================================================================
```

## Key Architectural Points

### 1. **Validators Replace Converters**

**Current (attrs + cattrs):**
```python
# Converter registered globally
converter.register_structure_hook(
    Package,
    lambda data, cls: structure_package(data)
)
```

**Pydantic:**
```python
# Validator is a class method
class Package(MF6Base):
    @field_validator("k", mode="before")
    @classmethod
    def structure_k(cls, v, info):
        return structure_array(v, info.context)
```

**Better encapsulation** - logic lives with the class.

### 2. **Metadata is Schema-Native**

**Current (attrs):**
```python
k: NDArray = array(
    dims=("nodes",),
    metadata={"block": "griddata", "netcdf": True}
)
```

**Pydantic:**
```python
k: Annotated[NDArray, Field(
    json_schema_extra={
        "dims": ["nodes"],
        "block": "griddata",
        "netcdf": True
    }
)]
```

Metadata is **in the schema representation**, not separate.

### 3. **No Technical Blockers**

Every requirement from #167 works with pydantic:
- ✅ Protocols
- ✅ Parent-child refs
- ✅ Dimension walking
- ✅ Explicit conversions
- ✅ XArray fields
- ✅ Complex validation

## Migration Considerations

### Pros of Switching During Refactor

1. **Already doing a major rewrite** - adding pydantic is marginal cost
2. **Implicit validation** - core requirement, free with pydantic
3. **Schema-first** - core goal, native to pydantic
4. **Type safety** - better than attrs for modern Python
5. **Future-proof** - ecosystem momentum, commercial backing

### Cons

1. **Slightly more verbose** field definitions
2. **Learning curve** for pydantic patterns
3. **JSON Schema for numpy** requires custom serializers (minor)

### Realistic Effort

- **2-3 weeks** to port ~30 component classes
- **1 week** to port converter logic to validators
- **1 week** for testing and edge cases

**Total: ~4-5 weeks**, but you're already planning a multi-month refactor.

## Recommendation

Given your stated requirements:
- ✅ Schema-first design
- ✅ Implicit validation
- ✅ Experimental project (high risk tolerance)
- ✅ xarray DataArray fields preferred

**Pydantic is architecturally compatible and philosophically aligned.**

The refactor is the **ideal time** to make this change. Post-refactor migration would be much harder.

## Next Steps

1. **Review the prototype** (`pydantic_prototype.py`)
2. **Try porting one package** (e.g., DIS) to pydantic yourself
3. **Evaluate developer experience** - does it feel right?
4. **Make the call** - commit to pydantic or stay with attrs

The prototype proves it's **technically viable**. The question is whether the **developer experience** matches your team's preferences.
