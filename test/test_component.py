import numpy as np
from xarray import DataTree

from flopy4.mf6 import Simulation, Tdis
from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc


def test_components():
    # Create a simulation.
    sim = Simulation()
    tdis = Tdis(sim=sim, nper=1, perioddata=[Tdis.PeriodData()])
    gwf = Gwf(sim=sim)
    dis = Dis(model=gwf)
    ic = Ic(model=gwf, strt=1.0)
    oc = Oc(model=gwf, perioddata=[Oc.Steps()])
    npf = Npf(model=gwf, icelltype=0, k=1.0)

    # View the data tree.
    # sim.data
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
