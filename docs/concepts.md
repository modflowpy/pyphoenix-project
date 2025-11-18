# FloPy4 Concepts and Terminology

This guide explains the fundamental concepts you need to know to effectively use FloPy4 for MODFLOW 6 modeling.

## What is FloPy4?

FloPy4 is a Python interface for MODFLOW 6, the U.S. Geological Survey's modular hydrologic model. It provides a programmatic way to create, modify, run, and analyze groundwater flow simulations.

### Purpose

FloPy4 allows you to:
- Create MODFLOW 6 simulations from scratch using Python
- Load and modify existing MODFLOW 6 simulations
- Run simulations and access results
- Manipulate simulation data using familiar Python tools

### Key Benefits over FloPy 3.x

- **Modern data structures**: Built on xarray for intuitive data access and manipulation
- **Type-safe API**: Clear, typed interfaces that work well with IDEs and type checkers
- **Modular design**: Components can be created independently and combined flexibly
- **Native MODFLOW 6 support**: Direct mapping to MODFLOW 6 concepts and features

### When to Use FloPy4

Use FloPy4 when you need to:
- Automate groundwater modeling workflows
- Process and analyze simulation results programmatically
- Create or modify complex simulations that would be tedious to build manually
- Integrate MODFLOW 6 with other Python-based scientific workflows

## Core Concepts

### Simulations, Models, and Packages: The Hierarchy

MODFLOW 6 (and FloPy4) organize groundwater models as a **hierarchy of components**:

```
Simulation (root)
├── Temporal Discretization (TDIS)
├── Solution (e.g., IMS)
└── Models (e.g., GWF)
    ├── Discretization (DIS/DISV/DISU)
    ├── Initial Conditions (IC)
    ├── Node Property Flow (NPF)
    ├── Storage (STO)
    ├── Output Control (OC)
    └── Stress Packages (CHD, WEL, DRN, RCH, etc.)
```

#### Simulation

The **Simulation** is the top-level container representing everything needed to run MODFLOW 6. It includes:
- One or more models (typically groundwater flow models)
- Temporal discretization (how time is divided)
- Solution methods (how equations are solved)
- A workspace directory for input/output files

```python
from flopy4.mf6.simulation import Simulation

sim = Simulation(
    name="my_simulation",
    workspace=Path("./my_model"),
    tdis=time
)
```

#### Model

A **Model** represents a specific hydrological process being simulated. The most common type is **GWF** (Groundwater Flow):

```python
from flopy4.mf6.gwf import Gwf

gwf = Gwf(
    parent=sim,
    name="mymodel",
    save_flows=True,
    dis=grid
)
```

#### Package

A **Package** is a modular component that adds specific functionality to a model:

- **Basic packages**: Core model properties (DIS, IC, NPF, STO)
- **Stress packages**: Boundary conditions and sources/sinks (CHD, WEL, DRN, RCH)
- **Output packages**: Control what gets written (OC)

```python
from flopy4.mf6.gwf import Npf, Ic, Chd

# Node Property Flow package
npf = Npf(parent=gwf, save_flows=True)

# Initial Conditions package
ic = Ic(parent=gwf, strt=1.0)

# Constant Head boundary package
chd = Chd(
    parent=gwf,
    head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}}
)
```

### Grids and Time: Spatial and Temporal Domains

#### Grids

Grids define the **spatial domain** of your model. FloPy4 supports MODFLOW 6's three grid types:

- **DIS**: Structured (regular rectangular) grids
- **DISV**: Vertically structured with flexible horizontal discretization
- **DISU**: Unstructured grids

For structured grids, you define:

```python
from flopy4.mf6.utils.grid import StructuredGrid
import numpy as np

grid = StructuredGrid(
    nlay=3,        # Number of layers
    nrow=15,       # Number of rows
    ncol=15,       # Number of columns
    delr=5000.0,   # Cell width (m) - can be array for variable spacing
    delc=5000.0,   # Cell height (m) - can be array for variable spacing
    top=200.0,     # Top elevation (m)
    botm=[-200.0, -300.0, -450.0]  # Bottom elevation of each layer (m)
)
```

#### Time

Time discretization defines when and how the simulation progresses. It's divided into **stress periods** (see below):

```python
from flopy4.mf6.utils.time import Time

# Simple: equal time steps
time = Time(
    perlen=[1.0, 10.0, 100.0],  # Length of each stress period
    nstp=[1, 5, 10]              # Number of time steps per period
)

# Or use timestamps:
time = Time.from_timestamps([
    "2000-01-01",
    "2000-01-02",
    "2000-01-03",
    "2000-01-04"
])
```

### Stress Periods

**Stress periods** are time intervals during which boundary conditions and stresses remain constant. Between stress periods, these conditions can change.

For example:
- Period 0: Steady-state (initial conditions)
- Period 1: Pumping at rate Q1
- Period 2: Pumping at rate Q2

You specify stress period data using dictionaries where keys are period numbers:

```python
# Different heads for different stress periods
chd = Chd(
    parent=gwf,
    head={
        0: {(0, 0, 0): 1.0},      # Period 0
        1: {(0, 0, 0): 0.9},      # Period 1
        2: {(0, 0, 0): 0.8}       # Period 2
    }
)

# Use "*" for all periods
wel = Wel(
    parent=gwf,
    q={"*": {(0, 5, 5): -100.0}}  # Same for all periods
)
```

### Boundary Conditions

**Boundary conditions** specify fixed values or fluxes at the edges (or interior) of your model domain. Common types include:

#### Constant Head (CHD)

Fixes head at specific cells:

```python
chd = Chd(
    parent=gwf,
    head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
    print_input=True,
    print_flows=True,
    save_flows=True
)
```

#### Wells (WEL)

Adds or removes water at specific cells:

```python
wel = Wel(
    parent=gwf,
    q={"*": {
        (0, 5, 5): -100.0,   # Pumping (negative = extraction)
        (0, 8, 8): 50.0       # Injection (positive)
    }}
)
```

#### Drains (DRN)

Allows water to leave when head exceeds a threshold:

```python
drn = Drn(
    parent=gwf,
    elev={"*": {(0, 7, 5): 10.0}},  # Drain elevation
    cond={"*": {(0, 7, 5): 1.0}}    # Drain conductance
)
```

#### Recharge (RCH)

Adds water to the top of the model:

```python
rch = Rch(
    parent=gwf,
    recharge=3e-8  # Uniform recharge rate
)
```

## Working with Data

FloPy4 stores data using [xarray](https://docs.xarray.dev/), a powerful library for labeled multi-dimensional arrays. You don't need to be an xarray expert, but understanding basics helps.

### Accessing Data

Access component data via the `.data` attribute:

```python
# Access package data
chd_heads = chd.data["head"]     # or chd.data.head

# Access discretization data
bottom_elevations = gwf.dis.data.botm
```

### Indexing and Selection

Use `.sel()` for labeled indexing:

```python
# Get bottom elevation at specific location
elev = gwf.dis.data.botm.sel(lay=0, row=5, col=10)

# Get head data for stress period 0
period_0_heads = chd.data.head.sel(per=0)

# Get a slice
layer_1_bottom = gwf.dis.data.botm.sel(lay=1)
```

### Arrays vs Scalars

Some parameters are arrays (vary spatially), others are scalars:

```python
# Scalar: same value everywhere
ic = Ic(parent=gwf, strt=1.0)

# Array: different values by location
ic = Ic(parent=gwf, strt=np.linspace(1.0, 0.0, nodes))
```

## File I/O

### Reading Existing Simulations

Load a simulation from MODFLOW 6 input files:

```python
sim = Simulation.load(
    workspace=Path("./existing_model"),
    name="existing_simulation"
)

# Access components
gwf = sim.models["mymodel"]
npf = gwf.npf
```

### Writing Simulations

Write FloPy4 objects to MODFLOW 6 input files:

```python
sim.write()  # Writes to sim.workspace
```

### Running Simulations

Execute MODFLOW 6:

```python
sim.run()  # Runs mf6 executable
# Or with options:
sim.run(verbose=True)
```

The `mf6` executable must be available on your system PATH.

### Accessing Results

Read output files after running:

```python
# Head output
head = gwf.output.head

# Budget output
budget = gwf.output.budget

# Or load manually
from flopy4.mf6.utils import open_hds

head = open_hds(
    workspace / "mymodel.hds",
    workspace / "mymodel.dis.grb"
)
```

Results are returned as xarray DataArrays, ready for analysis and plotting:

```python
import matplotlib.pyplot as plt

# Plot using xarray's built-in methods
head.sel(time=0, layer=0).plot.imshow()
plt.show()
```

## Package Variants

MODFLOW 6 offers two input styles for many stress packages. FloPy4 supports both:

### List-Based Packages (CHD, WEL, DRN, etc.)

Specify individual cells and their values. Best for sparse data (few active cells):

```python
# Only 2 cells have constant heads
chd = Chd(
    parent=gwf,
    head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}}
)
```

**Advantages:**
- Memory-efficient for sparse data
- Easy to specify individual cells
- Clear what cells are active

### Array-Based Packages (CHDG, WELG, DRNG, etc.)

Specify values using full arrays. Best for dense data or when working with arrays:

```python
# Array covering entire grid (use NODATA for inactive cells)
head_array = np.full((nlay, nrow, ncol), FILL_DNODATA)
head_array[0, 0, 0] = 1.0
head_array[0, 9, 9] = 0.0

chdg = Chdg(
    parent=gwf,
    head=head_array.reshape(nper, -1)
)
```

**Advantages:**
- Natural for array-based workflows
- Easier for dense spatial patterns
- Convenient for applying spatial functions

### When to Use Each

| Situation | Recommendation |
|-----------|----------------|
| Few scattered wells | WEL (list-based) |
| Recharge over entire domain | RCHG (array-based) |
| Boundary along model edge | Either works fine |
| Complex spatial pattern | *G package (array-based) |
| Reading from spreadsheet/table | List-based |

## Common Workflows

### Create a New Simulation from Scratch

```python
from pathlib import Path
import numpy as np
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.gwf import Gwf, Ic, Npf, Chd, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time

# 1. Define time
time = Time(perlen=[1.0], nstp=[1])

# 2. Define grid
grid = StructuredGrid(
    nlay=1, nrow=10, ncol=10,
    delr=1.0, delc=1.0,
    top=1.0, botm=0.0
)

# 3. Create simulation
sim = Simulation(
    name="my_sim",
    workspace=Path("./output"),
    tdis=time
)

# 4. Create solver
ims = Ims(parent=sim, models=["gwf"])

# 5. Create groundwater flow model
gwf = Gwf(parent=sim, name="gwf", dis=grid)

# 6. Add packages
ic = Ic(parent=gwf, strt=1.0)
npf = Npf(parent=gwf, save_flows=True)
chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
oc = Oc(
    parent=gwf,
    head_file="gwf.hds",
    budget_file="gwf.bud",
    save_head={0: "all"},
    save_budget={0: "all"}
)

# 7. Write and run
sim.write()
sim.run()

# 8. Access results
head = gwf.output.head
```

### Load and Modify an Existing Simulation

```python
# Load
sim = Simulation.load(
    workspace=Path("./existing_model"),
    name="existing"
)

# Modify
gwf = sim.models["gwf"]
gwf.npf.data.k = gwf.npf.data.k * 1.5  # Increase conductivity by 50%

# Add a new well
from flopy4.mf6.gwf import Wel
wel = Wel(parent=gwf, q={0: {(0, 5, 5): -100.0}})

# Write to new location
sim.workspace = Path("./modified_model")
sim.write()
sim.run()
```

### Access Simulation Results

```python
# After running
head = gwf.output.head
budget = gwf.output.budget

# Head is an xarray DataArray with dimensions like (time, layer, row, col)
print(head.dims)
print(head.coords)

# Select specific times/locations
surface_head = head.sel(layer=0, time=0)

# Do calculations
head_change = head.sel(time=-1) - head.sel(time=0)

# Plot
import matplotlib.pyplot as plt
surface_head.plot.imshow()
plt.show()
```

## Glossary

| Term | Definition |
|------|------------|
| **Component** | A modular part of a simulation (simulation, model, or package) |
| **Package** | A component that adds specific functionality to a model |
| **Simulation** | The top-level container for a MODFLOW 6 run |
| **Model** | A component representing a hydrological process (e.g., GWF) |
| **Stress Period** | A time interval with constant boundary conditions |
| **Time Step** | A subdivision of a stress period for solving equations |
| **DIS/DISV/DISU** | Discretization packages defining the spatial grid |
| **GWF** | Groundwater Flow model |
| **CHD** | Constant Head boundary package (list-based) |
| **CHDG** | Constant Head boundary package (array-based) |
| **WEL** | Well package (list-based) |
| **WELG** | Well package (array-based) |
| **DRN** | Drain package (list-based) |
| **DRNG** | Drain package (array-based) |
| **RCH** | Recharge package |
| **NPF** | Node Property Flow package (hydraulic properties) |
| **IC** | Initial Conditions package |
| **STO** | Storage package |
| **OC** | Output Control package |
| **IMS** | Iterative Model Solution (solver) |
| **TDIS** | Temporal Discretization package |
| **Head** | Hydraulic head (water level elevation) |
| **Conductivity (K)** | Ease with which water moves through material |
| **Conductance** | Combined effect of K and geometry for boundary conditions |

## Next Steps

Now that you understand the core concepts, try:

1. **Run the quickstart example**: `python docs/examples/quickstart.py`
2. **Study the TWRI example**: `python docs/examples/twri.py` - a more complex model
3. **Explore the API**: Use your IDE's autocomplete to discover available packages and methods
4. **Read MODFLOW 6 documentation**: [MODFLOW 6 User Guide](https://modflow6.readthedocs.io/)

## Getting Help

- **FloPy Repository**: [github.com/modflowpy/flopy](https://github.com/modflowpy/flopy)
- **MODFLOW 6 Documentation**: [modflow6.readthedocs.io](https://modflow6.readthedocs.io/)
- **xarray Documentation**: [docs.xarray.dev](https://docs.xarray.dev/)
