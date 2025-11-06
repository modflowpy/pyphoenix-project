# # TWRI
#
# Import dependencies.

from pathlib import Path

import numpy as np
import xarray as xr

import flopy4

# Timing
time = flopy4.mf6.utils.time.Time.from_timestamps(
    ["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04"]
)
nper = time.nper

# Grid
nlay = 5
nrow = 15
ncol = 15
shape = (nlay, nrow, ncol)
nodes = np.prod(shape)
delr = np.ones((ncol,)) * 5000.0
delc = np.ones((nrow,)) * 5000.0
idomain = np.ones(shape, dtype=int)
top = np.ones((nrow, ncol), dtype=float) * 200.0
bottom = np.stack([np.full((nrow, ncol), val) for val in [-150.0, -200.0, -300.0, -350.0, -450.0]])
grid = flopy4.mf6.utils.grid.StructuredGrid(
    nlay=nlay, nrow=nrow, ncol=ncol, top=top, botm=bottom, delr=delr, delc=delc, idomain=idomain
)
dims = {"nper": nper, **dict(grid.dataset.sizes)}  # TODO: temporary

# Grid discretization
dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)

# Constant head boundary on the left
chd = flopy4.mf6.gwf.Chd(
    head={"*": {(k, i, 0): 0.0 for k in range(nlay) for i in range(nrow)}},
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Drain in the center left of the model
elevation = [0.0, 0.0, 10.0, 20.0, 30.0, 50.0, 70.0, 90.0, 100.0]
conductance = 1.0
drn = flopy4.mf6.gwf.Drn(
    elev={"*": {(0, 7, j): elevation[j] for j in range(9)}},
    cond={"*": {(0, 7, j): conductance for j in range(9)}},
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Initial conditions
ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)

# Node properties
icelltype = np.stack([np.full((nrow, ncol), val) for val in [1, 0, 0, 0, 0]])
k = np.stack([np.full((nrow, ncol), val) for val in [1.0e-3, 1.0e-8, 1.0e-4, 5.0e-7, 2.0e-4]])
k33 = np.stack([np.full((nrow, ncol), val) for val in [1.0e-3, 1.0e-8, 1.0e-4, 5.0e-7, 2.0e-4]])
npf = flopy4.mf6.gwf.Npf(
    # TODO: no need for reshaping once array structuring converter is done
    icelltype=icelltype.reshape((nodes,)),
    k=k.reshape((nodes,)),
    k33=k33.reshape((nodes,)),
    cvoptions=flopy4.mf6.gwf.Npf.CvOptions(variablecv=True, dewatered=True),
    perched=True,
    save_flows=True,
    dims=dims,
)

# Storage
sto = flopy4.mf6.gwf.Sto(
    storagecoefficient=False,
    ss=1.0e-5,
    sy=0.15,
    transient={"*": False},
    iconvert=0,
    dims=dims,
)

# Uniform recharge on the top layer
rch_rate = xr.full_like(grid.idomain.sel(k=1), 3.0e-8, dtype=float)
rch = flopy4.mf6.gwf.Rch(recharge=rch_rate, dims=dims)

# Output control
# TODO: show both ways to set up the Oc package, strings
# and proper record types? and/or with perioddata param?
oc = flopy4.mf6.gwf.Oc(save_head="all", save_budget="all", dims=dims)

# Wells scattered throughout the model
wel_q = -5.0
wel_nodes = [
    [3, 4, 10, -5.0],
    [2, 3, 5, -5.0],
    [2, 5, 11, -5.0],
    [0, 8, 7, -5.0],
    [0, 8, 9, -5.0],
    [0, 8, 11, -5.0],
    [0, 8, 13, -5.0],
    [0, 10, 7, -5.0],
    [0, 10, 9, -5.0],
    [0, 10, 11, -5.0],
    [0, 10, 13, -5.0],
    [0, 12, 7, -5.0],
    [0, 12, 9, -5.0],
    [0, 12, 11, -5.0],
    [0, 12, 13, -5.0],
]
wel = flopy4.mf6.gwf.Wel(
    q={"*": {(layer, row, col): wel_q for layer, row, col, wel_q in wel_nodes}},
    dims=dims,
)

# Flow model
gwf = flopy4.mf6.gwf.Gwf(
    dis=grid,
    chd=chd,
    ic=ic,
    npf=npf,
    sto=sto,
    oc=oc,
    rch=rch,
    wel=wel,
    drn=drn,
    dims=dims,
)

# Solver
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
)

# TDIS
tdis = flopy4.mf6.simulation.Tdis.from_time(time)

# Create workspace
workspace = Path(__file__).parent / "twri"
workspace.mkdir(parents=True, exist_ok=True)

# Create simulation
sim = flopy4.mf6.simulation.Simulation(
    name="twri",
    tdis=tdis,
    models={"gwf": gwf},
    solutions={"ims": ims},
    workspace=workspace,
)

# Write input files and run the simulation
sim.write()
sim.run()  # assumes the ``mf6`` executable is available on your PATH.

# Load head results
gwf_ws = Path(workspace) / gwf.name
head = flopy4.mf6.utils.open_hds(
    gwf_ws / f"{gwf.name}.hds",
    gwf_ws / f"{dis.name}.dis.grb",
)

# Plot head results
head.isel(layer=0, time=0).plot.contourf()
