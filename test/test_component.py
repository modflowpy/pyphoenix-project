import numpy as np
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


def test_empty_sim():
    sim = Simulation()


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
        # TODO get dims/coords from dis
        # and remove explicit arg below
        dims=dims,
    )

    assert isinstance(gwf.data, DataTree)
    assert gwf.dis is dis
    assert gwf.ic is ic
    assert gwf.oc is oc
    assert gwf.npf is npf
    assert gwf.data.dis is dis.data
    assert gwf.data.ic is ic.data
    assert gwf.data.oc is oc.data
    assert gwf.data.npf is npf.data
    assert np.array_equal(npf.k, np.ones(4))
    assert np.array_equal(npf.data.k, np.ones(4))

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
    assert np.array_equal(sim.models["gwf"].npf.k, np.ones(4))
    assert np.array_equal(sim.models["gwf"].npf.data.k, np.ones(4))
