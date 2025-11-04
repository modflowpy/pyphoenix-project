"""Test basic MF6 component behaviors like initialization, modification, access."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from flopy.discretization import StructuredGrid
from xarray import DataTree

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.constants import FILL_DNODATA, LENBOUNDNAME
from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utils.time import Time


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
    grid = StructuredGrid(nlay=1, nrow=100, ncol=100)
    sim = Simulation(tdis=time)
    gwf = Gwf(parent=sim, dis=grid)
    ic = Ic(parent=gwf)
    oc = Oc(parent=gwf)
    npf = Npf(parent=gwf)
    chd = Chd(parent=gwf, head={"*": {(0, 0, 0): 1.0, (0, 99, 99): 0.0}})

    assert sim.models["gwf"] is gwf
    assert isinstance(sim.data, DataTree)
    assert sim.data.gwf is gwf.data
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(sim.models["gwf"].npf.k, np.ones(10000))
    assert np.array_equal(sim.models["gwf"].npf.data.k, np.ones(10000))
    assert chd.head[0, 0].item() == 1.0
    assert chd.head[0, 9999].item() == 0.0
    assert np.array_equal(chd.head[0, 1:9999].data.todense(), np.full((9998,), FILL_DNODATA))
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
    assert isinstance(ds.per, xr.DataArray)
    assert np.array_equal(ds.per, [0, 1])
    assert ds.attrs["start_date_time"] == pd.Timestamp("2020-01-01")


def test_to_xarray_on_context(function_tmpdir):
    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0])
    ims = Ims(models=["gwf"])
    sim = Simulation(tdis=time, solutions={"ims": ims}, workspace=function_tmpdir)
    dt = sim.to_xarray()
    assert isinstance(dt, xr.DataTree)
    assert isinstance(dt.per, xr.DataArray)
    assert np.array_equal(dt.per, [0])
    assert dt.attrs["filename"] == "mfsim.nam"
    assert dt.attrs["workspace"] == Path(function_tmpdir)
