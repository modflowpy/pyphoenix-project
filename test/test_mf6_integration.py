"""Test basic MF6 component behaviors like initialization, modification, access."""

from pathlib import Path

import numpy as np
import xarray as xr

from flopy4.mf6 import Ems, GwfGwe, GwfGwt
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwe import Adv as GweAdv
from flopy4.mf6.gwe import Cnd as GweCnd
from flopy4.mf6.gwe import Ctp as GweCtp
from flopy4.mf6.gwe import Dis as GweDis
from flopy4.mf6.gwe import Esl as GweEsl
from flopy4.mf6.gwe import Est as GweEst
from flopy4.mf6.gwe import Gwe
from flopy4.mf6.gwe import Ic as GweIc
from flopy4.mf6.gwe import Ssm as GweSsm
from flopy4.mf6.gwf import (
    Buy,
    Chd,
    Chdg,
    Dis,
    Disv,
    Drn,
    Evt,
    Evta,
    Ghb,
    Gwf,
    Ic,
    Mvr,
    Npf,
    Oc,
    Rch,
    Rcha,
    Riv,
    Sto,
    Vsc,
    Wel,
)
from flopy4.mf6.gwt import Adv as GwtAdv
from flopy4.mf6.gwt import Cnc as GwtCnc
from flopy4.mf6.gwt import Dis as GwtDis
from flopy4.mf6.gwt import Dsp as GwtDsp
from flopy4.mf6.gwt import Gwt
from flopy4.mf6.gwt import Ic as GwtIc
from flopy4.mf6.gwt import Mst as GwtMst
from flopy4.mf6.gwt import Src as GwtSrc
from flopy4.mf6.gwt import Ssm as GwtSsm
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import WriteContext


def test_gwf_chd01(function_tmpdir):
    sim_name = "chd01"
    gwf_name = "gwf_chd01"
    time = Time(perlen=[5.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1.00000000e-06,
        outer_maximum=100,
        under_relaxation="none",
        inner_maximum=300,
        inner_dvclose=1.00000000e-06,
        rcloserecord=Ims.Rclose(inner_rclose=1.00000000e-06),
        linear_acceleration="cg",
        relaxation_factor=1.0,
        scaling_method="none",
        reordering_method="none",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(
        nlay=1,
        nrow=1,
        ncol=100,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=0.0,
        idomain=1,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)

    ic = Ic(parent=gwf, strt=1.0)

    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        head="PRINT_FORMAT COLUMNS  10  WIDTH  15  DIGITS  6  GENERAL",
        save_head=["last"],
        save_budget=["last"],
        print_head=["last"],
        print_budget=["last"],
    )

    npf = Npf(
        parent=gwf,
        save_specific_discharge=True,
        k=1.0,
        k33=1.0,
        icelltype=0,
    )

    chd = Chd(
        parent=gwf,
        print_flows=True,
        head={0: {(0, 0, 0): 1.0, (0, 0, 99): 0.0}},
        name="chd-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{sim_name}.tdis").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.nam").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.dis").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.ic").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.oc").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.npf").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.chd").is_file()
    assert Path(function_tmpdir, "sln1.ims").is_file()


def test_gwf_disv(function_tmpdir):
    # based on mf6 test_gwf_disv.py
    sim_name = "disv"
    gwf_name = "gwf_disv"
    time = Time(
        perlen=[1.0],
        nstp=[1],
        tsmult=[1.0],
        time_units="days",
    )

    ims = Ims(
        filename=f"{sim_name}.ims",
        models=[gwf_name],
        print_option="summary",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    nlay = 3
    ncpl = 9
    nvert = 16
    top = np.ones((ncpl), dtype=float) * 0.0
    botm = np.stack([np.full((ncpl), val) for val in [-10.0, -20.0, -30.0]])

    cells = [
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [4, 5, 9, 8],
        [5, 6, 10, 9],
        [6, 7, 11, 10],
        [8, 9, 13, 12],
        [9, 10, 14, 13],
        [10, 11, 15, 14],
    ]

    cell2ddata = []
    xc = 1.00000005e08
    yc = 1.00000025e08
    for n in range(ncpl):
        cell2ddata.append(
            Disv.Cell2dRecord(
                n,
                xc + float((n % 3) * 10.0),
                yc - float(10.0 * int(n / 3)),
                4,
                tuple(cells[n]),
            )
        )

    disv = Disv(
        nlay=nlay,
        ncpl=ncpl,
        nvert=nvert,
        top=top,
        botm=botm,
        idomain=1,
        iv=np.arange(0, nvert, dtype=int),
        xv=np.concatenate(
            [
                np.array([1.00000000e08, 1.00000010e08, 1.00000020e08, 1.00000030e08])
                for i in range(4)
            ]
        ),
        yv=np.concatenate(
            [
                np.array([1.00000030e08, 1.00000030e08, 1.00000030e08, 1.00000030e08])
                - float(10 * (i % 4))
                for i in range(4)
            ]
        ),
        cell2ddata=cell2ddata,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=disv, name=gwf_name)

    ic = Ic(parent=gwf, strt=0.0)

    npf = Npf(
        parent=gwf,
        k=1.0,
        icelltype=0,
    )

    chd = Chd(
        parent=gwf,
        print_flows=True,
        head={0: {(0, 0): 1.0, (0, 8): 0.0}},
    )

    sim.write()
    sim.run()


def test_gwf_disv_uzf(function_tmpdir):
    # based on mf6 test_gwf_disv_uzf.py but no uzf (yet)
    sim_name = "disv"
    gwf_name = "gwf_disv"
    time = Time(
        perlen=[10.0, 10.0, 10.0, 10.0, 10.0],
        nstp=[5, 5, 5, 5, 5],
        tsmult=[1.0, 1.0, 1.0, 1.0, 1.0],
        time_units="days",
    )

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1.00000000e-09,
        outer_maximum=100,
        under_relaxation="dbd",
        inner_maximum=300,
        inner_dvclose=1.00000000e-09,
        rcloserecord=Ims.Rclose(inner_rclose=1.00000000e-03),
        linear_acceleration="bicgstab",
        relaxation_factor=0.97000000,
        scaling_method="none",
        reordering_method="none",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    cells = [
        [0, 1, 12, 11],
        [1, 2, 13, 12],
        [2, 3, 14, 13],
        [3, 4, 15, 14],
        [4, 5, 16, 15],
        [5, 6, 17, 16],
        [6, 7, 18, 17],
        [7, 8, 19, 18],
        [8, 9, 20, 19],
        [9, 10, 21, 20],
        [11, 12, 23, 22],
        [12, 13, 24, 23],
        [13, 14, 25, 24],
        [14, 15, 26, 25],
        [15, 16, 27, 26],
        [16, 17, 28, 27],
        [17, 18, 29, 28],
        [18, 19, 30, 29],
        [19, 20, 31, 30],
        [20, 21, 32, 31],
        [22, 23, 34, 33],
        [23, 24, 35, 34],
        [24, 25, 36, 35],
        [25, 26, 37, 36],
        [26, 27, 38, 37],
        [27, 28, 39, 38],
        [28, 29, 40, 39],
        [29, 30, 41, 40],
        [30, 31, 42, 41],
        [31, 32, 43, 42],
        [33, 34, 45, 44],
        [34, 35, 46, 45],
        [35, 36, 47, 46],
        [36, 37, 48, 47],
        [37, 38, 49, 48],
        [38, 39, 50, 49],
        [39, 40, 51, 50],
        [40, 41, 52, 51],
        [41, 42, 53, 52],
        [42, 43, 54, 53],
        [44, 45, 56, 55],
        [45, 46, 57, 56],
        [46, 47, 58, 57],
        [47, 48, 59, 58],
        [48, 49, 60, 59],
        [49, 50, 61, 60],
        [50, 51, 62, 61],
        [51, 52, 63, 62],
        [52, 53, 64, 63],
        [53, 54, 65, 64],
        [55, 56, 67, 66],
        [56, 57, 68, 67],
        [57, 58, 69, 68],
        [58, 59, 70, 69],
        [59, 60, 71, 70],
        [60, 61, 72, 71],
        [61, 62, 73, 72],
        [62, 63, 74, 73],
        [63, 64, 75, 74],
        [64, 65, 76, 75],
        [66, 67, 78, 77],
        [67, 68, 79, 78],
        [68, 69, 80, 79],
        [69, 70, 81, 80],
        [70, 71, 82, 81],
        [71, 72, 83, 82],
        [72, 73, 84, 83],
        [73, 74, 85, 84],
        [74, 75, 86, 85],
        [75, 76, 87, 86],
        [77, 78, 89, 88],
        [78, 79, 90, 89],
        [79, 80, 91, 90],
        [80, 81, 92, 91],
        [81, 82, 93, 92],
        [82, 83, 94, 93],
        [83, 84, 95, 94],
        [84, 85, 96, 95],
        [85, 86, 97, 96],
        [86, 87, 98, 97],
        [88, 89, 100, 99],
        [89, 90, 101, 100],
        [90, 91, 102, 101],
        [91, 92, 103, 102],
        [92, 93, 104, 103],
        [93, 94, 105, 104],
        [94, 95, 106, 105],
        [95, 96, 107, 106],
        [96, 97, 108, 107],
        [97, 98, 109, 108],
        [99, 100, 111, 110],
        [100, 101, 112, 111],
        [101, 102, 113, 112],
        [102, 103, 114, 113],
        [103, 104, 115, 114],
        [104, 105, 116, 115],
        [105, 106, 117, 116],
        [106, 107, 118, 117],
        [107, 108, 119, 118],
        [108, 109, 120, 119],
    ]

    cell2ddata = []
    xc = 0.50000000
    yc = 9.50000000
    for n in range(100):
        cell2ddata.append(
            Disv.Cell2dRecord(
                n,
                float(n % 10) + xc,
                yc - float(int(n / 10)),
                4,
                tuple(cells[n]),
            )
        )

    ncpl = 100
    top = np.ones((ncpl), dtype=float) * 25.0
    botm = np.stack([np.full((ncpl), val) for val in [20.0, 15.0, 10.0, 5.0, 0.0]])

    disv = Disv(
        nlay=5,
        ncpl=ncpl,
        nvert=121,
        top=top,
        botm=botm,
        idomain=1,
        iv=np.arange(0, 121, dtype=int),
        xv=np.tile(
            [
                0.00000000,
                1.00000000,
                2.00000000,
                3.00000000,
                4.00000000,
                5.00000000,
                6.00000000,
                7.00000000,
                8.00000000,
                9.00000000,
                10.00000000,
            ],
            11,
        ),
        yv=np.concatenate(
            [
                np.array(
                    [
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                        10.00000000,
                    ]
                )
                - float(i)
                for i in range(11)
            ]
        ),
        cell2ddata=cell2ddata,
    )

    gwf = Gwf(parent=sim, save_flows=True, newton=True, dis=disv, name=gwf_name)

    ic = Ic(parent=gwf, strt=20.0)

    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        head="PRINT_FORMAT COLUMNS  10  WIDTH  15  DIGITS  6  GENERAL",
        save_head={0: "all"},
        save_budget={0: "all"},
        print_head={0: "all"},
        print_budget={0: "all"},
    )

    npf = Npf(
        parent=gwf,
        save_flows=True,
        k=0.1,
        k33=1.0,
        icelltype=1,
    )

    # Storage
    sto = Sto(
        parent=gwf,
        storagecoefficient=False,
        ss=1.00000000e-05,
        sy=0.2,
        transient=[True, False, False, False, False],
        iconvert=1,
    )

    ghb_cells = [
        (3, 9),
        (3, 19),
        (3, 29),
        (3, 39),
        (3, 49),
        (3, 59),
        (3, 69),
        (3, 79),
        (3, 89),
        (3, 99),
        (4, 9),
        (4, 19),
        (4, 29),
        (4, 39),
        (4, 49),
        (4, 59),
        (4, 69),
        (4, 79),
        (4, 89),
        (4, 99),
    ]

    bhead = {0: {}}
    cond = {0: {}}
    for c in ghb_cells:
        bhead[0][c] = 1.40000000e01
        cond[0][c] = 1.00000000e04

    ghb = Ghb(
        parent=gwf,
        print_flows=True,
        bhead=bhead,
        cond=cond,
        name="ghb-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{sim_name}.tdis").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.nam").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.disv").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.ic").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.oc").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.npf").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.sto").is_file()
    assert Path(function_tmpdir, f"{gwf_name}.ghb").is_file()
    assert Path(function_tmpdir, "sln1.ims").is_file()


def test_quickstart(function_tmpdir):
    sim_name = "quickstart"
    gwf_name = "mymodel"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=[gwf_name])
    dis = Dis(
        nlay=1,
        nrow=10,
        ncol=10,
        top=1.0,
        botm=0.0,
    )
    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.bud",
        head_file=f"{gwf_name}.hds",
        save_head=["all"],
        save_budget=["all"],
    )
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})

    sim.write()
    sim.run()


def test_quickstart_grid(function_tmpdir):
    sim_name = "quickstart"
    gwf_name = "mymodel"

    # dimensions
    nlay = 1
    nrow = 10
    ncol = 10
    nstp = 1

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=[gwf_name])
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=1.0,
        botm=0.0,
    )
    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.bud",
        head_file=f"{gwf_name}.hds",
        save_head=["all"],
        save_budget=["all"],
    )
    npf = Npf(parent=gwf, icelltype=0, k=1.0)

    # Chdg
    GRID_NODATA = np.full((nlay, nrow, ncol), FILL_DNODATA, dtype=float)
    head = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=1, axis=0)
    head[0, 0, 0, 0] = 1.0
    head[0, 0, 9, 9] = 0.0
    chd = Chdg(
        parent=gwf,
        head=head.reshape(1, -1),
    )

    sim.write()
    sim.run()


def test_quickstart_netcdf(function_tmpdir):
    from flopy4.mf6.netcdf import NetCDFModel

    sim_name = "quickstart"
    gwf_name = "mymodel"

    # dimensions
    nlay = 1
    nrow = 10
    ncol = 10
    nstp = 1

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=[gwf_name])
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=1.0,
        botm=0.0,
    )
    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.bud",
        head_file=f"{gwf_name}.hds",
        save_head=["all"],
        save_budget=["all"],
    )
    npf = Npf(parent=gwf, icelltype=0, k=1.0)

    # Chdg
    GRID_NODATA = np.full((nlay, nrow, ncol), FILL_DNODATA, dtype=float)
    head = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=1, axis=0)
    head[0, 0, 0, 0] = 1.0
    head[0, 0, 9, 9] = 0.0
    chd = Chdg(
        parent=gwf,
        head=head.reshape(1, -1),
    )

    nc_fpth = function_tmpdir / f"{gwf_name}.input.nc"
    gwf.netcdf_file = nc_fpth

    nc_model = NetCDFModel.from_model(gwf)
    ds = nc_model.to_xarray()
    ds.to_netcdf(nc_fpth)

    with WriteContext(use_netcdf=True):
        sim.write()

    with open(function_tmpdir / f"{gwf_name}.nam", "r") as fh:
        lines = fh.readlines()
        nc_fpth = function_tmpdir / f"{gwf_name}.input.nc"
        assert f" NETCDF FILEIN {nc_fpth}\n" in lines
    with open(function_tmpdir / f"{gwf_name}.dis", "r") as fh:
        lines = fh.readlines()
        assert " DELR NETCDF\n" in lines
        assert " DELC NETCDF\n" in lines
        assert " TOP NETCDF\n" in lines
        assert " BOTM NETCDF\n" in lines
        assert " IDOMAIN NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.npf", "r") as fh:
        lines = fh.readlines()
        assert " ICELLTYPE NETCDF\n" in lines
        assert " K NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.ic", "r") as fh:
        lines = fh.readlines()
        assert " STRT NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.chdg", "r") as fh:
        lines = fh.readlines()
        assert " HEAD NETCDF\n" in lines

    ds = xr.load_dataset(nc_fpth, mask_and_scale=False)
    assert ("dis_delr") in ds
    assert ("dis_delc") in ds
    assert ("dis_top") in ds
    assert ("dis_botm") in ds
    assert ("dis_idomain") in ds
    assert ("ic_strt") in ds
    assert ("npf_icelltype") in ds
    assert ("npf_k") in ds
    assert ("chdg0_head") in ds

    assert np.allclose(ds["dis_delr"].values, dis.delr)
    assert np.allclose(ds["dis_delc"].values, dis.delc)
    assert np.allclose(ds["dis_top"].values, dis.top)
    assert np.allclose(ds["dis_botm"].values, dis.botm)
    assert np.allclose(ds["dis_idomain"].values, dis.idomain)
    assert np.allclose(ds["ic_strt"].values.ravel(), ic.strt)
    assert np.allclose(ds["npf_icelltype"].values.ravel(), npf.icelltype)
    assert np.allclose(ds["npf_k"].values.ravel(), npf.k)
    assert np.allclose(ds["chdg0_head"].values.ravel(), chd.head)

    # requires mf6 extended to run
    # sim.run()


def test_quickstart_netcdf_mesh(function_tmpdir):
    from flopy4.mf6.netcdf import NetCDFModel

    sim_name = "quickstart"
    gwf_name = "mymodel"

    # dimensions
    nlay = 1
    nrow = 10
    ncol = 10
    nstp = 1

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=[gwf_name])
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        top=1.0,
        botm=0.0,
    )
    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )
    gwf = Gwf(parent=sim, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.bud",
        head_file=f"{gwf_name}.hds",
        save_head=["all"],
        save_budget=["all"],
    )
    npf = Npf(parent=gwf, icelltype=0, k=1.0)

    # Chdg
    GRID_NODATA = np.full((nlay, nrow, ncol), FILL_DNODATA, dtype=float)
    head = np.repeat(np.expand_dims(GRID_NODATA, axis=0), repeats=1, axis=0)
    head[0, 0, 0, 0] = 1.0
    head[0, 0, 9, 9] = 0.0
    chd = Chdg(
        parent=gwf,
        head=head.reshape(1, -1),
    )

    nc_fpth = function_tmpdir / f"{gwf_name}.input.nc"
    gwf.netcdf_file = nc_fpth

    nc_model = NetCDFModel.from_model(gwf, mesh="layered")
    ds = nc_model.to_xarray()
    ds.to_netcdf(nc_fpth)

    with WriteContext(use_netcdf=True):
        sim.write()

    with open(function_tmpdir / f"{gwf_name}.nam", "r") as fh:
        lines = fh.readlines()
        nc_fpth = function_tmpdir / f"{gwf_name}.input.nc"
        assert f" NETCDF FILEIN {nc_fpth}\n" in lines
    with open(function_tmpdir / f"{gwf_name}.dis", "r") as fh:
        lines = fh.readlines()
        assert " DELR NETCDF\n" in lines
        assert " DELC NETCDF\n" in lines
        assert " TOP NETCDF\n" in lines
        assert " BOTM NETCDF\n" in lines
        assert " IDOMAIN NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.npf", "r") as fh:
        lines = fh.readlines()
        assert " ICELLTYPE NETCDF\n" in lines
        assert " K NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.ic", "r") as fh:
        lines = fh.readlines()
        assert " STRT NETCDF\n" in lines
    with open(function_tmpdir / f"{gwf_name}.chdg", "r") as fh:
        lines = fh.readlines()
        assert " HEAD NETCDF\n" in lines

    ds = xr.load_dataset(nc_fpth, mask_and_scale=False)
    assert ("dis_delr") in ds
    assert ("dis_delc") in ds
    assert ("dis_top") in ds
    assert ("dis_botm_l1") in ds
    assert ("dis_idomain_l1") in ds
    assert ("ic_strt_l1") in ds
    assert ("npf_icelltype_l1") in ds
    assert ("npf_k_l1") in ds
    assert ("chdg0_head_l1") in ds

    assert np.allclose(ds["dis_delr"].values, dis.delr)
    assert np.allclose(ds["dis_delc"].values, dis.delc)
    assert np.allclose(ds["dis_top"].values, dis.top.values.ravel())
    assert np.allclose(ds["dis_botm_l1"].values, dis.botm.values.ravel())
    assert np.allclose(ds["dis_idomain_l1"].values, dis.idomain.values.ravel())
    assert np.allclose(ds["ic_strt_l1"].values.ravel(), ic.strt.values.ravel())
    assert np.allclose(ds["npf_icelltype_l1"].values.ravel(), npf.icelltype.values.ravel())
    assert np.allclose(ds["npf_k_l1"].values.ravel(), npf.k.values.ravel())
    assert np.allclose(ds["chdg0_head_l1"].values.ravel(), chd.head.values.ravel())

    # requires mf6 extended to run
    # sim.run()


def test_gwf_wel(function_tmpdir):
    """1-layer, 1-row, 10-col model with a single pumping well in the middle."""
    sim_name = "gwf_wel"
    gwf_name = "gwf_wel"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=5.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 5.0, (0, 0, 9): 5.0}}, name="chd-1")
    wel = Wel(parent=gwf, q={0: {(0, 0, 4): -1.0}}, name="wel-1")

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.wel").is_file()


def test_gwf_drn(function_tmpdir):
    """1-layer, 1-row, 10-col model with drain cells at one end."""
    sim_name = "gwf_drn"
    gwf_name = "gwf_drn"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=5.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 5.0}}, name="chd-1")
    drn = Drn(
        parent=gwf,
        elev={0: {(0, 0, 9): 4.0}},
        cond={0: {(0, 0, 9): 100.0}},
        name="drn-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.drn").is_file()


def test_gwf_riv(function_tmpdir):
    """1-layer, 1-row, 10-col model with river cells along one end."""
    sim_name = "gwf_riv"
    gwf_name = "gwf_riv"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=3.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 3.0}}, name="chd-1")
    riv = Riv(
        parent=gwf,
        stage={0: {(0, 0, 9): 5.0}},
        cond={0: {(0, 0, 9): 100.0}},
        rbot={0: {(0, 0, 9): 2.0}},
        name="riv-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.riv").is_file()


def test_gwf_rch(function_tmpdir):
    """1-layer, 1-row, 10-col model with uniform recharge (stress-package form)."""
    sim_name = "gwf_rch"
    gwf_name = "gwf_rch"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(
        parent=gwf,
        head={0: {(0, 0, 0): 1.0, (0, 0, 9): 1.0}},
        name="chd-1",
    )
    rch = Rch(
        parent=gwf,
        recharge={0: {(0, 0, i): 1e-3 for i in range(10)}},
        name="rch-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.rch").is_file()


def test_gwf_rcha(function_tmpdir):
    """1-layer, 1-row, 10-col model with uniform recharge (array-based form)."""
    sim_name = "gwf_rcha"
    gwf_name = "gwf_rcha"
    nrow, ncol = 1, 10
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=nrow, ncol=ncol, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(
        parent=gwf,
        head={0: {(0, 0, 0): 1.0, (0, 0, 9): 1.0}},
        name="chd-1",
    )
    rcha = Rcha(
        parent=gwf,
        recharge=np.full((1, nrow * ncol), 1e-3),
        name="rcha-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.rcha").is_file()


def test_gwf_evt(function_tmpdir):
    """1-layer, 1-row, 10-col model with ET (stress-package form)."""
    sim_name = "gwf_evt"
    gwf_name = "gwf_evt"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=8.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(
        parent=gwf,
        head={0: {(0, 0, 0): 8.0, (0, 0, 9): 8.0}},
        name="chd-1",
    )
    evt = Evt(
        parent=gwf,
        surface={0: {(0, 0, i): 10.0 for i in range(10)}},
        rate={0: {(0, 0, i): 1e-3 for i in range(10)}},
        depth={0: {(0, 0, i): 4.0 for i in range(10)}},
        name="evt-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.evt").is_file()


def test_gwf_evta(function_tmpdir):
    """1-layer, 1-row, 10-col model with ET (array-based form)."""
    sim_name = "gwf_evta"
    gwf_name = "gwf_evta"
    nrow, ncol = 1, 10
    ncpl = nrow * ncol
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=nrow, ncol=ncol, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=8.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    chd = Chd(
        parent=gwf,
        head={0: {(0, 0, 0): 8.0, (0, 0, 9): 8.0}},
        name="chd-1",
    )
    evta = Evta(
        parent=gwf,
        surface=np.full((1, ncpl), 10.0),
        rate=np.full((1, ncpl), 1e-3),
        depth=np.full((1, ncpl), 4.0),
        name="evta-1",
    )

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwf_name}.evta").is_file()


def test_gwf_mvr(function_tmpdir):
    """Verify MVR file writing: PACKAGES block (string arrays) and PERIOD block (tabular records).

    Write-only: MF6 is not run because a valid MVR simulation requires at least one
    advanced package (SFR, LAK, MAW, or UZF) as a receiver. Standard boundary packages
    (WEL, DRN, CHD, etc.) call pakmvrobj%ar with nreceivers=0 and cannot receive water
    from MVR. None of those advanced packages are implemented yet in this branch.

    The assertions verify the MVR file format, including the string array fields
    (pname1, pname2, mvrtype) that require special handling in the period block
    unstructurer.
    """
    sim_name = "gwf_mvr"
    gwf_name = "gwf_mvr"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="cg",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(nlay=1, nrow=1, ncol=10, delr=10.0, delc=10.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    ic = Ic(parent=gwf, strt=5.0)
    npf = Npf(parent=gwf, icelltype=0, k=1.0)
    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    # xattree appends the 0-based index for list-typed children, so Chd/Wel/Drn
    # get auto-names chd0/wel0/drn0. Explicit name= would be mangled (e.g. "wel-1" -> "wel-10").
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 5.0, (0, 0, 9): 5.0}})
    # mover=True writes MOVER keyword to OPTIONS block so MF6 allocates IMOVER
    wel = Wel(parent=gwf, mover=True, q={0: {(0, 0, 4): -1.0}})
    drn = Drn(
        parent=gwf,
        mover=True,
        elev={0: {(0, 0, 4): 4.0}},
        cond={0: {(0, 0, 4): 100.0}},
    )

    # MVR PACKAGES block lists participating packages by auto-assigned xattree name.
    # PERIOD block uses object-dtype string arrays (pname1, pname2, mvrtype) which
    # require the is_tabular check in _unstructure_block_param to be written correctly.
    mvr = Mvr(
        parent=gwf,
        maxpackages=2,
        maxmvr=1,
        pname=np.array(["wel0", "drn0"]),
        pname1=np.array(["wel0"]),
        id1=np.array([1], dtype=np.int64),
        pname2=np.array(["drn0"]),
        id2=np.array([1], dtype=np.int64),
        mvrtype=np.array(["FACTOR"]),
        value=np.array([0.5]),
        name="mvr",
    )

    sim.write()

    mvr_path = Path(function_tmpdir, f"{gwf_name}.mvr")
    assert mvr_path.is_file()
    content = mvr_path.read_text()

    # PACKAGES block must come before PERIOD block
    assert content.index("BEGIN PACKAGES") < content.index("BEGIN PERIOD")

    # PACKAGES block: both packages listed (from pname array)
    assert "wel0" in content
    assert "drn0" in content

    # PERIOD block: full record with all six columns in order
    # (pname1 id1 pname2 id2 mvrtype value)
    assert "wel0 1 drn0 1 FACTOR 0.5" in content


def test_gwt_basic(function_tmpdir):
    """1D GWF+GWT coupled test: advection-dispersion transport in a uniform flow field.

    Exercises ic, adv, mst, dsp, cnc packages and the GwfGwt exchange.
    """
    sim_name = "gwt_basic"
    gwf_name = "gwf"
    gwt_name = "gwt"
    nlay, nrow, ncol = 1, 1, 10

    time = Time(perlen=[10.0], nstp=[10], tsmult=[1.0], time_units="days")

    ims_gwf = Ims(
        filename="gwf.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )
    ims_gwt = Ims(
        filename="gwt.ims",
        models=[gwt_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"gwf_ims": ims_gwf, "gwt_ims": ims_gwt},
    )

    # GWF model: uniform left-to-right flow
    gwf_dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=gwf_dis, name=gwf_name)
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 0, ncol - 1): 0.0}}, name="chd-1")

    # GWF-GWT exchange
    GwfGwt(parent=sim, name="gwfgwt", exgmnamea=gwf_name, exgmnameb=gwt_name)

    # GWT model: tracer introduced at left boundary
    gwt_dis = GwtDis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwt = Gwt(parent=sim, dis=gwt_dis, name=gwt_name)
    GwtIc(parent=gwt, strt=0.0)
    GwtSsm(parent=gwt)
    GwtAdv(parent=gwt, scheme="upstream")
    GwtMst(parent=gwt, porosity=0.3)
    GwtDsp(parent=gwt, xt3d_off=True, diffc=0.0, alh=0.1, alv=0.1, ath1=0.0)
    GwtCnc(parent=gwt, conc={0: {(0, 0, 0): 1.0}}, name="cnc-1")
    GwtSrc(parent=gwt, smassrate={0: {(0, 0, 5): 1e-4}}, name="src-1")

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwt_name}.ic").is_file()
    assert Path(function_tmpdir, f"{gwt_name}.cnc").is_file()
    assert Path(function_tmpdir, f"{gwt_name}.src").is_file()

    # exgfile=None triggers default_filename() → "{exchange_name}.exg"
    mfsim = Path(function_tmpdir, "mfsim.nam").read_text()
    assert "gwfgwt.exg" in mfsim


def test_gwe_basic(function_tmpdir):
    """1D GWF+GWE coupled test: heat transport in a uniform flow field.

    Exercises ic, adv, est, cnd, ctp packages and the GwfGwe exchange.
    """
    sim_name = "gwe_basic"
    gwf_name = "gwf"
    gwe_name = "gwe"
    nlay, nrow, ncol = 1, 1, 10

    time = Time(perlen=[10.0], nstp=[10], tsmult=[1.0], time_units="days")

    ims_gwf = Ims(
        filename="gwf.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )
    ims_gwe = Ims(
        filename="gwe.ims",
        models=[gwe_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"gwf_ims": ims_gwf, "gwe_ims": ims_gwe},
    )

    # GWF model: uniform left-to-right flow
    gwf_dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=gwf_dis, name=gwf_name)
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 0, ncol - 1): 0.0}}, name="chd-1")

    # GWF-GWE exchange
    GwfGwe(parent=sim, name="gwfgwe", exgmnamea=gwf_name, exgmnameb=gwe_name)

    # GWE model: heat tracer introduced at left boundary
    gwe_dis = GweDis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwe = Gwe(parent=sim, dis=gwe_dis, name=gwe_name)
    GweIc(parent=gwe, strt=0.0)
    GweSsm(parent=gwe)
    GweAdv(parent=gwe, scheme="upstream")
    GweEst(parent=gwe, porosity=0.3, heat_capacity_solid=800.0, density_solid=2700.0)
    GweCnd(parent=gwe, ktw=0.58, kts=3.0)
    GweCtp(parent=gwe, temp={0: {(0, 0, 0): 1.0}}, name="ctp-1")
    GweEsl(parent=gwe, senerrate={0: {(0, 0, 5): 1e-4}}, name="esl-1")

    sim.write()
    sim.run()

    assert Path(function_tmpdir, f"{gwe_name}.ic").is_file()
    assert Path(function_tmpdir, f"{gwe_name}.ctp").is_file()
    assert Path(function_tmpdir, f"{gwe_name}.esl").is_file()

    # exgfile=None triggers default_filename() → "{exchange_name}.exg"
    mfsim = Path(function_tmpdir, "mfsim.nam").read_text()
    assert "gwfgwe.exg" in mfsim


def test_gwf_buy(function_tmpdir):
    """GWF+GWT with variable-density (BUY) package.

    Exercises the packagedata block tier: BUY links GWF density to GWT
    concentration via an auxiliary variable on the CHD boundary package.
    """
    sim_name = "gwf_buy"
    gwf_name = "gwf"
    gwt_name = "gwt"
    nlay, nrow, ncol = 1, 1, 10

    time = Time(perlen=[10.0], nstp=[10], tsmult=[1.0], time_units="days")

    ims_gwf = Ims(
        filename="gwf.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )
    ims_gwt = Ims(
        filename="gwt.ims",
        models=[gwt_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"gwf_ims": ims_gwf, "gwt_ims": ims_gwt},
    )

    gwf_dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=gwf_dis, name=gwf_name)
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    # CHD with auxiliary "conc" so BUY can read concentration per stress record
    Chd(
        parent=gwf,
        auxiliary=["conc"],
        head={0: {(0, 0, 0): 1.0, (0, 0, ncol - 1): 0.0}},
        aux={0: {(0, 0, 0): 0.0, (0, 0, ncol - 1): 0.0}},
        name="chd-1",
    )
    Buy(
        parent=gwf,
        nrhospecies=1,
        irhospec=np.array([1], dtype=np.int64),
        drhodc=np.array([0.7143]),
        crhoref=np.array([0.0]),
        modelname=np.array([gwt_name], dtype=object),
        auxspeciesname=np.array(["conc"], dtype=object),
    )

    GwfGwt(parent=sim, name="gwfgwt", exgmnamea=gwf_name, exgmnameb=gwt_name)

    gwt_dis = GwtDis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwt = Gwt(parent=sim, dis=gwt_dis, name=gwt_name)
    GwtIc(parent=gwt, strt=0.0)
    GwtSsm(parent=gwt)
    GwtAdv(parent=gwt, scheme="upstream")
    GwtMst(parent=gwt, porosity=0.3)
    GwtCnc(parent=gwt, conc={0: {(0, 0, 0): 1.0}}, name="cnc-1")

    sim.write()

    buy_input = Path(function_tmpdir, f"{gwf_name}.buy")
    assert buy_input.is_file()
    content = buy_input.read_text()
    assert "BEGIN PACKAGEDATA" in content
    assert gwt_name in content
    assert "conc" in content
    # Verify row format: all five columns on one line (irhospec drhodc crhoref modelname auxspeciesname)  # noqa: E501
    assert any(
        gwt_name in line and "conc" in line for line in content.splitlines()
    ), "PACKAGEDATA row should have all columns on one line"


def test_gwf_vsc(function_tmpdir):
    """GWF+GWE with variable-viscosity (VSC) package.

    Exercises the packagedata block tier: VSC links GWF viscosity to GWE
    temperature via an auxiliary variable on the CHD boundary package.
    """
    sim_name = "gwf_vsc"
    gwf_name = "gwf"
    gwe_name = "gwe"
    nlay, nrow, ncol = 1, 1, 10

    time = Time(perlen=[10.0], nstp=[10], tsmult=[1.0], time_units="days")

    ims_gwf = Ims(
        filename="gwf.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )
    ims_gwe = Ims(
        filename="gwe.ims",
        models=[gwe_name],
        print_option="summary",
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rcloserecord=Ims.Rclose(inner_rclose=1e-6),
        linear_acceleration="bicgstab",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"gwf_ims": ims_gwf, "gwe_ims": ims_gwe},
    )

    gwf_dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwf = Gwf(parent=sim, save_flows=True, dis=gwf_dis, name=gwf_name)
    Ic(parent=gwf, strt=1.0)
    Npf(parent=gwf, icelltype=0, k=1.0)
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    # CHD with auxiliary "temperature" so VSC can read temp per stress record
    Chd(
        parent=gwf,
        auxiliary=["temperature"],
        head={0: {(0, 0, 0): 1.0, (0, 0, ncol - 1): 0.0}},
        aux={0: {(0, 0, 0): 20.0, (0, 0, ncol - 1): 20.0}},
        name="chd-1",
    )
    Vsc(
        parent=gwf,
        viscref=8.904e-4,
        thermal_formulation="nonlinear",
        temperature_species_name="temperature",
        nviscspecies=1,
        iviscspec=np.array([1], dtype=np.int64),
        dviscdc=np.array([0.0]),
        cviscref=np.array([20.0]),
        modelname=np.array([gwe_name], dtype=object),
        auxspeciesname=np.array(["temperature"], dtype=object),
    )

    GwfGwe(parent=sim, name="gwfgwe", exgmnamea=gwf_name, exgmnameb=gwe_name)

    gwe_dis = GweDis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=1.0, botm=0.0)
    gwe = Gwe(parent=sim, dis=gwe_dis, name=gwe_name)
    GweIc(parent=gwe, strt=20.0)
    GweSsm(parent=gwe)
    GweAdv(parent=gwe, scheme="upstream")
    GweEst(parent=gwe, porosity=0.3, heat_capacity_solid=800.0, density_solid=2700.0)
    GweCnd(parent=gwe, ktw=0.58, kts=3.0)
    GweCtp(parent=gwe, temp={0: {(0, 0, 0): 40.0}}, name="ctp-1")

    sim.write()

    vsc_input = Path(function_tmpdir, f"{gwf_name}.vsc")
    assert vsc_input.is_file()
    content = vsc_input.read_text()
    assert "BEGIN PACKAGEDATA" in content
    assert gwe_name in content
    assert "temperature" in content
    # Verify row format: all five columns on one line (iviscspec dviscdc cviscref modelname auxspeciesname)  # noqa: E501
    assert any(
        gwe_name in line and "temperature" in line for line in content.splitlines()
    ), "PACKAGEDATA row should have all columns on one line"
    assert Path(function_tmpdir, f"{gwe_name}.ctp").is_file()


def test_prt_basic(function_tmpdir):
    """1-layer, 1-row, 5-col GWF+PRT: verify PRT file writing and run.

    PRT's FMI reads head/budget from a prior GWF run, so two separate simulations
    are used: GWF runs first to produce .hds/.cbc, then PRT reads them via FMI.
    NPF requires save_specific_discharge and save_saturation for particle tracking.

    PRP is not included: cellid is a 2D field (nreleasepts, ncelldim) not yet
    supported by the codegen-generated Prp class. PRT runs successfully with no
    release points (no particles tracked, empty track output).
    """
    from flopy4.mf6.prt import Dis as PrtDis
    from flopy4.mf6.prt import Fmi, Mip, Prt
    from flopy4.mf6.prt import Oc as PrtOc

    gwf_name = "gwf_prt"
    prt_name = "prt_prt"
    nlay, nrow, ncol = 1, 1, 5

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")

    # --- GWF simulation ---
    gwf_sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name="gwf_sim",
        solutions={
            "ims": Ims(
                filename="gwf.ims",
                models=[gwf_name],
                outer_dvclose=1e-6,
                outer_maximum=50,
                inner_maximum=100,
                inner_dvclose=1e-6,
                rcloserecord=Ims.Rclose(inner_rclose=1e-3),
                linear_acceleration="cg",
            )
        },
    )
    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=10.0, botm=0.0)
    gwf = Gwf(parent=gwf_sim, save_flows=True, dis=dis, name=gwf_name)
    Ic(parent=gwf, strt=5.0)
    # save_specific_discharge and save_saturation required by PRT for particle tracking
    Npf(
        parent=gwf,
        icelltype=0,
        k=1.0,
        save_flows=True,
        save_specific_discharge=True,
        save_saturation=True,
    )
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )
    Chd(parent=gwf, head={0: {(0, 0, 0): 5.0, (0, 0, 4): 3.0}})
    gwf_sim.write()
    gwf_sim.run()

    # --- PRT simulation (reads GWF output via FMI) ---
    prt_sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name="prt_sim",
        solutions={"ems": Ems(filename="prt.ems", models=[prt_name])},
    )
    prt_dis = PrtDis(nlay=nlay, nrow=nrow, ncol=ncol, delr=1.0, delc=1.0, top=10.0, botm=0.0)
    prt = Prt(parent=prt_sim, dis=prt_dis, name=prt_name)
    Mip(parent=prt, porosity=0.3)
    Fmi(
        parent=prt,
        gwfhead=Path(f"{gwf_name}.hds"),
        gwfbudget=Path(f"{gwf_name}.cbc"),
    )
    PrtOc(parent=prt, track_filerecord=f"{prt_name}.trk", trackcsv_filerecord=f"{prt_name}.trk.csv")
    prt_sim.write()
    prt_sim.run()

    # Verify PRT files written and FMI format correct
    fmi_path = Path(function_tmpdir, f"{prt_name}.fmi")
    oc_path = Path(function_tmpdir, f"{prt_name}.oc")
    assert fmi_path.is_file()
    assert oc_path.is_file()

    fmi_content = fmi_path.read_text()
    assert "GWFHEAD" in fmi_content
    assert "GWFBUDGET" in fmi_content
    assert "FILEIN" in fmi_content

    oc_content = oc_path.read_text()
    assert "TRACK FILEOUT" in oc_content
