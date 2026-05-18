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
from _timer import make_parser, report, time_writes, write_results

import flopy4

FF_ROOT = Path(__file__).parent.parent / "examples"
OUT = Path(__file__).parent / "results"


def build_flopy4_base():
    time_data = flopy4.mf6.utils.time.Time(
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
        nstp=[15] * 33,
        tsmult=[1.1] * 33,
    )
    nper = time_data.nper
    nlay, nrow, ncol = 10, 87, 87

    delr = np.array(
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
    delc = delr.copy()
    idomain = np.ones((nlay, nrow, ncol), dtype=int)
    top = np.zeros((nrow, ncol))
    botm = np.stack(
        [
            np.full((nrow, ncol), v)
            for v in [-200, -400, -600, -800, -1050, -1350, -1700, -2200, -2950, -3950]
        ]
    )

    grid = flopy4.mf6.utils.grid.StructuredGrid(
        lenuni="meters",
        xoff=573309.700,
        yoff=4102552.000 - delr.sum(),
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=top,
        botm=botm,
        delr=delr,
        delc=delc,
        idomain=idomain,
        crs="EPSG:26911",
    )
    dims = {"nper": nper, "ncpl": nrow * ncol, **dict(grid.dataset.sizes)}

    k = np.zeros((nlay, nrow, ncol))
    k33 = np.zeros((nlay, nrow, ncol))
    ss = np.zeros((nlay, nrow, ncol))
    arr_root = FF_ROOT / "data" / "frenchman-flat" / "arrays"
    for l in range(nlay):
        pad = "000" if l < 9 else "00"
        k[l] = np.loadtxt(arr_root / f"Array.MF-HydK_{pad}{l+1}.txt")
        k33[l] = k[l] * 0.1
        ss[l] = np.loadtxt(arr_root / f"Array.MF-HydS_{pad}{l+1}.txt")

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

    wel_crt = flopy4.mf6.gwf.Wel(
        filename="ff.crt.wel",
        q={
            0: {(1, 43, 43): -30992.50},
            1: {(1, 43, 43): 0.0},
            2: {(1, 43, 43): -30992.50},
            3: {(1, 43, 43): 0.0},
            4: {(1, 43, 43): -30992.50},
            5: {(1, 43, 43): 0.0},
        },
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )
    wel_leak = flopy4.mf6.gwf.Wel(
        filename="ff.leak.wel",
        q={
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
        },
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )
    wel_sampleQ = flopy4.mf6.gwf.Wel(
        filename="ff.sampleQ.wel",
        q={
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
        },
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )

    gwf = flopy4.mf6.gwf.Gwf(
        dis=grid,
        ic=ic,
        npf=npf,
        sto=sto,
        oc=oc,
        wel=[wel_crt, wel_leak, wel_sampleQ],
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
    sections = []

    gwf, ims, tdis, grid, dims, time_data, nlay, nrow, ncol, nper = build_flopy4_base()
    NODATA = flopy4.mf6.constants.FILL_DNODATA

    # ── flopy4 variants ──────────────────────────────────────────────────────
    print(f"\n{'='*60}\nfrenchman-flat  (10L×87R×87C = 75K cells, 33 periods)  n={N}\n{'='*60}")
    results = []

    # list
    ws = FF_ROOT / "frenchman-flat" / "list"
    ws.mkdir(parents=True, exist_ok=True)
    sim = flopy4.mf6.simulation.Simulation(
        name="ff",
        tdis=tdis,
        models={"ff": gwf},
        solutions={"ims": ims},
        workspace=ws,
    )
    results.append(
        report("flopy4 list  (WEL)", time_writes(sim.write, N, "flopy4 list  (WEL)", include_slow))
    )

    # welg_ascii — build WELG packages from list packages
    GRID_NODATA = np.full((nlay, nrow, ncol), NODATA)

    def make_welg(q_data):
        arr = np.repeat(np.expand_dims(GRID_NODATA, 0), nper, axis=0)
        for period, cells in q_data.items():
            for (la, ro, co), val in cells.items():
                arr[period, la, ro, co] = val
        return arr

    q_crt_arr = make_welg(
        {
            0: {(1, 43, 43): -30992.50},
            1: {(1, 43, 43): 0.0},
            2: {(1, 43, 43): -30992.50},
            3: {(1, 43, 43): 0.0},
            4: {(1, 43, 43): -30992.50},
            5: {(1, 43, 43): 0.0},
        }
    )
    q_leak_arr = make_welg(
        {
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
    )
    q_sampleQ_arr = make_welg(
        {
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
    )

    welg_crt = flopy4.mf6.gwf.Welg(
        filename="ff.crt.welg",
        q=q_crt_arr,
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )
    welg_leak = flopy4.mf6.gwf.Welg(
        filename="ff.leak.welg",
        q=q_leak_arr,
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )
    welg_sampleQ = flopy4.mf6.gwf.Welg(
        filename="ff.sampleQ.welg",
        q=q_sampleQ_arr,
        print_input=True,
        print_flows=True,
        save_flows=True,
        dims=dims,
    )
    del gwf.wel[0]
    del gwf.wel[1]
    del gwf.wel[2]
    gwf.wel = [welg_crt, welg_leak, welg_sampleQ]

    ws = FF_ROOT / "frenchman-flat" / "welg_ascii"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    gwf.netcdf_file = None
    gwf.netcdf_mesh2d_file = None
    results.append(
        report(
            "flopy4 welg_ascii (WELG, 7.5M elem)",
            time_writes(sim.write, N, "flopy4 welg_ascii", include_slow),
        )
    )

    # netcdf_base
    ws = FF_ROOT / "frenchman-flat" / "netcdf_base"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    nc_fpth = ws / "frenchman-flat.input.nc"
    gwf.netcdf_file = nc_fpth
    nc_model = flopy4.mf6.netcdf.NetCDFModel.from_model(
        gwf, mesh="layered", grid=grid, time=time_data
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

    # netcdf_mesh
    ws = FF_ROOT / "frenchman-flat" / "netcdf_mesh"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    gwf.netcdf_mesh2d_file = Path("frenchman-flat.nc")
    gwf.netcdf_file = Path("frenchman-flat.input.nc")
    nc_model2 = flopy4.mf6.netcdf.NetCDFModel.from_model(
        gwf, mesh="layered", grid=grid, time=time_data
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

    # netcdf_structured
    ws = FF_ROOT / "frenchman-flat" / "netcdf_structured"
    ws.mkdir(parents=True, exist_ok=True)
    sim.workspace = ws
    nc_fpth2 = ws / "frenchman-flat.input.nc"
    gwf.netcdf_file = nc_fpth2
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

    # ── flopy3 from-scratch list ─────────────────────────────────────────────
    ws3 = FF_ROOT / "frenchman-flat" / "flopy3_list"
    ws3.mkdir(parents=True, exist_ok=True)

    arr_root = FF_ROOT / "data" / "frenchman-flat" / "arrays"
    k_f3 = np.zeros((nlay, nrow, ncol))
    k33_f3 = np.zeros((nlay, nrow, ncol))
    ss_f3 = np.zeros((nlay, nrow, ncol))
    for l in range(nlay):
        pad = "000" if l < 9 else "00"
        k_f3[l] = np.loadtxt(arr_root / f"Array.MF-HydK_{pad}{l+1}.txt")
        k33_f3[l] = k_f3[l] * 0.1
        ss_f3[l] = np.loadtxt(arr_root / f"Array.MF-HydS_{pad}{l+1}.txt")

    perlen = [
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
    pd3 = [(p, 15, 1.1) for p in perlen]

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
        delr=np.array(
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
        ),
        delc=np.array(
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
        ),
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
        gwf3, icelltype=np.zeros((nlay, nrow, ncol), dtype=int), k=k_f3, k33=k33_f3, save_flows=True
    )
    flopy.mf6.ModflowGwfsto(gwf3, ss=ss_f3, iconvert=0)
    flopy.mf6.ModflowGwfwel(
        gwf3,
        filename="ff.crt.wel",
        print_input=True,
        print_flows=True,
        save_flows=True,
        pname="wel_crt",
        stress_period_data={
            0: [((1, 43, 43), -30992.50)],
            1: [((1, 43, 43), 0.0)],
            2: [((1, 43, 43), -30992.50)],
            3: [((1, 43, 43), 0.0)],
            4: [((1, 43, 43), -30992.50)],
            5: [((1, 43, 43), 0.0)],
        },
    )
    flopy.mf6.ModflowGwfwel(
        gwf3,
        filename="ff.leak.wel",
        print_input=True,
        print_flows=True,
        save_flows=True,
        pname="wel_leak",
        stress_period_data={
            0: [((1, 43, 43), 1e-05)],
            7: [((1, 43, 43), 1.5e3)],
            8: [((1, 43, 43), 2.65e3)],
            9: [((1, 43, 43), 3.15e3)],
            10: [((1, 43, 43), 4.1e3)],
            11: [((1, 43, 43), 4.65e3)],
            12: [((1, 43, 43), 4.95e3)],
            13: [((1, 43, 43), 5.3e3)],
            14: [((1, 43, 43), 5.8e3)],
            16: [((1, 43, 43), 5.9e3)],
            17: [((1, 43, 43), 5.8e3)],
            19: [((1, 43, 43), 5.6e3)],
            20: [((1, 43, 43), 4.7e3)],
            22: [((1, 43, 43), 3.4e3)],
            23: [((1, 43, 43), 1e-05)],
        },
    )
    flopy.mf6.ModflowGwfwel(
        gwf3,
        filename="ff.sampleQ.wel",
        print_input=True,
        print_flows=True,
        save_flows=True,
        pname="wel_sampleQ",
        stress_period_data={
            0: [((1, 43, 43), 0.0)],
            22: [((1, 43, 43), -4981.90)],
            23: [((1, 43, 43), 0.0)],
            24: [((1, 43, 43), -4059.83)],
            25: [((1, 43, 43), 0.0)],
            26: [((1, 43, 43), -5678.75)],
            27: [((1, 43, 43), 0.0)],
            28: [((1, 43, 43), -5755.75)],
            29: [((1, 43, 43), 0.0)],
            30: [((1, 43, 43), -4117.58)],
            31: [((1, 43, 43), 0.0)],
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
                lambda: sim3.write_simulation(silent=True), N, "flopy3 list  (WEL)", include_slow
            ),
        )
    )

    sections.append({"name": "frenchman-flat", "results": results})

    if args.output:
        write_results(args.output, "ff_write", N, sections)


if __name__ == "__main__":
    main()
