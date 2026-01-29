"""Test basic MF6 component behaviors like initialization, modification, access."""

from pathlib import Path

import numpy as np
import xarray as xr

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Chdg, Dis, Disv, Ghb, Gwf, Ic, Npf, Oc, Sto
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
        inner_rclose=1.00000000e-06,
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
        inner_rclose=1.00000000e-03,
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
