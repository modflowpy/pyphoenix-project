# flopy4's constructor annotations are narrower than its converters accept
# mypy: disable-error-code="arg-type,list-item,misc"
"""The Frenchman Flat model (``docs/examples/frenchman-flat.py``), built
directly with flopy4 or flopy3: 10 layers x 87 rows x 87 columns (75K
cells), 33 stress periods, and three WEL packages of one cell each."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np

NAME = "ff"
DATA_ROOT = Path(__file__).parents[2] / "docs" / "examples" / "data" / "frenchman-flat" / "arrays"
NLAY, NROW, NCOL = 10, 87, 87
BOTM = [-200, -400, -600, -800, -1050, -1350, -1700, -2200, -2950, -3950]

PERLEN = [
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
]

DELR = np.array(
    [
        2500,
        2500,
        2500,
        2150,
        1800,
        1500,
        1250,
        1000,
        750,
        750,
        500,
        500,
        500,
        500,
        500,
        350,
        250,
        200,
        150,
        125,
        100,
        100,
        100,
        100,
        100,
        75,
        50,
        50,
        50,
        50,
        50,
        30,
        30,
        15,
        15,
        13.5,
        10,
        6.5,
        5,
        3.5,
        2.5,
        2,
        1.5,
        1,
        1.5,
        2,
        2.5,
        3.5,
        5,
        6.5,
        10,
        13.5,
        15,
        15,
        30,
        30,
        50,
        50,
        50,
        50,
        50,
        75,
        100,
        100,
        100,
        100,
        100,
        125,
        150,
        200,
        250,
        350,
        500,
        500,
        500,
        500,
        500,
        750,
        750,
        1000,
        1250,
        1500,
        1800,
        2150,
        2500,
        2500,
        2500,
    ],
    dtype=float,
)

# WEL stress period data — used for both flopy4 (Wel/Welg) and flopy3
_WEL_CRT = {
    0: {(1, 43, 43): -30992.50},
    1: {(1, 43, 43): 0.0},
    2: {(1, 43, 43): -30992.50},
    3: {(1, 43, 43): 0.0},
    4: {(1, 43, 43): -30992.50},
    5: {(1, 43, 43): 0.0},
}
_WEL_LEAK = {
    0: {(1, 43, 43): 1e-05},
    7: {(1, 43, 43): 1.5e3},
    8: {(1, 43, 43): 2.65e3},
    9: {(1, 43, 43): 3.15e3},
    10: {(1, 43, 43): 4.1e3},
    11: {(1, 43, 43): 4.65e3},
    12: {(1, 43, 43): 4.95e3},
    13: {(1, 43, 43): 5.3e3},
    14: {(1, 43, 43): 5.8e3},
    16: {(1, 43, 43): 5.9e3},
    17: {(1, 43, 43): 5.8e3},
    19: {(1, 43, 43): 5.6e3},
    20: {(1, 43, 43): 4.7e3},
    22: {(1, 43, 43): 3.4e3},
    23: {(1, 43, 43): 1e-05},
}
_WEL_SAMPLEQ = {
    0: {(1, 43, 43): 0.0},
    22: {(1, 43, 43): -4981.90},
    23: {(1, 43, 43): 0.0},
    24: {(1, 43, 43): -4059.83},
    25: {(1, 43, 43): 0.0},
    26: {(1, 43, 43): -5678.75},
    27: {(1, 43, 43): 0.0},
    28: {(1, 43, 43): -5755.75},
    29: {(1, 43, 43): 0.0},
    30: {(1, 43, 43): -4117.58},
    31: {(1, 43, 43): 0.0},
}
_WEL_DICTS = [_WEL_CRT, _WEL_LEAK, _WEL_SAMPLEQ]
_WEL_NAMES = ["crt", "leak", "sampleQ"]


def load_arrays():
    """K, K33 and SS, from the example's data."""
    k = np.zeros((NLAY, NROW, NCOL))
    ss = np.zeros((NLAY, NROW, NCOL))
    for lay in range(NLAY):
        k[lay] = np.loadtxt(DATA_ROOT / f"Array.MF-HydK_{lay + 1:04d}.txt")
        ss[lay] = np.loadtxt(DATA_ROOT / f"Array.MF-HydS_{lay + 1:04d}.txt")
    return k, k * 0.1, ss


def _welg_array(q_data: dict, nper: int) -> np.ndarray:
    from flopy4.mf6.constants import FILL_DNODATA

    arr = np.full((nper, NLAY, NROW, NCOL), FILL_DNODATA)
    for period, cells in q_data.items():
        for (lay, row, col), q in cells.items():
            arr[period, lay, row, col] = q
    return arr


def build_flopy4(ws: Path, wel: str = "list") -> SimpleNamespace:
    """The model in flopy4, in `ws`, its wells as WEL lists (`wel="list"`)
    or as WELG grids (``"grid"``, 3 x 7.5M elements). Returns the
    simulation, model, grid and time discretization."""
    import flopy4

    k, k33, ss = load_arrays()
    time = flopy4.mf6.utils.time.Time(
        perlen=PERLEN, nstp=[15] * len(PERLEN), tsmult=[1.1] * len(PERLEN)
    )
    nper = time.nper
    grid = flopy4.mf6.utils.grid.StructuredGrid(
        lenuni="meters",
        xoff=573309.700,
        yoff=4102552.000 - DELR.sum(),
        nlay=NLAY,
        nrow=NROW,
        ncol=NCOL,
        top=np.zeros((NROW, NCOL)),
        botm=np.stack([np.full((NROW, NCOL), v) for v in BOTM]),
        delr=DELR,
        delc=DELR.copy(),
        idomain=np.ones((NLAY, NROW, NCOL), dtype=int),
        crs="EPSG:26911",
    )
    dims = {"nper": nper, **grid.dims}
    gwf = flopy4.mf6.gwf
    if wel == "list":
        wels = [
            gwf.Wel(
                filename=f"{NAME}.{name}.wel",
                stress_period_data={p: list(cells.items()) for p, cells in data.items()},
                print_input=True,
                print_flows=True,
                save_flows=True,
                dims=dims,
            )
            for name, data in zip(_WEL_NAMES, _WEL_DICTS)
        ]
    else:
        wels = [
            gwf.Welg(
                filename=f"{NAME}.{name}.welg",
                q=_welg_array(data, nper),
                print_input=True,
                print_flows=True,
                save_flows=True,
                dims=dims,
            )
            for name, data in zip(_WEL_NAMES, _WEL_DICTS)
        ]
    model = gwf.Gwf(
        name=NAME,
        dis=grid,
        ic=gwf.Ic(strt=0.0, dims=dims),
        npf=gwf.Npf(
            icelltype=np.zeros((NLAY, NROW, NCOL), dtype=int),
            k=k,
            k33=k33,
            save_flows=True,
            dims=dims,
        ),
        sto=gwf.Sto(ss=ss, iconvert=0, dims=dims),
        oc=gwf.Oc(
            budget_file=Path(f"{NAME}.cbc"),
            head_file=Path(f"{NAME}.hds"),
            stress_period_data={
                0: [
                    ("SAVE", "HEAD", "ALL"),
                    ("SAVE", "BUDGET", "STEPS", 1),
                    ("PRINT", "BUDGET", "STEPS", 1, 15),
                ],
                1: [("SAVE", "HEAD", "ALL"), ("PRINT", "BUDGET", "LAST")],
            },
            dims=dims,
        ),
        wel=wels,
        dims=dims,
    )
    ims = flopy4.mf6.Ims(
        print_option="summary",
        complexity="moderate",
        outer_dvclose=0.01,
        outer_maximum=50,
        under_relaxation="DBD",
        under_relaxation_theta=0.9,
        under_relaxation_kappa=0.0001,
        under_relaxation_gamma=0.0,
        under_relaxation_momentum=0.0,
        inner_dvclose=0.00001,
        rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.1),
        inner_maximum=100,
        linear_acceleration="bicgstab",
        number_orthogonalizations=0,
        reordering_method=None,
        models=[NAME],
    )
    sim = flopy4.mf6.simulation.Simulation(
        name=NAME,
        tdis=flopy4.mf6.simulation.Tdis.from_time(time),
        models=[model],
        solutiongroup=[ims],
        workspace=ws,
    )
    return SimpleNamespace(sim=sim, gwf=model, grid=grid, time=time)


def build_flopy3(ws: Path):
    """The model in flopy3 (WEL lists), in `ws`."""
    import flopy

    k, k33, ss = load_arrays()
    sim = flopy.mf6.MFSimulation(sim_name=NAME, sim_ws=str(ws), verbosity_level=0)
    flopy.mf6.ModflowTdis(sim, nper=len(PERLEN), perioddata=[(p, 15, 1.1) for p in PERLEN])
    flopy.mf6.ModflowIms(
        sim,
        print_option="summary",
        complexity="moderate",
        outer_dvclose=0.01,
        outer_maximum=50,
        under_relaxation="DBD",
        under_relaxation_theta=0.9,
        under_relaxation_kappa=0.0001,
        inner_dvclose=0.00001,
        rcloserecord=0.1,
        inner_maximum=100,
        linear_acceleration="bicgstab",
        number_orthogonalizations=0,
    )
    gwf = flopy.mf6.ModflowGwf(sim, modelname=NAME)
    flopy.mf6.ModflowGwfdis(
        gwf,
        nlay=NLAY,
        nrow=NROW,
        ncol=NCOL,
        delr=DELR,
        delc=DELR.copy(),
        top=np.zeros((NROW, NCOL)),
        botm=np.stack([np.full((NROW, NCOL), v) for v in BOTM]),
    )
    flopy.mf6.ModflowGwfic(gwf, strt=0.0)
    flopy.mf6.ModflowGwfnpf(
        gwf, icelltype=np.zeros((NLAY, NROW, NCOL), dtype=int), k=k, k33=k33, save_flows=True
    )
    flopy.mf6.ModflowGwfsto(gwf, ss=ss, iconvert=0)
    for name, data in zip(_WEL_NAMES, _WEL_DICTS):
        flopy.mf6.ModflowGwfwel(
            gwf,
            filename=f"{NAME}.{name}.wel",
            pname=f"wel_{name}",
            print_input=True,
            print_flows=True,
            save_flows=True,
            stress_period_data={
                p: [(*cellid, q) for cellid, q in cells.items()] for p, cells in data.items()
            },
        )
    flopy.mf6.ModflowGwfoc(
        gwf,
        budget_filerecord=f"{NAME}.cbc",
        head_filerecord=f"{NAME}.hds",
        saverecord={0: [("HEAD", "ALL"), ("BUDGET", "FIRST")]},
    )
    return sim
