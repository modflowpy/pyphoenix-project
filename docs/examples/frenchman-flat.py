# # Frenchman Flat, NV
#
# real-world DIS model
# https://www.sciencebase.gov/catalog/item/641a1b51d34eb496d1d2a1fd
#
# This example reproduces the Frenchman Flat, NV regional groundwater model:
# a 10-layer, 87×87 structured-grid (DIS) simulation with heterogeneous
# hydraulic conductivity, storage, and three well packages representing
# constant-rate pumping, subsurface leakage, and water-sampling extraction.
#
# The script demonstrates different input modes supported by flopy4:
# 1. **Ascii list based input**: traditional MODFLOW package files (always run)
# 2. **Ascii list based with base NetCDF input**: IC, NPF configurational input from NetCDF
# 3. **Layered-mesh NetCDF array based** (`mesh="layered"`): 2-D face-based UGRID NetCDF
# 4. **Structured NetCDF array based** (no `mesh` arg): CF-convention DIS NetCDF
#    (modes 2, 3 and 4 require extended `mf6` and environment variable
#    `MF6_EXTENDED=1` to actually run the MODFLOW simulation)
#
# It also shows how to wrap DIS head and budget output in `xu.UgridDataArray`
# for unstructured-style vector plotting with xugrid.

# ### Import dependencies

import os
from pathlib import Path

import numpy as np

import flopy4

# ### Setup

try:
    FF_ROOT = Path(__file__).parent
except NameError:
    FF_ROOT = Path.cwd()

# ### Define plot functions


def plot_head(head, workspace):
    import matplotlib.pyplot as plt

    # Plot head results
    plt.figure(figsize=(10, 6))
    head.isel(layer=0, time=0).plot.contourf()
    plt.title("Filled Contour Plot FF Head")
    plt.xlabel("x")
    plt.ylabel("y")
    plt.grid(True)
    plt.savefig(workspace / "head.png", dpi=300, bbox_inches="tight")
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        plt.show()
    plt.close()


def plot_head_ugrid(head, cbc, grid, workspace):
    """Plot head and flow vectors using xugrid on a DIS (structured) grid.

    Even though the model uses DIS discretization, we can wrap the 2-D
    (y, x) head slice in a ``xu.UgridDataArray`` by flattening it to a
    face dimension whose topology is defined by ``grid.ugrid``.  This lets
    us use xugrid's plotting API without converting the model to DISV.

    Flow vectors come from the CBC budget terms:
    * ``u = flow-right-face``  (positive = eastward / +x direction)
    * ``v = -flow-front-face`` (negated because MODFLOW's "front" face is
      the south face; positive "front" flow is southward, so we negate to
      get the northward (+y) component for a conventional quiver plot)
    """
    import matplotlib.pyplot as plt
    import xarray as xr
    import xugrid as xu

    ugrid = grid.ugrid
    facedim = ugrid.face_dimension

    # Select first timestep and first layer; flatten (y, x) -> face dimension
    h = head.isel(time=0, layer=0).compute()
    head_uda = xu.UgridDataArray(
        xr.DataArray(h.values.ravel(), dims=[facedim], name="head"),
        grid=ugrid,
    )

    # Flow vectors: u = flow-right-face (+x/east), v = -flow-front-face (+y/north)
    u = cbc["flow-right-face"].isel(time=0, layer=0).compute()
    v = -cbc["flow-front-face"].isel(time=0, layer=0).compute()
    ds = xu.UgridDataset(grids=ugrid)
    ds["u"] = xu.UgridDataArray(
        xr.DataArray(u.values.ravel(), dims=[facedim], name="u"), grid=ugrid
    )
    ds["v"] = xu.UgridDataArray(
        xr.DataArray(v.values.ravel(), dims=[facedim], name="v"), grid=ugrid
    )
    ds = ds.ugrid.assign_face_coords()

    fig, ax = plt.subplots(figsize=(10, 8))
    head_uda.ugrid.plot(ax=ax)
    xu.plot.line(ugrid, ax=ax, color="white", linewidth=0.1)
    ds.plot.quiver(x="mesh2d_face_x", y="mesh2d_face_y", u="u", v="v", color="black")
    ax.set_aspect(1)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title("Head with flow vectors (layer 1, time 0)")
    plt.savefig(workspace / "head_ugrid.png", dpi=300, bbox_inches="tight")
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        plt.show()
    plt.close()


# # Timing
#
# 33 transient stress periods matching the original pumping schedule,
# with 15 time steps per period and a 1.1× geometric time-step multiplier.
time = flopy4.mf6.utils.time.Time(
    perlen=[
        001.17707,
        000.84374,
        004.61527,
        000.41874,
        000.77499,
        077.29513,
        166.49999,
        364.99999,
        364.99999,
        365.99999,
        364.99999,
        364.99999,
        364.99999,
        365.99999,
        364.99999,
        364.99999,
        364.99999,
        365.99999,
        364.99999,
        364.99999,
        364.99999,
        139.40624,
        001.05207,
        297.99027,
        001.02221,
        320.06666,
        000.96735,
        356.89999,
        001.05346,
        376.02568,
        000.95485,
        331.56110,
        364.99999,
    ],
    nstp=[
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
        15,
    ],
    tsmult=[
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
        1.1,
    ],
)

nper = time.nper

# ### Grid

# 87×87 structured grid with variable column widths (`delr`/`delc`) that
# refine toward the centre of the domain where wells are located.
# The upper-left corner (xul, yul) from the source data is converted to the
# lower-left origin expected by `StructuredGrid`.
nlay = 10
nrow = 87
ncol = 87
shape = (nlay, nrow, ncol)
nodes = np.prod(shape)
# The original downloaded model applies a unit-conversion factor of 3.280
# (feet->meters) to delr/delc.  It is set to 1.0 here because the arrays
# were already provided in SI units; the constant is preserved to document
# the relationship to the source data.
# FACTOR = 3.280
FACTOR = 1.0
delr = [
    2500.0,
    2500.0,
    2500.0,
    2150.0,
    1800.0,
    1500.0,
    1250.0,
    1000.0,
    750.0,
    750.0,
    500.0,
    500.0,
    500.0,
    500.0,
    500.0,
    350.0,
    250.0,
    200.0,
    150.0,
    125.0,
    100.0,
    100.0,
    100.0,
    100.0,
    100.0,
    75.0,
    50.0,
    50.0,
    50.0,
    50.0,
    50.0,
    30.0,
    30.0,
    15.0,
    15.0,
    13.5,
    10.0,
    6.5,
    5.0,
    3.5,
    2.5,
    2.0,
    1.5,
    1.0,
    1.5,
    2.0,
    2.5,
    3.5,
    5.0,
    6.5,
    10.0,
    13.5,
    15.0,
    15.0,
    30.0,
    30.0,
    50.0,
    50.0,
    50.0,
    50.0,
    50.0,
    75.0,
    100.0,
    100.0,
    100.0,
    100.0,
    100.0,
    125.0,
    150.0,
    200.0,
    250.0,
    350.0,
    500.0,
    500.0,
    500.0,
    500.0,
    500.0,
    750.0,
    750.0,
    1000.0,
    1250.0,
    1500.0,
    1800.0,
    2150.0,
    2500.0,
    2500.0,
    2500.0,
]
delr = np.array([f * FACTOR for f in delr])
delc = [
    2500.0,
    2500.0,
    2500.0,
    2150.0,
    1800.0,
    1500.0,
    1250.0,
    1000.0,
    750.0,
    750.0,
    500.0,
    500.0,
    500.0,
    500.0,
    500.0,
    350.0,
    250.0,
    200.0,
    150.0,
    125.0,
    100.0,
    100.0,
    100.0,
    100.0,
    100.0,
    75.0,
    50.0,
    50.0,
    50.0,
    50.0,
    50.0,
    30.0,
    30.0,
    15.0,
    15.0,
    13.5,
    10.0,
    6.5,
    5.0,
    3.5,
    2.5,
    2.0,
    1.5,
    1.0,
    1.5,
    2.0,
    2.5,
    3.5,
    5.0,
    6.5,
    10.0,
    13.5,
    15.0,
    15.0,
    30.0,
    30.0,
    50.0,
    50.0,
    50.0,
    50.0,
    50.0,
    75.0,
    100.0,
    100.0,
    100.0,
    100.0,
    100.0,
    125.0,
    150.0,
    200.0,
    250.0,
    350.0,
    500.0,
    500.0,
    500.0,
    500.0,
    500.0,
    750.0,
    750.0,
    1000.0,
    1250.0,
    1500.0,
    1800.0,
    2150.0,
    2500.0,
    2500.0,
    2500.0,
]
delc = np.array([f * FACTOR for f in delc])
idomain = np.ones(shape, dtype=int)
top = np.zeros((nrow, ncol), dtype=float)
bottom = np.stack(
    [
        np.full((nrow, ncol), val)
        for val in [
            -200.0,
            -400.0,
            -600.0,
            -800.0,
            -1050.0,
            -1350.0,
            -1700.0,
            -2200.0,
            -2950.0,
            -3950.0,
        ]
    ]
)
# xul 573309.700         # upper left x-coordinate
# yul 4102552.000        # upper left y-coordinate
grid = flopy4.mf6.utils.grid.StructuredGrid(
    lenuni="meters",
    xoff=573309.700,  # xul == xll
    yoff=4102552.000 - sum(delr),  # yul => yll
    nlay=nlay,
    nrow=nrow,
    ncol=ncol,
    top=top,
    botm=bottom,
    delr=delr,
    delc=delc,
    idomain=idomain,
    crs="EPSG:26911",
)
# `dims` captures array shapes needed by packages that pre-allocate xarray storage.
dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}

# ### Packages

# Discretization package: builds MODFLOW DIS input from the grid object.
dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)

# Initial conditions: zero starting head everywhere.
ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)

# Node-property flow: layer-specific horizontal and vertical conductivity
# loaded from per-layer text arrays.  `FACTOR = 0.1` gives k33 = 0.1 * k
# (10 : 1 horizontal-to-vertical anisotropy).
icelltype = np.stack([np.full((nrow, ncol), val) for val in [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])
k = np.zeros((nlay, nrow, ncol), dtype=float)
k33 = np.zeros((nlay, nrow, ncol), dtype=float)
FACTOR = 0.1
for l in range(nlay):
    pad = "000" if l < 9 else "00"
    k[l, ...] = np.loadtxt(
        FF_ROOT / "data" / "frenchman-flat" / "arrays" / f"Array.MF-HydK_{pad}{l + 1}.txt"
    )
    k33[l, ...] = (
        np.loadtxt(
            FF_ROOT / "data" / "frenchman-flat" / "arrays" / f"Array.MF-HydK_{pad}{l + 1}.txt"
        )
        * FACTOR
    )

npf = flopy4.mf6.gwf.Npf(
    icelltype=icelltype,
    k=k,
    k33=k33,
    save_flows=True,
    dims=dims,
)

# Specific storage loaded from per-layer text arrays; confined storage only
# (`iconvert=0` keeps all layers confined throughout the simulation).
ss = np.zeros((nlay, nrow, ncol), dtype=float)
for l in range(nlay):
    pad = "000" if l < 9 else "00"
    ss[l, ...] = np.loadtxt(
        FF_ROOT / "data" / "frenchman-flat" / "arrays" / f"Array.MF-HydS_{pad}{l + 1}.txt"
    )

sto = flopy4.mf6.gwf.Sto(
    ss=ss,
    iconvert=0,
    dims=dims,
)

# Three separate WEL packages track distinct physical processes at the
# same injection/extraction location (layer 2, row 44, col 44):
# * `wel_crt`: cyclic constant-rate pumping (on/off by stress period)
# * `wel_leak`: subsurface leakage from a radioactive waste site
# * `wel_sampleQ`: water-sampling extraction schedule

# Constant-rate pumping well: alternates between extraction and shut-in.
wel_crt = flopy4.mf6.gwf.Wel(
    filename="ff.crt.wel",
    q={
        0: {
            (1, 43, 43): -30992.50,
        },
        1: {
            (1, 43, 43): -00000.0,
        },
        2: {
            (1, 43, 43): -30992.50,
        },
        3: {
            (1, 43, 43): -00000.0,
        },
        4: {
            (1, 43, 43): -30992.50,
        },
        5: {
            (1, 43, 43): -00000.0,
        },
    },
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Leakage well: injects contaminated water at rates that vary by period.
wel_leak = flopy4.mf6.gwf.Wel(
    filename="ff.leak.wel",
    q={
        0: {
            (1, 43, 43): 1.0000000e-05,
        },
        7: {
            (1, 43, 43): 1.5000000e03,
        },
        8: {
            (1, 43, 43): 2.6500000e03,
        },
        9: {
            (1, 43, 43): 3.1500000e03,
        },
        10: {
            (1, 43, 43): 4.1000000e03,
        },
        11: {
            (1, 43, 43): 4.6500000e03,
        },
        12: {
            (1, 43, 43): 4.9500000e03,
        },
        13: {
            (1, 43, 43): 5.3000000e03,
        },
        14: {
            (1, 43, 43): 5.8000000e03,
        },
        16: {
            (1, 43, 43): 5.9000000e03,
        },
        17: {
            (1, 43, 43): 5.8000000e03,
        },
        19: {
            (1, 43, 43): 5.6000000e03,
        },
        20: {
            (1, 43, 43): 4.7000000e03,
        },
        22: {
            (1, 43, 43): 3.4000000e03,
        },
        23: {
            (1, 43, 43): 1.0000000e-05,
        },
    },
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Sampling well: extracts water for monitoring at scheduled intervals.
wel_sampleQ = flopy4.mf6.gwf.Wel(
    filename="ff.sampleQ.wel",
    q={
        0: {
            (1, 43, 43): -00000.0,
        },
        22: {
            (1, 43, 43): -04981.90,
        },
        23: {
            (1, 43, 43): -00000.0,
        },
        24: {
            (1, 43, 43): -04059.83,
        },
        25: {
            (1, 43, 43): -00000.0,
        },
        26: {
            (1, 43, 43): -05678.75,
        },
        27: {
            (1, 43, 43): -00000.0,
        },
        28: {
            (1, 43, 43): -05755.75,
        },
        29: {
            (1, 43, 43): -00000.0,
        },
        30: {
            (1, 43, 43): -04117.58,
        },
        31: {
            (1, 43, 43): -00000.0,
        },
    },
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)

# Save heads at every time step; save budget only at selected steps to keep
# output file size manageable for this large model.
oc = flopy4.mf6.gwf.Oc(
    budget_file=Path("ff.cbc"),
    head_file=Path("ff.hds"),
    perioddata={
        0: flopy4.mf6.gwf.Oc.PrintSaveSetting(
            printrecord=[
                flopy4.mf6.gwf.Oc.PrintRecord(
                    "budget",
                    flopy4.mf6.gwf.Oc.Steps(
                        steps=(
                            0,
                            99,
                        )
                    ),
                ),
            ],
            saverecord=[
                flopy4.mf6.gwf.Oc.SaveRecord("head", flopy4.mf6.gwf.Oc.Steps(all=True)),
                flopy4.mf6.gwf.Oc.SaveRecord("budget", flopy4.mf6.gwf.Oc.Steps(steps=(0,))),
            ],
        ),
        1: flopy4.mf6.gwf.Oc.PrintSaveSetting(
            printrecord=[
                flopy4.mf6.gwf.Oc.PrintRecord("budget", flopy4.mf6.gwf.Oc.Steps(last=True)),
            ],
            saverecord=[
                flopy4.mf6.gwf.Oc.SaveRecord("head", flopy4.mf6.gwf.Oc.Steps(all=True)),
            ],
        ),
    },
    dims=dims,
)

# ### FLow Model

# assemble GWF model from all packages defined above.
gwf = flopy4.mf6.gwf.Gwf(
    dis=grid,
    ic=ic,
    npf=npf,
    sto=sto,
    oc=oc,
    wel=[wel_crt, wel_leak, wel_sampleQ],
    dims=dims,
)

# ### Solver

# BiCGSTAB with dynamic under-relaxation (DBD) handles the
# non-symmetric system that arises from the unconfined/transient conditions.
ims = flopy4.mf6.Ims(
    print_option="summary",
    complexity="moderate",
    outer_dvclose=0.01,
    outer_maximum=50,
    under_relaxation="DBD",
    under_relaxation_theta=0.9,
    under_relaxation_kappa=0.0001,
    under_relaxation_gamma=0.000000,
    under_relaxation_momentum=0.000000,
    inner_dvclose=0.00001,
    inner_rclose=0.1,
    inner_maximum=100,
    linear_acceleration="bicgstab",
    number_orthogonalizations=0,
    reordering_method=None,
    models=["ff"],
)

# ### TDIS

tdis = flopy4.mf6.simulation.Tdis.from_time(time)

# ### Write and run — ascii list based inputs

# Create workspace
workspace = FF_ROOT / "frenchman-flat" / "list"
workspace.mkdir(parents=True, exist_ok=True)

# ### Simulation

# link the model and solver, then write and run.
sim = flopy4.mf6.simulation.Simulation(
    name="ff",
    tdis=tdis,
    models={"ff": gwf},
    solutions={"ims": ims},
    workspace=workspace,
)

# run verbose only this time
sim.write()
sim.run(verbose=True)

# ### Load head results

# Load head results
head = flopy4.mf6.utils.open_hds(
    workspace / "ff.hds",
    workspace / "ff.dis.grb",
)

# Load budget results
cbc = flopy4.mf6.utils.open_cbc(
    workspace / "ff.cbc",
    workspace / "ff.dis.grb",
)

# Plot head results
plot_head(head, workspace)
plot_head_ugrid(head, cbc, grid, workspace)

# ### NetCDF (mesh) base package input

# `NetCDFModel.from_model(gwf, mesh="layered")` writes a layered UGRID mesh
# NetCDF containing the NPF, STO, and IC arrays.  WEL packages remain list-
# based in the text input files.  Requires `MF6_EXTENDED=1` to run MODFLOW.

# create new workspace
workspace = FF_ROOT / "frenchman-flat" / "netcdf_base"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "frenchman-flat.input.nc"
gwf.netcdf_file = nc_fpth

# Here, grid and time info is passed to the `NetCDFModel' constructor
# so that coordinate and mesh data is written to the NetCDF file.
nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, mesh="layered", grid=grid, time=time)
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()

if os.getenv("MF6_EXTENDED"):
    sim.run()

    # Load head results
    head = flopy4.mf6.utils.open_hds(
        workspace / "ff.hds",
        workspace / "ff.dis.grb",
    )

    # Load budget results
    cbc = flopy4.mf6.utils.open_cbc(
        workspace / "ff.cbc",
        workspace / "ff.dis.grb",
    )

    # Plot head results
    plot_head(head, workspace)
    plot_head_ugrid(head, cbc, grid, workspace)

# ### Array-based NetCDF WEL packages + layered mesh NetCDF output

# Switch the three WEL packages from list-based to array-based (`Welg`),
# combine with a layered-mesh NetCDF input file, and also request mesh2d
# NetCDF output (`gwf.netcdf_mesh2d_file`).  `FILL_DNODATA` marks inactive
# cells so MODFLOW ignores them for those stress periods.

# update simulation with array based inputs
GRID_NODATA = np.full((nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA, dtype=float)

# Constant-rate pumping — array form of wel_crt.
q_crt = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
q_crt[0, 1, 43, 43] = -30992.50
q_crt[1, 1, 43, 43] = -00000.0
q_crt[2, 1, 43, 43] = -30992.50
q_crt[3, 1, 43, 43] = -00000.0
q_crt[4, 1, 43, 43] = -30992.50
q_crt[5, 1, 43, 43] = -00000.0
welg_crt = flopy4.mf6.gwf.Welg(
    filename="ff.crt.welg",
    q=q_crt,
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)


# Leakage — array form of wel_leak.
q_leak = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
q_leak[0, 1, 43, 43] = 1.0000000e-05
q_leak[7, 1, 43, 43] = 1.5000000e03
q_leak[8, 1, 43, 43] = 2.6500000e03
q_leak[9, 1, 43, 43] = 3.1500000e03
q_leak[10, 1, 43, 43] = 4.1000000e03
q_leak[11, 1, 43, 43] = 4.6500000e03
q_leak[12, 1, 43, 43] = 4.9500000e03
q_leak[13, 1, 43, 43] = 5.3000000e03
q_leak[14, 1, 43, 43] = 5.8000000e03
q_leak[16, 1, 43, 43] = 5.9000000e03
q_leak[17, 1, 43, 43] = 5.8000000e03
q_leak[19, 1, 43, 43] = 5.6000000e03
q_leak[20, 1, 43, 43] = 4.7000000e03
q_leak[22, 1, 43, 43] = 3.4000000e03
q_leak[23, 1, 43, 43] = 1.0000000e-05
welg_leak = flopy4.mf6.gwf.Welg(
    filename="ff.leak.welg",
    q=q_leak,
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)


# Sampling — array form of wel_sampleQ.
q_sampleQ = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
q_sampleQ[0, 1, 43, 43] = -00000.0
q_sampleQ[22, 1, 43, 43] = -04981.90
q_sampleQ[23, 1, 43, 43] = -00000.0
q_sampleQ[24, 1, 43, 43] = -04059.83
q_sampleQ[25, 1, 43, 43] = -00000.0
q_sampleQ[26, 1, 43, 43] = -05678.75
q_sampleQ[27, 1, 43, 43] = -00000.0
q_sampleQ[28, 1, 43, 43] = -05755.75
q_sampleQ[29, 1, 43, 43] = -00000.0
q_sampleQ[30, 1, 43, 43] = -04117.58
q_sampleQ[31, 1, 43, 43] = -00000.0
welg_sampleQ = flopy4.mf6.gwf.Welg(
    filename="ff.sampleQ.welg",
    q=q_sampleQ,
    print_input=True,
    print_flows=True,
    save_flows=True,
    dims=dims,
)


# Swap list-based WEL packages for their array-based equivalents.
del gwf.wel[0]
del gwf.wel[1]
del gwf.wel[2]

# Attach the array-based WEL packages.
gwf.wel = [welg_crt, welg_leak, welg_sampleQ]

# create new workspace
workspace = FF_ROOT / "frenchman-flat" / "netcdf_mesh"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

gwf.netcdf_mesh2d_file = Path("frenchman-flat.nc")
gwf.netcdf_file = Path("frenchman-flat.input.nc")

# Again, with grid and time info
nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, mesh="layered", grid=grid, time=time)
nc_model.to_netcdf(workspace / "frenchman-flat.input.nc")

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()
if os.getenv("MF6_EXTENDED"):
    sim.run()

    # Load head results
    # head = flopy4.mf6.utils.open_hds(
    #    workspace / "ff.hds",
    #    workspace / "ff.dis.grb",
    # )
    # Load head results — `UgridDataArray` backed by the NetCDF mesh2d output file.
    head = flopy4.mf6.utils.open_hds(
        workspace / gwf.netcdf_mesh2d_file,
        workspace / "ff.dis.grb",
    )

    # Load budget results
    cbc = flopy4.mf6.utils.open_cbc(
        workspace / "ff.cbc",
        workspace / "ff.dis.grb",
    )

    # Plot head results
    plot_head(head, workspace)
    plot_head_ugrid(head, cbc, grid, workspace)

# # NetCDF input — structured (no mesh)
#
# ![QGIS: Frenchman Flat K layer 7 input — layered mesh](images/ff.qgis.npf-k-layer7.png)

# ### NetCDF input — structured (no mesh)

# `NetCDFModel.from_model(gwf, grid=grid, time=time)` (no `mesh` argument)
# writes a CF-convention structured NetCDF.  This is a simpler format than
# the layered-mesh variant and does not require a UGRID-capable MODFLOW build.
workspace = FF_ROOT / "frenchman-flat" / "netcdf_structured"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "frenchnam-flat.input.nc"
gwf.netcdf_file = nc_fpth

# Again, with grid and time info
nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, grid=grid, time=time)
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()
if os.getenv("MF6_EXTENDED"):
    sim.run()

    # Load head results
    head = flopy4.mf6.utils.open_hds(
        workspace / "ff.hds",
        workspace / "ff.dis.grb",
    )

    # Load budget results
    cbc = flopy4.mf6.utils.open_cbc(
        workspace / "ff.cbc",
        workspace / "ff.dis.grb",
    )

    # Plot head results
    plot_head(head, workspace)
    plot_head_ugrid(head, cbc, grid, workspace)
