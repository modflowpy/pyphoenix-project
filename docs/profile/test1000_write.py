"""
test1000_751x751 write-time comparison: flopy4 vs flopy3.

Three scenarios
---------------
1. Sparse  — WEL (1 cell) + CHD (1550 cells)
2. Dense uniform RCH   — Rch/Rcha applied to all 582K cells, constant value
3. Dense hetero  RCH   — Rch/Rcha applied to all 582K cells, K-derived variable

flopy4 grid variants (WELG/CHDG) and NetCDF variants included in scenario 1.
flopy4 NetCDF variants included for array (Rcha) in scenarios 2 and 3.
Dense list variants are slow in flopy4 and will be skipped by default
unless --include-slow is passed.

Requires: modflow6-largetestmodels/test1000_751x751
Pass --models-root <DIR> to specify the repo root.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flopy
from _timer import make_parser, profile_fn, report, time_writes, write_results

import flopy4

OUT = Path(__file__).parent / "results"


def main():
    p = make_parser("test1000_751x751 write-time comparison")
    p.add_argument(
        "--scenarios",
        nargs="+",
        type=int,
        choices=[1, 2, 3],
        default=[1, 2, 3],
        metavar="N",
        help=(
            "which scenarios to run: 1=sparse WEL+CHD, 2=dense uniform RCH, "
            "3=dense hetero RCH (default: all)"
        ),
    )
    args = p.parse_args()
    N, include_slow = args.runs, args.include_slow
    flopy4_only = args.flopy4_only
    scenarios = set(args.scenarios)

    if args.models_root is None:
        print("ERROR: --models-root <DIR> is required (root of modflow6-largetestmodels repo)")
        raise SystemExit(1)
    SRC = args.models_root / "test1000_751x751"
    if not SRC.exists():
        print(f"ERROR: model not found at {SRC}")
        raise SystemExit(1)

    # ── load source data ─────────────────────────────────────────────────────
    _sim = flopy.mf6.MFSimulation.load(sim_ws=str(SRC), verbosity_level=0)
    _gwf = _sim.get_model()

    k_array = _gwf.npf.k.array
    chd_data = _gwf.chd.stress_period_data.data[0]
    wel_data = _gwf.wel.stress_period_data.data[1]

    chd_dict = {tuple(int(x) for x in rec[0]): float(rec[1]) for rec in chd_data}
    wel_dict = {tuple(int(x) for x in rec[0]): float(rec[1]) for rec in wel_data}

    nlay, nrow, ncol = k_array.shape
    ncpl = nrow * ncol
    perioddata = [(1.0, 1, 1.0), (1000.0, 10, 1.5), (1.0, 1, 1.0)]
    nper = len(perioddata)
    NODATA = flopy4.mf6.constants.FILL_DNODATA
    RCH_UNIFORM = 0.001

    rch_uniform_arr = np.full((nper, ncpl), RCH_UNIFORM)
    rch_het_arr = np.stack([(_gwf.npf.k.array[0] * 1e-5).reshape(ncpl)] * nper)
    # rch_*_dict are built lazily inside scenario blocks to avoid ~5-10 s dict construction
    # for scenarios that are skipped.

    # ── shared flopy4 helpers ────────────────────────────────────────────────
    grid = flopy4.mf6.utils.grid.StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=np.full((nrow, ncol), 100.0),
        botm=np.full((1, nrow, ncol), -100.0),
        delr=np.full(ncol, 25.6),
        delc=np.full(nrow, 25.6),
        idomain=np.ones((nlay, nrow, ncol), dtype=int),
    )
    dims = {"nper": nper, "ncpl": ncpl, **dict(grid.dataset.sizes)}
    time4 = flopy4.mf6.utils.time.Time(
        perlen=[p[0] for p in perioddata],
        nstp=[p[1] for p in perioddata],
        tsmult=[p[2] for p in perioddata],
    )

    def make_ims4():
        return flopy4.mf6.Ims(
            print_option="summary",
            outer_dvclose=1e-6,
            outer_maximum=100,
            inner_dvclose=1e-6,
            rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
            inner_maximum=100,
            linear_acceleration="cg",
            scaling_method=None,
            reordering_method=None,
            relaxation_factor=1.0,
            models=["test1000"],
        )

    def make_base4():
        dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)
        ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)
        npf = flopy4.mf6.gwf.Npf(
            icelltype=np.ones((nlay, nrow, ncol), dtype=int), k=k_array, save_flows=True, dims=dims
        )
        sto = flopy4.mf6.gwf.Sto(ss=0.0, sy=0.1, iconvert=1, dims=dims)
        oc = flopy4.mf6.gwf.Oc(
            budget_file=Path("test1000.cbc"),
            head_file=Path("test1000.hds"),
            save_head={0: "last"},
            save_budget={0: "last"},
            dims=dims,
        )
        return dis, ic, npf, sto, oc

    def make_sim4(ws, gwf):
        ws.mkdir(parents=True, exist_ok=True)
        return flopy4.mf6.simulation.Simulation(
            name="test1000",
            tdis=flopy4.mf6.simulation.Tdis.from_time(time4),
            models={"test1000": gwf},
            solutions={"ims": make_ims4()},
            workspace=ws,
        )

    def make_base3(ws):
        ws.mkdir(parents=True, exist_ok=True)
        s = flopy.mf6.MFSimulation(sim_name="test1000", sim_ws=str(ws), verbosity_level=0)
        flopy.mf6.ModflowTdis(s, nper=nper, perioddata=perioddata)
        flopy.mf6.ModflowIms(
            s,
            outer_dvclose=1e-6,
            outer_maximum=100,
            inner_dvclose=1e-6,
            rcloserecord=0.01,
            inner_maximum=100,
            linear_acceleration="cg",
            scaling_method="none",
            reordering_method="none",
            relaxation_factor=1.0,
        )
        g = flopy.mf6.ModflowGwf(s, modelname="test1000")
        flopy.mf6.ModflowGwfdis(
            g,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=25.6,
            delc=25.6,
            top=100.0,
            botm=-100.0,
            idomain=np.ones((nlay, nrow, ncol), dtype=int),
        )
        flopy.mf6.ModflowGwfic(g, strt=0.0)
        flopy.mf6.ModflowGwfnpf(g, icelltype=1, k=k_array, save_flows=True)
        flopy.mf6.ModflowGwfsto(
            g,
            ss=0.0,
            sy=0.1,
            iconvert=1,
            save_flows=True,
            steady_state={0: True, 2: True},
            transient={1: True},
        )
        flopy.mf6.ModflowGwfoc(
            g,
            budget_filerecord="test1000.cbc",
            head_filerecord="test1000.hds",
            saverecord={0: [("HEAD", "LAST"), ("BUDGET", "LAST")]},
        )
        return s, g

    ws_root = OUT / "test1000"
    sections = []

    # ── Scenario 1: Sparse ───────────────────────────────────────────────────
    if 1 in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario 1: Sparse  (WEL 1 cell + CHD 1550 cells)  n={N}")
        print(f"{'='*60}")
        results = []

        # flopy4 list
        dis, ic, npf, sto, oc = make_base4()
        chd4 = flopy4.mf6.gwf.Chd(head={0: chd_dict}, print_flows=True, save_flows=True, dims=dims)
        wel4 = flopy4.mf6.gwf.Wel(q={1: wel_dict}, save_flows=True, dims=dims)
        gwf4 = flopy4.mf6.gwf.Gwf(
            dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, chd=chd4, wel=wel4, dims=dims
        )
        sim4 = make_sim4(ws_root / "s1_flopy4_list", gwf4)
        if args.profile:
            profile_fn(sim4.write, "flopy4 list (WEL+CHD)")
        results.append(
            report(
                "flopy4 list        (WEL+CHD)",
                time_writes(sim4.write, N, "flopy4 list (WEL+CHD)", include_slow),
            )
        )

        # flopy4 grid ASCII
        chd_arr = np.full((nper, nlay, nrow, ncol), NODATA)
        for (la, ro, co), h in chd_dict.items():
            chd_arr[0, la, ro, co] = h
        wel_arr = np.full((nper, nlay, nrow, ncol), NODATA)
        for (la, ro, co), q in wel_dict.items():
            wel_arr[1, la, ro, co] = q
        dis, ic, npf, sto, oc = make_base4()
        chdg4 = flopy4.mf6.gwf.Chdg(head=chd_arr, print_flows=True, save_flows=True, dims=dims)
        welg4 = flopy4.mf6.gwf.Welg(q=wel_arr, save_flows=True, dims=dims)
        gwf4g = flopy4.mf6.gwf.Gwf(
            dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, chd=chdg4, wel=welg4, dims=dims
        )
        sim4g = make_sim4(ws_root / "s1_flopy4_grid", gwf4g)
        results.append(
            report(
                "flopy4 grid ASCII  (WELG+CHDG, 1.74M sparse)",
                time_writes(sim4g.write, N, "flopy4 grid (WELG+CHDG)", include_slow),
            )
        )

        # flopy4 netcdf_mesh (reuse gwf4g / sim4g)
        ws_nc = ws_root / "s1_flopy4_nc_mesh"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4g.workspace = ws_nc
        nc_fpth_s1m = ws_nc / "test1000.input.nc"
        gwf4g.netcdf_file = nc_fpth_s1m
        gwf4g.netcdf_mesh2d_file = Path("test1000.nc")
        nc_s1m = flopy4.mf6.netcdf.NetCDFModel.from_model(
            gwf4g, mesh="layered", grid=grid, time=time4
        )

        def write_s1_nc_mesh():
            nc_s1m.to_netcdf(nc_fpth_s1m)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4g.write()

        results.append(
            report(
                "flopy4 netcdf_mesh (WELG+CHDG)",
                time_writes(write_s1_nc_mesh, N, "flopy4 netcdf_mesh (WELG+CHDG)", include_slow),
            )
        )

        # flopy4 netcdf_structured
        ws_nc = ws_root / "s1_flopy4_nc_struct"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4g.workspace = ws_nc
        nc_fpth_s1s = ws_nc / "test1000.input.nc"
        gwf4g.netcdf_file = nc_fpth_s1s
        gwf4g.netcdf_mesh2d_file = None
        nc_s1s = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf4g, grid=grid, time=time4)

        def write_s1_nc_struct():
            nc_s1s.to_netcdf(nc_fpth_s1s)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4g.write()

        results.append(
            report(
                "flopy4 netcdf_struct (WELG+CHDG)",
                time_writes(
                    write_s1_nc_struct, N, "flopy4 netcdf_struct (WELG+CHDG)", include_slow
                ),
            )
        )

        if not flopy4_only:
            sim3, gwf3 = make_base3(ws_root / "s1_flopy3_list")
            flopy.mf6.ModflowGwfchd(
                gwf3,
                print_flows=True,
                save_flows=True,
                stress_period_data={0: list(chd_dict.items())},
            )
            flopy.mf6.ModflowGwfwel(
                gwf3, save_flows=True, stress_period_data={1: list(wel_dict.items())}
            )
            results.append(
                report(
                    "flopy3 list        (WEL+CHD)",
                    time_writes(
                        lambda: sim3.write_simulation(silent=True),
                        N,
                        "flopy3 list (WEL+CHD)",
                        include_slow,
                    ),
                )
            )
        sections.append({"name": "sparse (WEL+CHD)", "results": results})

    # ── Scenario 2: Dense uniform RCH ───────────────────────────────────────
    if 2 in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario 2: Dense uniform RCH  ({ncpl:,} cells)  n={N}")
        print(f"{'='*60}")
        results = []

        # Build the list dict here to avoid unnecessary overhead when scenario is skipped
        rch_uniform_dict = {
            p: {(0, r, c): RCH_UNIFORM for r in range(nrow) for c in range(ncol)}
            for p in range(nper)
        }

        # flopy4 list
        dis, ic, npf, sto, oc = make_base4()
        rch4l = flopy4.mf6.gwf.Rch(recharge=rch_uniform_dict, dims=dims)
        gwf4 = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, rch=[rch4l], dims=dims)
        sim4 = make_sim4(ws_root / "s2_flopy4_rch_list", gwf4)
        results.append(
            report(
                "flopy4 list        (Rch, 1.74M entries)",
                time_writes(sim4.write, N, "flopy4 list (Rch)", include_slow),
            )
        )

        # flopy4 array ASCII
        dis, ic, npf, sto, oc = make_base4()
        rcha4 = flopy4.mf6.gwf.Rcha(recharge=rch_uniform_arr, dims=dims)
        gwf4 = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, rch=[rcha4], dims=dims)
        sim4 = make_sim4(ws_root / "s2_flopy4_rch_array", gwf4)
        results.append(
            report(
                "flopy4 array ASCII (Rcha, CONSTANT)",
                time_writes(sim4.write, N, "flopy4 array (Rcha)", include_slow),
            )
        )

        # flopy4 netcdf_mesh (reuse gwf4 / sim4)
        ws_nc = ws_root / "s2_flopy4_nc_mesh"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4.workspace = ws_nc
        nc_fpth_s2m = ws_nc / "test1000.input.nc"
        gwf4.netcdf_file = nc_fpth_s2m
        gwf4.netcdf_mesh2d_file = Path("test1000.nc")
        nc_s2m = flopy4.mf6.netcdf.NetCDFModel.from_model(
            gwf4, mesh="layered", grid=grid, time=time4
        )

        def write_s2_nc_mesh():
            nc_s2m.to_netcdf(nc_fpth_s2m)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4.write()

        results.append(
            report(
                "flopy4 netcdf_mesh (Rcha, CONSTANT)",
                time_writes(write_s2_nc_mesh, N, "flopy4 netcdf_mesh (Rcha)", include_slow),
            )
        )

        # flopy4 netcdf_structured
        ws_nc = ws_root / "s2_flopy4_nc_struct"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4.workspace = ws_nc
        nc_fpth_s2s = ws_nc / "test1000.input.nc"
        gwf4.netcdf_file = nc_fpth_s2s
        gwf4.netcdf_mesh2d_file = None
        nc_s2s = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf4, grid=grid, time=time4)

        def write_s2_nc_struct():
            nc_s2s.to_netcdf(nc_fpth_s2s)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4.write()

        results.append(
            report(
                "flopy4 netcdf_struct (Rcha, CONSTANT)",
                time_writes(write_s2_nc_struct, N, "flopy4 netcdf_struct (Rcha)", include_slow),
            )
        )

        if not flopy4_only:
            sim3, gwf3 = make_base3(ws_root / "s2_flopy3_rch_list")
            flopy.mf6.ModflowGwfrch(
                gwf3,
                stress_period_data={
                    p: [((0, r, c), RCH_UNIFORM) for r in range(nrow) for c in range(ncol)]
                    for p in range(nper)
                },
            )
            results.append(
                report(
                    "flopy3 list        (Rch)",
                    time_writes(
                        lambda: sim3.write_simulation(silent=True),
                        N,
                        "flopy3 list (Rch)",
                        include_slow,
                    ),
                )
            )

            sim3, gwf3 = make_base3(ws_root / "s2_flopy3_rch_array")
            flopy.mf6.ModflowGwfrcha(gwf3, recharge=RCH_UNIFORM)
            results.append(
                report(
                    "flopy3 array       (Rcha, CONSTANT)",
                    time_writes(
                        lambda: sim3.write_simulation(silent=True),
                        N,
                        "flopy3 array (Rcha)",
                        include_slow,
                    ),
                )
            )
        sections.append({"name": "dense uniform RCH", "results": results})

    # ── Scenario 3: Dense heterogeneous RCH ─────────────────────────────────
    if 3 in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario 3: Dense heterogeneous RCH  ({ncpl:,} cells)  n={N}")
        print(f"{'='*60}")
        results = []

        # Build the list dict here to avoid unnecessary overhead when scenario is skipped
        rch_het_dict = {
            p: {
                (0, r, c): float(rch_het_arr[p, r * ncol + c])
                for r in range(nrow)
                for c in range(ncol)
            }
            for p in range(nper)
        }

        # flopy4 list
        dis, ic, npf, sto, oc = make_base4()
        rch4l = flopy4.mf6.gwf.Rch(recharge=rch_het_dict, dims=dims)
        gwf4 = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, rch=[rch4l], dims=dims)
        sim4 = make_sim4(ws_root / "s3_flopy4_rch_list", gwf4)
        results.append(
            report(
                "flopy4 list        (Rch, 1.74M entries)",
                time_writes(sim4.write, N, "flopy4 list (Rch)", include_slow),
            )
        )

        # flopy4 array ASCII
        dis, ic, npf, sto, oc = make_base4()
        rcha4 = flopy4.mf6.gwf.Rcha(recharge=rch_het_arr, dims=dims)
        gwf4 = flopy4.mf6.gwf.Gwf(dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, rch=[rcha4], dims=dims)
        sim4 = make_sim4(ws_root / "s3_flopy4_rch_array", gwf4)
        results.append(
            report(
                "flopy4 array ASCII (Rcha, per-cell)",
                time_writes(sim4.write, N, "flopy4 array (Rcha)", include_slow),
            )
        )

        # flopy4 netcdf_mesh (reuse gwf4 / sim4)
        ws_nc = ws_root / "s3_flopy4_nc_mesh"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4.workspace = ws_nc
        nc_fpth_s3m = ws_nc / "test1000.input.nc"
        gwf4.netcdf_file = nc_fpth_s3m
        gwf4.netcdf_mesh2d_file = Path("test1000.nc")
        nc_s3m = flopy4.mf6.netcdf.NetCDFModel.from_model(
            gwf4, mesh="layered", grid=grid, time=time4
        )

        def write_s3_nc_mesh():
            nc_s3m.to_netcdf(nc_fpth_s3m)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4.write()

        results.append(
            report(
                "flopy4 netcdf_mesh (Rcha, per-cell)",
                time_writes(write_s3_nc_mesh, N, "flopy4 netcdf_mesh (Rcha)", include_slow),
            )
        )

        # flopy4 netcdf_structured
        ws_nc = ws_root / "s3_flopy4_nc_struct"
        ws_nc.mkdir(parents=True, exist_ok=True)
        sim4.workspace = ws_nc
        nc_fpth_s3s = ws_nc / "test1000.input.nc"
        gwf4.netcdf_file = nc_fpth_s3s
        gwf4.netcdf_mesh2d_file = None
        nc_s3s = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf4, grid=grid, time=time4)

        def write_s3_nc_struct():
            nc_s3s.to_netcdf(nc_fpth_s3s)
            with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
                sim4.write()

        results.append(
            report(
                "flopy4 netcdf_struct (Rcha, per-cell)",
                time_writes(write_s3_nc_struct, N, "flopy4 netcdf_struct (Rcha)", include_slow),
            )
        )

        if not flopy4_only:
            sim3, gwf3 = make_base3(ws_root / "s3_flopy3_rch_list")
            flopy.mf6.ModflowGwfrch(
                gwf3,
                stress_period_data={
                    p: [
                        ((0, r, c), float(rch_het_arr[p, r * ncol + c]))
                        for r in range(nrow)
                        for c in range(ncol)
                    ]
                    for p in range(nper)
                },
            )
            results.append(
                report(
                    "flopy3 list        (Rch)",
                    time_writes(
                        lambda: sim3.write_simulation(silent=True),
                        N,
                        "flopy3 list (Rch)",
                        include_slow,
                    ),
                )
            )

            sim3, gwf3 = make_base3(ws_root / "s3_flopy3_rch_array")
            flopy.mf6.ModflowGwfrcha(
                gwf3, recharge={p: rch_het_arr[p].reshape(nrow, ncol) for p in range(nper)}
            )
            results.append(
                report(
                    "flopy3 array       (Rcha, per-cell)",
                    time_writes(
                        lambda: sim3.write_simulation(silent=True),
                        N,
                        "flopy3 array (Rcha)",
                        include_slow,
                    ),
                )
            )
        sections.append({"name": "dense heterogeneous RCH", "results": results})

    if args.output:
        write_results(args.output, "test1000_write", N, sections)


if __name__ == "__main__":
    main()
