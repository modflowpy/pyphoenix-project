import numpy as np
import pytest
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.interface.flopy3 import Flopy3Model, Flopy3Package


def test_flopy3_model():
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

    gwf3 = Flopy3Model(model=gwf, modeltime=time, ims=ims)
    assert isinstance(gwf3, ModelInterface)
    assert gwf3.modelgrid
    assert gwf3.modelgrid.nlay == gwf.dis.nlay
    assert gwf3.modelgrid.nrow == gwf.dis.nrow
    assert gwf3.modelgrid.ncol == gwf.dis.ncol
    assert gwf3.modelgrid.nnodes == grid.nnodes

    assert gwf3.solver_tols == (ims.inner_hclose, ims.inner_rclose)
    assert np.all(
        np.equal(gwf3.laytyp, np.zeros(gwf3.modelgrid.nnodes, dtype=int))
    )

    # model packages
    assert gwf3.get_package_list() == pnames
    for i, p in enumerate(gwf3.packagelist):
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

    gwf3.plot(filename_base="modelif")


def test_flopy3_package():
    from flopy.mbase import ModelInterface
    from flopy.pakbase import PackageInterface

    time = ModelTime(perlen=[1.0], nstp=[1], tsmult=[1.0])
    grid = StructuredGrid(
        nlay=1,
        nrow=10,
        ncol=10,
        xoff=0.0,
        yoff=0.0,
        angrot=0.0,
        delr=np.array([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]),
        delc=np.array([2.9, 2.8, 2.7, 2.6, 2.5, 2.4, 2.3, 2.2, 2.1, 2.0]),
        top=np.array(
            [
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
                [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
            ]
        ),
        botm=np.array(
            [
                [
                    [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    [1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0],
                ]
            ]
        ),
    )

    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
    }

    dis = Dis(**dims)
    dis.nogrb = True
    dis.xorigin = 0.0
    dis.yorigin = 0.0
    dis.delr = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    dis.delc = [2.9, 2.8, 2.7, 2.6, 2.5, 2.4, 2.3, 2.2, 2.1, 2.0]
    dis.top = [
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
    ]
    dis.botm = [
        [
            [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [1.9, 1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0],
        ]
    ]

    dims["nper"] = time.nper
    dims["nnodes"] = grid.nnodes

    gwf = Gwf(
        dis=dis,
        dims=dims,
    )

    # gwf3 is needed because "parent" property needs
    # to return it for flopy3 based plotting (below)
    gwf3 = Flopy3Model(model=gwf, modeltime=time)
    dis3 = Flopy3Package(package=dis, model=gwf3, modeltime=time)
    assert isinstance(gwf3, ModelInterface)
    assert isinstance(dis3, PackageInterface)
    assert gwf3.modelgrid.nlay == grid.nlay
    assert gwf3.modelgrid.nrow == grid.nrow
    assert gwf3.modelgrid.ncol == grid.ncol
    assert gwf3.modelgrid.nnodes == grid.nnodes
    assert gwf3.modelgrid.angrot == grid.angrot
    assert np.all(np.equal(gwf3.modelgrid.delr, grid.delr))
    assert np.all(np.equal(gwf3.modelgrid.delc, grid.delc))
    assert np.all(np.equal(gwf3.modelgrid.top, grid.top))
    assert np.all(np.equal(gwf3.modelgrid.botm, grid.botm))

    # model packages
    assert dis3.name == "dis"
    assert dis3.package_type == "DIS"
    assert not dis3.has_stress_period_data

    # package data
    data_list = [
        "nogrb",
        "xorigin",
        "yorigin",
        "export_array_netcdf",
        "delr",
        "delc",
        "top",
        "botm",
        "idomain",
    ]
    data = {
        "delr": grid.delr,
        "delc": grid.delc,
        "top": grid.top,
        "botm": grid.botm,
    }
    dlist = [d.name for d in dis3.data_list]
    assert dlist == data_list

    for k, v in data.items():
        for di in dis3.data_list:
            if di.name == k:
                assert np.all(np.equal(di.array, v))

    dis3.plot(filename_base="dis3")


def norun_test_cbd_small():
# def test_flopy3_cbd_small():
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
    gwf3 = Flopy3Model(model=gwf, modelgrid=cbd_small, modeltime=time)
    gwf3.plot(filename_base="cbd_small")


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
    gwf3 = Flopy3Model(model=gwf, modeltime=time)
    gwf3.plot(filename_base="grid2")

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
def test_flopy3_mgrid2():
    lx = 5.0
    lz = 1.0
    nlay = 1
    nrow = 1
    ncol = 5
    delc = 1.0
    delr = lx / ncol
    delz = lz / nlay
    # adelc = np.full((ncol, nrow), delc)
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


@pytest.mark.xfail(
    reason=(
        "demonstrate why wrapping array values "
        "with DataArray is necessary on set"
    )
)
def test_fails():
    from xarray import Dataset, DataTree
    from xarray.indexes import PandasIndex

    data = Dataset(
        {
            "delr": ("ncol", [1.0]),
            "delc": (
                "nrow",
                [
                    1.0,
                    1.0,
                    1.0,
                ],
            ),
        },
        coords={
            "col": ("ncol", [0]),
            "row": ("nrow", [0, 1, 2]),
        },
    )
    data.set_xindex("col", PandasIndex)
    data.set_xindex("row", PandasIndex)
    tree = DataTree(data)
    tree["delr"] = [2.0]
    tree["delc"] = [2.0, 2.0, 2.0]


def test_succeeds():
    from xarray import DataArray, Dataset, DataTree
    from xarray.indexes import PandasIndex

    data = Dataset(
        {
            "delr": ("ncol", [1.0]),
            "delc": (
                "nrow",
                [
                    1.0,
                    1.0,
                    1.0,
                ],
            ),
        },
        coords={
            "col": ("ncol", [0]),
            "row": ("nrow", [0, 1, 2]),
        },
    )
    data.set_xindex("col", PandasIndex)
    data.set_xindex("row", PandasIndex)
    tree = DataTree(data)
    tree["delr"] = DataArray([2.0], dims="ncol")
    tree["delc"] = DataArray([2.0, 2.0, 2.0], dims="nrow")
