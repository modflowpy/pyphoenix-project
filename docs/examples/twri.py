# # TWRI
#
# Transient Well, Recharge, and Injection
#
# The TWRI problem is a classical MODFLOW benchmark: a three-layer aquifer
# system with heterogeneous hydraulic conductivity, storage, a constant-head
# left boundary, a drain, recharge, and scattered pumping wells.
#
# This script demonstrates distinct ways to specify stress packages:
# 1. **List-based** (`Chd`, `Drn`, `Wel`): cell-by-cell `{(layer, row, col): value}` dicts
# 2. **Array-based** (`Chdg`, `Drng`, `Welg`): full `(nper, nlay, nrow, ncol)` arrays
#    with `FILL_DNODATA` marking inactive cells
# 3. **NetCDF input**: array data written to a `.nc` file and referenced by the
#    simulation (requires extended `mf6` and environment variable `MF6_EXTENDED=1`
#    to actually run the MODFLOW simulation)
#

# ### Import dependencies

import os
from pathlib import Path

import numpy as np

import flopy4

# ### Setup

try:
    TWRI_ROOT = Path(__file__).parent
except NameError:
    TWRI_ROOT = Path.cwd()

# ### Define plot function


def plot_head(head, workspace):
    import matplotlib.pyplot as plt

    # Plot head results
    plt.figure(figsize=(10, 6))
    head.isel(layer=0, time=0).plot.contourf()
    plt.title("Filled Contour Plot TWRI Head")
    plt.xlabel("x")
    plt.ylabel("y")
    plt.grid(True)
    plt.savefig(workspace / "head.png", dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()


# ### Timing

# Four daily stress periods; the first is steady-state, the rest transient.
time = flopy4.mf6.utils.time.Time.from_timestamps(
    ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04"]
)
nper = time.nper

# ### Grid

# Three-layer, 15×15 structured grid; 5,000 m cells capture a regional aquifer.
nlay = 3
nrow = 15
ncol = 15
shape = (nlay, nrow, ncol)
nodes = np.prod(shape)
delr = np.ones((ncol,)) * 5000.0
delc = np.ones((nrow,)) * 5000.0
idomain = np.ones(shape, dtype=int)
top = np.ones((nrow, ncol), dtype=float) * 200.0
bottom = np.stack([np.full((nrow, ncol), val) for val in [-200.0, -300.0, -450.0]])
grid = flopy4.mf6.utils.grid.StructuredGrid(
    nlay=nlay, nrow=nrow, ncol=ncol, top=top, botm=bottom, delr=delr, delc=delc, idomain=idomain
)
dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}  # TODO: temporary

# ### Packages

# Discretization package: builds MODFLOW DIS input from the grid object.
# The grid origin can be set with `xoff`/`yoff` to place the model in a
# real-world coordinate system; it is omitted here for simplicity.
dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)

# Constant head boundary on the left: pins head to 0 m on the left column,
# creating the hydraulic gradient that drives flow through the domain.
chd = flopy4.mf6.gwf.Chd(
    head={"*": {(k, i, 0): 0.0 for k in range(nlay - 1) for i in range(nrow)}},
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Drain in the center left of the model: removes water when head exceeds
# the drain elevation, simulating a stream or tile drain.
elevation = [0.0, 0.0, 10.0, 20.0, 30.0, 50.0, 70.0, 90.0, 100.0]
conductance = 1.0
drn = flopy4.mf6.gwf.Drn(
    elev={"*": {(0, 7, j + 1): elevation[j] for j in range(9)}},
    cond={"*": {(0, 7, j + 1): conductance for j in range(9)}},
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Initial conditions
ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)

# Node-property flow: heterogeneous horizontal (k) and vertical (k33)
# conductivity; layer 1 is convertible (unconfined), layers 2–3 confined.
icelltype = np.stack([np.full((nrow, ncol), val) for val in [1, 0, 0]])
k = np.stack([np.full((nrow, ncol), val) for val in [1.0e-3, 1.0e-4, 2.0e-4]])
k33 = np.stack([np.full((nrow, ncol), val) for val in [2.0e-8, 2.0e-8, 2.0e-8]])
npf = flopy4.mf6.gwf.Npf(
    icelltype=icelltype,
    k=k,
    k33=k33,
    cvoptions=flopy4.mf6.gwf.Npf.CvOptions(dewatered=True),
    perched=True,
    save_flows=True,
    dims=dims,
)

# Storage: specific storage (ss) and specific yield (sy); period 1 is steady-state.
sto = flopy4.mf6.gwf.Sto(
    storagecoefficient=False,
    ss=1.0e-5,
    sy=0.15,
    steady_state=[True, False, False],
    iconvert=0,
    dims=dims,
)

# Uniform recharge on the top layer.  `FILL_DNODATA` is the sentinel
# value that marks cells with no stress data for a given period.
rch_rate = np.full((nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA)
rate = np.repeat(np.expand_dims(rch_rate, axis=0), repeats=nper, axis=0)
rate[0, 0, ...] = 3.0e-8
rch = flopy4.mf6.gwf.Rch(recharge=rate, dims=dims)

# Output control: save heads and budget at the start of the simulation.
oc = flopy4.mf6.gwf.Oc(
    budget_file="gwf.bud",
    head_file="gwf.hds",
    save_head={0: "all"},
    save_budget={0: "all"},
    dims=dims,
)

# Wells scattered throughout the model: extraction is negative by MODFLOW convention.
wel_q = -5.0
wel_nodes = [
    [2, 4, 10],
    [1, 3, 5],
    [1, 5, 11],
    [0, 8, 7],
    [0, 8, 9],
    [0, 8, 11],
    [0, 8, 13],
    [0, 10, 7],
    [0, 10, 9],
    [0, 10, 11],
    [0, 10, 13],
    [0, 12, 7],
    [0, 12, 9],
    [0, 12, 11],
    [0, 12, 13],
]
wel = flopy4.mf6.gwf.Wel(
    q={"*": {(layer, row, col): wel_q for layer, row, col in wel_nodes}},
    dims=dims,
)

# ### Flow Model

# assemble GWF model from all packages defined above.
gwf = flopy4.mf6.gwf.Gwf(
    dis=grid,
    ic=ic,
    npf=npf,
    sto=sto,
    oc=oc,
    chd=[chd],
    rch=[rch],
    wel=[wel],
    drn=[drn],
    dims=dims,
)

# ### Solver

# conjugate-gradient with relaxation; suitable for symmetric SPD systems.
ims = flopy4.mf6.Ims(
    print_option="summary",
    outer_dvclose=1.0e-4,
    outer_maximum=500,
    under_relaxation=None,
    inner_dvclose=1.0e-4,
    inner_rclose=0.001,
    inner_maximum=100,
    linear_acceleration="cg",
    scaling_method=None,
    reordering_method=None,
    relaxation_factor=0.97,
    models=["gwf"],
)

# ### TDIS

tdis = flopy4.mf6.simulation.Tdis.from_time(time)

# ### Write and run — list-based stress packages

# Create workspace
workspace = TWRI_ROOT / "twri" / "list"
workspace.mkdir(parents=True, exist_ok=True)

# Simulation: link the model and solver, then write and run.
sim = flopy4.mf6.simulation.Simulation(
    name="twri",
    tdis=tdis,
    models={"gwf": gwf},
    solutions={"ims": ims},
    workspace=workspace,
)

# Write input files and run the simulation
sim.write()
sim.run(verbose=True)  # assumes the ``mf6`` executable is available on your PATH.

# ### Load head results

head = flopy4.mf6.utils.open_hds(
    workspace / f"{gwf.name}.hds",
    workspace / f"{gwf.name}.dis.grb",
)

# ### Plot head results

plot_head(head, workspace)

# ### Array-based stress packages

# The `Chdg`, `Drng`, and `Welg` ("G" = grid-array) variants accept a full
# `(nper, nlay, nrow, ncol)` NumPy array.  Cells inactive for a given stress
# period are set to `FILL_DNODATA`; MODFLOW skips those cells automatically.

# update simulation with array based inputs
LAYER_NODATA = np.full((nrow, ncol), flopy4.mf6.constants.FILL_DNODATA, dtype=float)
GRID_NODATA = np.full((nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA, dtype=float)

chd_head = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
for i in range(nrow):
    for k in range(nlay - 1):
        chd_head[0, k, i, 0] = 0.0
chdg = flopy4.mf6.gwf.Chdg(
    print_input=True,
    print_flows=True,
    save_flows=True,
    head=chd_head,
    dims=dims,
)

# Array-based drain: same geometry as the list-based version above.
elev = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
cond = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
for j in range(9):
    elev[0, 0, 7, j + 1] = elevation[j]
    cond[0, 0, 7, j + 1] = conductance
drng = flopy4.mf6.gwf.Drng(
    print_input=True,
    print_flows=True,
    save_flows=True,
    elev=elev,
    cond=cond,
    dims=dims,
)

# well
q = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
for layer, row, col in wel_nodes:
    q[0, layer, row, col] = wel_q
welg = flopy4.mf6.gwf.Welg(
    q=q,
    dims=dims,
)

# recharge
recharge = np.repeat(np.expand_dims(LAYER_NODATA, axis=0), repeats=nper, axis=0)
recharge[0, ...] = 3.0e-8
rcha = flopy4.mf6.gwf.Rcha(recharge=recharge, dims=dims)

# Swap list-based packages for array-based equivalents.
# `gwf.chd.remove(chd)` removes by object identity; `del gwf.drn[0]`
# removes by index.  Both leave the rest of the package list intact.
gwf.chd.remove(chd)
del gwf.drn[0]
del gwf.wel[0]
del gwf.rch[0]

# Attach the array-based packages.
gwf.chd = [chdg]
gwf.drn = [drng]
gwf.wel = [welg]
gwf.rch = [rcha]

# ### Write and run — array-based stress packages

# create new workspace
workspace = TWRI_ROOT / "twri" / "array"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

sim.write()
sim.run(verbose=True)

# ### Load head results

head = flopy4.mf6.utils.open_hds(
    workspace / f"{gwf.name}.hds",
    workspace / f"{gwf.name}.dis.grb",
)

# ### Plot head results

plot_head(head, workspace)

# ### NetCDF input — structured (no mesh)

# `NetCDFModel.from_model(gwf)` serializes all array-based packages to a
# CF-compliant NetCDF file that MODFLOW 6 reads directly.  Running the
# simulation requires a NetCDF-capable build; guard with `MF6_EXTENDED`.

# Create workspace
workspace = TWRI_ROOT / "twri" / "netcdf_structured"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "twri.input.nc"
gwf.netcdf_file = nc_fpth

nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf)
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()

if os.getenv("MF6_EXTENDED"):
    sim.run(verbose=True)

    # Load head results
    head = flopy4.mf6.utils.open_hds(
        workspace / f"{gwf.name}.hds",
        workspace / f"{gwf.name}.dis.grb",
    )

    # Plot head results
    plot_head(head, workspace)

# ### NetCDF input — layered mesh

# `mesh="layered"` writes a layered UGRID mesh NetCDF, which MODFLOW 6
# reads with its NetCDF-mesh2d input mode.

# Create workspace
workspace = TWRI_ROOT / "twri" / "netcdf_mesh"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "twri.input.nc"
gwf.netcdf_file = nc_fpth

nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, mesh="layered")
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()

if os.getenv("MF6_EXTENDED"):
    sim.run(verbose=True)

    # Load head results
    head = flopy4.mf6.utils.open_hds(
        workspace / f"{gwf.name}.hds",
        workspace / f"{gwf.name}.dis.grb",
    )

    # Plot head results
    plot_head(head, workspace)
