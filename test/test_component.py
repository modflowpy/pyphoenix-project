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
    sim.data
