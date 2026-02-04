# Frenchman Flat NV
# https://www.sciencebase.gov/catalog/item/641a1b51d34eb496d1d2a1fd
from pathlib import Path

import numpy as np

import flopy4


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
    plt.close()


# Timing
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

# Grid
nlay = 10
nrow = 87
ncol = 87
shape = (nlay, nrow, ncol)
nodes = np.prod(shape)
# TODO This is the factor in the downloaded model which changes sim results if removed.
#   However, when it is applied the generated grid does not match the model domain on the website
#   or downloaded jpeg.  Seems like it shouldn't be applied to delr/delc in the downloaded model?
# FACTOR = 3.280  # TODO
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
dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}

# discretization
dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)

# Initial conditions
ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)

# NPF
icelltype = np.stack([np.full((nrow, ncol), val) for val in [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])
k = np.zeros((nlay, nrow, ncol), dtype=float)
k33 = np.zeros((nlay, nrow, ncol), dtype=float)
FACTOR = 0.1
for l in range(nlay):
    pad = "000" if l < 9 else "00"
    k[l, ...] = np.loadtxt(
        Path(__file__).parent
        / "data"
        / "frenchman-flat"
        / "arrays"
        / f"Array.MF-HydK_{pad}{l + 1}.txt"
    )
    k33[l, ...] = (
        np.loadtxt(
            Path(__file__).parent
            / "data"
            / "frenchman-flat"
            / "arrays"
            / f"Array.MF-HydK_{pad}{l + 1}.txt"
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

# Storage
ss = np.zeros((nlay, nrow, ncol), dtype=float)
for l in range(nlay):
    pad = "000" if l < 9 else "00"
    ss[l, ...] = np.loadtxt(
        Path(__file__).parent
        / "data"
        / "frenchman-flat"
        / "arrays"
        / f"Array.MF-HydS_{pad}{l + 1}.txt"
    )

sto = flopy4.mf6.gwf.Sto(
    ss=ss,
    iconvert=0,
    dims=dims,
)

# WEL constant rate
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

# WEL leakage
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

# WEL sampling
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

# Output control
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

# Flow model
gwf = flopy4.mf6.gwf.Gwf(
    dis=grid,
    ic=ic,
    npf=npf,
    sto=sto,
    oc=oc,
    wel=[wel_crt, wel_leak, wel_sampleQ],
    dims=dims,
)

# Solver
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

# TDIS
tdis = flopy4.mf6.simulation.Tdis.from_time(time)

# Create workspace
workspace = Path(__file__).parent / "frenchman-flat" / "ff"
workspace.mkdir(parents=True, exist_ok=True)

# Create simulation
sim = flopy4.mf6.simulation.Simulation(
    name="ff",
    tdis=tdis,
    models={"ff": gwf},
    solutions={"ims": ims},
    workspace=workspace,
)

sim.write()
sim.run()

# Load head results
head = flopy4.mf6.utils.open_hds(
    workspace / "ff.hds",
    workspace / "ff.dis.grb",
)

# Plot head results
plot_head(head, workspace)

# netcdf input (no netcdf stress package input)
# create new workspace
workspace = Path(__file__).parent / "frenchman-flat" / "ff_netcdf"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "frenchman-flat.input.nc"
gwf.netcdf_file = nc_fpth

nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, mesh="layered", grid=grid, time=time)
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()

# extended mf6 required to run
# sim.run()

# Load head results
# head = flopy4.mf6.utils.open_hds(
#    workspace / "ff.hds",
#    workspace / "ff.dis.grb",
# )

# Plot head results
# plot_head(head, workspace)

# update simulation with array based inputs
LAYER_NODATA = np.full((nrow, ncol), flopy4.mf6.constants.FILL_DNODATA, dtype=float)
GRID_NODATA = np.full((nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA, dtype=float)

# well
q = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=nper, axis=0)
q[0, 1, 43, 43] = -30992.50
q[1, 1, 43, 43] = -00000.0
q[2, 1, 43, 43] = -30992.50
q[3, 1, 43, 43] = -00000.0
q[4, 1, 43, 43] = -30992.50
q[5, 1, 43, 43] = -00000.0
welg_crt = flopy4.mf6.gwf.Welg(
    q=q,
    dims=dims,
)

# remove list base WEL packages
del gwf.wel[0]
del gwf.wel[1]
del gwf.wel[2]

# add array based WEL package
gwf.wel = [welg_crt]

# Don't generate outputs so they aren't checked in testing-
# the model has been modified (single wel package)
gwf.oc = None

# create new workspace
workspace = Path(__file__).parent / "frenchman-flat" / "ff_array_mesh"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

gwf.netcdf_mesh2d_file = Path("frenchman-flat.nc")
gwf.netcdf_file = Path("frenchman-flat.input.nc")

nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, mesh="layered", grid=grid, time=time)
nc_model.to_netcdf(workspace / "frenchman-flat.input.nc")

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()
# requires extended mf6
# sim.run()

workspace = Path(__file__).parent / "frenchman-flat" / "ff_array_structured"
workspace.mkdir(parents=True, exist_ok=True)
sim.workspace = workspace

nc_fpth = workspace / "frenchnam-flat.input.nc"
gwf.netcdf_file = nc_fpth

nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, grid=grid, time=time)
nc_model.to_netcdf(nc_fpth)

with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
    sim.write()
# requires extended mf6
# sim.run()
