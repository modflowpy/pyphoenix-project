import numpy as np
from xarray import DataTree

from flopy4.mf6 import COMPONENTS, Sim, Tdis
from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc


def test_components():
    assert COMPONENTS["sim"] is Sim
    assert COMPONENTS["tdis"] is Tdis
    assert COMPONENTS["gwf"] is Gwf
    assert COMPONENTS["npf"] is Npf


def test_sim():
    sim = Sim()
    tdis = Tdis(sim, nper=1, perioddata=[Tdis.PeriodData()])
    gwf = Gwf(sim)
    dis = Dis(gwf)
    ic = Ic(gwf, strt=1.0)
    oc = Oc(gwf, saverecord=[Oc.Steps_("all")])
    npf = Npf(gwf, icelltype=0, k=1.0)

    assert isinstance(sim.data, DataTree)
    sim.data  # view the tree

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
    assert sim.data.children["gwf"] is gwf.data

    # TODO: figure out how to deduplicate trees. components proxy root?
    # assert gwf.parent.data.children["gwf"].children["npf"] is npf.data
