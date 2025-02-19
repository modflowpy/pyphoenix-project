import numpy as np
import pytest
from flopy.discretization import StructuredGrid
from flopy.discretization.modeltime import ModelTime
from xarray import DataTree

from flopy4.mf6 import COMPONENTS, Simulation, Tdis
from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc


def test_registry():
    assert COMPONENTS["simulation"] is Simulation
    assert COMPONENTS["tdis"] is Tdis
    assert COMPONENTS["gwf"] is Gwf
    assert COMPONENTS["npf"] is Npf
    assert COMPONENTS["ic"] is Ic
    assert COMPONENTS["oc"] is Oc


@pytest.mark.xfail(reason="TODO finish debugging")
def test_init_bottom_up():
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
    gwf = Gwf(
        dis=dis,
        ic=ic,
        oc=oc,
        npf=npf,
        dims=dims,
    )
    tdis = Tdis(dims=dims)
    sim = Simulation(tdis=tdis, models={"gwf": gwf})

    assert sim.tdis is tdis
    # TODO test autoincrement
    # assert sim.models["gwf0"] is gwf
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    # TODO test multipackages e.g. chd
    # assert isinstance(gwf.chd, list)

    assert isinstance(sim.data, DataTree)
    assert "tdis" in sim.data.children
    assert "gwf" in sim.data.children
    assert "dis" in sim.data.children["gwf"].children
    assert "ic" in sim.data.children["gwf"].children
    assert "oc" in sim.data.children["gwf"].children
    assert "npf" in sim.data.children["gwf"].children
    assert "perioddata" in sim.data.children["tdis"]
    assert np.array_equal(
        sim.data.children["gwf"].children["npf"].k, np.ones((4))
    )
    assert np.array_equal(npf.k, npf.data.k)

    # TODO: figure out how to deduplicate trees. components proxy root?
    # assert npf.k is npf.data.k
    # assert gwf.parent.data.children["gwf"].children["npf"] is npf.data
