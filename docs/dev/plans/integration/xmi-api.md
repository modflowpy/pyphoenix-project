# FloPy4 XMI API Design

**Date**: 2026-02-11
**Status**: Design Document

## Goal

Integrate modflowapi functionality into FloPy4 following these principles:

1. **Follow modflowapi's API closely** - they've figured out what users need
2. **Step-by-step execution is primary** - that's the whole point of using XMI
3. **Phase A uses modflowapi internally** - implement FloPy4 API wrapping modflowapi
4. **Phase B ports to direct xmipy** - replace internals, keep API unchanged
5. **Phase C provides backward compat** - modflowapi wraps FloPy4

## modflowapi's Actual API

Based on examination of modflowapi source code:

### ApiSimulation Properties
- **Time**: `kper`, `kstp`, `nstp`, `nper`, `totim`, `delt`
- **Models**: `model_names`, `models` (list), `get_model(name)`
- **Solutions**: `solution_id`, `solutions`, `sln`
- **Exchanges**: `exchange_names`, `get_exchange(name)`
- **Control**: `iteration`, `allow_convergence`, `ats_active`, `ats_period`
- **TDIS/ATS packages**: `tdis`, `ats`

### ApiModel Properties
- **Time**: `kper`, `kstp`, `nstp`, `nper`, `totim` (inherited from sim)
- **Grid**: `shape`, `size`, `nodetouser`, `usertonode`
- **Solution**: `X` (heads/concentrations/temperatures)
- **Packages**: `package_list`, `package_names`, `package_types`, `get_package(name)`
- **IDs**: `subcomponent_id`, `solution_id`

### Typical Workflow

```python
from modflowapi import ModflowApi
from modflowapi.extensions import ApiSimulation

# 1. Initialize
mf6 = ModflowApi(lib_path="libmf6", working_directory="./sim")
mf6.initialize()

# 2. Get high-level access
sim = ApiSimulation.load(mf6)

# 3. Step through (this is the main use case!)
while not mf6.finalized:
    mf6.update()  # Advance one timestep

    # Access data during execution
    print(f"Period {sim.kper}, Step {sim.kstp}, Time {sim.totim}")

    for model in sim.models:
        heads = model.X
        print(f"  {model.name}: head range [{heads.min()}, {heads.max()}]")

        # Could modify parameters
        wel_pkg = model.get_package("wel")
        # wel_pkg.stress_period_data = ...

# 4. Cleanup
mf6.finalize()
```

**Key insight**: Users want to loop through timesteps accessing/modifying data. A `run()` method that does everything at once defeats the purpose.

## FloPy4 XMI API (Matches modflowapi)

### XmiSimulation Class

```python
# flopy4/mf6/xmi/simulation.py
from flopy4.mf6.simulation import Simulation as BaseSimulation

class XmiSimulation(BaseSimulation):
    """
    MODFLOW 6 simulation with XMI runtime access.

    API mirrors modflowapi.extensions.ApiSimulation for familiarity.
    Use this when you need step-by-step execution control.

    Examples
    --------
    Basic step-by-step execution:

    >>> sim = XmiSimulation.load("sim.nam")
    >>> sim.initialize_xmi()
    >>> while not sim.finalized:
    ...     sim.update()
    ...     print(f"kper={sim.kper}, heads={sim.get_model('gwf').X.max()}")
    >>> sim.finalize()

    Or use convenience method:

    >>> sim.run_xmi(callback=lambda s: print(f"kper={s.kper}"))
    """

    def initialize_xmi(self, lib_path: str | None = None) -> None:
        """
        Initialize XMI library and load simulation.

        Call this before stepping through simulation.

        Parameters
        ----------
        lib_path : str, optional
            Path to MODFLOW 6 shared library.
            If None, uses default library discovery.
        """
        pass  # Implementation in phases below

    def update(self) -> None:
        """
        Advance simulation one timestep.

        Call this repeatedly in a loop to step through the simulation.
        Access runtime data between calls.
        """
        pass

    def finalize(self) -> None:
        """
        Cleanup XMI resources.

        Call this when done with simulation.
        """
        pass

    @property
    def finalized(self) -> bool:
        """Has simulation been finalized?"""
        pass

    # Time discretization properties (from modflowapi)
    @property
    def kper(self) -> int:
        """Current stress period (0-indexed)."""
        pass

    @property
    def kstp(self) -> int:
        """Current time step within stress period (0-indexed)."""
        pass

    @property
    def nstp(self) -> int:
        """Number of time steps in current stress period."""
        pass

    @property
    def nper(self) -> int:
        """Total number of stress periods."""
        pass

    @property
    def totim(self) -> float:
        """Current simulation time."""
        pass

    @property
    def delt(self) -> float:
        """Current time step length."""
        pass

    # Model access (from modflowapi)
    @property
    def model_names(self) -> list[str]:
        """List of all model names in simulation."""
        pass

    @property
    def models(self) -> list["XmiModel"]:
        """List of all models with XMI access."""
        pass

    def get_model(self, name: str) -> "XmiModel":
        """
        Get model by name with XMI runtime access.

        Parameters
        ----------
        name : str
            Model name

        Returns
        -------
        XmiModel
            Model with runtime data access
        """
        pass

    # Solution properties (from modflowapi)
    @property
    def iteration(self) -> int:
        """Current iteration number."""
        pass

    @iteration.setter
    def iteration(self, value: int):
        """Set iteration number."""
        pass

    @property
    def allow_convergence(self) -> bool:
        """Allow model to converge when solution converges."""
        pass

    @allow_convergence.setter
    def allow_convergence(self, value: bool):
        """Set allow convergence flag."""
        pass

    # Optional convenience method (not primary workflow)
    def run_xmi(
        self,
        lib_path: str | None = None,
        callback: callable | None = None
    ) -> None:
        """
        Convenience method to run simulation to completion.

        For step-by-step control (recommended), use:
        initialize_xmi() / update() / finalize() directly.

        Parameters
        ----------
        lib_path : str, optional
            Path to MODFLOW 6 shared library
        callback : callable, optional
            Function called each timestep: callback(sim)

        Examples
        --------
        >>> def monitor(sim):
        ...     print(f"kper={sim.kper}, kstp={sim.kstp}")
        >>> sim.run_xmi(callback=monitor)
        """
        self.initialize_xmi(lib_path=lib_path)
        while not self.finalized:
            self.update()
            if callback:
                callback(self)
        self.finalize()
```

### XmiModel Class

```python
# flopy4/mf6/xmi/model.py
from flopy4.mf6.model import Gwf as BaseGwf

class XmiGwf(BaseGwf):
    """
    Groundwater flow model with XMI runtime access.

    API mirrors modflowapi.extensions.ApiModel.
    """

    # Time properties (inherited from parent simulation)
    @property
    def kper(self) -> int:
        """Current stress period."""
        pass

    @property
    def kstp(self) -> int:
        """Current time step."""
        pass

    @property
    def totim(self) -> float:
        """Current simulation time."""
        pass

    # Grid properties (from modflowapi)
    @property
    def shape(self) -> tuple[int, ...]:
        """
        Model grid shape.

        Returns (nlay, nrow, ncol) for structured grids,
        (nlay, ncpl) for DISV, or (nodes,) for DISU.
        """
        pass

    @property
    def size(self) -> int:
        """Total number of cells/nodes."""
        pass

    @property
    def nodetouser(self) -> NDArray:
        """Array mapping internal nodes to user node numbering."""
        pass

    @property
    def usertonode(self) -> NDArray:
        """Array mapping user nodes to internal node numbering."""
        pass

    # Solution array (from modflowapi)
    @property
    def X(self) -> NDArray:
        """
        Solution array (hydraulic heads for GWF).

        Can be modified for warm starts or adaptive control.
        """
        pass

    @X.setter
    def X(self, value: NDArray):
        """Set solution array."""
        pass

    # Package access (from modflowapi)
    def get_package(self, name: str):
        """
        Get package with XMI runtime access.

        Parameters
        ----------
        name : str
            Package name

        Returns
        -------
        Package with runtime data access
        """
        pass
```

## Implementation Phases

### Phase A: Wrap modflowapi

Implement the FloPy4 XMI API by delegating to modflowapi internally.

**Key files**:
- `flopy4/mf6/xmi/simulation.py` - `XmiSimulation` class
- `flopy4/mf6/xmi/model.py` - `XmiGwf`, `XmiGwt`, `XmiGwe` classes

**Implementation approach**:

```python
# Phase A: XmiSimulation delegates to modflowapi
class XmiSimulation(BaseSimulation):
    def initialize_xmi(self, lib_path=None):
        """Initialize - uses modflowapi."""
        from modflowapi import ModflowApi
        from modflowapi.extensions import ApiSimulation

        self.write()  # Write MF6 input files

        # Use modflowapi
        self._mf6 = ModflowApi(
            lib_path=lib_path,
            working_directory=str(self.workspace)
        )
        self._mf6.initialize()
        self._api_sim = ApiSimulation.load(self._mf6)

    def update(self):
        """Update - delegates to modflowapi."""
        self._mf6.update()

    def finalize(self):
        """Finalize - delegates to modflowapi."""
        self._mf6.finalize()

    @property
    def finalized(self):
        """Finalized check - delegates to modflowapi."""
        return self._mf6.finalized

    @property
    def kper(self):
        """Current period - delegates to modflowapi."""
        return self._api_sim.kper

    @property
    def totim(self):
        """Current time - delegates to modflowapi."""
        return self._api_sim.totim

    # ... all other properties delegate similarly

    def get_model(self, name):
        """Get model - wraps modflowapi's ApiModel."""
        # Get FloPy4 model from component tree
        flopy_model = self[name]

        # Attach modflowapi's ApiModel for delegation
        flopy_model._api_model = self._api_sim.get_model(name)

        return flopy_model


# Phase A: XmiGwf delegates to modflowapi's ApiModel
class XmiGwf(BaseGwf):
    @property
    def X(self):
        """Solution - delegates to modflowapi."""
        return self._api_model.X

    @X.setter
    def X(self, value):
        """Set solution - delegates to modflowapi."""
        self._api_model.X = value

    @property
    def shape(self):
        """Shape - delegates to modflowapi."""
        return self._api_model.shape

    # ... all other properties delegate similarly
```

**Testing Phase A**:
- Verify FloPy4 XMI API produces same results as modflowapi
- Test all properties and methods
- Validate step-by-step execution
- Test parameter modification during execution

### Phase B: Port to Direct xmipy

Replace modflowapi delegation with direct xmipy calls. **API unchanged.**

**Port priority** (modflowapi → FloPy4):
1. Variable discovery logic (`ApiSimulation.load()`)
2. Simulation properties (kper, kstp, totim, etc.)
3. Model properties (X, shape, etc.)
4. Package access
5. Advanced features (iteration, allow_convergence, etc.)

**Implementation approach**:

```python
# Phase B: XmiSimulation uses xmipy directly
class XmiSimulation(BaseSimulation):
    def initialize_xmi(self, lib_path=None):
        """Initialize - uses xmipy directly."""
        from xmipy import XmiWrapper

        self.write()

        # Direct xmipy
        self._xmi = XmiWrapper(
            lib_path=lib_path or "libmf6",
            working_directory=str(self.workspace)
        )
        self._xmi.initialize()

        # Discover variables (ported from modflowapi)
        self._discover_variables()

    def _discover_variables(self):
        """
        Discover and cache XMI variable addresses.

        Ported from modflowapi.extensions.ApiSimulation.load()
        """
        var_names = self._xmi.get_var_names()

        # Parse variable names and populate caches
        # (Port modflowapi's parsing logic)
        pass

    def update(self):
        """Update - xmipy directly."""
        self._xmi.update()

    @property
    def kper(self):
        """Current period - xmipy directly."""
        return int(self._xmi.get_value_ptr("SIM/TDIS/KPER"))

    @property
    def totim(self):
        """Current time - xmipy directly."""
        return float(self._xmi.get_value_ptr("SIM/TDIS/TOTIM"))

    # ... other properties use direct xmipy calls
```

**Testing Phase B**:
- Run same tests as Phase A
- Verify outputs match Phase A exactly
- Performance comparison (should be similar or better)
- Remove modflowapi dependency from FloPy4

### Phase C: modflowapi Backward Compatibility

modflowapi 2.0 wraps FloPy4 XMI. Legacy code works unchanged.

```python
# modflowapi 2.0: Wrapper around FloPy4
class ModflowApi:
    def __init__(self, lib_path=None, working_directory="."):
        from flopy4.mf6.xmi import XmiSimulation

        self._sim = XmiSimulation.load(f"{working_directory}/mfsim.nam")
        self._lib_path = lib_path

    def initialize(self):
        self._sim.initialize_xmi(lib_path=self._lib_path)

    def update(self):
        self._sim.update()

    def finalize(self):
        self._sim.finalize()

    @property
    def finalized(self):
        return self._sim.finalized


class ApiSimulation:
    def __init__(self, sim: XmiSimulation):
        self._sim = sim

    @staticmethod
    def load(mf6: ModflowApi):
        return ApiSimulation(mf6._sim)

    @property
    def kper(self):
        return self._sim.kper

    # ... all properties delegate to FloPy4
```

## Task List

### Phase A: Wrap modflowapi
- [ ] Create `flopy4/mf6/xmi/` package
- [ ] Implement `XmiSimulation` class (delegates to modflowapi)
- [ ] Implement all simulation properties (kper, kstp, totim, etc.)
- [ ] Implement `get_model()` method
- [ ] Implement `XmiGwf` class (delegates to ApiModel)
- [ ] Implement all model properties (X, shape, etc.)
- [ ] Implement `get_package()` method
- [ ] Add `run_xmi()` convenience method
- [ ] Write tests (using modflowapi under hood)
- [ ] Write documentation
- [ ] Create example notebooks showing step-by-step execution

### Phase B: Port to xmipy
- [ ] Study modflowapi variable discovery logic
- [ ] Implement `_discover_variables()` (port from ApiSimulation.load())
- [ ] Port simulation properties to use xmipy directly
- [ ] Port model properties to use xmipy directly
- [ ] Port package access to use xmipy directly
- [ ] Test Phase B outputs match Phase A
- [ ] Remove modflowapi dependency from FloPy4
- [ ] Update documentation (no user-facing changes)

### Phase C: modflowapi Compatibility
- [ ] Create modflowapi 2.0 compatibility wrapper
- [ ] Implement ModflowApi wrapping XmiSimulation
- [ ] Implement ApiSimulation wrapping XmiSimulation
- [ ] Implement ApiModel wrapping XmiGwf/etc
- [ ] Add deprecation warnings
- [ ] Test legacy modflowapi examples
- [ ] Write migration guide
- [ ] Support transition period (~1 year)
- [ ] Archive modflowapi repo

## Design Decisions

### 1. Primary workflow is step-by-step
- `initialize_xmi()` / `update()` / `finalize()` is the main API
- `run_xmi()` is optional convenience only
- Documentation emphasizes step-by-step pattern

### 2. Follow modflowapi's API closely
- Same property names
- Same method signatures
- Same workflow patterns
- Minimizes learning curve for modflowapi users

### 3. XMI is opt-in via explicit class
- Use `XmiSimulation` when you want XMI
- Regular `Simulation` for subprocess execution
- Clear intent, no magic

### 4. Gradual internal evolution
- Phase A ships quickly (thin wrapper)
- Phase B improves internals (no API change)
- Phase C ensures backward compat

## Open Questions

1. **Dynamic model access**: Should `sim.get_model(name)` return the same model object from the component tree but enhanced, or a wrapper? Currently: returns enhanced component tree model.

2. **Property access patterns**: Should we support both `sim.get_model("gwf").X` and `sim["gwf"].X`? Currently: only via `get_model()` to be explicit about XMI access.

3. **Package-level XMI**: What package properties/methods need XMI access? Follow modflowapi's ApiPackage implementations.

4. **Error handling**: How to handle XMI errors gracefully? Match modflowapi's error patterns.

## Success Criteria

- [ ] FloPy4 XMI API feels natural to modflowapi users
- [ ] Step-by-step execution is well-documented and easy
- [ ] All modflowapi functionality available in FloPy4
- [ ] Performance matches or exceeds modflowapi
- [ ] Legacy modflowapi code migrates easily
- [ ] Single codebase reduces maintenance burden
