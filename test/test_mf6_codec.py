"""Test the MF6 input file reading/writing capability."""

from pprint import pprint

import numpy as np
import pytest

from flopy4.mf6.codec import dumps, loads, writer
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converter import COMPONENT_CONVERTER


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


def test_dumps_sto():
    from flopy4.mf6.gwf import Dis, Gwf, Sto

    dis = Dis()
    gwf = Gwf(dis=dis)
    sto = Sto(
        dims={"nper": 3},
        parent=gwf,
        steady_state=[False, True, False],
        transient=[True, False, True],
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(sto))
    print("STO dump:")
    print(dumped)
    assert "BEGIN PERIOD 1\n TRANSIENT" in dumped
    assert "BEGIN PERIOD 2\n STEADY-STATE" in dumped
    assert "BEGIN PERIOD 3\n TRANSIENT" in dumped
    assert dumped

    loaded = loads(dumped)
    print("STO load:")
    pprint(loaded)


def test_dumps_oc():
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 1},
        budget_file="test.bud",
        head_file="test.hds",
        save_head={0: "all"},
        save_budget={0: "all"},
        print_head={0: "all"},
        print_budget={0: "all"},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print("OC dump:")
    print(dumped)
    assert "SAVE HEAD all" in dumped
    assert "SAVE BUDGET all" in dumped
    assert "PRINT HEAD all" in dumped
    assert "PRINT BUDGET all" in dumped
    assert dumped

    loaded = loads(dumped)
    print("OC load:")
    pprint(loaded)


def test_dumps_oc2():
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 1},
        budget_file="test.bud",
        head_file="test.hds",
        save_head={0: "last"},
        save_budget={0: "first"},
        print_head={0: "first"},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print("OC dump:")
    print(dumped)
    assert "SAVE HEAD last" in dumped
    assert "SAVE BUDGET first" in dumped
    assert "PRINT HEAD first" in dumped
    assert dumped

    loaded = loads(dumped)
    print("OC load:")
    pprint(loaded)


@pytest.fixture
def dis_with_constant_arrays():
    from flopy4.mf6.gwf import Dis

    return Dis(
        nlay=2,
        nrow=10,
        ncol=10,
        delr=100.0,
        delc=100.0,
        idomain=1,
        length_units="feet",
    )


def test_dumps_dis_with_constant_arrays(dis_with_constant_arrays):
    dis = dis_with_constant_arrays
    dumped = dumps(COMPONENT_CONVERTER.unstructure(dis))
    print("DIS dump:")
    print(dumped)
    assert dumped

    loaded = loads(dumped)
    print("DIS load:")
    pprint(loaded)

    assert ["LENGTH_UNITS", "feet"] in loaded["OPTIONS"]
    assert loaded["DIMENSIONS"] == [["NLAY", 2], ["NCOL", 10], ["NROW", 10]]
    assert ["DELR"] in loaded["GRIDDATA"]
    assert ["DELC"] in loaded["GRIDDATA"]


def test_dumps_dis_with_layered_arrays(dis_with_constant_arrays):
    dis = dis_with_constant_arrays
    dis.delr[0] = 101.0
    dis.botm[0, 0, 0] = -1.0  # 3d array will force layered output
    dumped = dumps(COMPONENT_CONVERTER.unstructure(dis))
    print("DIS dump:")
    print(dumped)
    assert dumped
    assert "BOTM LAYERED" in dumped

    loaded = loads(dumped)
    print("DIS load:")
    pprint(loaded)


@pytest.fixture
def disv_with_constant_arrays():
    from flopy4.mf6.gwf import Disv

    return Disv(
        nlay=3,
        ncpl=1,
        nvert=4,
        top=30.0,
        botm=np.stack([np.full((1), val) for val in [20.0, 10.0, 0.0]]),
        # TODO support vertex_array (_detect_grid_reshape support) in ingress structure
        iv=[0, 1, 2, 3],
        xv=[0.0, 0.0, 1.0, 1.0],
        yv=[0.0, 1.0, 1.0, 0.0],
        cell2ddata=[Disv.Cell2dRecord(0, 0.50000000, 0.50000000, 5, (0, 1, 2, 3, 0))],
        length_units="feet",
    )


def test_dumps_disv_with_constant_arrays(disv_with_constant_arrays):
    disv = disv_with_constant_arrays
    dumped = dumps(COMPONENT_CONVERTER.unstructure(disv))
    print("DISV dump:")
    print(dumped)
    assert dumped

    loaded = loads(dumped)
    print("DISV load:")
    pprint(loaded)

    assert ["LENGTH_UNITS", "feet"] in loaded["OPTIONS"]
    assert loaded["DIMENSIONS"] == [["NLAY", 3], ["NCPL", 1], ["NVERT", 4]]
    assert ["TOP"] in loaded["GRIDDATA"]
    assert ["BOTM", "LAYERED"] in loaded["GRIDDATA"]
    assert ["CONSTANT", 30.0] in loaded["GRIDDATA"]
    assert ["CONSTANT", 20.0] in loaded["GRIDDATA"]
    assert ["CONSTANT", 10.0] in loaded["GRIDDATA"]
    assert ["CONSTANT", 0.0] in loaded["GRIDDATA"]


def test_dumps_disv_with_layered_arrays(disv_with_constant_arrays):
    disv = disv_with_constant_arrays
    disv.top[0] = 30.0
    disv.botm[0, 0] = 20.0  # TODO 3d array will force layered output
    dumped = dumps(COMPONENT_CONVERTER.unstructure(disv))
    print("DISV dump:")
    print(dumped)
    assert dumped
    assert "BOTM LAYERED" in dumped

    loaded = loads(dumped)
    print("DIS load:")
    pprint(loaded)


def test_dumps_tdis():
    from flopy4.mf6.tdis import Tdis
    from flopy4.mf6.utils.time import Time

    tdis = Tdis.from_time(Time(perlen=[1.0, 2.0], nstp=[1, 2]))
    tdis.time_units = "days"

    dumped = dumps(COMPONENT_CONVERTER.unstructure(tdis))
    print("TDIS dump:")
    print(dumped)
    assert dumped
    assert "BEGIN PERIODDATA" in dumped
    assert " 1.0 1 1.0" in dumped
    assert " 2.0 2 1.0" in dumped
    assert "END PERIODDATA" in dumped

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
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
    pprint(loaded)


def test_dumps_chdg():
    from flopy4.mf6.gwf import Chdg, Dis, Gwf

    nlay = 1
    nrow = 10
    ncol = 10

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    head = np.full((nlay, nrow, ncol), FILL_DNODATA, dtype=float)
    head[0, 0, 0] = 1.0
    head[0, 9, 9] = 0.0
    chd = Chdg(
        parent=gwf,
        head=np.expand_dims(head.ravel(), axis=0),
        save_flows=True,
        print_input=True,
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD dump:")
    print(dumped)

    assert "READARRAYGRID" in dumped
    assert "MAXBOUND 2" in dumped
    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 12
    dump_data = [[float(x) for x in line.split()] for line in lines[2:12]]
    dump_head = np.array(dump_data)
    assert np.allclose(head, dump_head)

    loaded = loads(dumped)
    print("CHDG load:")
    pprint(loaded)


def test_dumps_rcha():
    from flopy4.mf6.gwf import Dis, Gwf, Rcha

    nlay = 3
    nrow = 10
    ncol = 10

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    recharge = np.full((nrow, ncol), FILL_DNODATA, dtype=float)
    irch = np.full((nrow, ncol), 1, dtype=int)
    irch[0, 0] = 2
    irch[9, 9] = 2
    recharge[0, 0] = 1.0
    recharge[9, 9] = 0.0
    rch = Rcha(
        parent=gwf,
        irch=np.expand_dims(irch.ravel(), axis=0),
        recharge=np.expand_dims(recharge.ravel(), axis=0),
        save_flows=True,
        print_input=True,
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCH dump:")
    print(dumped)

    assert "READASARRAYS" in dumped
    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 6
    dump_irch = [int(x) for x in lines[2].split()]
    dump_lidx = np.array(dump_irch)
    assert np.allclose(irch, dump_lidx.reshape(nrow, ncol))
    dump_rch = [float(x) for x in lines[5].split()]
    dump_recharge = np.array(dump_rch)
    assert np.allclose(recharge, dump_recharge.reshape(nrow, ncol))

    loaded = loads(dumped)
    print("RCHA load:")
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
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

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
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("DRN load:")
    pprint(loaded)


def test_dumps_npf():
    from flopy4.mf6.gwf import Dis, Gwf, Npf

    dis = Dis(nlay=2, nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    npf = Npf(parent=gwf, cvoptions=Npf.Cvoptions(dewatered=True), k=1.0)

    dumped = dumps(COMPONENT_CONVERTER.unstructure(npf))
    print("NPF dump:")
    print(dumped)

    assert "VARIABLECV" in dumped
    assert "DEWATERED" in dumped
    assert "ICELLTYPE\n CONSTANT 0" in dumped
    assert "K\n CONSTANT 1.0" in dumped


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
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
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
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("WEL+aux load:")
    pprint(loaded)


def test_dumps_wel_double_aux():
    """Two auxiliary variables in WEL period block round-trip correctly."""
    from flopy4.mf6.gwf import Dis, Gwf, Wel

    dis = Dis(nlay=2, nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    wel = Wel(
        parent=gwf,
        auxiliary=["well_id", "temp"],
        q={0: {(0, 1, 2): -75.0}},
        aux={0: {(0, 1, 2): [1.0, 25.0]}},
        dims={"nper": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]
    assert len(lines) == 1
    # cellid q aux1 aux2
    assert "1 2 3 -75.0 1.0 25.0" in dumped


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
    from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc
    from flopy4.mf6.simulation import Simulation
    from flopy4.mf6.tdis import Tdis
    from flopy4.mf6.utils.time import Time

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
    time = Time(perlen=[1.0], nstp=[1])
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


def test_clean_last_chunk():
    cleaned = writer._clean_last_chunk(iter(["chunk1", "chunk2", "\n\n"]))
    assert list(cleaned) == ["chunk1", "chunk2", "\n"]


def test_dumps_tas_inner_classes():
    """utl-tas: multi=True package with 3 inner record classes unstructures correctly.

    TimeSeriesName, InterpolationMethod, and Sfac each have a _keyword token that
    must appear before the scalar value in the ATTRIBUTES block.
    """
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(
        time_series_name=Tas.TimeSeriesName(time_series_name="my_ts"),
        interpolation_method=Tas.InterpolationMethod(interpolation_method="linear"),
        sfac=Tas.Sfac(sfacval=1.5),
    )

    unstructured = COMPONENT_CONVERTER.unstructure(tas)
    assert "attributes" in unstructured
    assert unstructured["attributes"]["time_series_name"] == ("NAME", "my_ts")
    assert unstructured["attributes"]["interpolation_method"] == ("METHOD", "linear")
    assert unstructured["attributes"]["sfac"] == ("SFAC", 1.5)

    dumped = dumps(unstructured)
    assert "BEGIN ATTRIBUTES" in dumped
    assert "NAME my_ts" in dumped
    assert "METHOD linear" in dumped
    assert "SFAC 1.5" in dumped


def test_dumps_zero_field_exg():
    """Zero-field exchange classes (gwfprt, gwfgwe, gwfgwt) instantiate and unstructure
    to empty dicts, producing no output — the pass-only class body must not interfere
    with xattree or the converter.
    """
    from flopy4.mf6.exg.gwfgwe import Gwfgwe
    from flopy4.mf6.exg.gwfgwt import Gwfgwt
    from flopy4.mf6.exg.gwfprt import Gwfprt

    for cls in (Gwfprt, Gwfgwe, Gwfgwt):
        obj = cls()
        unstructured = COMPONENT_CONVERTER.unstructure(obj)
        assert unstructured == {}, f"{cls.__name__} should unstructure to empty dict"
        dumped = dumps(unstructured)
        assert dumped == "", f"{cls.__name__} should produce no output"


def test_dumps_gwt_oc_per_period():
    """gwt-oc save/print fields write SAVE CONCENTRATION and SAVE BUDGET per period."""
    from flopy4.mf6.gwt.oc import Oc

    oc = Oc(
        dims={"nper": 2},
        budget_file="gwt.bud",
        concentration_file="gwt.conc",
        save_concentration={0: "last", 1: "all"},
        save_budget={0: "last"},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    assert "SAVE CONCENTRATION last" in dumped
    assert "SAVE CONCENTRATION all" in dumped
    assert "SAVE BUDGET last" in dumped


def test_dumps_gwt_oc_wildcard():
    """gwt-oc wildcard period key '*' sets period 0, which MF6 inherits to all periods."""
    from flopy4.mf6.gwt.oc import Oc

    oc = Oc(
        dims={"nper": 1},
        budget_file="gwt.bud",
        concentration_file="gwt.conc",
        save_concentration={"*": "last"},
        save_budget={"*": "all"},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    assert "SAVE CONCENTRATION last" in dumped
    assert "SAVE BUDGET all" in dumped


def test_dumps_prt_prp_release_setting():
    """prt-prp period release fields (all_, first, last) write correct MF6 keywords."""
    from flopy4.mf6.prt.prp import Prp

    prp = Prp(
        dims={"nper": 3, "nreleasepts": 0},
        all_={0: True},
        first={1: True},
        last={2: True},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(prp))
    assert "ALL" in dumped
    assert "FIRST" in dumped
    assert "LAST" in dumped
    assert "ALL_" not in dumped


# ---------------------------------------------------------------------------
# OC period dict API coverage
# ---------------------------------------------------------------------------


def _oc_blocks(oc):
    """Return the unstructured block dict for an Oc instance."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    return unstructure_component(oc)


def _period_blocks(oc):
    blocks = _oc_blocks(oc)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_oc_period_string_int_keys():
    """String integer keys ('0', '1') are treated identically to integer keys."""
    from flopy4.mf6.gwf import Oc

    dims = {"nper": 3}
    # integer keys
    oc_int = Oc(dims=dims, save_budget={0: "all", 1: "last"})
    # string-int keys
    oc_str = Oc(dims=dims, save_budget={"0": "all", "1": "last"})

    pb_int = _period_blocks(oc_int)
    pb_str = _period_blocks(oc_str)

    assert pb_int == pb_str
    assert pb_int["period 1"]["save budget"] == "all"
    assert pb_int["period 2"]["save budget"] == "last"
    # No fill-forward: period 3 was not specified so it produces no block.
    assert "period 3" not in pb_int


def test_oc_period_wildcard_fillforward():
    """'*' key expands to all periods not covered by explicit integer keys."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(dims={"nper": 4}, save_head={"*": "all"}, save_budget={"*": "last"})
    pb = _period_blocks(oc)

    assert len(pb) == 4
    for i in range(1, 5):
        assert pb[f"period {i}"]["save head"] == "all"
        assert pb[f"period {i}"]["save budget"] == "last"


def test_oc_period_steps_syntax():
    """STEPS values with step numbers pass through verbatim to the period block."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 2},
        save_budget={0: "STEPS 1 3 5"},
        print_budget={0: "STEPS 1", 1: "last"},
    )
    pb = _period_blocks(oc)

    assert pb["period 1"]["save budget"] == "STEPS 1 3 5"
    assert pb["period 1"]["print budget"] == "STEPS 1"
    assert "save budget" not in pb["period 2"]  # no fill-forward: period 2 not specified
    assert pb["period 2"]["print budget"] == "last"


def test_oc_period_stop_sentinel():
    """Empty string '' suppresses output for that period; unspecified periods are omitted."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 3},
        save_head={"*": "all"},
        save_budget={0: "STEPS 1", 1: ""},
    )
    pb = _period_blocks(oc)

    # All periods have save_head (fill-forward from '*')
    assert len(pb) == 3
    for i in range(1, 4):
        assert pb[f"period {i}"]["save head"] == "all"

    # Only period 1 has save_budget; periods 2-3 omit it
    assert pb["period 1"]["save budget"] == "STEPS 1"
    assert "save budget" not in pb["period 2"]
    assert "save budget" not in pb["period 3"]


def test_oc_period_mixed_keys_no_silent_drop():
    """Mixed string-int and int keys all take effect — none are silently dropped."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 3},
        save_head={"0": "first", 1: "last", 2: "all"},
    )
    pb = _period_blocks(oc)

    assert pb["period 1"]["save head"] == "first"
    assert pb["period 2"]["save head"] == "last"
    assert pb["period 3"]["save head"] == "all"


def test_oc_dumps_steps_in_output():
    """Round-trip: STEPS syntax appears correctly in the serialised OC text."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 2},
        budget_file="t.bud",
        head_file="t.hds",
        save_head={"*": "all"},
        save_budget={0: "STEPS 1 5", 1: ""},
        print_budget={"*": "last"},
    )
    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))

    assert "SAVE HEAD all" in dumped
    assert "SAVE BUDGET STEPS 1 5" in dumped
    assert "PRINT BUDGET last" in dumped
    # Period 2 must not re-emit SAVE BUDGET
    lines = dumped.splitlines()
    period2_start = next(i for i, l in enumerate(lines) if "BEGIN PERIOD 2" in l)
    period2_block = "\n".join(lines[period2_start:])
    assert "SAVE BUDGET" not in period2_block


def test_oc_period_frequency():
    """FREQUENCY n ocsetting is emitted and preserved in the period block."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 3},
        save_head={"*": "FREQUENCY 2"},
        save_budget={0: "all"},
    )
    pb = _period_blocks(oc)

    assert pb["period 1"]["save head"] == "FREQUENCY 2"
    assert pb["period 2"]["save head"] == "FREQUENCY 2"
    assert pb["period 3"]["save head"] == "FREQUENCY 2"
    assert pb["period 1"]["save budget"] == "all"


# ---------------------------------------------------------------------------
# LAK period tests
# ---------------------------------------------------------------------------


def _lak_period_blocks(lak):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    blocks = unstructure_component(lak)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_lak_period_lake_keywords():
    """LAK lake-keyword period rows: ifno KEYWORD value."""
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        dims={"nper": 2},
        nlakes=2,
        status={0: ["ACTIVE", "CONSTANT"]},
        stage={0: [np.nan, 5.0]},
    )
    pb = _lak_period_blocks(lak)

    # period 1 rows: STATUS for both lakes + STAGE for lake 2 (lake 1 is NaN → fill → skipped)
    rows_p1 = pb["period 1"]["lak_period"]
    assert (1, "STATUS", "ACTIVE") in rows_p1
    assert (2, "STATUS", "CONSTANT") in rows_p1
    assert (2, "STAGE", 5.0) in rows_p1
    # lake 1 STAGE is NaN → no row
    assert not any(r[0] == 1 and r[1] == "STAGE" for r in rows_p1)

    # period 2 fill-forwards period 1 values
    rows_p2 = pb["period 2"]["lak_period"]
    assert (1, "STATUS", "ACTIVE") in rows_p2


def test_lak_period_outlet_keywords():
    """LAK outlet-keyword period rows: ioutletno KEYWORD value."""
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        dims={"nper": 2},
        nlakes=1,
        noutlets=2,
        rate={0: [100.0, 200.0]},
        invert={0: [4.5, 3.5]},
    )
    pb = _lak_period_blocks(lak)

    rows = pb["period 1"]["lak_period"]
    assert (1, "RATE", 100.0) in rows
    assert (2, "RATE", 200.0) in rows
    assert (1, "INVERT", 4.5) in rows
    assert (2, "INVERT", 3.5) in rows


def test_lak_period_dumps():
    """LAK period rows are written in the expected MF6 format."""
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        dims={"nper": 1},
        nlakes=2,
        status={0: ["ACTIVE", "CONSTANT"]},
        stage={0: [np.nan, 5.0]},
    )
    dumped = dumps(COMPONENT_CONVERTER.unstructure(lak))
    print("LAK dump:")
    print(dumped)
    assert "BEGIN PERIOD 1" in dumped
    assert "1 STATUS ACTIVE" in dumped
    assert "2 STATUS CONSTANT" in dumped
    assert "2 STAGE 5.0" in dumped


# ---------------------------------------------------------------------------
# SSM tests
# ---------------------------------------------------------------------------


def _ssm_blocks(ssm):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    return unstructure_component(ssm)


def test_ssm_empty_sources_block_present():
    """Empty SSM (no sources) must still write a SOURCES block for MF6."""
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm()
    blocks = _ssm_blocks(ssm)
    assert "sources" in blocks, "SOURCES block must appear even when no sources are configured"
    assert "__dim__" not in blocks, "__dim__ sentinel block must never appear in output"
    assert blocks["sources"] == {}, "sources block should be empty when no sources set"


def test_ssm_sources_tabular_output():
    """SSM with sources writes rows in MF6 tabular format."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        sources={
            "pname": np.array(["chd-1", "rch-1"]),
            "srctype": np.array(["AUX", "AUXMIXED"]),
            "auxname": np.array(["conc", "conc"]),
        },
    )
    blocks = _ssm_blocks(ssm)
    assert "sources" in blocks
    assert "__dim__" not in blocks

    text = dumps(blocks)
    assert "BEGIN SOURCES" in text
    assert "END SOURCES" in text
    assert "chd-1" in text
    assert "rch-1" in text
    assert "AUX" in text
    assert "AUXMIXED" in text


def test_ssm_options_passthrough():
    """SSM options (print_flows, save_flows) serialise correctly."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(print_flows=True, save_flows=True)
    blocks = _ssm_blocks(ssm)
    text = dumps(blocks)
    assert "PRINT_FLOWS" in text.upper()
    assert "SAVE_FLOWS" in text.upper()


def test_ssm_sources_row_order():
    """Sources rows appear in the order they were supplied."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        sources={
            "pname": np.array(["pkg-a", "pkg-b", "pkg-c"]),
            "srctype": np.array(["AUX", "AUX", "AUXMIXED"]),
            "auxname": np.array(["c1", "c2", "c3"]),
        },
    )
    text = dumps(_ssm_blocks(ssm))
    sources_block = text[text.index("BEGIN SOURCES") : text.index("END SOURCES")]
    positions = [sources_block.index(p) for p in ["pkg-a", "pkg-b", "pkg-c"]]
    assert positions == sorted(positions), "sources must appear in supplied order"


def test_gwe_ssm_empty_sources_block_present():
    """GWE SSM (heat transport) also writes an empty SOURCES block."""
    from flopy4.mf6.gwe.ssm import Ssm as GweSsm

    ssm = GweSsm()
    blocks = _ssm_blocks(ssm)
    assert "sources" in blocks
    assert "__dim__" not in blocks


def test_ims_required_fields_enforced():
    """Required IMS fields (outer_dvclose etc.) must be provided at construction."""
    from flopy4.mf6.ims import Ims

    with pytest.raises(TypeError, match="missing.*required"):
        Ims()

    with pytest.raises(TypeError, match="missing.*required"):
        Ims(outer_dvclose=1e-6)  # still missing outer_maximum, inner_*, linear_acceleration

    # All required fields → no error
    ims = Ims(
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        linear_acceleration="cg",
    )
    assert ims.outer_dvclose == pytest.approx(1e-6)
    assert ims.linear_acceleration == "cg"


def test_ims_inner_rclose_tagged_output():
    """inner_rclose must serialise as 'INNER_RCLOSE <value>', not a bare float."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.ims import Ims

    ims = Ims(
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        rclose=Ims.Rclose(inner_rclose=0.1),
        linear_acceleration="cg",
    )
    text = dumps(unstructure_component(ims))
    assert "INNER_RCLOSE" in text.upper(), "inner_rclose must be keyword-tagged in LINEAR block"
    assert "0.1" in text


def test_fmi_dumps_partial_paths():
    """Fmi with two of three path fields set serialises only the present ones."""
    from pathlib import Path

    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.prt.fmi import Fmi

    fmi = Fmi(
        gwfhead=Path("gwf.hds"),
        gwfbudget=Path("gwf.cbc"),
    )
    text = dumps(unstructure_component(fmi))
    assert "GWFHEAD" in text.upper()
    assert "GWFBUDGET" in text.upper()
    assert "FILEIN" in text.upper()
    assert "GWFSPDIS" not in text.upper(), "unset optional path must not appear in output"


def test_gwf_netcdf_input_file_serializes():
    """netcdf_input_file must write 'NETCDF FILEIN <path>' in the NAM OPTIONS block."""
    from pathlib import Path

    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwf import Dis, Gwf

    gwf = Gwf(dis=Dis())
    gwf.netcdf_input_file = Path("model.input.nc")
    text = dumps(unstructure_component(gwf))
    assert "NETCDF FILEIN model.input.nc" in text


def test_gwt_netcdf_fields_serialize():
    """All three NetCDF path fields on Gwt must produce the correct NAM OPTIONS tokens."""
    from pathlib import Path

    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt import Dis, Gwt

    gwt = Gwt(dis=Dis())
    gwt.netcdf_mesh2d_file = Path("model.mesh2d.nc")
    gwt.netcdf_structured_file = Path("model.structured.nc")
    gwt.netcdf_input_file = Path("model.input.nc")
    text = dumps(unstructure_component(gwt))
    assert "NETCDF_MESH2D FILEOUT model.mesh2d.nc" in text
    assert "NETCDF_STRUCTURED FILEOUT model.structured.nc" in text
    assert "NETCDF FILEIN model.input.nc" in text


def test_gwe_netcdf_fields_serialize():
    """All three NetCDF path fields on Gwe must produce the correct NAM OPTIONS tokens."""
    from pathlib import Path

    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwe import Dis, Gwe

    gwe = Gwe(dis=Dis())
    gwe.netcdf_mesh2d_file = Path("model.mesh2d.nc")
    gwe.netcdf_structured_file = Path("model.structured.nc")
    gwe.netcdf_input_file = Path("model.input.nc")
    text = dumps(unstructure_component(gwe))
    assert "NETCDF_MESH2D FILEOUT model.mesh2d.nc" in text
    assert "NETCDF_STRUCTURED FILEOUT model.structured.nc" in text
    assert "NETCDF FILEIN model.input.nc" in text


def test_ssm_fileinput_row_format():
    """fileinput rows must serialise as 'pname SPC6 FILEIN spc6_filename [MIXED]'."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        fileinput={
            "pname": np.array(["rch-1", "wel-1"]),
            "spc6_filename": np.array(["rch.spc6", "wel.spc6"]),
            "mixed": np.array([True, False]),
        },
    )
    text = dumps(unstructure_component(ssm))

    assert "BEGIN FILEINPUT" in text
    assert "END FILEINPUT" in text
    # each row contains the fixed tokens immediately before the filename
    assert "rch-1 SPC6 FILEIN rch.spc6" in text
    assert "wel-1 SPC6 FILEIN wel.spc6" in text
    # MIXED only appended to the row where fi_mixed=True
    assert "rch.spc6 MIXED" in text
    assert "wel.spc6 MIXED" not in text
    # row order preserved
    assert text.index("rch-1") < text.index("wel-1")


def test_ssm_fileinput_no_mixed():
    """fileinput rows without fi_mixed omit the MIXED keyword entirely."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        fileinput={
            "pname": np.array(["rch-1"]),
            "spc6_filename": np.array(["rch.spc6"]),
        },
    )
    text = dumps(unstructure_component(ssm))
    assert "SPC6" in text
    assert "FILEIN" in text
    assert "MIXED" not in text


def test_ssm_fileinput_absent_when_empty():
    """FILEINPUT block must not be written when no fileinput data is configured."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm

    blocks = unstructure_component(Ssm())
    assert "fileinput" not in blocks, "empty FILEINPUT block must be suppressed"
    assert "__dim__" not in blocks


def test_ssm_sources_and_fileinput_together():
    """SSM correctly writes both SOURCES and FILEINPUT blocks when both are set."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        sources={
            "pname": np.array(["chd-1"]),
            "srctype": np.array(["AUX"]),
            "auxname": np.array(["conc"]),
        },
        fileinput={
            "pname": np.array(["rch-1"]),
            "spc6_filename": np.array(["rch.spc6"]),
        },
    )
    text = dumps(unstructure_component(ssm))
    assert "BEGIN SOURCES" in text
    assert "chd-1 AUX conc" in text
    assert "BEGIN FILEINPUT" in text
    assert "rch-1 SPC6 FILEIN rch.spc6" in text
    # block order: SOURCES before FILEINPUT
    assert text.index("BEGIN SOURCES") < text.index("BEGIN FILEINPUT")


# ---------------------------------------------------------------------------
# Record.from_tokens tests
# ---------------------------------------------------------------------------


def test_headprint_from_tokens_full_string():
    """Full DFN string including keyword and extra tokens is parsed correctly."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("HEAD PRINT_FORMAT COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
    assert hp.format_ == "exponential"
    assert hp.columns == 10
    assert hp.width == 12
    assert hp.digits == 6


def test_headprint_from_tokens_no_prefix():
    """Tokens without the leading keyword/extra_tokens prefix are parsed correctly."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
    assert hp.format_ == "exponential"
    assert hp.columns == 10
    assert hp.width == 12
    assert hp.digits == 6


def test_headprint_from_tokens_format_only():
    """A single untagged token populates the required positional field."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("exponential")
    assert hp.format_ == "exponential"
    assert hp.columns is None
    assert hp.width is None
    assert hp.digits is None


def test_headprint_from_tokens_list():
    """Token list form works the same as the string form."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens(["COLUMNS", "10", "exponential"])
    assert hp.format_ == "exponential"
    assert hp.columns == 10
    assert hp.width is None
    assert hp.digits is None


def test_headprint_from_tokens_tagged_types():
    """Tagged integer fields are coerced from string tokens to int."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("WIDTH 15 DIGITS 4 fixed")
    assert isinstance(hp.width, int)
    assert hp.width == 15
    assert isinstance(hp.digits, int)
    assert hp.digits == 4
    assert hp.columns is None


def test_rclose_from_tokens_with_keyword():
    """Rclose parses the INNER_RCLOSE keyword prefix and float value."""
    from flopy4.mf6.ims import Ims

    rc = Ims.Rclose.from_tokens("INNER_RCLOSE 0.1")
    assert rc.inner_rclose == pytest.approx(0.1)
    assert rc.rclose_option is None


def test_rclose_from_tokens_value_only():
    """Rclose parses a bare float without the keyword prefix."""
    from flopy4.mf6.ims import Ims

    rc = Ims.Rclose.from_tokens("0.001")
    assert rc.inner_rclose == pytest.approx(0.001)
    assert rc.rclose_option is None


def test_rclose_from_tokens_with_option():
    """Rclose parses both the float and the optional rclose_option string."""
    from flopy4.mf6.ims import Ims

    rc = Ims.Rclose.from_tokens("INNER_RCLOSE 1e-6 strict")
    assert rc.inner_rclose == pytest.approx(1e-6)
    assert rc.rclose_option == "strict"


def test_from_tokens_missing_required_raises():
    """attrs raises TypeError when a required field has no value."""
    from flopy4.mf6.gwf.oc import Oc

    with pytest.raises(TypeError):
        Oc.Headprint.from_tokens("")


# ---------------------------------------------------------------------------
# LAK integration-style test: gwf-lak-status
#
# Recreates the model structure from
# modflow6/autotest/test_gwf_lak_status.py for manual comparison.
#
# Grid layout (C=CHD, L=lake cell):
#   C . . . . . . . . .
#   . . . . . . . . . .
#   . . . . . . . . . .
#   . . . L L L . . . .
#   . . . L L L . . . .
#   . . . L L L . . . .
#   . . . . . . . . . .
#   . . . . . . . . . .
#   . . . . . . . . . .
#   . . . . . . . . . C
#
# 3 stress periods:
#   period 1  RAINFALL 0.1 (lake active, default)
#   period 2  STATUS inactive
#   period 3  STATUS active  (returns to active; rainfall fill-forwards)
# ---------------------------------------------------------------------------


def test_lak_status_input():
    """Recreate gwf-lak-status LAK input for manual comparison.

    The expected MF6 packagedata / connectiondata / period text is shown
    in the docstring so the output of dumps() can be compared visually.

    Expected period block output::

        BEGIN PERIOD 1
          1 RAINFALL 0.1
        END PERIOD 1

        BEGIN PERIOD 2
          1 STATUS inactive
        END PERIOD 2

        BEGIN PERIOD 3
          1 STATUS active
        END PERIOD 3
    """
    from flopy4.mf6.gwf.lak import Lak

    nper = 3
    nlakes = 1
    # Lake occupies rows 3-5, cols 3-5 (0-based); writer adds +1 → file: rows 4-6, cols 4-6
    bedleak = 1.0
    nconn = 9
    lake_connections = [
        (3, 3),
        (3, 4),
        (3, 5),
        (4, 3),
        (4, 4),
        (4, 5),
        (5, 3),
        (5, 4),
        (5, 5),
    ]

    cellids = np.array([(0, r, c) for r, c in lake_connections])  # (9, 3) int array
    lak = Lak(
        dims={"nper": nper},
        nlakes=nlakes,
        surfdep=1.0,
        print_input=True,
        print_stage=True,
        print_flows=True,
        save_flows=True,
        # block property dict API: dict keys match v1 DFN column names
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([100.0]),
            "nlakeconn": np.array([nconn]),
            "boundname": np.array(["lake1"], dtype=object),
        },
        connectiondata={
            "ifno": np.zeros(nconn, dtype=int),
            "iconn": np.arange(nconn, dtype=int),
            "cellid": cellids,  # (9, 3) int array; converter packs into tuples
            "claktype": np.full(nconn, "vertical", dtype=object),
            "bedleak": np.full(nconn, bedleak),
            "belev": np.zeros(nconn),
            "telev": np.zeros(nconn),
            "connlen": np.zeros(nconn),
            "connwidth": np.zeros(nconn),
        },
        # period data: period 0 sets RAINFALL; period 1 → inactive; period 2 → active
        rainfall={0: [0.1]},
        status={1: ["inactive"], 2: ["active"]},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(lak))
    print("LAK status input:")
    print(dumped)

    # --- period block checks ---
    assert "BEGIN PERIOD 1" in dumped
    assert "1 RAINFALL 0.1" in dumped
    assert "BEGIN PERIOD 2" in dumped
    assert "1 STATUS inactive" in dumped
    assert "BEGIN PERIOD 3" in dumped
    assert "1 STATUS active" in dumped

    # RAINFALL should fill-forward into periods 2 and 3 (array fill-forward)
    # but period 2 STATUS=inactive suppresses the lake so rainfall is irrelevant
    # (that's a MF6 runtime concern; we just verify it's in the input text)

    # --- packagedata checks ---
    assert "BEGIN PACKAGEDATA" in dumped
    assert "lake1" in dumped
    assert "100.0" in dumped  # initial stage

    # --- connectiondata checks ---
    # All indices written 1-based: ifno, iconn, layer, row, col all get +1
    assert "BEGIN CONNECTIONDATA" in dumped
    # first row: ifno=0→1, iconn=0→1, layer=0→1, row=3→4, col=3→4
    assert " 1 1 1 4 4 vertical" in dumped
    # last row: ifno=0→1, iconn=8→9, layer=0→1, row=5→6, col=5→6
    assert " 1 9 1 6 6 vertical" in dumped


def test_lak_structure_component_roundtrip():
    """structure_component reconstructs a Lak from loads() output."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.lak import Lak

    nconn = 3
    cellids = np.array([(0, 0, 0), (0, 0, 1), (0, 1, 0)])
    lak = Lak(
        nlakes=1,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([5.0]),
            "nlakeconn": np.array([nconn]),
            "boundname": np.array(["lake1"], dtype=object),
        },
        connectiondata={
            "ifno": np.zeros(nconn, dtype=int),
            "iconn": np.arange(nconn, dtype=int),
            "cellid": cellids,
            "claktype": np.full(nconn, "vertical", dtype=object),
            "bedleak": np.ones(nconn),
            "belev": np.zeros(nconn),
            "telev": np.zeros(nconn),
            "connlen": np.zeros(nconn),
            "connwidth": np.zeros(nconn),
        },
    )

    text = dumps(unstructure_component(lak))
    raw = loads(text)
    lak2 = structure_component(raw, Lak)

    assert lak2.nlakes == 1
    pd = lak2.packagedata
    assert list(pd["strt"].values) == [5.0]
    assert list(pd["boundname"].values) == ["lake1"]
    cd = lak2.connectiondata
    assert list(cd["ifno"].values) == [0, 0, 0]
    assert list(cd["iconn"].values) == [0, 1, 2]
    assert cd["cellid"].values[0] == (0, 0, 0)
    assert cd["cellid"].values[1] == (0, 0, 1)
    assert cd["cellid"].values[2] == (0, 1, 0)
    assert list(cd["claktype"].values) == ["vertical", "vertical", "vertical"]


def test_lak_packagedata_single_aux_roundtrip():
    """LAK packagedata with one aux variable round-trips through dump→load→structure."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        auxiliary=["CONCENTRATION"],
        nlakes=1,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([5.0]),
            "nlakeconn": np.array([2]),
            "aux": np.array([100.0]),
            "boundname": np.array(["lake1"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lak))
    print("LAK single-aux dump:")
    print(text)

    # Aux value must appear in the packagedata row between nlakeconn and boundname
    assert "100.0" in text or "100.00000000" in text or "1.00000000e+02" in text
    assert "lake1" in text

    raw = loads(text)
    lak2 = structure_component(raw, Lak)
    pd = lak2.packagedata
    assert list(pd["strt"].values) == [5.0]
    aux_vals = pd["aux"].values
    assert len(aux_vals) == 1
    assert float(aux_vals[0].item()) == pytest.approx(100.0)
    assert list(pd["boundname"].values) == ["lake1"]


def test_lak_packagedata_double_aux_roundtrip():
    """LAK packagedata with two aux variables (e.g. CONCENTRATION DENSITY) round-trips."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.lak import Lak

    # Two lakes, two aux variables each.
    lak = Lak(
        auxiliary=["CONCENTRATION", "DENSITY"],
        nlakes=2,
        packagedata={
            "ifno": np.array([0, 1]),
            "strt": np.array([-0.4, -0.5]),
            "nlakeconn": np.array([3, 2]),
            "aux": np.array([[0.0, 1025.0], [5.0, 1010.0]]),  # shape (nlakes, naux)
            "boundname": np.array(["lake1", "lake2"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lak))
    print("LAK double-aux dump:")
    print(text)

    # Both rows must include both aux values
    assert "1025" in text
    assert "1010" in text
    assert "lake1" in text
    assert "lake2" in text

    raw = loads(text)
    lak2 = structure_component(raw, Lak)
    pd = lak2.packagedata
    assert lak2.nlakes == 2
    aux_arr = pd["aux"].values  # expect shape (2, 2) or similar
    assert aux_arr[0, 0] == pytest.approx(0.0)
    assert aux_arr[0, 1] == pytest.approx(1025.0)
    assert aux_arr[1, 0] == pytest.approx(5.0)
    assert aux_arr[1, 1] == pytest.approx(1010.0)


def test_lkt_packagedata_double_aux_roundtrip():
    """LKT packagedata with two aux variables round-trips."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        auxiliary=["aux1", "aux2"],
        nlakes=1,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([35.0]),
            "aux": np.array([[99.0, 999.0]]),  # shape (nlakes=1, naux=2)
            "boundname": np.array(["mylake"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lkt))
    print("LKT double-aux dump:")
    print(text)

    assert "99" in text
    assert "999" in text
    assert "mylake" in text

    raw = loads(text)
    lkt2 = structure_component(raw, Lkt)
    pd = lkt2.packagedata
    aux_arr = pd["aux"].values
    assert aux_arr[0, 0] == pytest.approx(99.0)
    assert aux_arr[0, 1] == pytest.approx(999.0)
    assert list(pd["boundname"].values) == ["mylake"]


# ---------------------------------------------------------------------------
# GWT/GWE FMI — packagedata block with prefix=("FILEIN",) on fname column
# ---------------------------------------------------------------------------


def test_gwt_fmi_packagedata_dump():
    """gwt.Fmi packagedata writes flowtype and FILEIN fname tokens."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.fmi import Fmi

    fmi = Fmi(
        packagedata={
            "flowtype": np.array(["HEAD", "BUDGET"]),
            "fname": np.array(["gwf.hds", "gwf.cbc"]),
        }
    )
    text = dumps(unstructure_component(fmi))
    assert "BEGIN PACKAGEDATA" in text
    assert "END PACKAGEDATA" in text
    assert "HEAD FILEIN gwf.hds" in text
    assert "BUDGET FILEIN gwf.cbc" in text


def test_gwt_fmi_packagedata_roundtrip():
    """gwt.Fmi packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.fmi import Fmi

    fmi = Fmi(
        packagedata={
            "flowtype": np.array(["HEAD"]),
            "fname": np.array(["gwf.hds"]),
        }
    )
    text = dumps(unstructure_component(fmi))
    raw = loads(text)
    fmi2 = structure_component(raw, Fmi)
    pd = fmi2.packagedata
    assert list(pd["flowtype"].values) == ["HEAD"]
    assert list(pd["fname"].values) == ["gwf.hds"]


def test_gwe_fmi_packagedata_dump():
    """gwe.Fmi packagedata writes flowtype and FILEIN fname tokens."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwe.fmi import Fmi

    fmi = Fmi(
        packagedata={
            "flowtype": np.array(["HEAD"]),
            "fname": np.array(["gwf.hds"]),
        }
    )
    text = dumps(unstructure_component(fmi))
    assert "BEGIN PACKAGEDATA" in text
    assert "HEAD FILEIN gwf.hds" in text


# ---------------------------------------------------------------------------
# HPC — partitions block (simple 2-column, no prefix)
# ---------------------------------------------------------------------------


def test_hpc_partitions_dump():
    """Hpc partitions block writes mname and mrank columns."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.utl.hpc import Hpc

    hpc = Hpc(
        partitions={
            "mname": np.array(["model1", "model2"]),
            "mrank": np.array([0, 1], dtype=np.int64),
        }
    )
    text = dumps(unstructure_component(hpc))
    assert "BEGIN PARTITIONS" in text
    assert "END PARTITIONS" in text
    assert "model1" in text
    assert "model2" in text
    assert text.index("model1") < text.index("model2")


def test_hpc_partitions_roundtrip():
    """Hpc partitions survive a dump→load→structure_component cycle."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl.hpc import Hpc

    hpc = Hpc(
        partitions={
            "mname": np.array(["model1", "model2"]),
            "mrank": np.array([0, 1], dtype=np.int64),
        }
    )
    text = dumps(unstructure_component(hpc))
    raw = loads(text)
    hpc2 = structure_component(raw, Hpc)
    parts = hpc2.partitions
    assert list(parts["mname"].values) == ["model1", "model2"]
    assert list(parts["mrank"].values) == [0, 1]


# ---------------------------------------------------------------------------
# GWT-LKT / GWE-LKE — lake transport/energy packages with coupled nlakes dim
# ---------------------------------------------------------------------------


def _lkt_period_blocks(lkt):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    blocks = unstructure_component(lkt)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_lkt_period_keywords():
    """LKT period rows: ifno KEYWORD value (STATUS and CONCENTRATION)."""
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        dims={"nper": 1},
        nlakes=2,
        status={0: ["ACTIVE", "CONSTANT"]},
        concentration={0: [10.0, 20.0]},
    )
    pb = _lkt_period_blocks(lkt)
    rows = pb["period 1"]["lak_period"]
    assert (1, "STATUS", "ACTIVE") in rows
    assert (2, "STATUS", "CONSTANT") in rows
    assert (1, "CONCENTRATION", 10.0) in rows
    assert (2, "CONCENTRATION", 20.0) in rows


def test_lkt_period_dumps():
    """LKT period block is written in the expected MF6 format."""
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        dims={"nper": 1},
        nlakes=2,
        status={0: ["ACTIVE", "CONSTANT"]},
        concentration={0: [10.0, np.nan]},
    )
    text = dumps(COMPONENT_CONVERTER.unstructure(lkt))
    assert "BEGIN PERIOD 1" in text
    assert "1 STATUS ACTIVE" in text
    assert "2 STATUS CONSTANT" in text
    assert "1 CONCENTRATION 10.0" in text
    assert not any("CONCENTRATION" in line and "2 " in line for line in text.splitlines())


def test_lkt_packagedata_roundtrip():
    """LKT packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        nlakes=2,
        packagedata={
            "ifno": np.array([0, 1]),
            "strt": np.array([1.0, 2.0]),
            "boundname": np.array(["lake_a", "lake_b"], dtype=object),
        },
    )
    text = dumps(unstructure_component(lkt))
    raw = loads(text)
    lkt2 = structure_component(raw, Lkt)

    assert lkt2.nlakes == 2
    pd = lkt2.packagedata
    assert list(pd["strt"].values) == [1.0, 2.0]
    assert list(pd["boundname"].values) == ["lake_a", "lake_b"]


def _lke_period_blocks(lke):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    blocks = unstructure_component(lke)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_lke_period_keywords():
    """LKE period rows: lakeno KEYWORD value (STATUS and TEMPERATURE)."""
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        dims={"nper": 1},
        nlakes=2,
        status={0: ["ACTIVE", "CONSTANT"]},
        temperature={0: [15.0, 20.0]},
    )
    pb = _lke_period_blocks(lke)
    rows = pb["period 1"]["lak_period"]
    assert (1, "STATUS", "ACTIVE") in rows
    assert (2, "STATUS", "CONSTANT") in rows
    assert (1, "TEMPERATURE", 15.0) in rows
    assert (2, "TEMPERATURE", 20.0) in rows


def test_lke_period_dumps():
    """LKE period block is written in the expected MF6 format."""
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        dims={"nper": 1},
        nlakes=1,
        temperature={0: [18.5]},
    )
    text = dumps(COMPONENT_CONVERTER.unstructure(lke))
    assert "BEGIN PERIOD 1" in text
    assert "1 TEMPERATURE 18.5" in text


def test_lke_packagedata_roundtrip():
    """LKE packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        nlakes=2,
        packagedata={
            "lakeno": np.array([0, 1]),
            "strt": np.array([12.0, 14.0]),
            "ktf": np.array([0.6, 0.6]),
            "rbthcnd": np.array([0.1, 0.1]),
            "boundname": np.array(["lakeA", "lakeB"], dtype=object),
        },
    )
    text = dumps(unstructure_component(lke))
    raw = loads(text)
    lke2 = structure_component(raw, Lke)

    assert lke2.nlakes == 2
    pd = lke2.packagedata
    assert list(pd["strt"].values) == [12.0, 14.0]
    assert list(pd["ktf"].values) == [0.6, 0.6]
    assert list(pd["boundname"].values) == ["lakeA", "lakeB"]


def test_lke_packagedata_double_aux_roundtrip():
    """LKE packagedata with two aux variables round-trips through dump→load→structure."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        auxiliary=["aux1", "aux2"],
        nlakes=2,
        packagedata={
            "lakeno": np.array([0, 1]),
            "strt": np.array([12.0, 14.0]),
            "ktf": np.array([0.6, 0.7]),
            "rbthcnd": np.array([0.1, 0.2]),
            "aux": np.array([[10.0, 20.0], [30.0, 40.0]]),
            "boundname": np.array(["lakeA", "lakeB"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lke))

    assert "10" in text
    assert "20" in text
    assert "lakeA" in text
    assert "lakeB" in text

    raw = loads(text)
    lke2 = structure_component(raw, Lke)

    assert lke2.nlakes == 2
    pd = lke2.packagedata
    aux_arr = pd["aux"].values
    assert aux_arr[0, 0] == pytest.approx(10.0)
    assert aux_arr[0, 1] == pytest.approx(20.0)
    assert aux_arr[1, 0] == pytest.approx(30.0)
    assert aux_arr[1, 1] == pytest.approx(40.0)
    assert list(pd["boundname"].values) == ["lakeA", "lakeB"]


# ---------------------------------------------------------------------------
# Period block roundtrip — CHD / WEL / DRN
# ---------------------------------------------------------------------------


def test_chd_period_roundtrip():
    """structure_component reconstructs CHD head values from loads(dumps(...))."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd, Dis, Gwf

    dis = Dis(nrow=10, ncol=10)
    gwf = Gwf(dis=dis)
    chd = Chd(
        parent=gwf,
        head={
            0: {(0, 0, 0): 10.0, (0, 9, 9): 0.0},
        },
        dims={"nper": 1},
    )

    text = dumps(unstructure_component(chd))
    raw = loads(text)
    chd2 = structure_component(raw, Chd, dims={"nper": 1, "nodes": 100, "nrow": 10, "ncol": 10})

    assert chd2.head is not None
    head_arr = chd2.head if not hasattr(chd2.head, "values") else chd2.head.values
    assert float(head_arr[0, 0]) == pytest.approx(10.0)
    # kper=0, node (0,9,9) → flat index 99
    assert float(head_arr[0, 99]) == pytest.approx(0.0)


def test_chd_period_multi_stress_period_roundtrip():
    """CHD with two stress periods reconstructs correctly."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd, Dis, Gwf

    dis = Dis(nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    chd = Chd(
        parent=gwf,
        head={
            0: {(0, 0, 0): 10.0, (0, 4, 4): 5.0},
            1: {(0, 0, 0): 8.0, (0, 4, 4): 3.0},
        },
        dims={"nper": 2},
    )

    text = dumps(unstructure_component(chd))
    raw = loads(text)
    chd2 = structure_component(raw, Chd, dims={"nper": 2, "nodes": 25, "nrow": 5, "ncol": 5})

    assert chd2.head is not None
    head_arr = chd2.head if not hasattr(chd2.head, "values") else chd2.head.values
    assert float(head_arr[0, 0]) == pytest.approx(10.0)
    assert float(head_arr[0, 24]) == pytest.approx(5.0)
    assert float(head_arr[1, 0]) == pytest.approx(8.0)
    assert float(head_arr[1, 24]) == pytest.approx(3.0)


def test_wel_period_roundtrip():
    """structure_component reconstructs WEL q values from loads(dumps(...))."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Dis, Gwf, Wel

    dis = Dis(nlay=2, nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    wel = Wel(
        parent=gwf,
        q={
            0: {(0, 1, 2): -75.0, (1, 3, 4): -25.0},
        },
        dims={"nper": 1},
    )

    text = dumps(unstructure_component(wel))
    raw = loads(text)
    # nlay=2, nrow=5, ncol=5 → 50 nodes
    wel2 = structure_component(raw, Wel, dims={"nper": 1, "nodes": 50, "nrow": 5, "ncol": 5})

    assert wel2.q is not None
    q_arr = wel2.q if not hasattr(wel2.q, "values") else wel2.q.values
    # (0,1,2) → flat index 7; (1,3,4) → flat index 44
    ncol, nrow = 5, 5
    nn1 = 0 * nrow * ncol + 1 * ncol + 2  # = 7
    nn2 = 1 * nrow * ncol + 3 * ncol + 4  # = 44
    assert float(q_arr[0, nn1]) == pytest.approx(-75.0)
    assert float(q_arr[0, nn2]) == pytest.approx(-25.0)


def test_drn_period_roundtrip():
    """structure_component reconstructs DRN elev+cond values."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Dis, Drn, Gwf

    dis = Dis(nrow=5, ncol=5)
    gwf = Gwf(dis=dis)
    drn = Drn(
        parent=gwf,
        elev={0: {(0, 2, 2): 5.0}},
        cond={0: {(0, 2, 2): 1.0}},
        dims={"nper": 1},
    )

    text = dumps(unstructure_component(drn))
    raw = loads(text)
    drn2 = structure_component(raw, Drn, dims={"nper": 1, "nodes": 25, "nrow": 5, "ncol": 5})

    assert drn2.elev is not None
    assert drn2.cond is not None
    elev_arr = drn2.elev if not hasattr(drn2.elev, "values") else drn2.elev.values
    cond_arr = drn2.cond if not hasattr(drn2.cond, "values") else drn2.cond.values
    # (0,2,2) → flat index 12
    assert float(elev_arr[0, 12]) == pytest.approx(5.0)
    assert float(cond_arr[0, 12]) == pytest.approx(1.0)


def test_wel_period_aux_ingress_from_file():
    """structure_component reconstructs WEL aux from a raw MF6 input string."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Wel

    text = """
BEGIN options
  AUXILIARY well_id
  PRINT_INPUT
END options
BEGIN period 1
  1 2 3 -75.000000000e+00 1.000000000e+00
END period 1
"""
    raw = loads(text)
    # nlay=1, nrow=5, ncol=5 → 25 nodes; (0,1,2) → flat index 7
    wel = structure_component(raw, Wel, dims={"nper": 1, "nodes": 25, "nrow": 5, "ncol": 5})

    assert wel.aux is not None
    aux_arr = wel.aux if not hasattr(wel.aux, "values") else wel.aux.values
    # shape must be (nper, nodes, naux)
    assert aux_arr.ndim == 3
    assert aux_arr.shape[0] == 1  # nper
    assert aux_arr.shape[2] == 1  # naux=1
    node = 0 * 5 + 1 * 5 + 2  # (0,1,2) → 7
    assert float(aux_arr[0, node, 0]) == pytest.approx(1.0)

    assert wel.q is not None
    q_arr = wel.q if not hasattr(wel.q, "values") else wel.q.values
    assert float(q_arr[0, node]) == pytest.approx(-75.0)


def test_wel_period_double_aux_ingress_from_file():
    """structure_component reconstructs WEL with two aux variables from a raw MF6 input string."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Wel

    text = """
BEGIN options
  AUXILIARY well_id temp
  PRINT_INPUT
END options
BEGIN period 1
  1 2 3 -75.000000000e+00 1.000000000e+00 2.500000000e+01
END period 1
"""
    raw = loads(text)
    # nlay=1, nrow=5, ncol=5 → 25 nodes; (0,1,2) → flat index 7
    wel = structure_component(raw, Wel, dims={"nper": 1, "nodes": 25, "nrow": 5, "ncol": 5})

    assert wel.aux is not None
    aux_arr = wel.aux if not hasattr(wel.aux, "values") else wel.aux.values
    assert aux_arr.ndim == 3
    assert aux_arr.shape[0] == 1  # nper
    assert aux_arr.shape[2] == 2  # naux=2
    node = 0 * 5 + 1 * 5 + 2  # (0,1,2) → 7
    assert float(aux_arr[0, node, 0]) == pytest.approx(1.0)
    assert float(aux_arr[0, node, 1]) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Period-block aux for GWT/GWE transport and GWF array-recharge packages
# ---------------------------------------------------------------------------


def test_cnc_period_aux_roundtrip():
    """GWT CNC: conc + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.cnc import Cnc

    # node (2,) with explicit dims — no GWT model parent needed
    cnc = Cnc(
        auxiliary=["tracer_id"],
        conc={0: {(2,): 35.0}},
        aux={0: {(2,): 99.0}},
        dims={"nper": 1, "nodes": 5},
    )

    text = dumps(unstructure_component(cnc))
    assert "35" in text
    assert "99" in text

    raw = loads(text)
    cnc2 = structure_component(raw, Cnc, dims={"nper": 1, "nodes": 5})

    assert cnc2.conc is not None
    assert cnc2.aux is not None
    conc_arr = cnc2.conc if not hasattr(cnc2.conc, "values") else cnc2.conc.values
    aux_arr = cnc2.aux if not hasattr(cnc2.aux, "values") else cnc2.aux.values
    assert float(conc_arr[0, 2]) == pytest.approx(35.0)
    assert aux_arr.shape == (1, 5, 1)
    assert float(aux_arr[0, 2, 0]) == pytest.approx(99.0)


def test_src_period_aux_roundtrip():
    """GWT SRC: smassrate + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.src import Src

    # node (3,) with explicit dims
    src = Src(
        auxiliary=["src_id"],
        smassrate={0: {(3,): 0.5}},
        aux={0: {(3,): 7.0}},
        dims={"nper": 1, "nodes": 5},
    )

    text = dumps(unstructure_component(src))
    assert "0.5" in text
    assert "7" in text

    raw = loads(text)
    src2 = structure_component(raw, Src, dims={"nper": 1, "nodes": 5})

    assert src2.smassrate is not None
    assert src2.aux is not None
    rate_arr = src2.smassrate if not hasattr(src2.smassrate, "values") else src2.smassrate.values
    aux_arr = src2.aux if not hasattr(src2.aux, "values") else src2.aux.values
    assert float(rate_arr[0, 3]) == pytest.approx(0.5)
    assert aux_arr.shape == (1, 5, 1)
    assert float(aux_arr[0, 3, 0]) == pytest.approx(7.0)


def test_ctp_period_aux_roundtrip():
    """GWE CTP: temp + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.ctp import Ctp

    # node (1,) with explicit dims
    ctp = Ctp(
        auxiliary=["zone"],
        temp={0: {(1,): 20.0}},
        aux={0: {(1,): 3.0}},
        dims={"nper": 1, "nodes": 5},
    )

    text = dumps(unstructure_component(ctp))
    assert "20" in text
    assert "3" in text

    raw = loads(text)
    ctp2 = structure_component(raw, Ctp, dims={"nper": 1, "nodes": 5})

    assert ctp2.temp is not None
    assert ctp2.aux is not None
    temp_arr = ctp2.temp if not hasattr(ctp2.temp, "values") else ctp2.temp.values
    aux_arr = ctp2.aux if not hasattr(ctp2.aux, "values") else ctp2.aux.values
    assert float(temp_arr[0, 1]) == pytest.approx(20.0)
    assert aux_arr.shape == (1, 5, 1)
    assert float(aux_arr[0, 1, 0]) == pytest.approx(3.0)


def test_esl_period_aux_roundtrip():
    """GWE ESL: senerrate + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.esl import Esl

    # node (4,) with explicit dims
    esl = Esl(
        auxiliary=["esl_id"],
        senerrate={0: {(4,): 1.25}},
        aux={0: {(4,): 55.0}},
        dims={"nper": 1, "nodes": 5},
    )

    text = dumps(unstructure_component(esl))
    assert "1.25" in text
    assert "55" in text

    raw = loads(text)
    esl2 = structure_component(raw, Esl, dims={"nper": 1, "nodes": 5})

    assert esl2.senerrate is not None
    assert esl2.aux is not None
    rate_arr = esl2.senerrate if not hasattr(esl2.senerrate, "values") else esl2.senerrate.values
    aux_arr = esl2.aux if not hasattr(esl2.aux, "values") else esl2.aux.values
    assert float(rate_arr[0, 4]) == pytest.approx(1.25)
    assert aux_arr.shape == (1, 5, 1)
    assert float(aux_arr[0, 4, 0]) == pytest.approx(55.0)


def test_rch_period_aux_roundtrip():
    """GWF RCH: recharge + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.rch import Rch

    # node (0,) with explicit dims
    rch = Rch(
        auxiliary=["rch_id"],
        recharge={0: {(0,): 0.001}},
        aux={0: {(0,): 42.0}},
        dims={"nper": 1, "nodes": 5},
    )

    text = dumps(unstructure_component(rch))
    assert "0.001" in text
    assert "42" in text

    raw = loads(text)
    rch2 = structure_component(raw, Rch, dims={"nper": 1, "nodes": 5})

    assert rch2.recharge is not None
    assert rch2.aux is not None
    rch_arr = rch2.recharge if not hasattr(rch2.recharge, "values") else rch2.recharge.values
    aux_arr = rch2.aux if not hasattr(rch2.aux, "values") else rch2.aux.values
    assert float(rch_arr[0, 0]) == pytest.approx(0.001)
    assert aux_arr.shape == (1, 5, 1)
    assert float(aux_arr[0, 0, 0]) == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# G/A variant aux — RCHA and CHDG with auxiliary period arrays
# ---------------------------------------------------------------------------


def test_rcha_period_aux_dump():
    """RCHA aux array is written as a named readarray block per variable."""
    from flopy4.mf6.gwf import Dis, Gwf, Rcha

    nlay = 1
    nrow = 3
    ncol = 3
    ncpl = nrow * ncol

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    recharge = np.full(ncpl, FILL_DNODATA, dtype=float)
    recharge[4] = 1.0e-3
    aux = np.full(ncpl, FILL_DNODATA, dtype=float)
    aux[4] = 7.0

    rch = Rcha(
        parent=gwf,
        auxiliary=["tracer"],
        recharge=np.expand_dims(recharge, axis=0),
        aux=np.expand_dims(np.expand_dims(aux, axis=0), axis=-1),  # (nper, ncpl, naux)
        dims={"nper": 1, "naux": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCHA aux dump:")
    print(dumped)

    assert "READASARRAYS" in dumped.upper()
    assert "AUXILIARY TRACER" in dumped.upper()
    assert "BEGIN PERIOD 1" in dumped.upper()
    assert "RECHARGE" in dumped.upper()
    assert "TRACER" in dumped.upper()

    # aux variable block appears under its name, not as "aux"
    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0]
    assert "tracer" in period_section.lower()
    assert " aux " not in period_section.lower()


def test_chdg_period_aux_dump():
    """CHDG aux array is written as a named readarray block per variable."""
    from flopy4.mf6.gwf import Chdg, Dis, Gwf

    nlay = 1
    nrow = 3
    ncol = 3
    ncpl = nrow * ncol

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    head = np.full(ncpl, FILL_DNODATA, dtype=float)
    head[0] = 1.0
    aux = np.full(ncpl, FILL_DNODATA, dtype=float)
    aux[0] = 99.0

    chd = Chdg(
        parent=gwf,
        auxiliary=["well_id"],
        head=np.expand_dims(head, axis=0),
        aux=np.expand_dims(np.expand_dims(aux, axis=0), axis=-1),
        dims={"nper": 1, "naux": 1},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHDG aux dump:")
    print(dumped)

    assert "READARRAYGRID" in dumped.upper()
    assert "AUXILIARY WELL_ID" in dumped.upper()
    assert "BEGIN PERIOD 1" in dumped.upper()
    assert "WELL_ID" in dumped.upper()

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0]
    assert "well_id" in period_section.lower()
    assert " aux " not in period_section.lower()


def test_rcha_period_double_aux_dump():
    """RCHA with two aux variables emits two named readarray blocks."""
    from flopy4.mf6.gwf import Dis, Gwf, Rcha

    nlay = 1
    nrow = 2
    ncol = 2
    ncpl = nrow * ncol

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    recharge = np.zeros(ncpl, dtype=float)
    recharge[0] = 1.0e-4
    aux = np.zeros((ncpl, 2), dtype=float)
    aux[0, 0] = 5.0
    aux[0, 1] = 10.0

    rch = Rcha(
        parent=gwf,
        auxiliary=["tracer_a", "tracer_b"],
        recharge=np.expand_dims(recharge, axis=0),
        aux=np.expand_dims(aux, axis=0),  # (nper, ncpl, naux)
        dims={"nper": 1, "naux": 2},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCHA double aux dump:")
    print(dumped)

    assert "TRACER_A" in dumped.upper()
    assert "TRACER_B" in dumped.upper()

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0]
    assert "tracer_a" in period_section.lower()
    assert "tracer_b" in period_section.lower()


def test_evt_period_aux_roundtrip():
    """EVT aux column round-trips through dumps/loads/structure_component.

    EVT is list-based: aux is a trailing inline column in each period row.
    All six period fields must be present in each row so the ingress can
    back-compute ncelldim = len(row) - n_value - naux correctly.
    """
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Dis, Evt, Gwf

    nlay = 1
    nrow = 3
    ncol = 3
    ncpl = nrow * ncol

    dis = Dis(nlay=nlay, nrow=nrow, ncol=ncol)
    gwf = Gwf(dis=dis)

    def _field(val):
        a = np.full(ncpl, FILL_DNODATA, dtype=float)
        a[4] = val
        return np.expand_dims(a, axis=0)

    aux = np.full(ncpl, FILL_DNODATA, dtype=float)
    aux[4] = 3.14

    evt = Evt(
        parent=gwf,
        auxiliary=["et_zone"],
        surface=_field(10.0),
        rate=_field(1.5e-3),
        depth=_field(2.0),
        pxdp=_field(0.5),
        petm=_field(0.9),
        petm0=_field(0.1),
        aux=np.expand_dims(np.expand_dims(aux, axis=0), axis=-1),
        dims={"nper": 1, "naux": 1},
    )

    text = dumps(unstructure_component(evt))
    assert "AUXILIARY ET_ZONE" in text.upper()
    assert "3.14" in text

    raw = loads(text)
    evt2 = structure_component(
        raw, Evt, dims={"nper": 1, "nlay": nlay, "nrow": nrow, "ncol": ncol, "nodes": ncpl}
    )

    assert evt2.surface is not None
    assert evt2.aux is not None
    surf_arr = evt2.surface if not hasattr(evt2.surface, "values") else evt2.surface.values
    aux_arr = evt2.aux if not hasattr(evt2.aux, "values") else evt2.aux.values
    assert float(surf_arr[0, 4]) == pytest.approx(10.0)
    assert aux_arr.shape == (1, ncpl, 1)
    assert float(aux_arr[0, 4, 0]) == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# SPC / TVK / TVS — options-only packages with path(inout="filein")
# ---------------------------------------------------------------------------
