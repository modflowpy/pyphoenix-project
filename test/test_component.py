import numpy as np
import pytest
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime
from xarray import DataTree

from flopy4.mf6.component import COMPONENTS
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.interface.flopy3 import Flopy3Model
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis


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


def test_init_gwf_top_down_misaligned():
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }
    gwf = Gwf()
    with pytest.raises(
        ValueError, match=r"group '/dis' is not aligned with its parents"
    ):
        Dis(parent=gwf, **dims)

    # passing dims explicitly to gwf doesn't work either.
    # one MUST create the component declaring dims first.
    with pytest.raises(
        ValueError, match=r"group '/dis' is not aligned with its parents"
    ):
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
    assert gwf.dis is dis
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
    )


def test_init_big_sim():
    # if size over threshold, arrays should be sparse
    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=100, ncol=100)
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
    chd = Chd(dims=dims, head={"*": {(0, 0, 0): 1.0, (0, 99, 99): 0.0}})
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
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.chd[0] is chd
    assert np.array_equal(sim.models["gwf"].npf.k, np.ones(10000))
    assert np.array_equal(sim.models["gwf"].npf.data.k, np.ones(10000))
    assert chd.head[0, 0] == 1.0
    assert chd.head[0, 9999] == 0.0
    assert np.array_equal(
        chd.head[0, 1:9999].data.todense(), np.full((9998,), FILL_DNODATA)
    )
    assert np.array_equal(
        chd.head.data.todense(), chd.data.head.data.todense()
    )
    assert np.array_equal(
        chd.head.data.todense(),
        sim.models["gwf"].chd[0].data.head.data.todense(),
    )


def test_modelif():
    from flopy.mbase import ModelInterface
    from flopy.pakbase import PackageInterface

    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)

    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }

    dis = Dis(**dims)
    dis.nogrb = True
    dis.xorigin = 0.0
    dis.yorigin = 0.0

    dims["nper"] = time.nper
    dims["nnodes"] = grid.nnodes

    # ims = Ims(dims=dims)
    ims = Ims()
    ims.inner_hclose = 1e-6
    ims.inner_rclose = 0.1000000
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

    pnames = ["dis", "ic", "oc", "npf", "chd0"]
    ptypes = ["DIS", "IC", "OC", "NPF", "CHD"]

    gwfif = Flopy3Model(model=gwf, modeltime=time, ims=ims)
    assert isinstance(gwfif, ModelInterface)
    assert gwfif.modelgrid
    assert gwfif.modelgrid.nlay == gwf.dis.nlay
    assert gwfif.modelgrid.nrow == gwf.dis.nrow
    assert gwfif.modelgrid.ncol == gwf.dis.ncol
    assert gwfif.modelgrid.nnodes == grid.nnodes

    assert gwfif.solver_tols == (ims.inner_hclose, ims.inner_rclose)
    assert np.all(
        np.equal(gwfif.laytyp, np.zeros(gwfif.modelgrid.nnodes, dtype=int))
    )

    # model packages
    assert gwfif.get_package_list() == pnames
    for i, p in enumerate(gwfif.packagelist):
        assert isinstance(p, PackageInterface)
        assert p.name == pnames[i]
        assert p.package_type == ptypes[i]
        # assert p.parent == "gwf"
        # TODO oc?
        if p.name == "chd0" or p.name == "oc":
            assert p.has_stress_period_data
        else:
            assert not p.has_stress_period_data

        # package data
        dlist = [d.name for d in p.data_list]
        print(f"PACKAGE {p.name} data list => {dlist}")
        for d in p.data_list:
            print(f"{p.name} data={d.name}")
            # assert d.model == "gwf"
            print(f"dtype: {d.dtype}")
            print(f"data_type: {d.data_type}")
            print(f"array: {d.array}\n")

    kwargs = {}
    kwargs["filename_base"] = "modelif"

    # gwfif.plot(**kwargs)
    gwfif.plot(filename_base="modelif")


def norun_test_cbd_small():
    import sys

    sys.path.append("/home/mjreno/.clone/usgs/flopy/autotest")
    from test_grid_cases import GridCases

    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])

    cbd_small = GridCases.structured_cbd_small()
    dims = {
        "nlay": cbd_small.nlay,
        "nrow": cbd_small.nrow,
        "ncol": cbd_small.ncol,
    }
    dis = Dis(**dims)
    dims["nper"] = time.nper
    dims["nnodes"] = cbd_small.nnodes
    gwf = Gwf(
        dis=dis,
        dims=dims,
    )
    gwfif = Flopy3Model(model=gwf, modelgrid=cbd_small, modeltime=time)
    gwfif.plot(filename_base="cbd_small")


def norun_test_grid2():
    lx = 5.0
    lz = 1.0
    nlay = 1
    nrow = 1
    ncol = 5
    nper = 1
    delc = 1.0
    delr = lx / ncol
    delz = lz / nlay
    adelc = np.full((nrow), delc)
    adelr = np.full((ncol), delr)
    top = [0.0, 0.0, -0.90, 0.0, 0.0]
    botm = list(top - np.arange(delz, nlay * delz + delz, delz))
    botm[2] = -1.0
    idomain = np.full((nlay, nrow, ncol), 1)

    dims = {
        "nlay": nlay,
        "nrow": nrow,
        "ncol": ncol,
    }

    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    dis = Dis(**dims)
    dis.delr = adelr
    dis.delc = adelc
    dis.top = top
    dis.botm = botm
    # dis.idomain = idomain
    dims["nper"] = time.nper
    dims["nnodes"] = nlay * nrow * ncol
    gwf = Gwf(
        dis=dis,
        dims=dims,
    )
    gwfif = Flopy3Model(model=gwf, modeltime=time)
    gwfif.plot(filename_base="grid2")

    # dis = flopy.mf6.ModflowGwfdis(
    #    gwf,
    #    nlay=nlay,
    #    nrow=nrow,
    #    ncol=ncol,
    #    delr=delr,
    #    delc=delc,
    #    top=top,
    #    botm=botm,
    #    idomain=idomain,
    # )


# demo failed case
def test_mgrid2():
    lx = 5.0
    lz = 1.0
    nlay = 1
    nrow = 1
    ncol = 5
    delc = 1.0
    delr = lx / ncol
    delz = lz / nlay
    adelc = np.full((nrow), delc)
    adelr = np.full((ncol), delr)

    dims = {
        "nlay": nlay,
        "nrow": nrow,
        "ncol": ncol,
    }

    dis = Dis(**dims)

    print(dis.delr.dims)  # prints ('ncol',)
    print(dis.delc.dims)  # prints ('nrow',)

    dis.delr = adelr  # succeeds
    dis.delc = adelc  # fails
