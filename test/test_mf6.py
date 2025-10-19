import numpy as np
from flopy.discretization.modeltime import ModelTime

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc, Sto, Wel
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation


def test_gwf_chd01(function_tmpdir):
    # mf6 test_gwf_chd01
    sim_name = "chd01"
    gwf_name = "gwf_chd01"
    time = ModelTime(perlen=[5.0], nstp=[1], tsmult=[1.0], time_units="days")

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1.00000000e-06,
        outer_maximum=100,
        under_relaxation="none",
        inner_maximum=300,
        inner_dvclose=1.00000000e-06,
        inner_rclose=1.00000000e-06,
        linear_acceleration="cg",
        relaxation_factor=1.0,
        scaling_method="none",
        reordering_method="none",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(
        nlay=1,
        nrow=1,
        ncol=100,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=0.0,
        idomain=1,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)

    ic = Ic(parent=gwf, strt=1.0)

    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        head="PRINT_FORMAT COLUMNS  10  WIDTH  15  DIGITS  6  GENERAL",
        save_head=["last"],
        # save_head={0: "last"},
        save_budget=["last"],
        print_head=["last"],
        print_budget=["last"],
    )

    npf = Npf(
        parent=gwf,
        save_specific_discharge=True,
        k=1.0,
        k33=1.0,
        icelltype=0,
    )

    chd = Chd(
        parent=gwf,
        print_flows=True,
        head={0: {(0, 0, 0): 1.0, (0, 0, 99): 0.0}},
        name="chd-1",
    )

    sim.write()
    sim.run()


def test_gwf_npf01(function_tmpdir):
    # mf6 test_gwf_npf01_75X75
    sim_name = "npf01"
    gwf_name = "npf01_75x75"

    time = ModelTime(
        perlen=[1.0, 1000.0, 1.0], nstp=[1, 10, 1], tsmult=[1.0, 1.5, 1.0], time_units="days"
    )

    ims = Ims(
        filename="sln1.ims",
        models=[gwf_name],
        print_option="summary",
        outer_dvclose=1.00000000e-06,
        outer_maximum=100,
        under_relaxation="none",
        inner_maximum=300,
        inner_dvclose=1.00000000e-06,
        inner_rclose=0.01000000,
        linear_acceleration="cg",
        relaxation_factor=1.0,
        scaling_method="none",
        reordering_method="none",
    )

    sim = Simulation(
        tdis=time,
        workspace=function_tmpdir,
        name=sim_name,
        solutions={"ims": ims},
    )

    dis = Dis(
        nlay=1,
        nrow=75,
        ncol=75,
        delr=266.66666667,
        delc=266.66666667,
        top=100.00000000,
        botm=-100.00000000,
        idomain=1,
    )

    gwf = Gwf(parent=sim, save_flows=True, dis=dis, name=gwf_name)

    ic = Ic(parent=gwf, strt=40.0)

    oc = Oc(
        parent=gwf,
        budget_file=f"{gwf_name}.cbc",
        head_file=f"{gwf_name}.hds",
        head="PRINT_FORMAT COLUMNS  10  WIDTH  15  DIGITS  6  GENERAL",
        # save_head=[None, None, "last"],
        # print_head=[None, None, "last"],
        save_head=["last", None, None],
        print_head=["last", None, None],
        print_budget=["last", None, None],
    )

    k = np.loadtxt("data/npf01_75x75.k").flatten()
    k33 = np.loadtxt("data/npf01_75x75.k33").flatten()
    # k = np.loadtxt("data/npf01_75x75.k")
    # k33 = np.loadtxt("data/npf01_75x75.k33")

    npf = Npf(
        parent=gwf,
        k=k,
        k33=k33,
        icelltype=1,
    )

    sto = Sto(
        parent=gwf,
        iconvert=1,
        ss=0.0,
        sy=0.1,
        storage=np.array(["steady-state", "transient", "steady-state"]),
    )

    import json

    chd_data = {}
    chd_data[0] = {}
    with open("data/npf01_75x75.head", "r") as f:
        chddata = json.load(f)
        keys = list(chddata["0"])
        for k in keys:
            kup = k.replace("(", "").replace(")", "")
            tokens = kup.split(",")
            l = list(int(x) for x in tokens)
            lx = tuple(l)
            chd_data[0][lx] = float(chddata["0"][k])

    chd = Chd(
        parent=gwf,
        print_flows=True,
        head=chd_data,
    )

    wel = Wel(
        parent=gwf,
        print_input=True,
        print_flows=True,
        q={1: {(0, 38, 38): -1.00000000e03}},
    )

    sim.write()
    sim.run()
