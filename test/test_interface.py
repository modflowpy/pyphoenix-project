import numpy as np
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.interface.flopy3 import Flopy3Model


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
    # def test_cbd_small():
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
