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
    assert pb_int["period 3"]["save budget"] == "last"  # fill-forward


def test_oc_period_wildcard_fillforward():
    """'*' key sets period 0 and fills forward to all nper periods."""
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
    assert pb["period 2"]["save budget"] == "STEPS 1 3 5"  # fill-forward
    assert pb["period 2"]["print budget"] == "last"


def test_oc_period_stop_sentinel():
    """Empty string '' stops fill-forward: subsequent periods omit that field."""
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
        nsources=2,
        pname=np.array(["chd-1", "rch-1"]),
        srctype=np.array(["AUX", "AUXMIXED"]),
        auxname=np.array(["conc", "conc"]),
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
        nsources=3,
        pname=np.array(["pkg-a", "pkg-b", "pkg-c"]),
        srctype=np.array(["AUX", "AUX", "AUXMIXED"]),
        auxname=np.array(["c1", "c2", "c3"]),
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


def test_ssm_fileinput_row_format():
    """fileinput rows must serialise as 'pname SPC6 FILEIN spc6_filename [MIXED]'."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm

    ssm = Ssm(
        nfileinput=2,
        fi_pname=np.array(["rch-1", "wel-1"]),
        fi_spc6_filename=np.array(["rch.spc6", "wel.spc6"]),
        fi_mixed=np.array([True, False]),
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
        nfileinput=1,
        fi_pname=np.array(["rch-1"]),
        fi_spc6_filename=np.array(["rch.spc6"]),
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
        nsources=1,
        pname=np.array(["chd-1"]),
        srctype=np.array(["AUX"]),
        auxname=np.array(["conc"]),
        nfileinput=1,
        fi_pname=np.array(["rch-1"]),
        fi_spc6_filename=np.array(["rch.spc6"]),
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
