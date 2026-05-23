"""
Frenchman Flat write-time comparison: flopy4 vs flopy3.

Variants
--------
flopy4 list          WEL (list) — 3 packages, 1 cell each, 33 periods
flopy4 welg_ascii    WELG (array, ASCII) — 3×(33,10,87,87) = 7.5M elements
flopy4 netcdf_base   WEL list + array data in NetCDF
flopy4 netcdf_mesh   WELG + layered-mesh NetCDF
flopy4 netcdf_struct WELG + CF-convention structured NetCDF
flopy3 list          flopy3.mf6, WEL list, built from scratch
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flopy
from _timer import make_parser, profile_fn, report, time_writes, write_results

import flopy4
from flopy4.mf6.enums import NetCDFFormat

DATA_ROOT = Path(__file__).parent.parent / "examples" / "data" / "frenchman-flat" / "arrays"
OUT = Path(__file__).parent / "results" / "ff"

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


def load_arrays(nlay: int, nrow: int, ncol: int):
    """Load K and SS arrays from the frenchman-flat data directory."""
    k = np.zeros((nlay, nrow, ncol))
    ss = np.zeros((nlay, nrow, ncol))
    for l in range(nlay):
        pad = "000" if l < 9 else "00"
        k[l] = np.loadtxt(DATA_ROOT / f"Array.MF-HydK_{pad}{l+1}.txt")
        ss[l] = np.loadtxt(DATA_ROOT / f"Array.MF-HydS_{pad}{l+1}.txt")
    return k, k * 0.1, ss  # k, k33, ss


def build_flopy4_base(k, k33, ss):
    nlay, nrow, ncol = k.shape
    time_data = flopy4.mf6.utils.time.Time(
        perlen=PERLEN, nstp=[15] * len(PERLEN), tsmult=[1.1] * len(PERLEN)
    )
    nper = time_data.nper

    grid = flopy4.mf6.utils.grid.StructuredGrid(
        lenuni="meters",
        xoff=573309.700,
        yoff=4102552.000 - DELR.sum(),
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=np.zeros((nrow, ncol)),
        botm=np.stack(
            [
                np.full((nrow, ncol), v)
                for v in [-200, -400, -600, -800, -1050, -1350, -1700, -2200, -2950, -3950]
            ]
        ),
        delr=DELR,
        delc=DELR.copy(),
        idomain=np.ones((nlay, nrow, ncol), dtype=int),
        crs="EPSG:26911",
    )
    dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}

    dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)
    ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)
    npf = flopy4.mf6.gwf.Npf(
        icelltype=np.zeros((nlay, nrow, ncol), dtype=int),
        k=k,
        k33=k33,
        save_flows=True,
        dims=dims,
    )
    sto = flopy4.mf6.gwf.Sto(ss=ss, iconvert=0, dims=dims)
    oc = flopy4.mf6.gwf.Oc(
        budget_file=Path("ff.cbc"),
        head_file=Path("ff.hds"),
        save_head={"0": "all", 1: "all"},
        save_budget={"0": "STEPS 1"},
        print_budget={"0": "STEPS 1 15", 1: "last"},
        dims=dims,
    )
    wels = [
        flopy4.mf6.gwf.Wel(
            filename=f"ff.{name}.wel",
            q=data,
            print_input=True,
            print_flows=True,
            save_flows=True,
            dims=dims,
        )
        for name, data in zip(_WEL_NAMES, _WEL_DICTS)
    ]
    gwf = flopy4.mf6.gwf.Gwf(
        dis=grid,
        ic=ic,
        npf=npf,
        sto=sto,
        oc=oc,
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
        models=["ff"],
    )
    tdis = flopy4.mf6.simulation.Tdis.from_time(time_data)
    return gwf, ims, tdis, grid, dims, time_data, nlay, nrow, ncol, nper


def main():
    args = make_parser("Frenchman Flat write-time comparison").parse_args()
    N, include_slow = args.runs, args.include_slow
    flopy4_only = args.flopy4_only
    sections = []

    k, k33, ss = load_arrays(nlay=10, nrow=87, ncol=87)
    gwf, ims, tdis, grid, dims, time_data, nlay, nrow, ncol, nper = build_flopy4_base(k, k33, ss)
    NODATA = flopy4.mf6.constants.FILL_DNODATA

    print(f"\n{'='*60}\nfrenchman-flat  (10L×87R×87C = 75K cells, 33 periods)  n={N}\n{'='*60}")
    results = []

    # ── flopy4 list ──────────────────────────────────────────────────────────
    ws = OUT / "list"
    ws.mkdir(parents=True, exist_ok=True)
    sim = flopy4.mf6.simulation.Simulation(
        name="ff",
        tdis=tdis,
        models={"ff": gwf},
        solutions={"ims": ims},
        workspace=ws,
    )
    if args.profile:
        profile_fn(sim.write, "flopy4 list (WEL)")
    results.append(
        report("flopy4 list  (WEL)", time_writes(sim.write, N, "flopy4 list  (WEL)", include_slow))
    )

    # ── flopy4 welg_ascii ────────────────────────────────────────────────────
    GRID_NODATA = np.full((nlay, nrow, ncol), NODATA)

    def make_welg_array(q_data):
        arr = np.repeat(np.expand_dims(GRID_NODATA, 0), nper, axis=0)
        for period, cells in q_data.items():
            for (la, ro, co), val in cells.items():
                arr[period, la, ro, co] = val
        return arr

    welgs = [
        flopy4.mf6.gwf.Welg(
            filename=f"ff.{name}.welg",
            q=make_welg_array(data),
            print_input=True,
            print_flows=True,
            save_flows=True,
            dims=dims,
        )
        for name, data in zip(_WEL_NAMES, _WEL_DICTS)
    ]
    del gwf.wel[0], gwf.wel[1], gwf.wel[2]
    gwf.wel = welgs

    ws = OUT / "welg_ascii"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    gwf.netcdf_input_file = None
    gwf.netcdf_mesh2d_file = None
    results.append(
        report(
            "flopy4 welg_ascii (WELG, 7.5M elem)",
            time_writes(sim.write, N, "flopy4 welg_ascii", include_slow),
        )
    )

    # ── flopy4 netcdf_base ───────────────────────────────────────────────────
    ws = OUT / "netcdf_base"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    nc_fpth = ws / "frenchman-flat.input.nc"
    gwf.netcdf_input_file = nc_fpth
    nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(
        gwf, netcdf_format=NetCDFFormat.LAYERED_MESH, grid=grid, time=time_data
    )

    def write_nc_base():
        nc_model.to_netcdf(nc_fpth)
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim.write()

    results.append(
        report(
            "flopy4 netcdf_base (WEL+NetCDF arrays)",
            time_writes(write_nc_base, N, "flopy4 netcdf_base", include_slow),
        )
    )

    # ── flopy4 netcdf_mesh ───────────────────────────────────────────────────
    ws = OUT / "netcdf_mesh"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    gwf.netcdf_mesh2d_file = Path("frenchman-flat.nc")
    gwf.netcdf_input_file = Path("frenchman-flat.input.nc")
    nc_model2 = flopy4.mf6.netcdf.NetCDFModel.from_model(
        gwf, netcdf_format=NetCDFFormat.LAYERED_MESH, grid=grid, time=time_data
    )

    def write_nc_mesh():
        nc_model2.to_netcdf(ws / "frenchman-flat.input.nc")
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim.write()

    results.append(
        report(
            "flopy4 netcdf_mesh (WELG+layered NC)",
            time_writes(write_nc_mesh, N, "flopy4 netcdf_mesh", include_slow),
        )
    )

    # ── flopy4 netcdf_structured ─────────────────────────────────────────────
    ws = OUT / "netcdf_structured"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    nc_fpth2 = ws / "frenchman-flat.input.nc"
    gwf.netcdf_input_file = nc_fpth2
    nc_model3 = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf, grid=grid, time=time_data)

    def write_nc_struct():
        nc_model3.to_netcdf(nc_fpth2)
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim.write()

    results.append(
        report(
            "flopy4 netcdf_structured (WELG+CF NC)",
            time_writes(write_nc_struct, N, "flopy4 netcdf_structured", include_slow),
        )
    )

    # ── flopy3 list ──────────────────────────────────────────────────────────
    if not flopy4_only:
        ws3 = OUT / "flopy3_list"
        ws3.mkdir(parents=True, exist_ok=True)
        pd3 = [(p, 15, 1.1) for p in PERLEN]

        sim3 = flopy.mf6.MFSimulation(sim_name="ff", sim_ws=str(ws3), verbosity_level=0)
        flopy.mf6.ModflowTdis(sim3, nper=nper, perioddata=pd3)
        flopy.mf6.ModflowIms(
            sim3,
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
        gwf3 = flopy.mf6.ModflowGwf(sim3, modelname="ff")
        flopy.mf6.ModflowGwfdis(
            gwf3,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=DELR,
            delc=DELR.copy(),
            top=np.zeros((nrow, ncol)),
            botm=np.stack(
                [
                    np.full((nrow, ncol), v)
                    for v in [-200, -400, -600, -800, -1050, -1350, -1700, -2200, -2950, -3950]
                ]
            ),
        )
        flopy.mf6.ModflowGwfic(gwf3, strt=0.0)
        flopy.mf6.ModflowGwfnpf(
            gwf3, icelltype=np.zeros((nlay, nrow, ncol), dtype=int), k=k, k33=k33, save_flows=True
        )
        flopy.mf6.ModflowGwfsto(gwf3, ss=ss, iconvert=0)
        for name, data in zip(_WEL_NAMES, _WEL_DICTS):
            flopy.mf6.ModflowGwfwel(
                gwf3,
                filename=f"ff.{name}.wel",
                pname=f"wel_{name}",
                print_input=True,
                print_flows=True,
                save_flows=True,
                stress_period_data={
                    p: [(*list(cellid), q) for cellid, q in cells.items()]
                    for p, cells in data.items()
                },
            )
        flopy.mf6.ModflowGwfoc(
            gwf3,
            budget_filerecord="ff.cbc",
            head_filerecord="ff.hds",
            saverecord={0: [("HEAD", "ALL"), ("BUDGET", "FIRST")]},
        )
        results.append(
            report(
                "flopy3 list  (WEL)",
                time_writes(
                    lambda: sim3.write_simulation(silent=True),
                    N,
                    "flopy3 list  (WEL)",
                    include_slow,
                ),
            )
        )

    sections.append({"name": "frenchman-flat", "results": results})

    if args.output:
        write_results(args.output, "ff_write", N, sections)


if __name__ == "__main__":
    main()
