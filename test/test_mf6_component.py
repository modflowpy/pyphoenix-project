"""Test basic MF6 component behaviors like initialization, modification, access."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from xarray import DataTree

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.constants import FILL_DNODATA, LENBOUNDNAME
from flopy4.mf6.gwf import Chd, Chdg, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import WriteContext


def test_registry():
    assert COMPONENTS["simulation"] is Simulation
    assert COMPONENTS["tdis"] is Tdis
    assert COMPONENTS["gwf"] is Gwf
    assert COMPONENTS["npf"] is Npf
    assert COMPONENTS["ic"] is Ic
    assert COMPONENTS["oc"] is Oc


def test_init_empty_sim():
    sim = Simulation()


def test_init_gwf_explicit_dims():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=2, ncol=2)
    dims = {
        "nper": time.nper,
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
        "nodes": grid.nnodes,
    }
    dis = Dis(dims=dims)
    ic = Ic(dims=dims)
    oc = Oc(dims=dims)
    npf = Npf(dims=dims)
    chd = Chd(dims=dims)
    gwf = Gwf(
        dis=dis,
        ic=ic,
        oc=oc,
        npf=npf,
        chd=[chd],
        dims=dims,
    )

    assert isinstance(gwf.data, DataTree)
    assert gwf.dis is dis  # dimension order switched.. is this ok?
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert gwf.data.dis is dis.data
    assert gwf.data.ic is ic.data
    assert gwf.data.oc is oc.data
    assert gwf.data.npf is npf.data
    assert np.array_equal(npf.k, np.ones(4))
    assert np.array_equal(npf.data.k, np.ones(4))


@pytest.mark.skip(reason="TODO")
def test_init_gwf_from_grid_context():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=2, ncol=2)
    # TODO maybe a dumb idea, but we could put the
    # time and grid in a context manager? then you
    # don't have to pass them into each component.
    with Discretization(grid, time):
        dis = Dis()
        ic = Ic()
        oc = Oc()
        npf = Npf()
        chd = Chd()
        gwf = Gwf(
            dis=dis,
            ic=ic,
            oc=oc,
            npf=npf,
            chd=[chd],
        )

    assert isinstance(gwf.data, DataTree)
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert gwf.data.dis is dis.data
    assert gwf.data.ic is ic.data
    assert gwf.data.oc is oc.data
    assert gwf.data.npf is npf.data
    assert np.array_equal(npf.k, np.ones(4))
    assert np.array_equal(npf.data.k, np.ones(4))


def test_init_gwf_dis_first():
    dis = Dis()
    gwf = Gwf(dis=dis)
    ic = Ic(parent=gwf)
    oc = Oc(parent=gwf, strict=False)
    npf = Npf(parent=gwf)
    chd = Chd(parent=gwf, strict=False)

    assert isinstance(gwf.data, DataTree)
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(npf.k, np.ones(4))
    assert np.array_equal(npf.data.k, np.ones(4))


def test_init_gwf_dis_first_with_grid():
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    gwf = Gwf(dis=grid)
    dis = gwf.dis
    ic = Ic(parent=gwf)
    oc = Oc(parent=gwf, strict=False)
    npf = Npf(parent=gwf)
    chd = Chd(parent=gwf, strict=False)

    assert isinstance(gwf.data, DataTree)
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(npf.k, np.ones(100))
    assert np.array_equal(npf.data.k, np.ones(100))


def test_init_gwf_top_down_misaligned():
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }
    gwf = Gwf()
    with pytest.raises(ValueError, match=r"group '/dis' is not aligned with its parents"):
        Dis(parent=gwf, **dims)

    # passing dims explicitly to gwf doesn't work either.
    # one MUST create the component declaring dims first.
    with pytest.raises(ValueError, match=r"group '/dis' is not aligned with its parents"):
        Gwf(dims=dims)


def test_init_sim_explicit_dims():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }
    dis = Dis(**dims)
    dims["nper"] = time.nper
    dims["nodes"] = grid.nnodes
    ic = Ic(dims=dims)
    oc = Oc(dims=dims)
    npf = Npf(dims=dims)
    chd = Chd(
        dims=dims,
        head={"*": {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
        boundname={"*": {(0, 0, 0): "INLET", (0, 9, 9): "OUTLET"}},
    )
    gwf = Gwf(
        dis=dis,
        ic=ic,
        oc=oc,
        npf=npf,
        chd=[chd],
        dims=dims,
    )
    tdis = Tdis(dims=dims)
    sim = Simulation(tdis=tdis, models={"gwf": gwf})

    assert sim.tdis is tdis
    assert sim.models["gwf"] is gwf
    assert isinstance(sim.data, DataTree)
    assert sim.data.tdis is tdis.data
    assert sim.data.gwf is gwf.data
    assert gwf.dis is dis  # gwf.dis has inherited dim nper
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(sim.models["gwf"].npf.k, np.ones(100))
    assert np.array_equal(sim.models["gwf"].npf.data.k, np.ones(100))
    assert chd.head[0, 0] == 1.0
    assert chd.head[0, 99] == 0.0
    assert chd.boundname[0, 0] == "INLET"
    assert chd.boundname[0, 99] == "OUTLET"
    assert chd.boundname.dtype == np.dtype(f"<U{LENBOUNDNAME}")
    assert np.array_equal(chd.head[0, 1:99].data, np.full((98,), FILL_DNODATA))
    assert np.array_equal(chd.head.data, chd.data.head.data)
    assert np.array_equal(
        chd.head.data,
        sim.models["gwf"].chd[0].data.head.data,
        equal_nan=True,
    )


def test_init_big_sim():
    # if size over threshold, arrays should be sparse
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=1000, ncol=1000)
    sim = Simulation(tdis=time)
    gwf = Gwf(parent=sim, dis=grid)
    ic = Ic(parent=gwf)
    oc = Oc(parent=gwf)
    npf = Npf(parent=gwf)
    chd = Chd(parent=gwf, head={"*": {(0, 0, 0): 1.0, (0, 999, 999): 0.0}})

    assert sim.models["gwf"] is gwf
    assert isinstance(sim.data, DataTree)
    assert sim.data.gwf is gwf.data
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(sim.models["gwf"].npf.k, np.ones(1000000))
    assert np.array_equal(sim.models["gwf"].npf.data.k, np.ones(1000000))
    assert chd.head[0, 0].item() == 1.0
    assert chd.head[0, 999999].item() == 0.0
    assert np.array_equal(chd.head[0, 1:999999].data.todense(), np.full((999998,), FILL_DNODATA))
    assert np.array_equal(chd.head.data.todense(), chd.data.head.data.todense())
    assert np.array_equal(
        chd.head.data.todense(),
        sim.models["gwf"].chd[0].data.head.data.todense(),
        equal_nan=True,
    )

    # test dictionary access/deletion
    assert gwf["npf"] is npf
    del gwf["npf"]
    assert "npf" not in gwf


def test_gwf_dfn():
    gwf = Gwf()
    dfn = gwf.dfn
    assert dfn.name == "gwf"
    assert not dfn.advanced
    assert not dfn.multi
    assert dfn.ref is None
    assert "save_flows" in set(dfn.blocks["options"].keys())


def test_chd_dfn():
    chd = Chd(strict=False)
    dfn = chd.dfn
    assert dfn.name == "chd"
    assert not dfn.advanced
    assert dfn.multi
    assert dfn.ref is None
    assert "print_input" in set(dfn.blocks["options"].keys())
    assert "head" in set(dfn.blocks["period"].keys())


def test_ims_dfn():
    ims = Ims(strict=False)
    dfn = ims.dfn
    assert dfn.name == "ims"
    assert not dfn.advanced
    assert not dfn.multi
    assert dfn.ref is None
    assert "complexity" in set(dfn.blocks["options"].keys())
    assert "inner_maximum" in set(dfn.blocks["linear"].keys())


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
        # save_head={0: "last"},
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

    ds = gwf.to_xarray(format="structured")
    ds.to_netcdf(nc_fpth)

    with WriteContext(use_netcdf=True):
        sim.write()

    with open(function_tmpdir / f"{gwf_name}.nam", "r") as fh:
        lines = fh.readlines()
        assert f" NETCDF FILEIN {function_tmpdir}/{gwf_name}.input.nc\n" in lines
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

    ds = xr.load_dataset(nc_fpth)
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

    ds = gwf.to_xarray(format="layered")
    ds.to_netcdf(nc_fpth)

    with WriteContext(use_netcdf=True):
        sim.write()

    with open(function_tmpdir / f"{gwf_name}.nam", "r") as fh:
        lines = fh.readlines()
        assert f" NETCDF FILEIN {function_tmpdir}/{gwf_name}.input.nc\n" in lines
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

    ds = xr.load_dataset(nc_fpth)
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


def test_write_ascii(function_tmpdir):
    sim_name = "sim"
    gwf_name = "gwf"
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=[gwf_name])
    dis = Dis(
        nlay=1,
        nrow=10,
        ncol=10,
        delr=1.0,
        delc=1.0,
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
    oc = Oc(parent=gwf)
    npf = Npf(parent=gwf)
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})

    sim.write()

    files = list(Path(function_tmpdir).glob("*"))
    file_names = [f.name for f in files]
    assert "mfsim.nam" in file_names
    assert f"{sim_name}.tdis" in file_names
    assert f"{gwf_name}.nam" in file_names
    assert f"{gwf_name}.dis" in file_names
    assert f"{gwf_name}.ic" in file_names
    assert f"{gwf_name}.oc" in file_names
    assert f"{gwf_name}.npf" in file_names
    assert f"{gwf_name}.chd" in file_names


def test_to_dict_fields():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
        "nper": time.nper,
        "nodes": grid.nnodes,
    }

    chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
    result = chd.to_dict()

    assert "head" in result
    assert result["head"][0, 0] == 1.0
    assert result["head"][0, 99] == 0.0

    npf = Npf(dims=dims, k=5.0)
    result = npf.to_dict()

    assert "filename" not in result
    assert "k" in result
    assert "icelltype" in result
    assert "k33" in result
    assert np.array_equal(result["k"], np.full(100, 5.0))


def test_to_dict_blocks():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
        "nper": time.nper,
        "nodes": grid.nnodes,
    }

    chd = Chd(
        dims=dims,
        print_flows=True,
        head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
    )
    result = chd.to_dict(blocks=True)

    assert "options" in result
    assert "period" in result
    assert "print_flows" in result["options"]
    assert result["options"]["print_flows"] is True
    assert "head" in result["period"]
    assert result["period"]["head"][0, 0] == 1.0
    assert result["period"]["head"][0, 99] == 0.0

    npf = Npf(dims=dims, save_flows=True, k=2.0)
    result = npf.to_dict(blocks=True)

    assert "options" in result
    assert "griddata" in result
    assert "save_flows" in result["options"]
    assert result["options"]["save_flows"] is True
    assert "k" in result["griddata"]
    assert np.array_equal(result["griddata"]["k"], np.full(100, 2.0))


def test_to_dict_on_component():
    dims = {
        "nper": 1,
        "nlay": 1,
        "nrow": 2,
        "ncol": 2,
        "nodes": 4,
    }
    dis = Dis(dims=dims)
    result = dis.to_dict()

    assert "filename" not in result
    assert "nlay" in result


def test_to_dict_on_context():
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=["gwf"])
    sim = Simulation(tdis=time, solutions={"ims": ims})

    result = sim.to_dict()

    assert "filename" not in result
    assert "workspace" not in result
    assert "tdis" in result


def test_to_dict_with_strict_excludes_fields_without_block_metadata():
    dims = {
        "nper": 1,
        "nlay": 1,
        "nrow": 2,
        "ncol": 2,
        "nodes": 4,
    }
    dis = Dis(dims=dims)
    result = dis.to_dict(strict=True)

    assert "nlay" in result
    assert "nrow" in result
    assert "ncol" in result
    assert "nodes" not in result


def test_tdis_from_timestamps():
    tdis = Tdis.from_timestamps(["2020-01-01", "2020-01-05", "2020-01-15"], nstp=5, tsmult=1.2)

    assert tdis.nper == 2
    assert tdis.time_units == "days"
    assert tdis.start_date_time == pd.Timestamp("2020-01-01").to_pydatetime()
    np.testing.assert_array_equal(tdis.perlen, [4.0, 10.0])
    np.testing.assert_array_equal(tdis.nstp, [5, 5])
    np.testing.assert_array_equal(tdis.tsmult, [1.2, 1.2])


def test_to_xarray_on_component():
    tdis = Tdis.from_timestamps(["2020-01-01", "2020-01-05", "2020-01-15"], nstp=5, tsmult=1.2)
    ds = tdis.to_xarray()
    assert isinstance(ds, xr.Dataset)
    assert isinstance(ds.kper, xr.DataArray)
    assert np.array_equal(ds.kper, [0, 1])
    assert ds.attrs["start_date_time"] == pd.Timestamp("2020-01-01")


def test_to_xarray_on_context(function_tmpdir):
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=["gwf"])
    sim = Simulation(tdis=time, solutions={"ims": ims}, workspace=function_tmpdir)
    dt = sim.to_xarray()
    assert isinstance(dt, xr.DataTree)
    assert isinstance(dt.kper, xr.DataArray)
    assert np.array_equal(dt.kper, [0])
    assert dt.attrs["filename"] == "mfsim.nam"
    assert dt.attrs["workspace"] == Path(function_tmpdir)


def test_grid_coordinate_indexing():
    """Test that grid data can be indexed using x, y, z world coordinates."""
    # Create a simple structured grid with uniform elevation
    grid = StructuredGrid(
        nlay=3,
        nrow=10,
        ncol=10,
        delr=100.0,  # 100 m cell width
        delc=100.0,  # 100 m cell height
        top=100.0,
        botm=[0.0, -50.0, -100.0],
    )

    # Test that world coordinates are present
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords
    assert "z" in grid.dataset.coords

    # Test coordinate shapes
    # x and y are 1D (one value per column/row)
    # z is 3D (one value per cell, since each cell can have different elevation)
    assert grid.dataset.coords["x"].shape == (10,)  # 1D: ncol
    assert grid.dataset.coords["y"].shape == (10,)  # 1D: nrow
    assert grid.dataset.coords["z"].shape == (3, 10, 10)  # 3D: (nlay, nrow, ncol)

    # Test coordinate values
    # X coordinates should be cell centers: 50, 150, 250, ..., 950
    expected_x = np.array([50.0, 150.0, 250.0, 350.0, 450.0, 550.0, 650.0, 750.0, 850.0, 950.0])
    np.testing.assert_allclose(grid.dataset.coords["x"].values, expected_x)

    # Y coordinates should be cell centers from top: 950, 850, 750, ..., 50
    expected_y = np.array([950.0, 850.0, 750.0, 650.0, 550.0, 450.0, 350.0, 250.0, 150.0, 50.0])
    np.testing.assert_allclose(grid.dataset.coords["y"].values, expected_y)

    # Z coordinates should be cell centers (3D array)
    # With uniform top=100 and botm=[0, -50, -100], all cells in each layer have same z
    # Layer 0: (100 + 0) / 2 = 50
    # Layer 1: (0 + (-50)) / 2 = -25
    # Layer 2: (-50 + (-100)) / 2 = -75
    expected_z_layer0 = np.full((10, 10), 50.0)
    expected_z_layer1 = np.full((10, 10), -25.0)
    expected_z_layer2 = np.full((10, 10), -75.0)
    np.testing.assert_allclose(grid.dataset.coords["z"].values[0], expected_z_layer0)
    np.testing.assert_allclose(grid.dataset.coords["z"].values[1], expected_z_layer1)
    np.testing.assert_allclose(grid.dataset.coords["z"].values[2], expected_z_layer2)

    # Test coordinate-based selection using nearest
    # Select near x=250 (should get col=2, which has x=250)
    botm_at_x250 = grid.botm.sel(x=250.0, method="nearest")
    assert botm_at_x250.shape == (3, 10)  # (nlay, nrow)

    # Select near y=650 (should get row=3, which has y=650)
    botm_at_y650 = grid.botm.sel(y=650.0, method="nearest")
    assert botm_at_y650.shape == (3, 10)  # (nlay, ncol)

    # Test combined x,y selection
    botm_at_point = grid.botm.sel(x=250.0, y=650.0, method="nearest")
    assert botm_at_point.shape == (3,)  # Just the layer dimension remains

    # Verify the value makes sense: col=2, row=3 -> botm[0,3,2] = 0.0
    expected_botm = np.array([0.0, -50.0, -100.0])
    np.testing.assert_allclose(botm_at_point.values, expected_botm)


def test_grid_coordinate_indexing_variable_topography():
    """Test that z coordinates properly handle variable topography."""
    # Create a grid with variable topography using arrays
    nlay, nrow, ncol = 3, 10, 10

    # Create a sloping top surface (higher in the west, lower in the east)
    top = np.linspace(100.0, 50.0, ncol)  # Varies with column
    top = np.tile(top, (nrow, 1))  # Same for all rows

    # Create layer bottoms with uniform thickness
    botm = np.zeros((nlay, nrow, ncol))
    botm[0] = top - 50.0  # Layer 0: 50m thick
    botm[1] = botm[0] - 50.0  # Layer 1: 50m thick
    botm[2] = botm[1] - 50.0  # Layer 2: 50m thick

    # Need to provide delr/delc as arrays when using 2D/3D top/botm
    delr = np.full(ncol, 100.0)
    delc = np.full(nrow, 100.0)

    grid = StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=delr,
        delc=delc,
        top=top,
        botm=botm,
    )

    # Test that world coordinates are present and have correct shapes
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords
    assert "z" in grid.dataset.coords
    assert grid.dataset.coords["x"].shape == (10,)
    assert grid.dataset.coords["y"].shape == (10,)
    assert grid.dataset.coords["z"].shape == (3, 10, 10)

    # Verify z coordinates vary with column (due to sloping top)
    # Column 0: top=100, layer 0 center = (100 + 50) / 2 = 75
    # Column 9: top=50, layer 0 center = (50 + 0) / 2 = 25
    np.testing.assert_allclose(grid.dataset.coords["z"].values[0, 0, 0], 75.0, rtol=1e-5)
    np.testing.assert_allclose(grid.dataset.coords["z"].values[0, 0, 9], 25.0, rtol=1e-5)

    # Layer 1 centers
    # Column 0: (50 + 0) / 2 = 25
    # Column 9: (0 + (-50)) / 2 = -25
    np.testing.assert_allclose(grid.dataset.coords["z"].values[1, 0, 0], 25.0, rtol=1e-5)
    np.testing.assert_allclose(grid.dataset.coords["z"].values[1, 0, 9], -25.0, rtol=1e-5)

    # Verify z is constant across rows (since top only varies with column)
    for row in range(nrow):
        np.testing.assert_allclose(
            grid.dataset.coords["z"].values[:, row, :],
            grid.dataset.coords["z"].values[:, 0, :],
            rtol=1e-10,
        )


def test_grid_coordinates_match_legacy():
    """Test that our x, y, z coordinates match the legacy grid's cell centers."""
    # Create a grid with variable topography to thoroughly test z coordinates
    nlay, nrow, ncol = 3, 10, 10

    delr = np.full(ncol, 100.0)
    delc = np.full(nrow, 100.0)
    top = np.linspace(100.0, 50.0, ncol)
    top = np.tile(top, (nrow, 1))
    botm = np.zeros((nlay, nrow, ncol))
    botm[0] = top - 50.0
    botm[1] = botm[0] - 50.0
    botm[2] = botm[1] - 50.0

    grid = StructuredGrid(delr=delr, delc=delc, top=top, botm=botm)

    # Get legacy cell centers
    legacy_xyz = grid.xyzcellcenters
    legacy_x = legacy_xyz[0]  # Shape: (nrow, ncol)
    legacy_y = legacy_xyz[1]  # Shape: (nrow, ncol)
    legacy_z = legacy_xyz[2]  # Shape: (nlay, nrow, ncol)

    # Get our coordinates
    our_x = grid.dataset.coords["x"].values  # Shape: (ncol,)
    our_y = grid.dataset.coords["y"].values  # Shape: (nrow,)
    our_z = grid.dataset.coords["z"].values  # Shape: (nlay, nrow, ncol)

    # Compare x coordinates
    # Legacy x is 2D (nrow, ncol) where each row should have identical x values
    # Our x is 1D (ncol,) - the unique x values
    for row in range(nrow):
        np.testing.assert_allclose(
            legacy_x[row, :], our_x, rtol=1e-10, err_msg=f"X coordinates don't match for row {row}"
        )

    # Compare y coordinates
    # Legacy y is 2D (nrow, ncol) where each column should have identical y values
    # Our y is 1D (nrow,) - the unique y values
    for col in range(ncol):
        np.testing.assert_allclose(
            legacy_y[:, col],
            our_y,
            rtol=1e-10,
            err_msg=f"Y coordinates don't match for column {col}",
        )

    # Compare z coordinates
    # Both are 3D (nlay, nrow, ncol) - direct comparison
    np.testing.assert_allclose(
        legacy_z, our_z, rtol=1e-10, err_msg="Z coordinates don't match legacy zcellcenters"
    )


def test_grid_coordinate_indexing_in_dis():
    """Test that Dis package data also has coordinate indexing."""
    time = Time(perlen=[1.0], nstp=[1])
    # Dis expects properly-shaped arrays, not scalars
    nlay, nrow, ncol = 2, 5, 5
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=np.full(ncol, 10.0),
        delc=np.full(nrow, 10.0),
        top=np.full((nrow, ncol), 10.0),
        botm=np.array([np.full((nrow, ncol), 0.0), np.full((nrow, ncol), -10.0)]),
    )

    # Convert to grid to access coordinates
    grid = dis.to_grid()

    # Test that coordinates are available
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords
    assert "z" in grid.dataset.coords

    # Test coordinate-based selection on botm
    # X coordinates: 5, 15, 25, 35, 45
    botm_near_x15 = grid.botm.sel(x=15.0, method="nearest")
    assert botm_near_x15.shape == (2, 5)  # (nlay, nrow)

    # Y coordinates: 45, 35, 25, 15, 5
    botm_near_y25 = grid.botm.sel(y=25.0, method="nearest")
    assert botm_near_y25.shape == (2, 5)  # (nlay, ncol)


def test_grid_dimensions_only():
    """Test grid creation with only dimensions (no spatial data)."""
    grid = StructuredGrid(nlay=3, nrow=5, ncol=5)

    # Should have index-based coordinates
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords
    assert "z" in grid.dataset.coords
    assert "k" in grid.dataset.coords
    assert "i" in grid.dataset.coords
    assert "j" in grid.dataset.coords

    # Check shapes
    assert grid.dataset.coords["x"].shape == (5,)
    assert grid.dataset.coords["y"].shape == (5,)
    assert grid.dataset.coords["z"].shape == (3, 5, 5)

    # Check that x, y, z are index-based (0, 1, 2, ...)
    # When no spatial data is provided, coordinates are simple indices
    np.testing.assert_array_equal(grid.dataset.coords["x"].values, [0.0, 1.0, 2.0, 3.0, 4.0])
    np.testing.assert_array_equal(grid.dataset.coords["y"].values, [0.0, 1.0, 2.0, 3.0, 4.0])
    np.testing.assert_array_equal(grid.dataset.coords["z"].values[0, :, :], np.full((5, 5), 0.0))
    np.testing.assert_array_equal(grid.dataset.coords["z"].values[1, :, :], np.full((5, 5), 1.0))
    np.testing.assert_array_equal(grid.dataset.coords["z"].values[2, :, :], np.full((5, 5), 2.0))


def test_grid_horizontal_spacing_only():
    """Test grid with horizontal spacing but default vertical structure."""
    grid = StructuredGrid(nlay=3, nrow=5, ncol=5, delr=100.0, delc=50.0)

    # Should have real x, y coordinates based on delr/delc
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords

    # X coordinates should be cell centers based on delr
    expected_x = [50.0, 150.0, 250.0, 350.0, 450.0]
    np.testing.assert_allclose(grid.dataset.coords["x"].values, expected_x)

    # Y coordinates should be cell centers based on delc
    expected_y = [225.0, 175.0, 125.0, 75.0, 25.0]
    np.testing.assert_allclose(grid.dataset.coords["y"].values, expected_y)

    # Z should still be index-based since no top/botm provided
    assert grid.dataset.coords["z"].shape == (3, 5, 5)


def test_grid_variable_spacing():
    """Test grid with variable delr and delc arrays."""
    nlay, nrow, ncol = 2, 4, 5

    # Variable column widths (narrower in middle)
    delr = np.array([100.0, 50.0, 50.0, 50.0, 100.0])
    # Variable row widths (narrower in middle)
    delc = np.array([80.0, 60.0, 60.0, 80.0])

    grid = StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=delr,
        delc=delc,
        top=10.0,
        botm=[0.0, -10.0],
    )

    # Check x coordinates (cell centers)
    # Column 0: 0 to 100, center = 50
    # Column 1: 100 to 150, center = 125
    # Column 2: 150 to 200, center = 175
    # Column 3: 200 to 250, center = 225
    # Column 4: 250 to 350, center = 300
    expected_x = [50.0, 125.0, 175.0, 225.0, 300.0]
    np.testing.assert_allclose(grid.dataset.coords["x"].values, expected_x)

    # Check y coordinates (cell centers, from top)
    # Row 0: 0 to 80, center = 40 (but y is from top, so 280-40=240)
    # Row 1: 80 to 140, center = 110 (from top: 280-110=170)
    # Row 2: 140 to 200, center = 170 (from top: 280-170=110)
    # Row 3: 200 to 280, center = 240 (from top: 280-240=40)
    expected_y = [240.0, 170.0, 110.0, 40.0]
    np.testing.assert_allclose(grid.dataset.coords["y"].values, expected_y)


def test_grid_uniform_factory():
    """Test the uniform() factory method."""
    grid = StructuredGrid.uniform(
        nlay=3, nrow=10, ncol=10, delr=100.0, delc=50.0, top=20.0, thickness=5.0
    )

    # Check dimensions
    assert grid.nlay == 3
    assert grid.nrow == 10
    assert grid.ncol == 10

    # Check that top is correct
    assert grid.dataset["top"].shape == (10, 10)
    np.testing.assert_allclose(grid.dataset["top"].values, np.full((10, 10), 20.0))

    # Check that botm is correctly computed from thickness
    # Layer 0: top - thickness = 20 - 5 = 15
    # Layer 1: 15 - 5 = 10
    # Layer 2: 10 - 5 = 5
    assert grid.dataset["botm"].shape == (3, 10, 10)
    np.testing.assert_allclose(grid.dataset["botm"].values[0], np.full((10, 10), 15.0))
    np.testing.assert_allclose(grid.dataset["botm"].values[1], np.full((10, 10), 10.0))
    np.testing.assert_allclose(grid.dataset["botm"].values[2], np.full((10, 10), 5.0))

    # Check z coordinates (cell centers)
    # Layer 0: (20 + 15) / 2 = 17.5
    # Layer 1: (15 + 10) / 2 = 12.5
    # Layer 2: (10 + 5) / 2 = 7.5
    np.testing.assert_allclose(grid.dataset.coords["z"].values[0], np.full((10, 10), 17.5))
    np.testing.assert_allclose(grid.dataset.coords["z"].values[1], np.full((10, 10), 12.5))
    np.testing.assert_allclose(grid.dataset.coords["z"].values[2], np.full((10, 10), 7.5))

    # Check x, y coordinates
    assert grid.dataset.coords["x"].shape == (10,)
    assert grid.dataset.coords["y"].shape == (10,)
    # X: 50, 150, 250, ..., 950
    expected_x = np.arange(10) * 100.0 + 50.0
    np.testing.assert_allclose(grid.dataset.coords["x"].values, expected_x)


def test_grid_from_dis_factory():
    """Test the from_dis() factory method."""
    nlay, nrow, ncol = 2, 5, 5
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=np.full(ncol, 10.0),
        delc=np.full(nrow, 10.0),
        top=np.full((nrow, ncol), 10.0),
        botm=np.array([np.full((nrow, ncol), 0.0), np.full((nrow, ncol), -10.0)]),
    )

    # Use the classmethod factory
    grid = StructuredGrid.from_dis(dis)

    # Check that dimensions match
    assert grid.nlay == nlay
    assert grid.nrow == nrow
    assert grid.ncol == ncol

    # Check that spatial data matches
    assert "x" in grid.dataset.coords
    assert "y" in grid.dataset.coords
    assert "z" in grid.dataset.coords

    # Check z coordinates are cell centers
    # Layer 0: (10 + 0) / 2 = 5
    # Layer 1: (0 + (-10)) / 2 = -5
    np.testing.assert_allclose(grid.dataset.coords["z"].values[0], np.full((5, 5), 5.0))
    np.testing.assert_allclose(grid.dataset.coords["z"].values[1], np.full((5, 5), -5.0))

    # Check that coordinate-based selection works
    botm_near_x15 = grid.botm.sel(x=15.0, method="nearest")
    assert botm_near_x15.shape == (2, 5)


def test_grid_with_idomain():
    """Test grid with idomain array."""
    nlay, nrow, ncol = 2, 5, 5

    # Create idomain with some inactive cells
    idomain = np.ones((nlay, nrow, ncol), dtype=int)
    idomain[0, 0, 0] = 0  # Inactive
    idomain[1, 2, 2] = -1  # Vertical pass-through

    grid = StructuredGrid(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=10.0,
        delc=10.0,
        top=10.0,
        botm=[0.0, -10.0],
        idomain=idomain,
    )

    # Check that idomain is in the dataset
    assert "idomain" in grid.dataset
    assert grid.dataset["idomain"].shape == (nlay, nrow, ncol)

    # Verify specific values
    assert grid.dataset["idomain"].values[0, 0, 0] == 0
    assert grid.dataset["idomain"].values[1, 2, 2] == -1
    assert grid.dataset["idomain"].values[0, 1, 1] == 1
