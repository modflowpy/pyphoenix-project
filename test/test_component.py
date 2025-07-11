from pathlib import Path

import numpy as np
import pytest
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime
from modflow_devtools.dfn import Sln
from xarray import DataTree

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.modflow.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.modflow.ims import Ims
from flopy4.mf6.modflow.simulation import Simulation
from flopy4.mf6.modflow.tdis import Tdis


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
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=2, ncol=2)
    dims = {
        "nper": time.nper,
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
        "nnodes": grid.nnodes,
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
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
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
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }
    dis = Dis(**dims)
    dims["nper"] = time.nper
    dims["nnodes"] = grid.nnodes
    ic = Ic(dims=dims)
    oc = Oc(dims=dims)
    npf = Npf(dims=dims)
    chd = Chd(dims=dims, head={"*": {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
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
    assert np.array_equal(chd.head[0, 1:99].data, np.full((98,), FILL_DNODATA))
    assert np.array_equal(chd.head.data, chd.data.head.data)
    assert np.array_equal(
        chd.head.data,
        sim.models["gwf"].chd[0].data.head.data,
        equal_nan=True,
    )


def test_init_big_sim():
    # if size over threshold, arrays should be sparse
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
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
    assert dfn["name"] == "gwf"
    assert not dfn["advanced"]
    assert not dfn["multi"]
    assert dfn["ref"] is None
    assert dfn["sln"] is None
    assert "save_flows" in set(dfn["options"].keys())


def test_chd_dfn():
    chd = Chd(strict=False)
    dfn = chd.dfn
    assert dfn["name"] == "chd"
    assert not dfn["advanced"]
    assert dfn["multi"]
    assert dfn["ref"] is None
    assert dfn["sln"] is None
    assert "print_input" in set(dfn["options"].keys())
    assert "head" in set(dfn["period"].keys())


def test_ims_dfn():
    ims = Ims(strict=False)
    dfn = ims.dfn
    assert dfn["name"] == "ims"
    assert not dfn["advanced"]
    assert not dfn["multi"]
    assert dfn["ref"] is None
    assert dfn["sln"] == Sln(abbr="ims", pattern="*")
    assert "complexity" in set(dfn["options"].keys())
    assert "inner_maximum" in set(dfn["linear"].keys())


def test_write_ascii(function_tmpdir):
    sim_name = "sim"
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    sim = Simulation(tdis=time, workspace=function_tmpdir, name=sim_name)
    gwf_name = "gwf"
    gwf = Gwf(parent=sim, dis=grid, name=gwf_name)
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
