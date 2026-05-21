"""
test1005_secp write-time comparison: flopy4 vs flopy3.

Scenario: WEL (3971 cells × 6 periods) + CHD (18647 cells) + RCHA (array)
  16 layers × 130 rows × 275 cols = 572,000 cells, 6 stress periods

ASCII grid variants (WELG/CHDG) are omitted: at 6×16×130×275 = 34M elements
the arrays are too large for meaningful ASCII profiling.  NetCDF grid variants
are included — binary format makes the 34M-element arrays practical to write.

Requires: modflow6-largetestmodels/test1005_secp
Pass --models-root <DIR> to specify the repo root.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flopy
from _timer import make_parser, profile_fn, report, time_writes, write_results

import flopy4
from flopy4.mf6.enums import NetCDFFormat

OUT = Path(__file__).parent / "results"


def main():
    args = make_parser("test1005_secp write-time comparison").parse_args()
    N, include_slow = args.runs, args.include_slow
    flopy4_only = args.flopy4_only

    if args.models_root is None:
        print("ERROR: --models-root <DIR> is required (root of modflow6-largetestmodels repo)")
        raise SystemExit(1)
    SRC = args.models_root / "test1005_secp"
    if not SRC.exists():
        print(f"ERROR: model not found at {SRC}")
        raise SystemExit(1)

    # ── load source data ─────────────────────────────────────────────────────
    _sim = flopy.mf6.MFSimulation.load(sim_ws=str(SRC), verbosity_level=0)
    _gwf = _sim.get_model()

    k_array = _gwf.npf.k.array  # (16, 130, 275)
    ss_array = _gwf.sto.ss.array  # (16, 130, 275)
    rch_array = _gwf.rch.recharge.array  # (6, 1, 130, 275)
    botm = _gwf.dis.botm.array

    # WEL: 3971 cells × 6 periods, drop auxiliary iface column
    wel_raw = _gwf.wel.stress_period_data.data
    wel_dicts = {
        period: {tuple(int(x) for x in rec[0]): float(rec[1]) for rec in records}
        for period, records in wel_raw.items()
    }

    # CHD: 18,647 cells in period 0 only; constant head=0.0 (time series stripped)
    chd_raw = _gwf.chd.stress_period_data.data[0]
    chd_dict = {tuple(int(x) for x in rec[0]): 0.0 for rec in chd_raw}

    nlay, nrow, ncol = k_array.shape
    ncpl = nrow * ncol
    perioddata = [
        (1.0, 2, 1.1),
        (3651.0, 2, 1.1),
        (3652.0, 2, 1.1),
        (3653.0, 2, 1.1),
        (3652.0, 2, 1.1),
        (3653.0, 2, 1.1),
    ]
    nper = len(perioddata)

    wel_total = sum(len(v) for v in wel_dicts.values())
    print(f"Model: {nlay}L × {nrow}R × {ncol}C = {nlay*nrow*ncol:,} cells, {nper} periods")
    print(f"  WEL: {wel_total:,} total entries  CHD: {len(chd_dict):,} cells")

    # ── shared flopy4 helpers ────────────────────────────────────────────────
    grid = flopy4.mf6.utils.grid.StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=np.zeros((nrow, ncol)),
        botm=botm,
        delr=np.full(ncol, 10560.0),
        delc=np.full(nrow, 10560.0),
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
            outer_dvclose=1e-6,
            outer_maximum=200,
            inner_dvclose=1e-7,
            rclose=flopy4.mf6.Ims.Rclose(inner_rclose=0.01),
            inner_maximum=100,
            linear_acceleration="bicgstab",
            models=["test1005"],
        )

    def make_base4():
        dis = flopy4.mf6.gwf.Dis.from_grid(grid=grid)
        ic = flopy4.mf6.gwf.Ic(strt=0.0, dims=dims)
        npf = flopy4.mf6.gwf.Npf(
            icelltype=np.zeros((nlay, nrow, ncol), dtype=int), k=k_array, save_flows=True, dims=dims
        )
        sto = flopy4.mf6.gwf.Sto(ss=ss_array, sy=0.0, iconvert=0, dims=dims)
        oc = flopy4.mf6.gwf.Oc(
            budget_file=Path("test1005.cbc"),
            head_file=Path("test1005.hds"),
            save_head={0: "last"},
            save_budget={0: "last"},
            dims=dims,
        )
        return dis, ic, npf, sto, oc

    def make_sim4(ws, gwf):
        ws.mkdir(parents=True, exist_ok=True)
        return flopy4.mf6.simulation.Simulation(
            name="test1005",
            tdis=flopy4.mf6.simulation.Tdis.from_time(time4),
            models={"test1005": gwf},
            solutions={"ims": make_ims4()},
            workspace=ws,
        )

    def make_base3(ws):
        ws.mkdir(parents=True, exist_ok=True)
        s = flopy.mf6.MFSimulation(sim_name="test1005", sim_ws=str(ws), verbosity_level=0)
        flopy.mf6.ModflowTdis(s, nper=nper, perioddata=perioddata)
        flopy.mf6.ModflowIms(
            s,
            outer_dvclose=1e-6,
            outer_maximum=200,
            inner_dvclose=1e-7,
            rcloserecord=0.01,
            inner_maximum=100,
            linear_acceleration="bicgstab",
        )
        g = flopy.mf6.ModflowGwf(s, modelname="test1005")
        flopy.mf6.ModflowGwfdis(
            g,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=10560.0,
            delc=10560.0,
            top=np.zeros((nrow, ncol)),
            botm=botm,
            idomain=np.ones((nlay, nrow, ncol), dtype=int),
        )
        flopy.mf6.ModflowGwfic(g, strt=0.0)
        flopy.mf6.ModflowGwfnpf(g, icelltype=0, k=k_array, save_flows=True)
        flopy.mf6.ModflowGwfsto(
            g, ss=ss_array, sy=0.0, iconvert=0, save_flows=True, steady_state={0: True}
        )
        flopy.mf6.ModflowGwfrcha(g, recharge={p: rch_array[p, 0] for p in range(nper)})
        return s, g

    ws_root = OUT / "test1005"
    sections = []

    print(f"\n{'='*60}")
    print(f"Scenario: WEL+CHD+RCHA  n={N}")
    print(f"{'='*60}")
    results = []

    # flopy4 list
    dis, ic, npf, sto, oc = make_base4()
    rcha4 = flopy4.mf6.gwf.Rcha(recharge=rch_array[:, 0, :, :].reshape(nper, ncpl), dims=dims)
    chd4 = flopy4.mf6.gwf.Chd(head={0: chd_dict}, print_flows=True, save_flows=True, dims=dims)
    wel4 = flopy4.mf6.gwf.Wel(q=wel_dicts, save_flows=True, dims=dims)
    gwf4 = flopy4.mf6.gwf.Gwf(
        dis=grid, ic=ic, npf=npf, sto=sto, oc=oc, chd=chd4, wel=wel4, rch=[rcha4], dims=dims
    )
    sim4 = make_sim4(ws_root / "flopy4_list", gwf4)
    if args.profile:
        profile_fn(sim4.write, "flopy4 list (WEL+CHD+RCHA)")
    results.append(
        report(
            "flopy4 list  (WEL+CHD+RCHA)",
            time_writes(sim4.write, N, "flopy4 list (WEL+CHD+RCHA)", include_slow),
        )
    )

    # flopy3 list
    if not flopy4_only:
        sim3, gwf3 = make_base3(ws_root / "flopy3_list")
        flopy.mf6.ModflowGwfchd(
            gwf3,
            print_flows=True,
            save_flows=True,
            stress_period_data={0: [(cellid, h) for cellid, h in chd_dict.items()]},
        )
        flopy.mf6.ModflowGwfwel(
            gwf3,
            save_flows=True,
            stress_period_data={
                p: [(cellid, q) for cellid, q in cells.items()] for p, cells in wel_dicts.items()
            },
        )
        flopy.mf6.ModflowGwfoc(
            gwf3,
            budget_filerecord="test1005.cbc",
            head_filerecord="test1005.hds",
            saverecord={0: [("HEAD", "LAST"), ("BUDGET", "LAST")]},
        )
        results.append(
            report(
                "flopy3 list  (WEL+CHD+RCHA)",
                time_writes(
                    lambda: sim3.write_simulation(silent=True),
                    N,
                    "flopy3 list (WEL+CHD+RCHA)",
                    include_slow,
                ),
            )
        )

    # flopy4 NetCDF variants — build WELG/CHDG arrays (34M elements; ASCII omitted)
    welg_arr = np.full((nper, nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA)
    for period, cells in wel_dicts.items():
        for (la, ro, co), q in cells.items():
            welg_arr[period, la, ro, co] = q

    chdg_arr = np.full((nper, nlay, nrow, ncol), flopy4.mf6.constants.FILL_DNODATA)
    for (la, ro, co), h in chd_dict.items():
        chdg_arr[0, la, ro, co] = h

    dis_nc, ic_nc, npf_nc, sto_nc, oc_nc = make_base4()
    rcha_nc = flopy4.mf6.gwf.Rcha(recharge=rch_array[:, 0, :, :].reshape(nper, ncpl), dims=dims)
    welg_nc = flopy4.mf6.gwf.Welg(q=welg_arr, save_flows=True, dims=dims)
    chdg_nc = flopy4.mf6.gwf.Chdg(head=chdg_arr, print_flows=True, save_flows=True, dims=dims)
    gwf_nc = flopy4.mf6.gwf.Gwf(
        dis=grid,
        ic=ic_nc,
        npf=npf_nc,
        sto=sto_nc,
        oc=oc_nc,
        chd=chdg_nc,
        wel=welg_nc,
        rch=[rcha_nc],
        dims=dims,
    )
    sim_nc = make_sim4(ws_root / "flopy4_nc_mesh", gwf_nc)

    nc_fpth_m = ws_root / "flopy4_nc_mesh" / "test1005.input.nc"
    gwf_nc.netcdf_file = nc_fpth_m
    gwf_nc.netcdf_mesh2d_file = Path("test1005.nc")
    nc_mesh = flopy4.mf6.netcdf.NetCDFModel.from_model(
        gwf_nc, netcdf_format=NetCDFFormat.LAYERED_MESH, grid=grid, time=time4
    )

    def write_nc_mesh():
        nc_mesh.to_netcdf(nc_fpth_m)
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim_nc.write()

    results.append(
        report(
            "flopy4 netcdf_mesh  (WELG+CHDG+RCHA)",
            time_writes(write_nc_mesh, N, "flopy4 netcdf_mesh (WELG+CHDG+RCHA)", include_slow),
        )
    )

    ws_ncs = ws_root / "flopy4_nc_struct"
    ws_ncs.mkdir(parents=True, exist_ok=True)
    sim_nc.workspace = ws_ncs
    nc_fpth_s = ws_ncs / "test1005.input.nc"
    gwf_nc.netcdf_file = nc_fpth_s
    gwf_nc.netcdf_mesh2d_file = None
    nc_struct = flopy4.mf6.netcdf.NetCDFModel.from_model(gwf_nc, grid=grid, time=time4)

    def write_nc_struct():
        nc_struct.to_netcdf(nc_fpth_s)
        with flopy4.mf6.write_context.WriteContext(use_netcdf=True):
            sim_nc.write()

    results.append(
        report(
            "flopy4 netcdf_struct (WELG+CHDG+RCHA)",
            time_writes(write_nc_struct, N, "flopy4 netcdf_struct (WELG+CHDG+RCHA)", include_slow),
        )
    )

    sections.append({"name": "WEL+CHD+RCHA", "results": results})

    if args.output:
        write_results(args.output, "test1005_write", N, sections)


if __name__ == "__main__":
    main()
