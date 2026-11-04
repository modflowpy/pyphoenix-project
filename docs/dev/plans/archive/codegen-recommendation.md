# Code Generation: Final Recommendation

## Your Question

> "We will eventually be generating the MF6 object model from DFN files. So ideally, we'd keep the generated files minimal, and move as much shared logic into base classes or shared functions. Does this impact your recommendations regarding validators? The array structuring logic is generic, the only thing that varies is the array's dimensions."

## Direct Answer

**This actually STRENGTHENS the case for pydantic.** Here's why:

### With Pydantic: Zero Validation Code in Generated Classes

Pydantic's `model_validator` decorator on the base class means:
- ✅ **All validation logic lives in the base class**
- ✅ **Generated classes are just field declarations**
- ✅ **No duplication of `structure_array` logic**
- ✅ **Validator runs automatically for all subclasses**

### Example: Generated Code

```python
# Auto-generated from npf.dfn - JUST FIELD DECLARATIONS!
class Npf(Package):
    save_flows: Annotated[bool, MF6Field(block='options', default=False)]

    icelltype: Annotated[
        NDArray[np.int64],
        MF6Array(dims=('nodes',), dtype=np.int64, block='griddata')
    ]

    k: Annotated[
        NDArray[np.float64],
        MF6Array(dims=('nodes',), dtype=np.float64, block='griddata')
    ]
```

**That's it.** No validators, no converters, no logic. Just metadata.

### How It Works

In your **base library** (not generated):

```python
class Package(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def structure_all_arrays(cls, data, info):
        """
        Runs automatically for ALL Package subclasses.
        Inspects model_fields, finds arrays, calls structure_array_generic.
        """
        context = info.context or {}

        for field_name, field_info in cls.model_fields.items():
            metadata = field_info.json_schema_extra or {}

            if metadata.get('mf6_type') == 'array':
                data[field_name] = structure_array_generic(
                    value=data[field_name],
                    dims=metadata['dims'],
                    dtype=metadata['dtype'],
                    context=context
                )

        return data
```

**One method, all packages get it for free.**

---

## Comparison to attrs

### attrs + cattrs Approach

**Generated code:**
```python
@define
class Npf(Package):
    save_flows: bool = field(default=False, metadata={'block': 'options'})

    icelltype: NDArray[np.int64] = mf6_array(  # ← Still need to call helper
        dims=('nodes',),
        dtype=np.int64,
        block='griddata'
    )

    k: NDArray[np.float64] = mf6_array(  # ← Repeated for every array
        dims=('nodes',),
        dtype=np.float64,
        block='griddata'
    )
```

**Issues:**
- Still need `mf6_array(...)` call for every array field
- Converter attachment is in generated code
- Helper function reduces duplication but doesn't eliminate it

### pydantic Approach

**Generated code:**
```python
class Npf(Package):
    save_flows: bool = Field(default=False)

    icelltype: Annotated[NDArray[np.int64], MF6Array(dims=('nodes',), ...)]
    k: Annotated[NDArray[np.float64], MF6Array(dims=('nodes',), ...)]
```

**Benefits:**
- Just metadata, no function calls
- Base class handles everything
- Truly minimal

---

## Code Generator Template

With pydantic, your template is **simpler**:

```jinja2
# Auto-generated from {{ dfn_file }}
from typing import Annotated
from numpy.typing import NDArray
import numpy as np
from flopy4.base import Package, MF6Array, MF6Field

class {{ class_name }}(Package):
    {% for field in fields %}
    {{ field.name }}: Annotated[
        {{ field.python_type }},
        {{ field.factory }}({{ field.metadata_args }})
    ]
    {% endfor %}
```

**That's the entire template.** No logic for converter attachment, no special handling for arrays vs scalars. Just iterate fields and emit declarations.

---

## Revised Recommendation

Given **code generation is your goal**:

### Choose: Pydantic with model_validator (Option 2)

**Reasons:**
1. ✅ **Absolute minimum generated code** - just field declarations
2. ✅ **All validation in base class** - 1 method, ~50 lines
3. ✅ **Simpler code generator** - no complex logic in template
4. ✅ **Easy to maintain** - change validation logic once, all packages updated
5. ✅ **Schema-first design** - metadata is in `json_schema_extra`

### Your Structure

```
flopy4/
├── base/
│   ├── __init__.py
│   ├── package.py         # ← Package base class with model_validator
│   ├── fields.py          # ← MF6Array, MF6Field factories
│   └── validation.py      # ← structure_array_generic (500 lines)
│
├── mf6/
│   ├── gwf/
│   │   ├── npf.py        # ← GENERATED: ~40 lines, just fields
│   │   ├── dis.py        # ← GENERATED: ~60 lines, just fields
│   │   └── ...           # ← All generated, all minimal
│   └── ...
│
└── codegen/
    └── dfn_to_python.py   # ← Code generator (simple template)
```

### Base Class (~50 lines total validation logic)

```python
# flopy4/base/package.py
class Package(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True
    )

    parent: Any = Field(default=None, exclude=True)

    @model_validator(mode='before')
    @classmethod
    def structure_all_arrays(cls, data, info):
        # ~30 lines of introspection + calling structure_array_generic
        ...

    def to_dataset(self) -> xr.Dataset:
        # Generic implementation (~20 lines)
        ...
```

### Generated Class (~40 lines total, zero logic)

```python
# flopy4/mf6/gwf/npf.py - AUTO-GENERATED
class Npf(Package):
    # ~10 field declarations
    # That's it!
```

---

## Migration Path

1. **Week 1:** Build base infrastructure
   - `Package` base class with `model_validator`
   - Port `structure_array` → `structure_array_generic`
   - Create `MF6Array`, `MF6Field` factories

2. **Week 2:** Build code generator
   - Simple Jinja2 template (easier than current attrs version!)
   - DFN parser (may already exist)
   - Generate a few test packages

3. **Week 3:** Regenerate all packages
   - Run generator on all DFN files
   - Test that validation works identically
   - Update tests

4. **Week 4:** Polish
   - Documentation
   - Edge cases
   - Schema generation refinements

**Total: ~4 weeks** for complete migration including code generator.

---

## Bottom Line

**For code generation, pydantic is objectively better:**

| Metric | attrs + cattrs | pydantic |
|--------|---------------|----------|
| Lines per generated class | ~60 | ~40 |
| Validation code in generated class | Converter calls | 0 |
| Generator template complexity | Medium | Low |
| Duplication of structure logic | Via helper | None |
| Changes to validation logic | Regenerate all | Change base class only |

The `model_validator` pattern is **exactly what you need** for minimal code generation.

---

## Demo

Run: `pixi run -e dev python codegen_architecture.py`

This shows:
- DIS and NPF classes with **zero validation code**
- Base class validator that **runs automatically**
- Generic `structure_array_generic` function used for all arrays
- Confirmation that generated classes are minimal

**Try it and see** - this is the architecture I recommend.
