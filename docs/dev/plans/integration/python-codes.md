# Extending FloPy4 to Support Python-Based Modeling Codes

**Status**: Design Proposal
**Date**: 2026-02-11
**Authors**: Design discussion with wbonelli

## Executive Summary

This document describes how to extend FloPy4's current architecture to support both binary executables (MODFLOW 6 via subprocess) and in-process execution modes (MODFLOW 6 via modflowapi, plus Python-based codes like pywatershed and timflow). The approach maintains the existing metadata-driven component specification machinery while adapting execution patterns for in-process library loading and Python code execution.

## Background

### Current Architecture

FloPy4 is designed around MODFLOW 6 with a clear separation:

1. **Generic specification machinery** (`flopy4/spec.py`)
   - `field()`, `dim()`, `coord()`, `array()`, `path()` - core attribute decorators
   - `xattree`-based hierarchical component system
   - xarray DataTree integration for data access
   - Format-agnostic metadata system

2. **MF6-specific overlay** (`flopy4/mf6/spec.py`, `flopy4/mf6/component.py`)
   - Additional metadata: `block`, `inout`, MF6-specific defaults
   - Block-based file structure mapping
   - DFN (Definition File) integration
   - Component registry (`COMPONENTS`, `FTYPES`)

3. **Execution model** (`flopy4/mf6/simulation.py`)
   - Write input files → Run subprocess → Read output files
   - Batch execution paradigm

### Alternative Execution Modes

Beyond subprocess execution, several alternative modes exist:

**1. MODFLOW 6 via modflowapi** (https://github.com/MODFLOW-ORG/modflowapi)
- **Same components**: Uses existing MF6 component definitions
- **Execution**: Loads MF6 as shared library via XMI (eXtended Model Interface)
- **I/O**: Still writes MF6 input files, but reads data directly from memory
- **API**: `ApiSimulation`, `ApiModel` classes for runtime access
- **Lifecycle**: Step-by-step control, runtime parameter modification, direct state access
- **Use cases**: Real-time monitoring, parameter optimization, model coupling

**2. Python-based modeling codes** (pywatershed, timflow)
- **Execution**: In-process Python function calls
- **I/O**: Optional file-based I/O; typical usage is in-memory
- **API**: Each code has its own object-oriented API
- **Structure**: Each code has its own conceptual model and component hierarchy
- **Lifecycle**: May support iterative stepping, on-demand queries, direct state access

### Why modflowapi is Ideal for FloPy4

modflowapi is the **perfect first integration** for several reasons:

1. **Zero Component Changes**: Uses existing `flopy4.mf6` components unchanged
   - Same `Simulation`, `Gwf`, `Dis`, `Npf`, etc. classes
   - Same input files (MF6 format)
   - Same metadata and specification machinery

2. **Pure Execution Swap**: Only difference is how simulation runs
   - Subprocess: `run_cmd("mf6")` → reads/writes files
   - modflowapi: `ModflowApi().update()` → direct memory access

3. **Incremental Adoption**: Users can mix modes for same model
   ```python
   sim = Simulation.load("model.nam")
   sim.run()  # Subprocess for production
   api_sim = sim.run(executor=ModflowApiExecutor())  # API for debugging
   ```

4. **Immediate Value**: Enables new workflows without new components
   - Real-time monitoring during simulation
   - Parameter optimization loops
   - Model coupling (MODFLOW + other codes)
   - Interactive debugging

5. **Validation**: Same MODFLOW 6 engine ensures results match
   - Easy to verify correctness
   - Builds confidence in executor abstraction
   - Proves the design pattern works

6. **USGS Control**: Both FloPy4 and modflowapi are USGS products
   - Coordinated development
   - Consistent APIs
   - Joint documentation

## Design Principles

1. **Reuse core machinery**: All codes use `dim()`, `coord()`, `array()`, etc.
2. **Code-specific overlays**: Each code adds its own metadata (like MF6 adds `block`)
3. **Pluggable execution**: Support both subprocess and in-process execution
4. **Optional I/O**: File serialization available but not required for execution
5. **Minimal core changes**: Extend through subclassing and registration, not core modifications

## Proposed Architecture

### 1. Execution Abstraction Layer

#### Current (MF6)
```python
class Simulation(Context):
    def run(self, exe: str | PathLike = "mf6", verbose: bool = False) -> None:
        with cd(self.workspace):
            out, err, ret = run_cmd(exe, verbose=verbose)
```

#### Proposed Extension

**File**: `flopy4/execution.py` (new)

```python
from abc import ABC, abstractmethod
from typing import Any, Protocol

class Executor(ABC):
    """Base class for executing model simulations."""

    @abstractmethod
    def run(self, component: "Component", verbose: bool = False) -> Any:
        """
        Execute the model.

        Parameters
        ----------
        component : Component
            The component tree to execute (Simulation, Model, etc.)
        verbose : bool
            Whether to print execution details

        Returns
        -------
        Any
            Execution results (code-specific)
        """
        pass


class SubprocessExecutor(Executor):
    """Executes models via external binary."""

    def __init__(self, exe: str | PathLike = "mf6"):
        self.exe = exe

    def run(self, component: "Component", verbose: bool = False) -> None:
        """Run via subprocess in component's workspace."""
        # Write files first (component must support write())
        component.write()

        # Execute
        with cd(component.workspace):
            out, err, ret = run_cmd(self.exe, verbose=verbose)
            if ret != 0:
                raise RuntimeError(f"Execution failed: {err}")

        return None  # Results read separately via output readers


class ModflowApiExecutor(Executor):
    """Executes MODFLOW 6 via modflowapi (XMI library interface)."""

    def __init__(self, lib_path: str | PathLike | None = None):
        """
        Parameters
        ----------
        lib_path : str | PathLike | None
            Path to MODFLOW 6 shared library.
            If None, uses default library discovery.
        """
        self.lib_path = lib_path

    def run(self, component: "Component", verbose: bool = False) -> "ApiSimulation":
        """
        Execute via modflowapi.

        Returns
        -------
        ApiSimulation
            modflowapi simulation object with runtime access
        """
        from modflowapi import ModflowApi
        from modflowapi.extensions import ApiSimulation

        # Write input files (modflowapi still reads MF6 files)
        component.write()

        # Initialize modflowapi
        mf6 = ModflowApi(
            lib_path=self.lib_path or "libmf6",
            working_directory=str(component.workspace)
        )

        # Load simulation
        mf6.initialize()

        # Wrap in ApiSimulation for high-level access
        sim = ApiSimulation.load(mf6)

        # Execute (can be customized for stepping, callbacks, etc.)
        while not mf6.finalized:
            mf6.update()

        return sim


class PythonExecutor(Executor):
    """Executes Python-based models in-process."""

    def __init__(self, runner: Callable):
        """
        Parameters
        ----------
        runner : Callable[[Component, bool], Any]
            Function that executes the model given a component tree.
            Signature: runner(component, verbose) -> results
        """
        self.runner = runner

    def run(self, component: "Component", verbose: bool = False) -> Any:
        """Execute via Python function call."""
        return self.runner(component, verbose)


# Registry for default executors by component type
DEFAULT_EXECUTORS: dict[type, Executor] = {}

def register_executor(component_type: type, executor: Executor) -> None:
    """Register default executor for a component type."""
    DEFAULT_EXECUTORS[component_type] = executor
```

#### Updated Component Base Class

**File**: `flopy4/component.py` (modify)

```python
class Component(ABC, MutableMapping):
    # ... existing code ...

    def run(
        self,
        executor: Executor | str | PathLike | Callable | None = None,
        verbose: bool = False
    ) -> Any:
        """
        Execute this component.

        Parameters
        ----------
        executor : Executor | str | PathLike | Callable | None
            How to execute:
            - None: Use default executor for this component type
            - Executor instance: Use explicitly
            - str/PathLike: Create SubprocessExecutor with this binary path
            - Callable: Create PythonExecutor with this function
        verbose : bool
            Print execution details

        Returns
        -------
        Any
            Execution results (executor-specific)
        """
        # Resolve executor
        if executor is None:
            # Look up default
            executor = DEFAULT_EXECUTORS.get(type(self))
            if executor is None:
                raise ValueError(f"No default executor for {type(self).__name__}")
        elif isinstance(executor, (str, PathLike)):
            executor = SubprocessExecutor(exe=executor)
        elif callable(executor):
            executor = PythonExecutor(runner=executor)
        elif not isinstance(executor, Executor):
            raise TypeError(f"Invalid executor type: {type(executor)}")

        # Execute
        return executor.run(self, verbose=verbose)
```

#### Usage Examples

```python
# MF6 - subprocess (backward compatible, default)
from flopy4.mf6 import Simulation

sim = Simulation(...)
sim.run()  # Uses default SubprocessExecutor("mf6")
sim.run(executor="mf6-beta")  # Custom binary
sim.run(executor="/path/to/mf6")  # Explicit path

# MF6 - modflowapi (in-process with runtime access)
from flopy4.execution import ModflowApiExecutor

sim = Simulation(...)  # Same MF6 components!
api_sim = sim.run(executor=ModflowApiExecutor())

# Access runtime data
for model in api_sim.models:
    print(f"Model: {model.name}")
    print(f"  Current time: {model.totim}")
    print(f"  Heads: {model.X}")  # Solution array
    print(f"  Shape: {model.shape}")

    # Access packages
    wel = model.wel_0
    npf = model.npf

# Advanced: Step-by-step execution with callbacks
from modflowapi import ModflowApi
from modflowapi.extensions import ApiSimulation

def run_with_monitoring(component, verbose):
    """Custom executor with real-time head monitoring."""
    component.write()

    mf6 = ModflowApi(working_directory=str(component.workspace))
    mf6.initialize()
    sim = ApiSimulation.load(mf6)

    # Step through simulation
    while not mf6.finalized:
        mf6.update()

        # Monitor heads at each timestep
        for model in sim.models:
            if verbose:
                print(f"kper={model.kper}, kstp={model.kstp}, "
                      f"max_head={model.X.max()}")

    return sim

sim.run(executor=run_with_monitoring, verbose=True)

# Pywatershed - Python function
from flopy4.pywatershed import PRMSModel

def run_pywatershed(model, verbose):
    # Convert model to pywatershed objects
    pws = model.to_pywatershed()
    pws.run()  # Or step through with pws.advance()
    return pws

model = PRMSModel(...)
results = model.run(executor=run_pywatershed)

# Or register as default
from flopy4.execution import register_executor, PythonExecutor
register_executor(PRMSModel, PythonExecutor(run_pywatershed))
```

### 2. Specification Machinery Extension

#### Core Machinery (No Changes)

The existing generic decorators in `flopy4/spec.py` remain unchanged:
- `field()` - standard attributes with metadata dict
- `dim()` - dimension attributes (wraps `field()` with `coord` metadata)
- `coord()` - coordinate attributes
- `array()` - array attributes with `dims` metadata
- `path()` - path attributes

These all populate `field.metadata` dict with arbitrary key-value pairs.

#### Code-Specific Overlays

Each modeling code defines its own metadata conventions by creating wrapper decorators.

**Example: MF6** (`flopy4/mf6/spec.py` - existing)
```python
def field(block: str | None = None, **kwargs):
    """MF6 field with block metadata."""
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    if block is not None:
        kwargs["metadata"]["block"] = block
    return flopy4_field(**kwargs)  # Call core field()

def array(block: str | None = None, dims: tuple = None, **kwargs):
    """MF6 array with block and dims metadata."""
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    if block is not None:
        kwargs["metadata"]["block"] = block
    return flopy4_array(dims=dims, **kwargs)  # Call core array()
```

**Example: Timflow** (`flopy4/timflow/spec.py` - new)

```python
"""Timflow-specific specification decorators."""

from flopy4.spec import field as flopy4_field
from flopy4.spec import array as flopy4_array

def field(layer_property: bool = False, **kwargs):
    """
    Timflow field with custom metadata.

    Parameters
    ----------
    layer_property : bool
        Whether this is a per-layer aquifer property
    **kwargs
        Passed to core field()
    """
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    kwargs["metadata"]["layer_property"] = layer_property
    return flopy4_field(**kwargs)

def array(layer_varying: bool = False, dims: tuple = None, **kwargs):
    """
    Timflow array with layer-varying metadata.

    Parameters
    ----------
    layer_varying : bool
        Whether array varies by layer
    dims : tuple
        Array dimensions (e.g., ("nlayers",))
    **kwargs
        Passed to core array()
    """
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    kwargs["metadata"]["layer_varying"] = layer_varying
    return flopy4_array(dims=dims, **kwargs)
```

**Example: Pywatershed** (`flopy4/pywatershed/spec.py` - new)

```python
"""Pywatershed-specific specification decorators."""

from flopy4.spec import field as flopy4_field
from flopy4.spec import array as flopy4_array

def field(prms_name: str | None = None, units: str | None = None, **kwargs):
    """
    Pywatershed field with PRMS metadata.

    Parameters
    ----------
    prms_name : str
        Corresponding PRMS parameter name
    units : str
        Physical units
    **kwargs
        Passed to core field()
    """
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    if prms_name is not None:
        kwargs["metadata"]["prms_name"] = prms_name
    if units is not None:
        kwargs["metadata"]["units"] = units
    return flopy4_field(**kwargs)

def array(prms_name: str | None = None, dims: tuple = None, **kwargs):
    """
    Pywatershed array with PRMS metadata.

    Parameters
    ----------
    prms_name : str
        Corresponding PRMS parameter name
    dims : tuple
        Array dimensions (e.g., ("nhru", "nmonths"))
    **kwargs
        Passed to core array()
    """
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    if prms_name is not None:
        kwargs["metadata"]["prms_name"] = prms_name
    return flopy4_array(dims=dims, **kwargs)
```

#### Component Definitions Using Code-Specific Specs

**MF6 Example** (existing pattern):
```python
from flopy4.mf6.spec import field, dim, array
from flopy4.mf6.component import Package

@xattree
class Npf(Package):
    icelltype: NDArray[np.int32] = array(
        block="griddata",
        dims=("nlay", "nrow", "ncol"),
        default=0
    )
    k: NDArray[np.float64] = array(
        block="griddata",
        dims=("nlay", "nrow", "ncol"),
        default=1.0
    )
```

**Timflow Example** (proposed):
```python
from flopy4.timflow.spec import field, array
from flopy4.timflow.component import TimflowComponent

@xattree
class ModelMaq(TimflowComponent):
    """Multi-aquifer model."""

    kaq: NDArray[np.float64] = array(
        layer_property=True,
        dims=("nlayers",),
        default=1.0,
        longname="Aquifer hydraulic conductivity"
    )

    z: NDArray[np.float64] = array(
        layer_property=True,
        dims=("nlayers+1",),  # nlayers + 1 for tops/bottoms
        longname="Elevation of layer interfaces"
    )

    c: NDArray[np.float64] = array(
        layer_property=True,
        dims=("nlayers-1",),  # Resistance between layers
        default=1000.0,
        longname="Resistance of aquitards"
    )

    def to_timflow(self):
        """Convert to native timflow.ModelMaq object."""
        import timflow
        return timflow.ModelMaq(
            kaq=self.kaq.values,
            z=self.z.values,
            c=self.c.values
        )
```

**Pywatershed Example** (proposed):
```python
from flopy4.pywatershed.spec import field, array
from flopy4.pywatershed.component import PywatershedComponent

@xattree
class PRMSChannel(PywatershedComponent):
    """PRMS channel routing parameters."""

    K_coef: NDArray[np.float64] = array(
        prms_name="K_coef",
        dims=("nsegment", "nmonths"),
        units="hours",
        default=24.0,
        longname="Travel time coefficient"
    )

    x_coef: NDArray[np.float64] = array(
        prms_name="x_coef",
        dims=("nsegment",),
        units="fraction",
        default=0.2,
        longname="Muskingum weighting factor"
    )

    def to_pywatershed(self):
        """Convert to native pywatershed objects."""
        import pywatershed
        # Implementation depends on pywatershed API
        pass
```

### 3. I/O System Extension

#### Unified I/O Registry (Existing)

The `flopy4/uio.py` registry system already supports pluggable loaders/writers:

```python
class Registry:
    def register_loader(self, cls: type, format: str, function: Callable)
    def register_writer(self, cls: type, format: str, function: Callable)
```

#### Code-Specific I/O Formats

Each code can register its own formats while maintaining common interchange formats.

**Common formats** (all codes should support):
- `json` - Full component serialization to JSON
- `toml` - Human-readable configuration
- `yaml` - Alternative human-readable format
- `netcdf` - Array data in NetCDF format (via xarray)

**Code-specific formats**:
- `mf6` - MODFLOW 6 input file format
- `timflow-config` - Timflow configuration format (if exists)
- `prms` - PRMS parameter file format

#### Example Registration

**File**: `flopy4/timflow/__init__.py` (new)

```python
from flopy4.uio import DEFAULT_REGISTRY
from flopy4.timflow.component import TimflowComponent
from flopy4.timflow.io import load_json, write_json, load_timflow_config

# Register common formats
DEFAULT_REGISTRY.register_loader(TimflowComponent, "json", load_json)
DEFAULT_REGISTRY.register_writer(TimflowComponent, "json", write_json)

# Register timflow-specific format (if applicable)
DEFAULT_REGISTRY.register_loader(TimflowComponent, "timflow", load_timflow_config)

# Can reuse generic loaders for some formats
from flopy4.io import _load_toml, _dump_toml
DEFAULT_REGISTRY.register_loader(TimflowComponent, "toml", _load_toml)
DEFAULT_REGISTRY.register_writer(TimflowComponent, "toml", _dump_toml)
```

#### Usage Patterns

```python
# MF6 via subprocess (default, unchanged)
sim = Simulation.load("sim.nam")  # Reads MF6 files
sim.run()  # Writes input files, runs mf6 binary, reads output

# MF6 via modflowapi (same components, different execution)
from flopy4.execution import ModflowApiExecutor

sim = Simulation.load("sim.nam")  # Same as above
api_sim = sim.run(executor=ModflowApiExecutor())  # In-process execution
# Access data directly: api_sim.models[0].X (heads)

# Python codes - typical in-memory workflow (future)
model = PRMSModel(...)  # Uses pywatershed-specific components
results = model.run()  # No file I/O needed

# Optional: Export for reproducibility
model.write(format="json", path="model.json")
model.write(format="toml", path="model.toml")
```

### 4. Package Organization

Proposed directory structure:

```
flopy4/
├── spec.py                    # Core decorators (field, dim, coord, array, path)
├── component.py               # Base Component class with run() method
├── context.py                 # Base Context class
├── execution.py               # NEW: Executor classes and registry
├── uio.py                     # Unified I/O registry
├── adapters.py                # Generic adapters
│
├── mf6/                       # MODFLOW 6 support (existing)
│   ├── spec.py                # MF6-specific decorators (adds block, inout)
│   ├── component.py           # MF6 Component base with DFN support
│   ├── simulation.py          # Simulation (registers SubprocessExecutor)
│   ├── model.py               # Model base
│   ├── package.py             # Package base
│   ├── io.py                  # MF6 format I/O (_load_mf6, _write_mf6)
│   ├── execution.py           # NEW: ModflowApiExecutor implementation
│   └── ...
│
├── pywatershed/               # NEW: Pywatershed support
│   ├── __init__.py            # Register executors and I/O
│   ├── spec.py                # Pywatershed-specific decorators (prms_name, units)
│   ├── component.py           # PywatershedComponent base
│   ├── parameters.py          # PRMS parameter components
│   ├── processes.py           # Process components (channel routing, ET, etc.)
│   ├── io.py                  # PRMS format I/O
│   └── execution.py           # Pywatershed execution logic
│
└── timflow/                   # FUTURE: Timflow support
    ├── __init__.py            # Register executors and I/O
    ├── spec.py                # Timflow-specific decorators
    ├── component.py           # TimflowComponent base
    ├── model.py               # Timflow model components (ModelMaq, Model3D, etc.)
    ├── elements.py            # Analytic elements (Well, HeadLineSink, etc.)
    ├── io.py                  # Timflow I/O loaders/writers
    └── execution.py           # Timflow execution logic
```

**Note on modflowapi**: Since modflowapi uses the **same MF6 component definitions**, it doesn't need a separate package. The `ModflowApiExecutor` lives in `flopy4/mf6/execution.py` or `flopy4/execution.py` and operates on existing `flopy4.mf6.Simulation` objects.

### 5. Component Base Classes

Each code defines its own component hierarchy while inheriting core functionality.

**File**: `flopy4/mf6/component.py` (existing, minimal changes)
```python
from flopy4.component import Component as BaseComponent

class Component(BaseComponent, ABC):
    """MODFLOW 6 component with DFN support."""

    # MF6-specific features
    @classmethod
    def get_dfn(cls) -> Dfn:
        """Get MODFLOW 6 definition for this component."""
        pass

    def to_dict(self, blocks: bool = False) -> dict:
        """Convert to dict, optionally organized by MF6 blocks."""
        pass
```

**File**: `flopy4/timflow/component.py` (new)
```python
from flopy4.component import Component as BaseComponent

class TimflowComponent(BaseComponent, ABC):
    """Base for Timflow components."""

    @abstractmethod
    def to_timflow(self):
        """Convert to native timflow object."""
        pass

    @classmethod
    def from_timflow(cls, obj):
        """Create from native timflow object."""
        pass
```

**File**: `flopy4/pywatershed/component.py` (new)
```python
from flopy4.component import Component as BaseComponent

class PywatershedComponent(BaseComponent, ABC):
    """Base for Pywatershed components."""

    @abstractmethod
    def to_pywatershed(self):
        """Convert to native pywatershed object."""
        pass

    @property
    def prms_parameters(self) -> dict:
        """Get PRMS parameter name mapping."""
        params = {}
        for field in attrs.fields(type(self)):
            prms_name = field.metadata.get("prms_name")
            if prms_name:
                params[prms_name] = getattr(self, field.name)
        return params
```

## Implementation Phases

### Phase 1: Core Execution Abstraction
- [ ] Create `flopy4/execution.py` with `Executor` base class
- [ ] Implement `SubprocessExecutor` (current behavior)
- [ ] Add `Component.run()` method to base class
- [ ] Update `Simulation.run()` to use new executor system
- [ ] Maintain backward compatibility (existing MF6 code unchanged)
- [ ] Add tests for executor registry and dispatch
- [ ] Document executor API

### Phase 2: MODFLOW API Integration (Highest Priority)
- [ ] Implement `ModflowApiExecutor` class
- [ ] Add `flopy4/mf6/execution.py` module
- [ ] Create helper functions for common patterns (monitoring, optimization)
- [ ] Add optional `modflowapi` dependency to `pyproject.toml` extras
- [ ] Write tests using existing MF6 test simulations
- [ ] Create example notebooks:
  - [ ] Basic modflowapi execution
  - [ ] Real-time head monitoring
  - [ ] Parameter optimization workflow
  - [ ] Model coupling example
- [ ] Document differences between subprocess and modflowapi execution
- [ ] Benchmark performance comparison

**Rationale**: modflowapi is:
- A USGS product (we control both)
- Uses existing MF6 components (no new spec machinery needed)
- Provides immediate value (runtime access, monitoring, optimization)
- Easiest to implement (minimal new code)

### Phase 3: Pywatershed Integration
- [ ] Create `flopy4/pywatershed/` package structure
- [ ] Define `pywatershed/spec.py` decorators (add `prms_name`, `units`)
- [ ] Implement `PywatershedComponent` base class
- [ ] Create PRMS parameter components (initial subset)
- [ ] Create process components (channel, ET, etc.)
- [ ] Implement converters to/from pywatershed objects
- [ ] Create `PythonExecutor` with pywatershed runner
- [ ] Add PRMS file format I/O support
- [ ] Add JSON/TOML I/O support
- [ ] Create example notebooks
- [ ] Add optional `pywatershed` dependency to extras

### Phase 4: Documentation & Polish
- [ ] Update main documentation
- [ ] Create "Adding New Codes" developer guide
- [ ] API reference for execution system
- [ ] Tutorial notebooks for each integrated code
- [ ] Performance benchmarks (subprocess vs modflowapi vs Python codes)
- [ ] Migration guide for existing MF6 users
- [ ] Best practices guide (when to use each execution mode)

### Future Phases
- **Timflow Integration**: Similar to pywatershed, lower priority (not a USGS product)
- **Other Codes**: SWMM, MT3D-USGS, etc. can follow the same pattern

## Benefits

1. **Unified Interface**: Same component specification machinery across all codes
2. **Flexibility**: Each code customizes metadata and execution as needed
3. **Interoperability**: Common I/O formats enable data exchange
4. **Extensibility**: Adding new codes follows clear pattern
5. **Backward Compatibility**: Existing MF6 code continues to work
6. **Performance**: In-process execution eliminates file I/O overhead
7. **Developer Experience**: Consistent patterns reduce cognitive load
8. **Runtime Access** (modflowapi): Monitor and modify simulations during execution
9. **Same Components, Multiple Modes**: MF6 models can run via subprocess OR modflowapi without changes

## Open Questions

1. **Dimension Coordination**: How do we handle dimension naming conflicts?
   - MF6 uses: `nlay`, `nrow`, `ncol`
   - Timflow might use: `nlayers`
   - Pywatershed uses: `nhru`, `nsegment`
   - **Proposed**: Each code owns its dimension names; converters handle mapping

2. **Result Access Patterns**: Should results be accessed via:
   - Code-specific result objects? (`model.results.head`)
   - xarray DataArrays? (`model.data.head`)
   - Native code objects? (`model.to_timflow().head(x, y, z)`)
   - **Proposed**: All three; converters provide flexibility

3. **Testing Strategy**: How do we test without requiring external dependencies?
   - **Proposed**: Mock implementations for CI; optional integration tests with real packages

4. **Versioning**: How do we handle breaking changes in underlying Python packages?
   - **Proposed**: Version pinning in package extras (`pip install flopy4[timflow]`)

## Alternatives Considered

### Alternative 1: Separate Packages
Create `flopy4-timflow`, `flopy4-pywatershed` as separate packages.

**Pros**: Looser coupling, independent release cycles
**Cons**: Harder to share machinery, fragmented ecosystem

**Decision**: Keep in monorepo initially; can split later if needed

### Alternative 2: Pure Adapter Pattern
Don't create FloPy4 component hierarchies; just provide converters.

**Pros**: Minimal code duplication
**Cons**: Loses benefits of unified specification system, xarray integration, I/O

**Decision**: Full integration provides more value

### Alternative 3: Plugin System
Load code support dynamically via entry points.

**Pros**: External contributors can add codes
**Cons**: More complexity, harder to maintain quality

**Decision**: Direct integration initially; consider plugins later

## Success Criteria

A successful integration allows users to:

1. Define model components using declarative specifications
2. Access and manipulate data as xarray DataArrays
3. Run models in-process without file I/O (but with optional persistence)
4. Export/import using standard formats (JSON, TOML)
5. Mix components from different codes in analysis workflows
6. Extend the framework with new codes following documented patterns

## Next Steps

1. **Prototype**: Implement Phase 1 (execution abstraction) on a branch
2. **Validate**: Implement Phase 2 (modflowapi integration) to test approach
   - Use existing MF6 test cases
   - Verify same results as subprocess execution
   - Test runtime data access patterns
3. **Iterate**: Refine based on learnings from modflowapi
4. **Extend**: Add pywatershed support using proven pattern
5. **Document**: Write developer guide for adding new codes
6. **Release**: Merge when stable and tested

## References

- FloPy4 codebase: `C:/Users/wbonelli/dev/pyphoenix-project`
- MODFLOW API: https://github.com/MODFLOW-ORG/modflowapi
- Pywatershed: https://github.com/DOI-USGS/pywatershed
- Timflow: https://github.com/timflow-org/timflow
- xarray: https://docs.xarray.dev
- XMI (eXtended Model Interface): https://github.com/Deltares/xmipy
