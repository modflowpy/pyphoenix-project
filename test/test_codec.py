from pprint import pprint

import numpy as np
import pytest

from flopy4.mf6.codec import dumps, loads
from flopy4.mf6.converter import COMPONENT_CONVERTER

DNODATA = 3.0e30


def test_loads_dis_generic_simple():
    mf6_input = """
BEGIN options
  print_input
END options
BEGIN dimensions
  ncol 10
  nrow 10
  nlay 1
END dimensions
BEGIN griddata
  delr
    constant 100.0
  delc
    constant 100.0
END griddata
"""

    result = loads(mf6_input)
    pprint(result)
    assert "options" in result
    assert "dimensions" in result
    assert "griddata" in result
    assert result["options"] == [["print_input"]]
    assert result["dimensions"] == [["ncol", 10], ["nrow", 10], ["nlay", 1]]
    assert result["griddata"] == [["delr"], ["constant", 100.0], ["delc"], ["constant", 100.0]]


def test_dumps_ic():
    from flopy4.mf6.gwf import Dis, Gwf, Ic

    dis = Dis()
    gwf = Gwf(dis=dis)
    ic = Ic(
        parent=gwf,
        export_array_ascii=True,
        export_array_netcdf=True,
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(ic))
    print("IC dump:")
    print(dumped)
    assert dumped

    loaded = loads(dumped)
    print("IC load:")
    pprint(loaded)


@pytest.mark.xfail(reason="nested type unstructuring not yet supported")
def test_dumps_oc():
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 1},
        budget_file="test.bud",
        head_file="test.hds",
        save_head={0: "all"},
        save_budget={0: "all"},
        perioddata={
            0: Oc.PrintSaveSetting(
                printrecord=[
                    Oc.PrintRecord("head", Oc.Steps(all=True)),
                    Oc.PrintRecord("budget", Oc.Steps(all=True)),
                ],
            )
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print("OC dump:")
    print(dumped)
    assert "save head all" in dumped
    assert "save budget all" in dumped
    assert "print head all" in dumped
    assert "print budget all" in dumped
    assert dumped

    loaded = loads(dumped)
    print("OC load:")
    pprint(loaded)


def test_dumps_dis():
    from flopy4.mf6.gwf import Dis

    dis = Dis(
        nlay=1,
        nrow=10,
        ncol=10,
        delr=100.0,
        delc=100.0,
        idomain=1,
        length_units="feet",
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(dis))
    print("DIS dump:")
    print(dumped)
    assert dumped

    loaded = loads(dumped)
    print("DIS load:")
    pprint(loaded)

    assert ["LENGTH_UNITS", "feet"] in loaded["OPTIONS"]
    assert loaded["DIMENSIONS"] == [["NLAY", 1], ["NCOL", 10], ["NROW", 10]]
    assert ["DELR"] in loaded["GRIDDATA"]
    assert ["DELC"] in loaded["GRIDDATA"]


def test_dumps_tdis():
    from flopy.discretization.modeltime import ModelTime

    from flopy4.mf6.tdis import Tdis

    tdis = Tdis.from_time(ModelTime(perlen=[1.0, 2.0], nstp=[1, 2]))
    tdis.time_units = "days"

    dumped = dumps(COMPONENT_CONVERTER.unstructure(tdis))
    print("TDIS dump:")
    print(dumped)
    assert dumped
    assert "BEGIN PERIODDATA 1" in dumped
    assert " 1.0 1 1.0" in dumped
    assert "END PERIODDATA 1" in dumped
    assert "BEGIN PERIODDATA 2" in dumped
    assert " 2.0 2 1.0" in dumped
    assert "END PERIODDATA 2" in dumped

    loaded = loads(dumped)
    print("TDIS load:")
    pprint(loaded)


def test_dumps_chd():
    from flopy4.mf6.gwf import Chd, Dis, Gwf

    dis = Dis(nrow=10, ncol=10)
    gwf = Gwf(dis=dis)
    chd = Chd(
        parent=gwf,
        head={
            0: {
                (0, 0, 0): 10.0,
                (0, 9, 9): 20.0,
            }
        },
        save_flows=True,
        print_input=True,
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD dump:")
    print(dumped)

    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    assert "1 1 1 10.0" in dumped  # First CHD cell - node 1
    assert "1 10 10 20.0" in dumped  # Second CHD cell - node 100
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
    pprint(loaded)


def test_dumps_wel():
    from flopy4.mf6.gwf import Dis, Gwf, Wel

    dis = Dis(nlay=3, nrow=10, ncol=10)
    gwf = Gwf(dis=dis)
    wel = Wel(
        parent=gwf,
        q={
            0: {
                (0, 2, 3): -100.0,
                (1, 5, 7): -50.0,
                (2, 8, 1): 25.0,
            }
        },
        print_input=True,
        save_flows=True,
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL dump:")
    print(dumped)

    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 3
    # node q (nodes are 1-based)
    assert "1 3 4 -100.0" in dumped  # (0,2,3) -> node 24
    assert "2 6 8 -50.0" in dumped  # (1,5,7) -> node 158
    assert "3 9 2 25.0" in dumped  # (2,8,1) -> node 282
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("WEL load:")
    pprint(loaded)


def test_dumps_drn():
    from flopy4.mf6.gwf import Dis, Drn, Gwf

    dis = Dis(nlay=2, nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    drn = Drn(
        parent=gwf,
        elev={
            0: {
                (0, 0, 4): 10.0,
                (1, 4, 0): 8.0,
            },
            1: {
                (0, 1, 1): 12.0,
                (0, 2, 3): 9.0,
                (1, 3, 2): 7.0,
            },
        },
        cond={
            0: {
                (0, 0, 4): 1.0,
                (1, 4, 0): 2.0,
            },
            1: {
                (0, 1, 1): 1.5,
                (0, 2, 3): 0.8,
                (1, 3, 2): 2.2,
            },
        },
        print_flows=True,
        dims={"nper": 2},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(drn))
    print("DRN dump:")
    print(dumped)

    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped
    assert "BEGIN PERIOD 2" in dumped
    assert "END PERIOD 2" in dumped

    period1_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    period2_section = dumped.split("BEGIN PERIOD 2")[1].split("END PERIOD 2")[0].strip()

    period1_lines = [line.strip() for line in period1_section.split("\n") if line.strip()]
    period2_lines = [line.strip() for line in period2_section.split("\n") if line.strip()]

    assert len(period1_lines) == 2
    assert len(period2_lines) == 3

    # node elev cond
    assert "1 1 5 10.0 1.0" in dumped  # Period 1: (0,0,4)
    assert "2 5 1 8.0 2.0" in dumped  # Period 1: (1,4,0)
    assert "1 2 2 12.0 1.5" in dumped  # Period 2: (0,1,1)
    assert "1 3 4 9.0 0.8" in dumped  # Period 2: (0,2,3)
    assert "2 4 3 7.0 2.2" in dumped  # Period 2: (1,3,2)
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("DRN load:")
    pprint(loaded)


def test_dumps_chd_2():
    from flopy4.mf6.gwf import Chd, Dis, Gwf

    dis = Dis(nlay=1, nrow=20, ncol=30)
    gwf = Gwf(dis=dis)

    boundaries = {}
    for row in range(5, 15):
        boundaries[(0, row, 0)] = 100.0
    for row in range(8, 12):
        boundaries[(0, row, 29)] = 95.0
    for col in range(10, 20):
        boundaries[(0, 19, col)] = 98.0

    chd = Chd(parent=gwf, head={0: boundaries}, print_input=True, save_flows=True, dims={"nper": 1})

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 24
    assert "100.0" in dumped  # Left boundary
    assert "95.0" in dumped  # Right boundary
    assert "98.0" in dumped  # Bottom boundary
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
    pprint(loaded)


def test_dumps_rch():
    from flopy4.mf6.gwf import Dis, Gwf, Rch

    dis = Dis(nlay=1, nrow=20, ncol=30)
    gwf = Gwf(dis=dis)

    boundaries = {}
    for row in range(5, 15):
        boundaries[(0, row, 0)] = 100.0
    for row in range(8, 12):
        boundaries[(0, row, 29)] = 95.0
    for col in range(10, 20):
        boundaries[(0, 19, col)] = 98.0

    rch = Rch(
        parent=gwf, recharge={0: boundaries}, print_input=True, save_flows=True, dims={"nper": 1}
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCH dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 24
    assert "100.0" in dumped  # Left boundary
    assert "95.0" in dumped  # Right boundary
    assert "98.0" in dumped  # Bottom boundary
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("RCH load:")
    pprint(loaded)


def test_dumps_rcha():
    from flopy4.mf6.gwf import Dis, Gwf, Rcha

    dis = Dis(nlay=1, nrow=20, ncol=30)
    gwf = Gwf(dis=dis)

    boundaries = np.full((20, 30), DNODATA, dtype=float)
    for row in range(5, 15):
        boundaries[row, 0] = 100.0
    for row in range(8, 12):
        boundaries[row, 29] = 95.0
    for col in range(10, 20):
        boundaries[19, col] = 98.0

    rch = Rcha(
        parent=gwf, recharge={0: boundaries}, print_input=True, save_flows=True, dims={"nper": 1}
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCH dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 24
    assert "100.0" in dumped  # Left boundary
    assert "95.0" in dumped  # Right boundary
    assert "98.0" in dumped  # Bottom boundary
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("RCH load:")
    pprint(loaded)


def test_dumps_wel_with_aux():
    from flopy4.mf6.gwf import Dis, Gwf, Wel

    dis = Dis(nlay=2, nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    wel = Wel(
        parent=gwf,
        auxiliary=["well_id"],
        q={
            0: {
                (0, 1, 2): -75.0,
                (1, 3, 4): -25.0,
            }
        },
        aux={
            0: {
                (0, 1, 2): 1.0,
                (1, 3, 4): 2.0,
            }
        },
        print_input=True,
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL+aux dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    # node q aux_value
    assert "1 2 3 -75.0 1.0" in dumped  # (0,1,2) -> node 8, q=-75.0, aux=1.0
    assert "2 4 5 -25.0 2.0" in dumped  # (1,3,4) -> node 45, q=-25.0, aux=2.0
    assert "1e+30" not in dumped
    assert "1.0e+30" not in dumped

    loaded = loads(dumped)
    print("WEL+aux load:")
    pprint(loaded)


def test_dumps_gwf():
    from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc

    dis = Dis(nlay=1, nrow=10, ncol=10, delr=100.0, delc=100.0)
    gwf = Gwf(name="test_model", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)
    oc = Oc(parent=gwf, head_file="test.hds", budget_file="test.bud", dims={"nper": 1})
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 10.0}}, dims={"nper": 1})

    gwf = Gwf(
        name="test_model",
        dis=dis,
        ic=ic,
        npf=npf,
        oc=oc,
        chd=[chd],
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(gwf))
    print("GWF dump:")
    print(dumped)

    # Check that child component bindings are included
    assert "DIS6" in dumped
    assert "IC6" in dumped
    assert "NPF6" in dumped
    assert "OC6" in dumped
    assert "test_model.dis" in dumped
    assert "test_model.ic" in dumped
    assert "test_model.npf" in dumped
    assert "test_model.oc" in dumped

    loaded = loads(dumped)
    print("GWF load:")
    pprint(loaded)


def test_dumps_simulation():
    from flopy.discretization.modeltime import ModelTime

    from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc
    from flopy4.mf6.simulation import Simulation
    from flopy4.mf6.tdis import Tdis

    # Create model components
    dis = Dis(nlay=1, nrow=5, ncol=5, delr=100.0, delc=100.0)
    gwf = Gwf(name="model1", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)
    oc = Oc(parent=gwf, head_file="model1.hds", budget_file="model1.bud", dims={"nper": 1})

    # Create model
    gwf = Gwf(
        name="model1",
        dis=dis,
        ic=ic,
        npf=npf,
        oc=oc,
    )

    # Create time discretization
    time = ModelTime(perlen=[1.0], nstp=[1])
    tdis = Tdis.from_time(time)

    # Create simulation
    sim = Simulation(
        name="test_sim",
        models={"model1": gwf},
        exchanges={},
        solutions={},
        tdis=tdis,
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(sim))
    print("Simulation dump:")
    print(dumped)

    # Check that model bindings are included
    assert "GWF6" in dumped
    assert "model1" in dumped
    assert "TDIS6" in dumped

    loaded = loads(dumped)
    print("Simulation load:")
    pprint(loaded)
