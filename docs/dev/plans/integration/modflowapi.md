# Integrating modflowapi into FloPy4

**Status**: Detailed Implementation Plan
**Date**: 2026-02-11
**Authors**: Design discussion with wbonelli

## Executive Summary

This document outlines a plan to merge modflowapi functionality into FloPy4 as a **plugin architecture** using mixins. The core FloPy4 components remain clean and XMI-agnostic, while XMI capabilities are added through optional enhanced classes. This provides first-class XMI support while maintaining clean separation and backward compatibility.

## Current State Analysis

### modflowapi Architecture (Current)

**Repository**: https://github.com/MODFLOW-ORG/modflowapi

**Core Classes**:
```python
# modflowapi/modflowapi.py
class ModflowApi(XmiWrapper):
    """Wraps MODFLOW 6 shared library via xmipy."""
    def __init__(self, lib_path, working_directory, ...)
    # Inherits: initialize(), update(), finalize() from XmiWrapper

# modflowapi/extensions/apisimulation.py
class ApiSimulation:
    """High-level simulation access."""
    def __init__(self, mf6: ModflowApi, models, solutions, exchanges, ...)

    @property
    def kper(self) -> int  # Current stress period
    @property
    def totim(self) -> float  # Current time

    def get_model(self, name) -> ApiModel

    @staticmethod
    def load(mf6: ModflowApi) -> ApiSimulation
        """Parse XMI variables and construct ApiSimulation."""

# modflowapi/extensions/apimodel.py
class ApiModel:
    """High-level model access."""
    @property
    def X(self) -> NDArray  # Solution array (heads)
    @property
    def shape(self) -> tuple
    @property
    def kper(self) -> int

    def get_package(self, name) -> ApiPackage
```

**Workflow**:
```python
# Current modflowapi usage
from modflowapi import ModflowApi
from modflowapi.extensions import ApiSimulation

# Load library
mf6 = ModflowApi(lib_path="libmf6", working_directory="./sim")
mf6.initialize()

# Get high-level access
sim = ApiSimulation.load(mf6)

# Step through
while not mf6.finalized:
    mf6.update()
    print(f"kper={sim.kper}, head={sim.models[0].X.max()}")

mf6.finalize()
```

### FloPy4 Architecture (Current)

**Repository**: C:/Users/wbonelli/dev/pyphoenix-project

**Core Classes** (XMI-agnostic):
```python
# flopy4/mf6/simulation.py
class Simulation(Context):
    """MODFLOW 6 simulation."""
    def run(self, exe="mf6", verbose=False):
        """Run via subprocess."""
        # Write files, run binary, done

# flopy4/mf6/model.py
class Model(Context):
    """MODFLOW 6 model base."""
    # Contains packages, discretization, etc.
```

**Workflow**:
```python
# Current FloPy4 usage
from flopy4.mf6 import Simulation

sim = Simulation.load("sim.nam")
sim.run()  # Subprocess execution
```

### The Gap

- **modflowapi**: Runtime access, no construction utilities
- **FloPy4**: Construction utilities, no runtime access
- **Users want**: Single tool for both

## Design Principles

1. **Core components stay clean**: `Simulation`, `Model`, `Package` have zero XMI code
2. **XMI is a plugin**: Optional mixin-based enhancement
3. **Explicit opt-in**: Users choose XMI-enhanced classes when needed
4. **Backward compatible**: Existing FloPy4 code unchanged
5. **Migration path**: modflowapi users can transition gradually
6. **Unified object model**: Same component definitions, XMI adds runtime capabilities

## Proposed Architecture

### Package Structure

```
flopy4/
├── mf6/
│   ├── simulation.py       # Base Simulation (no XMI)
│   ├── model.py            # Base Model (no XMI)
│   ├── package.py          # Base Package (no XMI)
│   └── xmi/                # NEW: XMI plugin package
│       ├── __init__.py     # Exports XmiSimulation, XmiModel, etc.
│       ├── mixins.py       # XMI capability mixins
│       ├── simulation.py   # XmiSimulation class
│       ├── model.py        # XmiModel class
│       ├── package.py      # XmiPackage class
│       ├── variables.py    # XMI variable parsing/mapping
│       └── compat.py       # Backward compat layer for modflowapi

# Optional: Keep modflowapi as thin compatibility wrapper
modflowapi/  # Could eventually become flopy4[xmi] or deprecated
```

### Core Design: Mixin-based Plugin

**File**: `flopy4/mf6/xmi/mixins.py`

```python
"""XMI capability mixins - add runtime access to components."""

from abc import ABC, abstractmethod
from typing import Any
import numpy as np
from numpy.typing import NDArray
from xmipy import XmiWrapper


class XmiCapable(ABC):
    """
    Mixin adding XMI runtime capabilities to FloPy4 components.

    Core components remain clean - this mixin adds XMI-specific
    properties and methods only when mixed in to create XMI-enhanced
    versions.

    Design:
    - Base classes (Simulation, Model) are XMI-agnostic
    - XMI-enhanced classes (XmiSimulation, XmiModel) mix this in
    - Properties/methods fail gracefully if XMI not initialized
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # XMI state (only exists in XMI-enhanced instances)
        self._xmi: XmiWrapper | None = None
        self._xmi_vars: dict[str, Any] = {}  # Cached variable addresses

    # Core XMI lifecycle

    def initialize_xmi(self, lib_path: str | None = None) -> None:
        """
        Initialize XMI wrapper with MODFLOW 6 shared library.

        Parameters
        ----------
        lib_path : str, optional
            Path to libmf6 shared library. If None, uses default discovery.
        """
        if self._xmi is not None:
            raise RuntimeError("XMI already initialized")

        self._xmi = XmiWrapper(
            lib_path=lib_path or self._get_default_lib_path(),
            working_directory=str(self.workspace)
        )
        self._xmi.initialize()
        self._discover_xmi_variables()

    def step_xmi(self) -> None:
        """Advance simulation one timestep (XMI mode only)."""
        self._check_xmi_active()
        self._xmi.update()

    def finalize_xmi(self) -> None:
        """Cleanup XMI resources."""
        if self._xmi is not None:
            self._xmi.finalize()
            self._xmi = None
            self._xmi_vars.clear()

    # XMI state queries

    @property
    def xmi_active(self) -> bool:
        """Is XMI library currently loaded and active?"""
        return self._xmi is not None and not self._xmi.finalized

    @property
    def xmi_initialized(self) -> bool:
        """Has XMI been initialized (may be finalized)?"""
        return self._xmi is not None

    # Internal helpers

    def _check_xmi_active(self) -> None:
        """Raise error if XMI not active."""
        if not self.xmi_active:
            raise RuntimeError(
                f"XMI not active on {type(self).__name__}. "
                f"Call initialize_xmi() first or use XMI-enhanced run methods."
            )

    def _get_xmi_var(self, var_address: str) -> Any:
        """
        Get XMI variable value by address.

        Parameters
        ----------
        var_address : str
            XMI variable address (e.g., "SIM/TDIS/KPER", "GWF_1/X")

        Returns
        -------
        Any
            Variable value (scalar, array, etc.)
        """
        self._check_xmi_active()

        # Cache variable addresses for performance
        if var_address not in self._xmi_vars:
            self._xmi_vars[var_address] = self._xmi.get_var(var_address)

        return self._xmi_vars[var_address]

    def _set_xmi_var(self, var_address: str, value: Any) -> None:
        """Set XMI variable value by address."""
        self._check_xmi_active()
        self._xmi.set_var(var_address, value)

    @abstractmethod
    def _discover_xmi_variables(self) -> None:
        """
        Discover and cache XMI variable addresses for this component.

        Called after XMI initialization. Subclasses implement to populate
        _xmi_vars with component-specific variables.
        """
        pass

    def _get_default_lib_path(self) -> str:
        """Get default library path (platform-specific)."""
        import sys
        if sys.platform == "win32":
            return "libmf6.dll"
        elif sys.platform == "darwin":
            return "libmf6.dylib"
        else:
            return "libmf6.so"


class XmiSimulationMixin(XmiCapable):
    """XMI capabilities for Simulation objects."""

    def _discover_xmi_variables(self) -> None:
        """Discover simulation-level XMI variables."""
        # Parse available XMI variables and cache addresses
        # This is where modflowapi's ApiSimulation.load() logic goes
        var_names = self._xmi.get_var_names()

        # Parse TDIS variables
        for var in var_names:
            if var.startswith("SIM/TDIS/"):
                self._xmi_vars[var] = None  # Cache address, fetch on demand

    # Simulation-level runtime properties

    @property
    def kper(self) -> int:
        """Current stress period (1-based)."""
        return int(self._get_xmi_var("SIM/TDIS/KPER"))

    @property
    def kstp(self) -> int:
        """Current time step within stress period (1-based)."""
        return int(self._get_xmi_var("SIM/TDIS/KSTP"))

    @property
    def totim(self) -> float:
        """Current simulation time."""
        return float(self._get_xmi_var("SIM/TDIS/TOTIM"))

    @property
    def delt(self) -> float:
        """Current timestep length."""
        return float(self._get_xmi_var("SIM/TDIS/DELT"))

    @property
    def nper(self) -> int:
        """Total number of stress periods."""
        return int(self._get_xmi_var("SIM/TDIS/NPER"))

    def get_model_xmi(self, name: str) -> "XmiModel":
        """
        Get XMI-enhanced model by name.

        Parameters
        ----------
        name : str
            Model name

        Returns
        -------
        XmiModel
            XMI-enhanced model (if XMI active)
        """
        self._check_xmi_active()
        model = self[name]  # Get from component tree

        # If model is not already XMI-enhanced, enhance it
        if not isinstance(model, XmiModelMixin):
            # Dynamically add XMI capabilities
            model = self._enhance_model_with_xmi(model)

        # Propagate XMI wrapper
        model._xmi = self._xmi
        model._discover_xmi_variables()

        return model

    def _enhance_model_with_xmi(self, model):
        """Dynamically add XMI capabilities to a model instance."""
        # This is a fallback for models loaded before XMI initialization
        # Ideally, users create XmiSimulation which creates XmiModels
        from flopy4.mf6.xmi.model import XmiModel

        # Create new XMI-enhanced instance copying state
        xmi_model = XmiModel(**model.to_dict())
        xmi_model._xmi = self._xmi
        return xmi_model


class XmiModelMixin(XmiCapable):
    """XMI capabilities for Model objects."""

    def _discover_xmi_variables(self) -> None:
        """Discover model-level XMI variables."""
        var_names = self._xmi.get_var_names()
        model_prefix = self.name.upper()

        # Cache model-specific variables
        for var in var_names:
            if var.startswith(f"{model_prefix}/"):
                self._xmi_vars[var] = None

    # Model-level runtime properties

    @property
    def X(self) -> NDArray:
        """
        Solution array.

        For GWF: hydraulic heads
        For GWT: concentrations
        For GWE: temperatures
        """
        var_address = f"{self.name.upper()}/X"
        return self._get_xmi_var(var_address)

    @X.setter
    def X(self, value: NDArray) -> None:
        """Set solution array (e.g., for warm start)."""
        var_address = f"{self.name.upper()}/X"
        self._set_xmi_var(var_address, value)

    @property
    def shape(self) -> tuple[int, ...]:
        """Model grid shape (nlay, nrow, ncol) or (nodes,)."""
        # Determine shape from discretization package
        if hasattr(self, 'dis') and self.dis is not None:
            return (self.dis.nlay, self.dis.nrow, self.dis.ncol)
        elif hasattr(self, 'disv') and self.disv is not None:
            return (self.disv.nlay, self.disv.ncpl)
        elif hasattr(self, 'disu') and self.disu is not None:
            return (self.disu.nodes,)
        else:
            raise ValueError("No discretization package found")

    @property
    def size(self) -> int:
        """Total number of cells/nodes."""
        return int(np.prod(self.shape))

    @property
    def kper(self) -> int:
        """Current stress period (inherited from parent simulation)."""
        if hasattr(self, 'parent') and hasattr(self.parent, 'kper'):
            return self.parent.kper
        raise RuntimeError("Model has no parent simulation")

    @property
    def kstp(self) -> int:
        """Current time step (inherited from parent simulation)."""
        if hasattr(self, 'parent') and hasattr(self.parent, 'kstp'):
            return self.parent.kstp
        raise RuntimeError("Model has no parent simulation")

    def get_package_xmi(self, name: str) -> "XmiPackage":
        """Get XMI-enhanced package by name."""
        self._check_xmi_active()
        pkg = self[name]

        # Enhance if needed
        if not isinstance(pkg, XmiPackageMixin):
            pkg = self._enhance_package_with_xmi(pkg)

        pkg._xmi = self._xmi
        pkg._discover_xmi_variables()
        return pkg


class XmiPackageMixin(XmiCapable):
    """XMI capabilities for Package objects."""

    def _discover_xmi_variables(self) -> None:
        """Discover package-level XMI variables."""
        var_names = self._xmi.get_var_names()

        # Determine package prefix
        if hasattr(self, 'parent') and hasattr(self.parent, 'name'):
            model_name = self.parent.name.upper()
            pkg_name = type(self).__name__.upper()
            prefix = f"{model_name}/{pkg_name}"

            for var in var_names:
                if var.startswith(prefix):
                    self._xmi_vars[var] = None

    # Package-level runtime properties (example for NPF)

    @property
    def k(self) -> NDArray | None:
        """Hydraulic conductivity (NPF package, runtime access)."""
        if not hasattr(self, 'parent'):
            return None
        model_name = self.parent.name.upper()
        var_address = f"{model_name}/NPF/K11"
        try:
            return self._get_xmi_var(var_address)
        except:
            return None

    @k.setter
    def k(self, value: NDArray) -> None:
        """Set hydraulic conductivity at runtime."""
        if not hasattr(self, 'parent'):
            raise RuntimeError("Package has no parent model")
        model_name = self.parent.name.upper()
        var_address = f"{model_name}/NPF/K11"
        self._set_xmi_var(var_address, value)
```

### XMI-Enhanced Component Classes

**File**: `flopy4/mf6/xmi/simulation.py`

```python
"""XMI-enhanced Simulation class."""

from flopy4.mf6.simulation import Simulation as BaseSimulation
from flopy4.mf6.xmi.mixins import XmiSimulationMixin


class XmiSimulation(XmiSimulationMixin, BaseSimulation):
    """
    MODFLOW 6 Simulation with XMI runtime capabilities.

    This class combines the standard FloPy4 Simulation with XMI
    runtime access via the XmiSimulationMixin. Use this when you
    need to interact with MODFLOW 6 during execution.

    Examples
    --------
    >>> # Standard workflow
    >>> sim = XmiSimulation.load("sim.nam")
    >>> sim.write()
    >>>
    >>> # Run with XMI and access runtime data
    >>> sim.initialize_xmi()
    >>> while sim.xmi_active:
    ...     sim.step_xmi()
    ...     print(f"Time: {sim.totim}, Period: {sim.kper}")
    ...     model = sim.get_model_xmi("gwf_1")
    ...     print(f"Max head: {model.X.max()}")
    >>> sim.finalize_xmi()

    >>> # Or use the high-level run method
    >>> sim.run_xmi()  # Runs to completion with XMI
    """

    def run_xmi(
        self,
        lib_path: str | None = None,
        callback: callable | None = None,
        verbose: bool = False
    ) -> None:
        """
        Run simulation using XMI with optional callback.

        Parameters
        ----------
        lib_path : str, optional
            Path to MODFLOW 6 shared library
        callback : callable, optional
            Function called each timestep: callback(sim)
        verbose : bool
            Print progress messages
        """
        self.write()
        self.initialize_xmi(lib_path=lib_path)

        try:
            while self.xmi_active:
                if verbose:
                    print(f"kper={self.kper}, kstp={self.kstp}, t={self.totim}")

                self.step_xmi()

                if callback is not None:
                    callback(self)

        finally:
            self.finalize_xmi()

    def run(self, executor=None, verbose=False, **kwargs):
        """
        Run simulation (subprocess or XMI based on executor).

        This overrides the base run() to provide seamless switching
        between subprocess and XMI execution modes.

        Parameters
        ----------
        executor : str | callable | None
            - None: Use XMI if available, else subprocess
            - "xmi": Force XMI execution
            - str path: Subprocess with specific binary
            - callable: Custom executor function
        verbose : bool
            Print execution details
        **kwargs
            Passed to XMI executor if used (lib_path, callback, etc.)
        """
        if executor == "xmi" or (executor is None and self._prefer_xmi()):
            # XMI execution
            return self.run_xmi(verbose=verbose, **kwargs)
        else:
            # Subprocess execution (fall back to base class)
            return super().run(executor=executor, verbose=verbose)

    def _prefer_xmi(self) -> bool:
        """Should we prefer XMI execution by default?"""
        # Could check for xmipy installation, user preferences, etc.
        try:
            import xmipy
            return True
        except ImportError:
            return False
```

**File**: `flopy4/mf6/xmi/model.py`

```python
"""XMI-enhanced Model classes."""

from flopy4.mf6.model import Gwf as BaseGwf
from flopy4.mf6.xmi.mixins import XmiModelMixin


class XmiGwf(XmiModelMixin, BaseGwf):
    """Groundwater Flow model with XMI runtime capabilities."""

    # Inherits all XMI properties from XmiModelMixin
    # Inherits all standard properties from BaseGwf
    pass


# Similarly for other model types
class XmiGwt(XmiModelMixin, BaseGwt):
    """Groundwater Transport model with XMI runtime capabilities."""
    pass


class XmiGwe(XmiModelMixin, BaseGwe):
    """Groundwater Energy model with XMI runtime capabilities."""
    pass
```

**File**: `flopy4/mf6/xmi/__init__.py`

```python
"""
FloPy4 XMI Plugin - Runtime access to MODFLOW 6 via XMI.

This package provides XMI-enhanced versions of FloPy4 components
that add runtime simulation control and data access capabilities
using the eXtended Model Interface (XMI).

Quick Start
-----------
>>> from flopy4.mf6.xmi import XmiSimulation
>>>
>>> sim = XmiSimulation.load("sim.nam")
>>> sim.run_xmi()  # Run with XMI
>>>
>>> # Or step through manually
>>> sim.initialize_xmi()
>>> while sim.xmi_active:
...     sim.step_xmi()
...     heads = sim.get_model_xmi("gwf_1").X
>>> sim.finalize_xmi()

Classes
-------
XmiSimulation : Simulation with XMI runtime access
XmiGwf, XmiGwt, XmiGwe : Model classes with XMI runtime access
XmiPackage : Package base with XMI runtime access

Requirements
------------
This plugin requires the `xmipy` package:
    pip install xmipy

Or install FloPy4 with XMI support:
    pip install flopy4[xmi]
"""

from flopy4.mf6.xmi.simulation import XmiSimulation
from flopy4.mf6.xmi.model import XmiGwf, XmiGwt, XmiGwe
from flopy4.mf6.xmi.mixins import (
    XmiCapable,
    XmiSimulationMixin,
    XmiModelMixin,
    XmiPackageMixin
)

__all__ = [
    "XmiSimulation",
    "XmiGwf",
    "XmiGwt",
    "XmiGwe",
    "XmiCapable",
    "XmiSimulationMixin",
    "XmiModelMixin",
    "XmiPackageMixin",
]
```

## Migration Path for modflowapi Users

### Option 1: Backward Compatibility Layer

Keep `modflowapi` package as thin wrapper around FloPy4 XMI:

**File**: `modflowapi/compat.py` (new compatibility shim)

```python
"""
Backward compatibility layer for modflowapi.

This module provides the legacy modflowapi API as a thin wrapper
around FloPy4's XMI plugin. Existing code continues to work while
encouraging migration to the unified FloPy4 API.
"""

import warnings
from flopy4.mf6.xmi import XmiSimulation as _FlopyXmiSimulation


class ModflowApi:
    """
    Legacy modflowapi interface.

    .. deprecated:: 2.0.0
        Use `flopy4.mf6.xmi.XmiSimulation` instead.

    This class wraps FloPy4's XmiSimulation to provide backward
    compatibility with the modflowapi 1.x API.
    """

    def __init__(self, lib_path=None, working_directory=".", **kwargs):
        warnings.warn(
            "ModflowApi is deprecated. Use flopy4.mf6.xmi.XmiSimulation instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Load simulation using FloPy4
        from flopy4.mf6 import Simulation
        self._sim = _FlopyXmiSimulation.load(
            working_directory + "/mfsim.nam"
        )
        self._sim._lib_path = lib_path
        self._initialized = False
        self._finalized = False

    def initialize(self):
        """Initialize XMI library."""
        self._sim.initialize_xmi(lib_path=self._sim._lib_path)
        self._initialized = True

    def update(self):
        """Advance one timestep."""
        self._sim.step_xmi()

    def finalize(self):
        """Cleanup XMI resources."""
        self._sim.finalize_xmi()
        self._finalized = True

    @property
    def finalized(self):
        """Is simulation finalized?"""
        return self._finalized or not self._sim.xmi_active


class ApiSimulation:
    """
    Legacy ApiSimulation interface.

    .. deprecated:: 2.0.0
        Use `flopy4.mf6.xmi.XmiSimulation` directly.
    """

    def __init__(self, sim: _FlopyXmiSimulation):
        warnings.warn(
            "ApiSimulation is deprecated. Use flopy4.mf6.xmi.XmiSimulation directly.",
            DeprecationWarning,
            stacklevel=2
        )
        self._sim = sim

    @staticmethod
    def load(mf6: ModflowApi):
        """Load from ModflowApi instance."""
        return ApiSimulation(mf6._sim)

    @property
    def models(self):
        """Get list of models."""
        return [self._sim.get_model_xmi(name) for name in self._sim.keys()]

    @property
    def kper(self):
        """Current stress period."""
        return self._sim.kper

    @property
    def kstp(self):
        """Current timestep."""
        return self._sim.kstp

    @property
    def totim(self):
        """Current simulation time."""
        return self._sim.totim

    def get_model(self, name):
        """Get model by name."""
        return ApiModel(self._sim.get_model_xmi(name))


class ApiModel:
    """Legacy ApiModel interface."""

    def __init__(self, model):
        self._model = model

    @property
    def X(self):
        """Solution array."""
        return self._model.X

    @property
    def shape(self):
        """Grid shape."""
        return self._model.shape

    # ... other properties ...


# Re-export for backward compatibility
__all__ = ["ModflowApi", "ApiSimulation", "ApiModel"]
```

**File**: `modflowapi/__init__.py` (updated)

```python
"""
modflowapi - MODFLOW 6 API

.. deprecated:: 2.0.0
    This package is deprecated in favor of flopy4.mf6.xmi.

    For new code, use::

        from flopy4.mf6.xmi import XmiSimulation

        sim = XmiSimulation.load("sim.nam")
        sim.run_xmi()

    This compatibility layer will be maintained through version 2.x
    and removed in version 3.0.

Migration Guide
---------------
Old (modflowapi 1.x)::

    from modflowapi import ModflowApi
    from modflowapi.extensions import ApiSimulation

    mf6 = ModflowApi(working_directory="./sim")
    mf6.initialize()
    sim = ApiSimulation.load(mf6)

    while not mf6.finalized:
        mf6.update()
        print(sim.kper, sim.models[0].X.max())

    mf6.finalize()

New (flopy4.mf6.xmi)::

    from flopy4.mf6.xmi import XmiSimulation

    sim = XmiSimulation.load("sim.nam")
    sim.initialize_xmi()

    while sim.xmi_active:
        sim.step_xmi()
        print(sim.kper, sim.get_model_xmi("gwf_1").X.max())

    sim.finalize_xmi()

Or simply::

    sim.run_xmi(callback=lambda s: print(s.kper))
"""

import warnings

warnings.warn(
    "The modflowapi package is deprecated. Use flopy4.mf6.xmi instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import from compatibility layer
from modflowapi.compat import ModflowApi, ApiSimulation, ApiModel

__version__ = "2.0.0"  # Major version bump signals breaking change
__all__ = ["ModflowApi", "ApiSimulation", "ApiModel"]
```

### Option 2: Direct Migration (No Compatibility Layer)

Archive `modflowapi` and point users directly to FloPy4:

**modflowapi README.md** (updated):

```markdown
# modflowapi - Archived

**This package has been merged into FloPy4 and is no longer maintained.**

## Migrating to FloPy4

All modflowapi functionality is now available in FloPy4's XMI plugin:

```bash
# Install FloPy4 with XMI support
pip install flopy4[xmi]
```

### Quick Migration Guide

**Before (modflowapi)**:
```python
from modflowapi import ModflowApi
from modflowapi.extensions import ApiSimulation

mf6 = ModflowApi(working_directory="./sim")
mf6.initialize()
sim = ApiSimulation.load(mf6)

while not mf6.finalized:
    mf6.update()
    print(f"kper={sim.kper}")

mf6.finalize()
```

**After (FloPy4)**:
```python
from flopy4.mf6.xmi import XmiSimulation

sim = XmiSimulation.load("sim.nam")
sim.run_xmi(callback=lambda s: print(f"kper={s.kper}"))

# Or step-by-step
sim.initialize_xmi()
while sim.xmi_active:
    sim.step_xmi()
    print(f"kper={sim.kper}")
sim.finalize_xmi()
```

See [FloPy4 XMI Documentation](https://flopy.readthedocs.io/xmi) for details.
```

## Implementation Phases

### Phase 1: Core XMI Plugin (4-6 weeks)

**Week 1-2: Mixin infrastructure**
- [ ] Create `flopy4/mf6/xmi/` package structure
- [ ] Implement `XmiCapable` base mixin
- [ ] Implement `XmiSimulationMixin` with TDIS properties
- [ ] Implement `XmiModelMixin` with solution array access
- [ ] Implement `XmiPackageMixin` base
- [ ] Add tests for mixin functionality (mocked XMI)

**Week 3-4: XMI-enhanced component classes**
- [ ] Create `XmiSimulation` class
- [ ] Create `XmiGwf`, `XmiGwt`, `XmiGwe` classes
- [ ] Implement `run_xmi()` method with callback support
- [ ] Implement variable discovery logic (port from modflowapi)
- [ ] Add integration tests with real libmf6

**Week 5-6: Documentation and examples**
- [ ] Write XMI plugin documentation
- [ ] Create tutorial notebooks:
  - [ ] Basic XMI execution
  - [ ] Real-time monitoring
  - [ ] Parameter modification during runtime
  - [ ] Optimization workflow example
- [ ] Add API reference documentation
- [ ] Performance benchmarks (subprocess vs XMI)

### Phase 2: Backward Compatibility (2-3 weeks)

**Week 1-2: Compatibility layer**
- [ ] Create `modflowapi/compat.py` wrapper module
- [ ] Implement `ModflowApi` compatibility class
- [ ] Implement `ApiSimulation` compatibility class
- [ ] Implement `ApiModel` compatibility class
- [ ] Add deprecation warnings
- [ ] Test with existing modflowapi examples

**Week 3: Migration guide**
- [ ] Write detailed migration guide
- [ ] Create side-by-side comparison examples
- [ ] Document breaking changes
- [ ] Create automated migration tool (optional)

### Phase 3: Advanced Features (3-4 weeks)

**Week 1: Package-level XMI access**
- [ ] Implement package-specific XMI properties (NPF, CHD, WEL, etc.)
- [ ] Add runtime parameter modification for stress packages
- [ ] Add tests for package XMI access

**Week 2: Advanced workflows**
- [ ] Parameter estimation helper utilities
- [ ] Model coupling utilities
- [ ] Callback library (convergence monitoring, adaptive timestepping, etc.)
- [ ] Add examples for each workflow

**Week 3-4: Polish and optimization**
- [ ] Performance optimization (variable caching, batch access)
- [ ] Error handling improvements
- [ ] Memory profiling and optimization
- [ ] Comprehensive test coverage

### Phase 4: Deprecation and Archival (Ongoing)

**Months 1-3: Soft deprecation**
- [ ] Release modflowapi 2.0 with compatibility layer
- [ ] Add deprecation warnings to all functions
- [ ] Update all documentation to point to FloPy4
- [ ] Notify users via mailing lists, GitHub, etc.

**Months 4-12: Migration support**
- [ ] Help users migrate their code
- [ ] Fix compatibility layer bugs
- [ ] No new features in modflowapi (FloPy4 only)

**Month 12+: Hard deprecation**
- [ ] Final modflowapi release with "archived" status
- [ ] README points to FloPy4
- [ ] No further updates
- [ ] Repository marked as archived on GitHub

## Benefits of This Approach

### Technical Benefits

1. **Clean separation**: Core components stay XMI-agnostic
2. **Plugin architecture**: XMI is opt-in, not forced on all users
3. **Explicit intent**: `XmiSimulation` vs `Simulation` makes user intent clear
4. **Type safety**: Separate classes enable better IDE support and type checking
5. **Testing**: Can test XMI features in isolation
6. **Performance**: XMI overhead only for users who opt in

### User Benefits

1. **Unified object model**: Same components for construction and runtime
2. **Seamless workflows**: Build in FloPy4, run with XMI, all same objects
3. **Gradual migration**: modflowapi users can transition incrementally
4. **Better documentation**: One place for MODFLOW 6 + Python
5. **Consistent APIs**: No impedance mismatch between construction and runtime
6. **First-class support**: XMI is native FloPy4 capability, not afterthought

### Maintenance Benefits

1. **Single codebase**: FloPy4 evolves in lockstep with MF6
2. **Coordinated releases**: FloPy4 + XMI released together
3. **Shared infrastructure**: Tests, CI/CD, documentation all unified
4. **Reduced duplication**: One set of components, not two
5. **Clear ownership**: USGS maintains both FloPy4 core and XMI plugin

## Open Questions and Decisions Needed

### Question 1: Compatibility Layer Timeline

**Options**:
- **A**: Keep modflowapi compatibility indefinitely (FloPy4 XMI is "modflowapi 2.0")
- **B**: 1-year transition, then archive modflowapi
- **C**: Immediate deprecation, no compatibility layer

**Recommendation**: **Option B** - 1-year transition balances user needs with maintenance burden

### Question 2: Auto-enhancement vs Explicit Classes

**Current proposal**: Users choose `XmiSimulation` explicitly

**Alternative**: Auto-enhance on XMI execution
```python
sim = Simulation.load("sim.nam")  # Regular Simulation
sim.run(executor="xmi")  # Dynamically adds XMI capabilities
# Now sim has .kper, .step_xmi(), etc.
```

**Pros**: More convenient, no separate classes
**Cons**: "Spooky action at a distance", harder to type check, confusing behavior

**Recommendation**: **Stick with explicit XMI classes** - clearer, more predictable

### Question 3: Default Executor Behavior

When user calls `XmiSimulation.run()` with no arguments, should it:
- **A**: Default to XMI (since they chose XmiSimulation)
- **B**: Default to subprocess (backward compatible)
- **C**: Check if xmipy installed, use XMI if available, else subprocess

**Recommendation**: **Option A** - if you choose `XmiSimulation`, you want XMI

### Question 4: Package Dependencies

Should `xmipy` be:
- **A**: Required dependency (everyone gets it)
- **B**: Optional dependency via extras: `pip install flopy4[xmi]`
- **C**: Separate plugin package: `pip install flopy4-xmi`

**Recommendation**: **Option B** - optional extras balances accessibility with minimal deps

### Question 5: Variable Naming

XMI properties on components could conflict with existing FloPy4 attributes. How to handle?

**Options**:
- **A**: Prefix XMI properties: `sim.xmi_kper`, `model.xmi_X`
- **B**: Namespace: `sim.xmi.kper`, `model.xmi.X`
- **C**: No prefix, careful naming (current proposal)

**Recommendation**: **Option C** with careful review - most natural, least verbose

## Success Criteria

A successful integration achieves:

1. **Zero pollution**: Base `Simulation`/`Model` classes have no XMI code
2. **Feature parity**: All modflowapi capabilities available in FloPy4 XMI
3. **Easy migration**: Existing modflowapi code converts in <1 hour per project
4. **Performance**: XMI execution as fast as native modflowapi (no overhead)
5. **Documentation**: Complete migration guide and tutorials
6. **User adoption**: 80%+ of modflowapi users migrate within 1 year
7. **Maintainability**: Single team can maintain FloPy4 + XMI plugin

## Next Steps

### Immediate (This Week)
1. **Socialize proposal**: Share with modflowapi maintainers (Deltares, USGS)
2. **Get buy-in**: Confirm USGS/Deltares support for merger
3. **Create prototype**: Implement `XmiSimulationMixin` with 2-3 properties
4. **Validate approach**: Test with simple MF6 model

### Short-term (Next Month)
1. **Implement Phase 1**: Core XMI plugin functionality
2. **Write migration guide**: Document modflowapi → FloPy4 XMI path
3. **Test with real models**: Verify feature parity
4. **Create examples**: Port modflowapi examples to FloPy4 XMI

### Medium-term (3-6 Months)
1. **Release FloPy4 with XMI**: Beta release for early adopters
2. **Release modflowapi 2.0**: Compatibility layer pointing to FloPy4
3. **Gather feedback**: Iterate based on user experience
4. **Stabilize API**: Lock down XMI plugin interface

### Long-term (6-12 Months)
1. **Promote migration**: Encourage all modflowapi users to switch
2. **Archive modflowapi**: Mark as deprecated, redirect to FloPy4
3. **Full integration**: XMI plugin is mature, well-documented FloPy4 feature

## References

- FloPy4 codebase: `C:/Users/wbonelli/dev/pyphoenix-project`
- modflowapi: https://github.com/MODFLOW-ORG/modflowapi
- xmipy: https://github.com/Deltares/xmipy
- XMI specification: https://csdms.colorado.edu/wiki/BMI
- Python code integration design: `docs/python_code_integration.md`
