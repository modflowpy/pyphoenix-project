import numpy as np
import pytest
import xarray as xr
import xugrid as xu

from flopy4.mf6.gwf import Chd, Dis, Disv, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.cbc_reader import open_cbc
from flopy4.mf6.utils.heads_reader import open_hds
from flopy4.mf6.utils.time import Time


@pytest.fixture
def dis_model_output(function_tmpdir):
    sim_name = "dis_test"
    gwf_name = "gwf_dis"

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")
    ims = Ims(filename=f"{sim_name}.ims", models=[gwf_name], print_option="summary")
    sim = Simulation(tdis=time, workspace=function_tmpdir, name=sim_name, solutions={"ims": ims})

    nlay, nrow, ncol = 2, 3, 4
    botm = np.stack([np.full((nrow, ncol), 0.0), np.full((nrow, ncol), -10.0)])
    dis = Dis(
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        delr=10.0,
        delc=10.0,
        top=10.0,
        botm=botm,
        idomain=1,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)
    Ic(parent=gwf, strt=5.0)
    Npf(parent=gwf, k=1.0, icelltype=0)
    Chd(parent=gwf, print_flows=True, head={0: {(0, 0): 10.0, (0, ncol - 1): 0.0}})
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )

    sim.write()
    sim.run()

    base_path = function_tmpdir
    hds_path = function_tmpdir / f"{gwf_name}.hds"
    cbc_path = function_tmpdir / f"{gwf_name}.cbc"
    grb_path = function_tmpdir / f"{gwf_name}.dis.grb"

    assert hds_path.is_file(), f"HDS file not found: {hds_path}"
    assert cbc_path.is_file(), f"CBC file not found: {cbc_path}"
    assert grb_path.is_file(), f"GRB file not found: {grb_path}"

    return {
        "base": base_path,
        "hds": hds_path,
        "cbc": cbc_path,
        "grb": grb_path,
        "nlay": nlay,
        "nrow": nrow,
        "ncol": ncol,
    }


@pytest.fixture
def disv_model_output(function_tmpdir):
    sim_name = "disv_test"
    gwf_name = "gwf_disv"

    time = Time(perlen=[1.0], nstp=[1], tsmult=[1.0], time_units="days")
    ims = Ims(filename=f"{sim_name}.ims", models=[gwf_name], print_option="summary")
    sim = Simulation(tdis=time, workspace=function_tmpdir, name=sim_name, solutions={"ims": ims})

    nlay = 2
    ncpl = 9
    nvert = 16

    top = np.ones(ncpl, dtype=float) * 10.0
    botm = np.stack([np.full(ncpl, 0.0), np.full(ncpl, -10.0)])

    # 3x3 grid of quads
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
    for n in range(ncpl):
        cell2ddata.append(
            Disv.Cell2dRecord(
                n,
                float((n % 3) * 10 + 5),
                float(25 - (n // 3) * 10),
                4,
                tuple(cells[n]),
            )
        )

    # 4x4 grid of vertices (16 total)
    xv = np.array([float(i * 10) for i in range(4)] * 4)
    yv = np.array([float(30 - j * 10) for j in range(4) for _ in range(4)])

    disv = Disv(
        nlay=nlay,
        ncpl=ncpl,
        nvert=nvert,
        top=top,
        botm=botm,
        idomain=1,
        iv=np.arange(nvert, dtype=int),
        xv=xv,
        yv=yv,
        cell2ddata=cell2ddata,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=disv, name=gwf_name)
    Ic(parent=gwf, strt=5.0)
    Npf(parent=gwf, k=1.0, icelltype=0)
    Chd(parent=gwf, print_flows=True, head={0: {(0, 0): 10.0, (0, 8): 0.0}})
    Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        save_head=["last"],
        save_budget=["last"],
    )

    sim.write()
    sim.run()

    base_path = function_tmpdir
    hds_path = function_tmpdir / f"{gwf_name}.hds"
    cbc_path = function_tmpdir / f"{gwf_name}.cbc"
    grb_path = function_tmpdir / f"{gwf_name}.disv.grb"

    assert hds_path.is_file(), f"HDS file not found: {hds_path}"
    assert cbc_path.is_file(), f"CBC file not found: {cbc_path}"
    assert grb_path.is_file(), f"GRB file not found: {grb_path}"

    return {
        "base": base_path,
        "hds": hds_path,
        "cbc": cbc_path,
        "grb": grb_path,
        "nlay": nlay,
        "ncpl": ncpl,
    }


def test_open_hds_dis(dis_model_output):
    paths = dis_model_output
    head = open_hds(paths["base"])

    assert isinstance(head, xr.DataArray)
    assert set(head.dims) == {"time", "layer", "y", "x"}
    assert head.shape == (1, paths["nlay"], paths["nrow"], paths["ncol"])
    assert not np.all(np.isnan(head.values))


def test_open_cbc_dis(dis_model_output):
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])

    assert isinstance(cbc, xr.Dataset)
    # Should have at least flow-ja-face decomposed keys
    keys = set(cbc.data_vars)
    assert len(keys) > 0


def test_open_cbc_dis_flowja(dis_model_output):
    paths = dis_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"], flowja=True)

    assert isinstance(cbc, xr.Dataset)
    assert "flow-ja-face" in cbc.data_vars
    assert "connectivity" in cbc.data_vars


def test_open_hds_disv(disv_model_output):
    paths = disv_model_output
    head = open_hds(paths["base"])

    assert isinstance(head, xu.UgridDataArray)
    assert "time" in head.dims
    assert "layer" in head.dims
    ntime, nlayer = 1, paths["nlay"]
    assert head.shape[0] == ntime
    assert head.shape[1] == nlayer
    assert head.shape[2] == paths["ncpl"]
    assert not np.all(np.isnan(head.values))


def test_open_cbc_disv(disv_model_output):
    paths = disv_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"])

    assert isinstance(cbc, (xr.Dataset, xu.UgridDataset))
    keys = set(cbc.data_vars)
    assert len(keys) > 0


def test_open_cbc_disv_flowja(disv_model_output):
    paths = disv_model_output
    cbc = open_cbc(paths["cbc"], paths["grb"], flowja=True)

    assert isinstance(cbc, (xr.Dataset, xu.UgridDataset))
    assert "flow-ja-face" in cbc.data_vars
    assert "connectivity" in cbc.data_vars
