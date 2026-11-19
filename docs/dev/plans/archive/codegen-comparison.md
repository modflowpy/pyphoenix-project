# Code Generation: attrs vs pydantic

## The Problem

You're generating MF6 classes from DFN files. Requirements:
1. **Minimal generated code** - DFN → Python should be simple
2. **No duplicated validation logic** - `structure_array` is generic
3. **Parameterized by metadata** - only dimensions/dtype vary per field

## Solution Comparison

### Option 1: attrs with cattrs (Current Approach)

#### Base Library (not generated)
```python
from cattrs import Converter
from attrs import define, field

# Generic structuring function (500+ lines, exists once)
def structure_array(value, self_, field, *, dims=None):
    # All your complex logic here
    ...

# Helper for generated code
def mf6_array(dims, dtype, block, **kwargs):
    """Factory that attaches converter."""
    return field(
        metadata={'dims': dims, 'block': block, **kwargs},
        converter=Converter(
            structure_array,
            takes_self=True,
            takes_field=True
        )
    )
```

#### Generated Code
```python
# GENERATED from DIS.dfn
@define
class Dis(Package):
    nlay: int = field(metadata={'block': 'dimensions'})
    nrow: int = field(metadata={'block': 'dimensions'})
    ncol: int = field(metadata={'block': 'dimensions'})

    delr: NDArray[np.float64] = mf6_array(
        dims=('ncol',),
        dtype=np.float64,
        block='griddata',
        netcdf=True
    )

    delc: NDArray[np.float64] = mf6_array(
        dims=('nrow',),
        dtype=np.float64,
        block='griddata',
        netcdf=True
    )

    top: NDArray[np.float64] = mf6_array(
        dims=('nrow', 'ncol'),
        dtype=np.float64,
        block='griddata',
        netcdf=True
    )

    botm: NDArray[np.float64] = mf6_array(
        dims=('nlay', 'nrow', 'ncol'),
        dtype=np.float64,
        block='griddata',
        netcdf=True
    )
```

**Analysis:**
- ✅ Generic `structure_array` logic in one place
- ✅ Helper function (`mf6_array`) minimizes repetition
- ⚠️ Still need to call `mf6_array(...)` for every array field
- ⚠️ Converter attachment is in generated code (minor)
- Lines per class: ~60 (field declarations + converter attachments)

---

### Option 2: pydantic with model_validator (Recommended)

#### Base Library (not generated)
```python
from pydantic import BaseModel, Field, model_validator
from typing import Annotated

# Generic structuring function (500+ lines, exists once)
def structure_array_generic(value, field_name, dims, dtype, context):
    # All your complex logic here
    ...

# Field factory (just metadata)
def MF6Array(dims, dtype, block, **kwargs):
    """Just stores metadata - NO validation logic."""
    return Field(json_schema_extra={
        'mf6_type': 'array',
        'dims': dims,
        'dtype': dtype,
        'block': block,
        **kwargs
    })

# Base class with generic validator
class Package(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True
    )

    @model_validator(mode='before')
    @classmethod
    def structure_all_arrays(cls, data, info):
        """
        Generic validator that runs for ALL Package subclasses.
        Inspects model_fields, finds arrays, structures them.
        """
        context = info.context or {}

        for field_name, field_info in cls.model_fields.items():
            if field_name not in data:
                continue

            metadata = field_info.json_schema_extra or {}

            # Only process array fields
            if metadata.get('mf6_type') == 'array':
                data[field_name] = structure_array_generic(
                    value=data[field_name],
                    field_name=field_name,
                    dims=metadata['dims'],
                    dtype=metadata['dtype'],
                    context=context
                )

        return data
```

#### Generated Code
```python
# GENERATED from DIS.dfn
class Dis(Package):
    nlay: Annotated[int, Field(json_schema_extra={'block': 'dimensions'})]
    nrow: Annotated[int, Field(json_schema_extra={'block': 'dimensions'})]
    ncol: Annotated[int, Field(json_schema_extra={'block': 'dimensions'})]

    delr: Annotated[
        NDArray[np.float64],
        MF6Array(dims=('ncol',), dtype=np.float64, block='griddata', netcdf=True)
    ]

    delc: Annotated[
        NDArray[np.float64],
        MF6Array(dims=('nrow',), dtype=np.float64, block='griddata', netcdf=True)
    ]

    top: Annotated[
        NDArray[np.float64],
        MF6Array(dims=('nrow', 'ncol'), dtype=np.float64, block='griddata', netcdf=True)
    ]

    botm: Annotated[
        NDArray[np.float64],
        MF6Array(dims=('nlay', 'nrow', 'ncol'), dtype=np.float64, block='griddata', netcdf=True)
    ]
```

**Analysis:**
- ✅ Generic `structure_array_generic` logic in one place
- ✅ **ZERO validation code in generated classes**
- ✅ Base class validator runs automatically for all subclasses
- ✅ Field factory is pure metadata (no converter attachment)
- ✅ Can make even more concise (see Option 3)
- Lines per class: ~50 (pure field declarations)

---

### Option 3: pydantic with Custom Type (Advanced, Most Concise)

#### Base Library
```python
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

class MF6ArrayType:
    """
    Custom type that handles validation automatically.
    This is the most advanced pydantic pattern.
    """
    def __init__(self, dims, dtype, block, **metadata):
        self.dims = dims
        self.dtype = dtype
        self.block = block
        self.metadata = metadata

    def __get_pydantic_core_schema__(
        self,
        source_type,
        handler: GetCoreSchemaHandler
    ):
        """Define how to validate this type."""
        def validate(value, info):
            return structure_array_generic(
                value,
                dims=self.dims,
                dtype=self.dtype,
                context=info.context
            )

        return core_schema.with_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: x.tolist() if hasattr(x, 'tolist') else x
            )
        )
```

#### Generated Code
```python
# GENERATED from DIS.dfn - MOST CONCISE VERSION
class Dis(Package):
    nlay: int
    nrow: int
    ncol: int

    delr: MF6ArrayType(dims=('ncol',), dtype=np.float64, block='griddata')
    delc: MF6ArrayType(dims=('nrow',), dtype=np.float64, block='griddata')
    top: MF6ArrayType(dims=('nrow', 'ncol'), dtype=np.float64, block='griddata')
    botm: MF6ArrayType(dims=('nlay', 'nrow', 'ncol'), dtype=np.float64, block='griddata')
```

**Analysis:**
- ✅ **Most concise generated code possible**
- ✅ Validation logic in type definition
- ✅ Type hints are the field definition
- ⚠️ More advanced pydantic pattern (steeper learning curve)
- Lines per class: ~40 (absolute minimum)

---

## Side-by-Side Comparison

### Generated Class: NPF Package

#### attrs + cattrs
```python
@define
class Npf(Package):
    save_flows: bool = field(
        default=False,
        metadata={'block': 'options'}
    )

    icelltype: NDArray[np.int64] = mf6_array(
        dims=('nodes',),
        dtype=np.int64,
        block='griddata',
        netcdf=True,
        longname='cell type'
    )

    k: NDArray[np.float64] = mf6_array(
        dims=('nodes',),
        dtype=np.float64,
        block='griddata',
        netcdf=True,
        longname='hydraulic conductivity'
    )
```

#### pydantic (Option 2)
```python
class Npf(Package):
    save_flows: Annotated[
        bool,
        Field(default=False, json_schema_extra={'block': 'options'})
    ]

    icelltype: Annotated[
        NDArray[np.int64],
        MF6Array(
            dims=('nodes',),
            dtype=np.int64,
            block='griddata',
            netcdf=True,
            longname='cell type'
        )
    ]

    k: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=('nodes',),
            dtype=np.float64,
            block='griddata',
            netcdf=True,
            longname='hydraulic conductivity'
        )
    ]
```

#### pydantic (Option 3 - Custom Type)
```python
class Npf(Package):
    save_flows: bool = False

    icelltype: MF6ArrayType(
        dims=('nodes',),
        dtype=np.int64,
        block='griddata',
        longname='cell type'
    )

    k: MF6ArrayType(
        dims=('nodes',),
        dtype=np.float64,
        block='griddata',
        longname='hydraulic conductivity'
    )
```

---

## Key Differences for Code Generation

| Aspect | attrs + cattrs | pydantic (Option 2) | pydantic (Option 3) |
|--------|---------------|---------------------|---------------------|
| **Validation code in generated class** | Converter attachment | None | None |
| **Lines per class** | ~60 | ~50 | ~40 |
| **Validation logic location** | `mf6_array()` helper | Base class `model_validator` | Custom type `__get_pydantic_core_schema__` |
| **Readability** | Good | Good | Excellent |
| **Type safety** | Good | Excellent | Excellent |
| **Schema generation** | Custom code needed | Automatic (with caveats) | Automatic |
| **Learning curve** | Low | Medium | High |

---

## Recommendation for Code Generation

**Use pydantic Option 2** (model_validator on base class):

### Why?

1. **Zero validation code in generated classes** - they're pure declarations
2. **All complexity in base class** - easy to maintain and test
3. **Clear and explicit** - easier than Option 3 for team to understand
4. **Good balance** - not too magical, not too verbose

### Code Generator Output

Your DFN → Python generator would emit:

```python
# Auto-generated from {package}.dfn
# DO NOT EDIT - regenerate from DFN file

from typing import Annotated
from numpy.typing import NDArray
import numpy as np
from flopy4.base import Package, MF6Array, MF6Field

class {ClassName}(Package):
    {for field in fields}
    {field.name}: Annotated[
        {field.python_type},
        {field.factory}({field.metadata})
    ]
    {endfor}
```

**Simple template**, minimal logic, easy to maintain.

### Example Generated Output

```python
# Auto-generated from npf.dfn
# DO NOT EDIT

from typing import Annotated
from numpy.typing import NDArray
import numpy as np
from flopy4.base import Package, MF6Array, MF6Field

class Npf(Package):
    save_flows: Annotated[bool, MF6Field(block='options', default=False)]
    icelltype: Annotated[NDArray[np.int64], MF6Array(dims=('nodes',), dtype=np.int64, block='griddata')]
    k: Annotated[NDArray[np.float64], MF6Array(dims=('nodes',), dtype=np.float64, block='griddata')]
```

That's it. **No validation code**, no converters, no complex logic. Just field declarations with metadata.

---

## Migration Path

If you choose pydantic:

1. **Build base class** with `model_validator` (~100 lines)
2. **Port `structure_array`** to `structure_array_generic` (~500 lines, mostly copy-paste)
3. **Update code generator** to emit pydantic classes (simpler template than attrs!)
4. **Regenerate all packages** from DFN files
5. **Test** - validation should work identically

Estimated effort: **1-2 weeks** for the base infrastructure, then regeneration is instant.

---

## Bonus: Even More Concise with Defaults

You can make common patterns even simpler:

```python
# In base library
def GridDataArray(dims, dtype=np.float64, **kwargs):
    """Shortcut for griddata block arrays."""
    return MF6Array(dims=dims, dtype=dtype, block='griddata', netcdf=True, **kwargs)

# Generated code becomes:
class Npf(Package):
    k: Annotated[NDArray[np.float64], GridDataArray(dims=('nodes',))]
    icelltype: Annotated[NDArray[np.int64], GridDataArray(dims=('nodes',), dtype=np.int64)]
```

Even more concise!
