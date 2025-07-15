from flopy4.mf6.codec import dumps
from flopy4.mf6.converter import COMPONENT_CONVERTER


def test_dumps_ic():
    from flopy4.mf6.gwf import Dis, Gwf, Ic

    dis = Dis()
    gwf = Gwf(dis=dis)
    ic = Ic(
        parent=gwf,
        export_array_ascii=True,
        export_array_netcdf=True,
    )

    result = dumps(COMPONENT_CONVERTER.unstructure(ic))
    print(result)
    assert result


def test_dumps_oc():
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        budget_file="test.bud",
        head_file="test.hds",
        save_head={0: "all"},
        save_budget={0: "all"},
        dims={"nper": 1},
    )

    result = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print(result)
    assert result


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

    result = dumps(COMPONENT_CONVERTER.unstructure(dis))
    print(result)
    assert result


def test_dumps_tdis():
    from flopy.discretization.modeltime import ModelTime

    from flopy4.mf6.tdis import Tdis

    tdis = Tdis.from_time(ModelTime(perlen=[1.0, 2.0], nstp=[1, 2]))
    tdis.time_units = "days"

    result = dumps(COMPONENT_CONVERTER.unstructure(tdis))
    print(result)
    assert result


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

    result = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print(result)

    assert "BEGIN PERIOD 1" in result
    assert "END PERIOD 1" in result

    period_section = result.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    assert "1 10.0" in result  # First CHD cell - node 1
    assert "100 20.0" in result  # Second CHD cell - node 100
    assert "1e+30" not in result
    assert "1.0e+30" not in result


def test_dumps_wel_sparse():
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

    result = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL sparse result:")
    print(result)

    assert "BEGIN PERIOD 1" in result
    assert "END PERIOD 1" in result

    period_section = result.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 3
    # node q (nodes are 1-based)
    assert "24 -100.0" in result  # (0,2,3) -> node 24
    assert "158 -50.0" in result  # (1,5,7) -> node 158
    assert "282 25.0" in result  # (2,8,1) -> node 282
    assert "1e+30" not in result
    assert "1.0e+30" not in result


def test_dumps_drn_sparse_multiperiod():
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

    result = dumps(COMPONENT_CONVERTER.unstructure(drn))

    assert "BEGIN PERIOD 1" in result
    assert "END PERIOD 1" in result
    assert "BEGIN PERIOD 2" in result
    assert "END PERIOD 2" in result

    period1_section = result.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    period2_section = result.split("BEGIN PERIOD 2")[1].split("END PERIOD 2")[0].strip()

    period1_lines = [line.strip() for line in period1_section.split("\n") if line.strip()]
    period2_lines = [line.strip() for line in period2_section.split("\n") if line.strip()]

    assert len(period1_lines) == 2
    assert len(period2_lines) == 3

    # node elev cond
    assert "5 10.0 1.0" in result  # Period 1: (0,0,4)
    assert "46 8.0 2.0" in result  # Period 1: (1,4,0)
    assert "7 12.0 1.5" in result  # Period 2: (0,1,1)
    assert "14 9.0 0.8" in result  # Period 2: (0,2,3)
    assert "43 7.0 2.2" in result  # Period 2: (1,3,2)
    assert "1e+30" not in result
    assert "1.0e+30" not in result


def test_dumps_chd_sparse_realistic():
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

    result = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD realistic sparse result:")
    print(result)

    period_section = result.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 24
    assert "100.0" in result  # Left boundary
    assert "95.0" in result  # Right boundary
    assert "98.0" in result  # Bottom boundary
    assert "1e+30" not in result
    assert "1.0e+30" not in result


def test_dumps_wel_with_auxiliary():
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

    result = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL with auxiliary sparse result:")
    print(result)

    period_section = result.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    # node q aux_value
    assert "8 -75.0 1.0" in result  # (0,1,2) -> node 8, q=-75.0, aux=1.0
    assert "45 -25.0 2.0" in result  # (1,3,4) -> node 45, q=-25.0, aux=2.0
    assert "1e+30" not in result
    assert "1.0e+30" not in result
