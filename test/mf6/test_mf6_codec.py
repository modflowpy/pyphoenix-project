"""Test the MF6 input file reading/writing capability."""

from pathlib import Path
from pprint import pprint

import numpy as np
import pytest
import xarray as xr

from flopy4.mf6.codec import dumps, loads, writer
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converter import COMPONENT_CONVERTER
from flopy4.mf6.load_context import LoadContext


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


def test_loads_number_only_as_whole_token():
    mf6_input = """
BEGIN options
  start_date_time 1997-07-16T19:20:30.45+01:00
  ts6 filein 1model.ts
  x 1,2.5 .5 7. 1e5 3 # comment
  y -5 +2 -1.5e3 1D-5 8.2d-4
END options
"""

    result = loads(mf6_input)
    assert result["options"] == [
        ["start_date_time", "1997-07-16T19:20:30.45+01:00"],
        ["ts6", "filein", "1model.ts"],
        ["x", 1, 2.5, 0.5, 7.0, 1e5, 3],
        ["y", -5, 2, -1500.0, 1e-5, 8.2e-4],
    ]


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
    from flopy4.mf6.gwf import Sto

    sto = Sto(
        stress_period_data={
            0: [("TRANSIENT",)],
            1: [("STEADY-STATE",)],
            2: [("TRANSIENT",)],
        }
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
        stress_period_data={
            0: [
                ("SAVE", "HEAD", "ALL"),
                ("SAVE", "BUDGET", "ALL"),
                ("PRINT", "HEAD", "ALL"),
                ("PRINT", "BUDGET", "ALL"),
            ]
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print("OC dump:")
    print(dumped)
    assert "SAVE HEAD ALL" in dumped
    assert "SAVE BUDGET ALL" in dumped
    assert "PRINT HEAD ALL" in dumped
    assert "PRINT BUDGET ALL" in dumped
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
        stress_period_data={
            0: [
                ("SAVE", "HEAD", "LAST"),
                ("SAVE", "BUDGET", "FIRST"),
                ("PRINT", "HEAD", "FIRST"),
            ]
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    print("OC dump:")
    print(dumped)
    assert "SAVE HEAD LAST" in dumped
    assert "SAVE BUDGET FIRST" in dumped
    assert "PRINT HEAD FIRST" in dumped
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
    assert loaded["DIMENSIONS"] == [["NLAY", 2], ["NROW", 10], ["NCOL", 10]]
    assert ["DELR"] in loaded["GRIDDATA"]
    assert ["DELC"] in loaded["GRIDDATA"]


def test_dumps_dis_with_layered_arrays(dis_with_constant_arrays):
    dis = dis_with_constant_arrays
    dis.delr[0] = 101.0
    dis.botm[0] = -1.0  # modify first cell of layer 0 to force layered output
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
        vertices=dict(iv=[0, 1, 2, 3], xv=[0.0, 0.0, 1.0, 1.0], yv=[0.0, 1.0, 1.0, 0.0]),
        cell2d=[Disv.Cell2d(0, 0.50000000, 0.50000000, 5, (0, 1, 2, 3, 0))],
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
    disv.botm[0] = 20.0  # modify first cell to force layered output
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


def test_tdis_nper_from_perioddata():
    from flopy4.mf6.tdis import Tdis

    assert Tdis(perioddata=[(1.0, 1, 1.0), (2.0, 2, 1.5)]).nper == 2
    tdis = Tdis(nper=3)
    assert [r.nstp for r in tdis.perioddata] == [1, 1, 1]
    with pytest.raises(ValueError, match="nper"):
        Tdis(nper=2, perioddata=[(1.0, 1, 1.0)] * 3)
    # perioddata's shape is exact (nper): too few rows is an error too
    with pytest.raises(ValueError, match="nper"):
        Tdis(nper=3, perioddata=[(1.0, 1, 1.0)] * 2)


def test_tdis_nper_default_is_still_explicit():
    """An explicit nper equal to the DFN default (1) is checked like any other."""
    from flopy4.mf6.tdis import Tdis

    tdis = Tdis()
    assert tdis.nper == 1
    assert [r.nstp for r in tdis.perioddata] == [1]
    assert Tdis(perioddata=[(1.0, 1, 1.0)] * 3).nper == 3
    with pytest.raises(ValueError, match="nper"):
        Tdis(nper=1, perioddata=[(1.0, 1, 1.0)] * 3)
    # only the default row is repeated to fill nper, not an equal explicit one
    assert len(Tdis(nper=3).perioddata) == 3
    with pytest.raises(ValueError, match="nper"):
        Tdis(nper=3, perioddata=((1.0, 1, 1.0),))


def test_ats_maxats_bounds_perioddata():
    """ATS perioddata's shape is a bound ("<=maxats"): fewer rows than an
    explicit maxats is fine, more is an error."""
    from flopy4.mf6.utl import Ats

    row = (1, 1.0, 0.1, 10.0, 2.0, 5.0)
    assert Ats(perioddata=[row, row]).maxats == 2
    assert Ats(maxats=5, perioddata=[row, row]).maxats == 5
    with pytest.raises(ValueError, match="maxats"):
        Ats(maxats=2, perioddata=[row] * 3)
    # an explicit maxats equal to the DFN default (1) still bounds the rows
    with pytest.raises(ValueError, match="maxats"):
        Ats(maxats=1, perioddata=[row, row])
    assert Ats().maxats is None


def test_tdis_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.tdis import Tdis

    tdis = Tdis(perioddata=[(1.0, 1, 1.0), (2.0, 2, 1.5)])
    text = dumps(unstructure_component(tdis))
    raw = loads(text)
    tdis2 = structure_component(raw, Tdis)
    assert tdis2.nper == 2
    assert tdis2.perioddata == tdis.perioddata


def test_disv_vertices_roundtrip(disv_with_constant_arrays):
    dumped = dumps(COMPONENT_CONVERTER.unstructure(disv_with_constant_arrays))
    assert "BEGIN VERTICES" in dumped
    assert "END VERTICES" in dumped

    loaded = loads(dumped)
    vertices = loaded["VERTICES"]
    assert len(vertices) == 4
    # iv values are 1-based in the MF6 file
    assert vertices[0][0] == 1
    assert vertices[1][0] == 2
    assert vertices[2][0] == 3
    assert vertices[3][0] == 4
    # xv, yv values match the fixture: xv=[0,0,1,1], yv=[0,1,1,0]
    assert vertices[0][1] == pytest.approx(0.0)
    assert vertices[0][2] == pytest.approx(0.0)
    assert vertices[2][1] == pytest.approx(1.0)
    assert vertices[2][2] == pytest.approx(1.0)


def test_disu_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Disu

    # two unit cells side by side
    disu = Disu(
        nodes=2,
        nja=4,
        nvert=6,
        top=1.0,
        bot=0.0,
        area=1.0,
        iac=[2, 2],
        ja=[0, 1, 1, 0],
        ihc=[0, 1, 0, 1],
        cl12=[0.0, 0.5, 0.0, 0.5],
        hwva=[0.0, 1.0, 0.0, 1.0],
        vertices=[
            (0, 0.0, 0.0),
            (1, 0.0, 1.0),
            (2, 1.0, 1.0),
            (3, 1.0, 0.0),
            (4, 2.0, 1.0),
            (5, 2.0, 0.0),
        ],
        cell2d=[
            Disu.Cell2d(0, 0.5, 0.5, 5, (0, 1, 2, 3, 0)),
            Disu.Cell2d(1, 1.5, 0.5, 5, (3, 2, 4, 5, 3)),
        ],
    )
    assert disu.get_dims() == {"nodes": 2, "nja": 4, "nvert": 6, "ncelldim": 1, "njas": 1}

    text = dumps(unstructure_component(disu))
    raw = loads(text)
    # MF6 reads CONNECTIONDATA before VERTICES and CELL2D
    assert list(raw)[-4:] == ["GRIDDATA", "CONNECTIONDATA", "VERTICES", "CELL2D"]
    # ja is 0-based, 1-based in the file
    conn = raw["CONNECTIONDATA"]
    assert conn[conn.index(["JA"]) + 2] == [1, 2, 2, 1]

    disu2 = structure_component(raw, Disu)
    for name in ("top", "bot", "area", "iac", "ja", "ihc", "cl12", "hwva"):
        np.testing.assert_array_equal(getattr(disu2, name), getattr(disu, name))
    assert disu2.vertices == disu.vertices
    assert disu2.cell2d == disu.cell2d

    grid = disu2.to_grid()
    assert grid.nnodes == 2
    np.testing.assert_array_equal(grid.ja, [0, 1, 1, 0])


@pytest.mark.parametrize("dims", [None, {"nlay": 1, "nrow": 2, "ncol": 3}])
def test_gnc_round_trip(dims):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Gnc

    gnc = Gnc(
        gncdata=[
            Gnc.Gncdata((0, 0, 1), (0, 0, 2), ((0, 1, 1), (0, 1, 2)), (0.25, 0.25)),
            # a zero (dummy) cellid in the file is -1 in python
            Gnc.Gncdata((0, 1, 1), (0, 1, 2), ((0, 0, 1), (-1, -1, -1)), (0.5, 0.0)),
        ],
    )
    assert (gnc.numgnc, gnc.numalphaj) == (2, 2)
    raw = loads(dumps(unstructure_component(gnc)))
    assert raw["GNCDATA"] == [
        [1, 1, 2, 1, 1, 3, 1, 2, 2, 1, 2, 3, 0.25, 0.25],
        [1, 2, 2, 1, 2, 3, 1, 1, 2, 0, 0, 0, 0.5, 0.0],
    ]
    assert structure_component(raw, Gnc, context=LoadContext(dims=dims)).gncdata == gnc.gncdata


def test_gnc_numalphaj_mismatch():
    from flopy4.mf6.gwf import Gnc

    row = Gnc.Gncdata((0,), (1,), ((2,), (3,)), (0.25, 0.25))
    with pytest.raises(ValueError, match="numalphaj=1 but cellidsj has 2 values"):
        Gnc(numalphaj=1, gncdata=[row])


def test_evt_segments_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Evt

    evt = Evt(
        stress_period_data={
            0: [
                ((0, 0, 0), 59.0, 0.01, 6.0, (0.5, 0.9), (1.0, 0.7)),
                ((0, 0, 1), 59.0, "etrate", 6.0, (0.4, "pxdp2"), (0.9, 0.6)),
            ]
        },
    )
    assert evt.nseg == 3
    raw = loads(dumps(unstructure_component(evt)))
    assert raw["PERIOD 1"][0] == [1, 1, 1, 59.0, 0.01, 6.0, 0.5, 0.9, 1.0, 0.7]
    evt2 = structure_component(
        raw, Evt, context=LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 2})
    )
    assert evt2.stress_period_data == evt.stress_period_data


def test_ts_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl import Ts

    ts = Ts(
        time_series_name=Ts.TimeSeriesName(time_series_names=["a", "b"]),
        interpolation_method=Ts.InterpolationMethod(interpolation_method=["linear", "stepwise"]),
        timeseries=[(0.0, (1.0, 2.0)), (10.0, (3.0, 4.0))],
    )
    raw = loads(dumps(unstructure_component(ts)))
    assert raw["TIMESERIES"] == [[0.0, 1.0, 2.0], [10.0, 3.0, 4.0]]
    ts2 = structure_component(raw, Ts)
    assert ts2.time_series_name == ts.time_series_name
    assert ts2.timeseries == ts.timeseries


def test_ts_names_mismatch():
    from flopy4.mf6.utl import Ts

    with pytest.raises(ValueError, match="time_series_names=1 but ts_array has 2 values"):
        Ts(
            time_series_name=Ts.TimeSeriesName(time_series_names=["a"]),
            timeseries=[(0.0, (1.0, 2.0))],
        )


def test_ts_reference_must_name_a_series(function_tmpdir, monkeypatch):
    """Writing checks that each name in a time-series column, aux and
    keystring rows included, is a series the package's TS6 files define,
    in any case, as MF6 needs."""
    from flopy4.mf6.gwf import Chd, Maw
    from flopy4.mf6.utl import Ts

    monkeypatch.chdir(function_tmpdir)

    def ts(name):
        return Ts(
            time_series_name=Ts.TimeSeriesName(time_series_names=[name]),
            interpolation_method=Ts.InterpolationMethod(interpolation_method=["linear"]),
            timeseries=[(0.0, (1.0,)), (10.0, (2.0,))],
        )

    chd = Chd(
        auxiliary=["conc"],
        stress_period_data={0: [Chd.StressPeriodData(cellid=(0, 0, 0), head="HeadSeries")]},
        ts=[ts("headseries")],
        filename=function_tmpdir / "gwf.chd",
    )
    chd.write()

    chd.stress_period_data = {
        0: [Chd.StressPeriodData(cellid=(0, 0, 0), head=1.0, aux=("concseries",))]
    }
    with pytest.raises(
        ValueError, match=r"stress_period_data: period 0 names .*'concseries'.*\['headseries'\]"
    ):
        chd.write()

    maw = Maw(
        packagedata=[(0, 0.1, -10.0, 5.0, "THIEM", 1)],
        connectiondata=[(0, 0, (0, 0, 0), 0.0, -10.0, 1.0, 0.2)],
        stress_period_data={0: [Maw.Rate(ifno=0, rate="pumping")]},
        filename=function_tmpdir / "gwf.maw",
    )
    with pytest.raises(ValueError, match=r"'pumping'.*none"):
        maw.write()
    maw.ts.append(ts("pumping"))
    maw.write()
    assert "pumping" in (function_tmpdir / "gwf.maw").read_text()


def test_maw_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Maw

    maw = Maw(
        packagedata=[(0, 0.1, -10.0, 5.0, "THIEM", 2), (1, 0.1, -10.0, 5.0, "SKIN", 1)],
        connectiondata=[
            (0, 0, (0, 0, 0), 0.0, -10.0, 1.0, 0.2),
            (0, 1, (1, 0, 0), 0.0, -10.0, 1.0, 0.2),
            (1, 0, (0, 0, 1), 0.0, -10.0, 1.0, 0.2),
        ],
        stress_period_data={
            0: [Maw.Rate(ifno=0, rate=-100.0), Maw.Status(ifno=1, status="INACTIVE")]
        },
    )
    raw = loads(dumps(unstructure_component(maw)))
    assert raw["CONNECTIONDATA"][1] == [1, 2, 2, 1, 1, 0.0, -10.0, 1.0, 0.2]
    maw2 = structure_component(
        raw, Maw, context=LoadContext(dims={"nlay": 2, "nrow": 1, "ncol": 2})
    )
    assert maw2.packagedata == maw.packagedata
    assert maw2.connectiondata == maw.connectiondata
    assert maw2.stress_period_data == maw.stress_period_data


def test_hfb_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Hfb

    hfb = Hfb(
        stress_period_data={0: [((0, 0, 0), (0, 0, 1), 0.001), ((0, 1, 0), (0, 1, 1), 0.002)]}
    )
    assert hfb.maxhfb == 2
    raw = loads(dumps(unstructure_component(hfb)))
    assert raw["PERIOD 1"][0] == [1, 1, 1, 1, 1, 2, 0.001]
    hfb2 = structure_component(
        raw, Hfb, context=LoadContext(dims={"nlay": 1, "nrow": 2, "ncol": 2})
    )
    assert hfb2.stress_period_data == hfb.stress_period_data


def test_uzf_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Uzf

    uzf = Uzf(
        packagedata=[
            (0, (0,), 1, 1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
            (1, (1,), 0, -1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
        ],
        stress_period_data={0: [(0, 0.01, 0.001, 2.25, 0.05, 0.0, 0.0, 0.0)]},
    )
    raw = loads(dumps(unstructure_component(uzf)))
    # ivertcon 1 -> 2; -1 (no underlying cell) -> 0
    assert [r[3] for r in raw["PACKAGEDATA"]] == [2, 0]
    uzf2 = structure_component(raw, Uzf, context=LoadContext(dims={"nodes": 2}))
    assert uzf2.packagedata == uzf.packagedata
    assert uzf2.stress_period_data == uzf.stress_period_data


def test_sfr_connections_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Sfr

    reach = (1.0, 1.0, 1e-3, 0.0, 0.1, 0.0, 0.03)
    sfr = Sfr(
        packagedata=[
            (0, (0, 0, 0), *reach, 1, 1.0, 0),
            (1, (0, 0, 1), *reach, 2, 1.0, 0),
            (2, (0, 0, 2), *reach, 1, 1.0, 0),
        ],
        connectiondata=[(0, ((1, -1),)), (1, ((0, 1), (2, -1))), (2, ((1, 1),))],
    )
    # ints as in the file: 1-based, signed
    assert Sfr(packagedata=sfr.packagedata, connectiondata=[(0, -2), (1, 1, -3), (2, 2)]) == sfr
    raw = loads(dumps(unstructure_component(sfr)))
    assert raw["CONNECTIONDATA"] == [[1, -2], [2, 1, -3], [3, 2]]
    sfr2 = structure_component(
        raw, Sfr, context=LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 3})
    )
    assert sfr2.connectiondata == sfr.connectiondata


def test_sfr_ncon_mismatch():
    from flopy4.mf6.gwf import Sfr

    reach = (1.0, 1.0, 1e-3, 0.0, 0.1, 0.0, 0.03)
    with pytest.raises(ValueError, match="ic has 2 values but packagedata.ncon is 1"):
        Sfr(
            packagedata=[(0, (0, 0, 0), *reach, 1, 1.0, 0), (1, (0, 0, 1), *reach, 1, 1.0, 0)],
            connectiondata=[(0, ((1, -1), (1, 1))), (1, ((0, 1),))],
        )


def test_sfr_signed_index_zero():
    from flopy4.mf6.gwf import Sfr

    with pytest.raises(ValueError, match="1-based, got 0"):
        Sfr.Connectiondata(ifno=0, ic=(0,))


def test_sfr_diversion_keyword_after_row_key():
    from flopy4.mf6.gwf import Sfr

    # the keyword follows the row key (ifno) but precedes other index columns
    div = Sfr.Diversion(ifno=0, idv=1, divflow=0.5)
    assert div.to_tokens() == (1, "DIVERSION", 2, 0.5)
    assert Sfr.Diversion.from_tokens([1, "diversion", 2, 0.5]) == div


def test_sfr_unconnected_reach_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Sfr

    reach = (1.0, 1.0, 1e-3, 0.0, 0.1, 0.0, 0.03)
    sfr = Sfr(
        packagedata=[(0, (0, 0, 0), *reach, 1, 1.0, 0), (1, None, *reach, 1, 1.0, 0)],
        connectiondata=[(0, ((1, -1),)), (1, ((0, 1),))],
    )
    raw = loads(dumps(unstructure_component(sfr)))
    assert raw["PACKAGEDATA"][1][1] == "NONE"
    sfr2 = structure_component(
        raw, Sfr, context=LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 1})
    )
    assert sfr2.packagedata == sfr.packagedata


def test_loads_block_header_remark():
    # MF6 ignores anything after the block index (MAW's legacy STEADY-STATE)
    raw = loads("BEGIN PERIOD 1 STEADY-STATE\n  1 RATE -1.0\nEND PERIOD\n")
    assert raw == {"PERIOD 1": [[1, "RATE", -1.0]]}


def test_record_flag_options():
    """A record that's a keyword and its options, all optional, can be
    given as a bool: True is the bare record, False leaves it out."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwf import Gwf, Npf

    gwf = Gwf(name="m", newtonoptions=True)
    assert gwf.newtonoptions == Gwf.Newtonoptions()
    assert "\n NEWTON\n" in dumps(unstructure_component(gwf))
    gwf.newtonoptions = False
    assert gwf.newtonoptions is None
    assert "NEWTON" not in dumps(unstructure_component(gwf))
    gwf.newtonoptions = Gwf.Newtonoptions(under_relaxation=True)
    assert "NEWTON UNDER_RELAXATION" in dumps(unstructure_component(gwf))

    npf = Npf(xt3doptions=True, cvoptions=np.True_, k=1.0)
    text = dumps(unstructure_component(npf))
    assert "\n XT3D\n" in text
    assert "\n VARIABLECV\n" in text


@pytest.mark.parametrize("model", ["gwf", "gwt", "gwe", "prt"])
def test_model_list_option_name(model):
    import importlib

    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    cls = getattr(importlib.import_module(f"flopy4.mf6.{model}"), model.capitalize())
    text = dumps(unstructure_component(cls(name="m", list_="m.lst")))
    assert " LIST m.lst" in text
    assert "LIST_" not in text


def test_simulation_options_roundtrip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.simulation import Simulation

    text = """BEGIN OPTIONS
  CONTINUE
  NOCHECK
  MEMORY_PRINT_OPTION summary
  MAXERRORS 5
  PRINT_INPUT
END OPTIONS
BEGIN SOLUTIONGROUP 1
  MXITER 3
END SOLUTIONGROUP
"""
    sim = structure_component(loads(text), Simulation)
    assert sim.continue_ and sim.nocheck and sim.print_input
    assert sim.memory_print_option == "summary"
    assert sim.maxerrors == 5
    assert sim.mxiter == 3

    out = dumps(unstructure_component(sim))
    for line in ("CONTINUE", "NOCHECK", "MEMORY_PRINT_OPTION summary", "MAXERRORS 5", "MXITER 3"):
        assert f" {line}\n" in out
    assert "CONTINUE_" not in out


def test_oc_head_file_and_print_format():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Oc

    text = """BEGIN OPTIONS
  HEAD FILEOUT m.hds
  HEAD PRINT_FORMAT COLUMNS 10 WIDTH 11 DIGITS 4 GENERAL
END OPTIONS
BEGIN PERIOD 1
  SAVE HEAD STEPS 1 5 10
END PERIOD
"""
    oc = structure_component(loads(text), Oc)
    assert str(oc.head_file) == "m.hds"
    assert oc.headprint.formatrecord.columns == 10
    out = dumps(unstructure_component(oc))
    assert "HEAD FILEOUT m.hds" in out
    assert "HEAD PRINT_FORMAT COLUMNS 10 WIDTH 11 DIGITS 4 GENERAL" in out
    assert "STEPS 1 5 10\n" in out


def test_ims_rclose_and_unknown_block():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.ims import Ims

    text = """BEGIN LINEAR
  INNER_MAXIMUM 50
  INNER_RCLOSE 1.0e-5 STRICT
  LINEAR_ACCELERATION bicgstab
END LINEAR
BEGIN XMD
  INNER_MAXIMUM 30
  LINEAR_ACCELERATION cg
END XMD
"""
    with pytest.warns(UserWarning, match="unknown block XMD"):
        ims = structure_component(loads(text), Ims)
    assert ims.inner_maximum == 50
    assert ims.linear_acceleration == "bicgstab"
    assert (ims.rclose.inner_rclose, ims.rclose.rclose_option) == (1e-5, "STRICT")
    assert "INNER_RCLOSE 1e-05 STRICT" in dumps(unstructure_component(ims))


def test_dumps_chd():
    from flopy4.mf6.gwf import Chd

    chd = Chd(
        save_flows=True,
        print_input=True,
        stress_period_data={0: [((0, 0, 0), 10.0), ((0, 9, 9), 20.0)]},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD dump:")
    print(dumped)

    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    assert "1 1 1 10.0" in dumped
    assert "1 10 10 20.0" in dumped
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
    pprint(loaded)


@pytest.mark.parametrize(
    "style",
    ["list_of_tuples", "recarray", "dict_of_columns", "list_of_dicts"],
)
def test_chd_spd_input_styles(style):
    """All SPD input styles produce identical MF6 output."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.chd import Chd

    # Build SPD in each style for the same 2-cell boundary
    if style == "list_of_tuples":
        spd = {0: [((0, 0, 0), 1.0), ((0, 9, 9), 0.0)]}
    elif style == "recarray":
        dtype = np.dtype([("cellid", np.int64, (3,)), ("head", "O")])
        arr = np.zeros(2, dtype=dtype)
        arr["cellid"][0] = (0, 0, 0)
        arr["cellid"][1] = (0, 9, 9)
        arr["head"][0] = 1.0
        arr["head"][1] = 0.0
        spd = {0: arr.view(np.recarray)}
    elif style == "dict_of_columns":
        spd = {0: {"cellid": [(0, 0, 0), (0, 9, 9)], "head": [1.0, 0.0]}}
    elif style == "list_of_dicts":
        spd = {0: [{"cellid": (0, 0, 0), "head": 1.0}, {"cellid": (0, 9, 9), "head": 0.0}]}

    chd = Chd(stress_period_data=spd)
    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))

    # All styles must produce the same period block
    assert "BEGIN PERIOD 1" in dumped
    assert "1 1 1 1.0" in dumped
    assert "1 10 10 0.0" in dumped

    # Round-trip: reload and verify recarray contents
    loaded = loads(dumped)
    chd2 = structure_component(loaded, Chd)
    rec = chd2.stress_period_data[0]
    assert len(rec) == 2
    assert tuple(rec[0].cellid) == (0, 0, 0)
    assert float(rec[0].head) == 1.0
    assert tuple(rec[1].cellid) == (0, 9, 9)
    assert float(rec[1].head) == 0.0


def test_dumps_chdg():
    """Chdg (G-variant CHD) uses READARRAY period arrays (head per stress period)."""
    from flopy4.mf6.gwf import Chdg

    nper, nlay, ncpl = 1, 2, 9
    FILL = 3.0e30
    head = np.full((nper, nlay, ncpl), FILL, dtype=float)
    head[0, 0, 0] = 1.0
    head[0, 0, 8] = 0.0

    chd = Chdg(
        save_flows=True,
        print_input=True,
        head=head,
        dims={"nper": nper, "ncpl": ncpl, "nlay": nlay},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHDG dump:")
    print(dumped)

    assert "READARRAYGRID" in dumped
    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped
    assert "HEAD LAYERED" in dumped
    assert "INTERNAL" in dumped
    assert "1.0" in dumped
    assert "0.0" in dumped

    loaded = loads(dumped)
    print("CHDG load:")
    pprint(loaded)


def test_dumps_rcha():
    """Rcha (A-variant RCH) uses READARRAY period arrays (recharge per stress period)."""
    from flopy4.mf6.gwf import Rcha

    nper, ncpl = 1, 9
    FILL = 3.0e30
    recharge = np.full((nper, ncpl), FILL, dtype=float)
    recharge[0, 4] = 1.0e-3

    rch = Rcha(
        save_flows=True,
        print_input=True,
        recharge=recharge,
        dims={"nper": nper, "ncpl": ncpl},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(rch))
    print("RCHA dump:")
    print(dumped)

    assert "READASARRAYS" in dumped
    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped
    assert "RECHARGE" in dumped
    assert "INTERNAL" in dumped
    assert "0.001" in dumped

    loaded = loads(dumped)
    print("RCHA load:")
    pprint(loaded)


def test_rcha_irch_round_trip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Rcha

    nper, ncpl = 2, 3
    dims = {"nper": nper, "nlay": 2, "ncpl": ncpl, "nodes": 2 * ncpl}
    # irch given only in period 0: an int array, no fill value
    rch = Rcha(irch={0: np.array([0, 1, 0])}, recharge=np.full((nper, ncpl), 1e-3), dims=dims)

    raw = loads(dumps(unstructure_component(rch)))
    # irch is 0-based, 1-based in the file
    period = raw["PERIOD 1"]
    assert period[period.index(["IRCH"]) + 2] == [1, 2, 1]
    assert ["IRCH"] not in raw["PERIOD 2"]

    rch2 = structure_component(raw, Rcha, context=LoadContext(dims=dims))
    assert list(rch2.irch) == [0]
    assert rch2.irch[0].dtype == np.int64
    np.testing.assert_array_equal(rch2.irch[0], [0, 1, 0])
    np.testing.assert_array_equal(rch2.period_array("irch", nper=nper)[1], [0, 1, 0])


def test_welg_cleared_period_round_trip():
    """A grid period whose stress arrays are all DNODATA clears every boundary:
    an empty period block, which loads back as a clear. A period not given
    carries forward."""
    from flopy4.mf6._types import array_eq
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Welg

    dims = {"nper": 4, "nlay": 1, "ncpl": 3, "nodes": 3}
    welg = Welg(
        auxiliary=["conc"],
        q={0: np.array([-1.0, FILL_DNODATA, -2.0]), 2: np.full(3, FILL_DNODATA)},
        aux={0: {"conc": np.array([5.0, FILL_DNODATA, 6.0])}},
    )

    text = dumps(unstructure_component(welg))
    assert "BEGIN PERIOD 2" not in text.upper()
    cleared = text.upper().split("BEGIN PERIOD 3")[1].split("END PERIOD")[0]
    assert cleared.strip() == ""

    welg2 = structure_component(loads(text), Welg, context=LoadContext(dims=dims))
    assert welg2.q[2] is None
    assert array_eq(welg2.q, welg.q)
    assert array_eq(welg2.aux, welg.aux)
    np.testing.assert_array_equal(
        welg2.period_array("q", nper=4)[:, 0], [-1, -1, FILL_DNODATA, FILL_DNODATA]
    )


def test_drng_partly_cleared_period_writes_dnodata():
    """A cleared (None) array in a period other arrays are given in is
    written as DNODATA, a constant."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwf import Drng

    drng = Drng(
        elev={0: np.array([1.0, 2.0, 3.0]), 1: None},
        cond={0: np.array([10.0, 10.0, 10.0]), 1: np.array([5.0, FILL_DNODATA, 5.0])},
    )
    assert drng.elev[1] is None
    text = dumps(unstructure_component(drng)).upper()
    period2 = text.split("BEGIN PERIOD 2")[1].split("END PERIOD")[0]
    assert "ELEV" in period2 and "CONSTANT 3" in period2
    assert "COND" in period2


def test_welg_aux_period_without_stress():
    from flopy4.mf6.gwf import Welg

    with pytest.raises(ValueError, match=r"periods \[1\] with no stress arrays"):
        Welg(auxiliary=["conc"], q={0: np.ones(2)}, aux={1: {"conc": np.ones(2)}})


def test_rcha_aux_name_collision():
    """An AUXILIARY name matching a field's (RECHARGE) loads into aux, as in MF6."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Rcha

    text = """BEGIN OPTIONS
  AUXILIARY recharge
  READASARRAYS
END OPTIONS
BEGIN PERIOD 1
  RECHARGE
    CONSTANT 5.0
END PERIOD
"""
    rcha = structure_component(
        loads(text), Rcha, context=LoadContext(dims={"nlay": 1, "ncpl": 2, "nodes": 2})
    )
    assert rcha.recharge is None
    np.testing.assert_array_equal(rcha.aux[0]["recharge"], [5.0, 5.0])


def test_wel_empty_period_round_trip():
    """An empty list period block turns off every boundary: it loads as an
    empty period and is written back."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Wel

    text = """BEGIN DIMENSIONS
  MAXBOUND 1
END DIMENSIONS
BEGIN PERIOD 1
  1 1 1 -1.0
END PERIOD
BEGIN PERIOD 3
END PERIOD
"""
    dims = {"nlay": 1, "nrow": 1, "ncol": 2, "ncpl": 2, "nodes": 2}
    wel = structure_component(loads(text), Wel, context=LoadContext(dims=dims))
    assert list(wel.stress_period_data) == [0, 2]
    assert wel.stress_period_data[2] == []

    out = dumps(unstructure_component(wel))
    cleared = out.upper().split("BEGIN PERIOD 3")[1].split("END PERIOD")[0]
    assert cleared.strip() == ""
    assert structure_component(
        loads(out), Wel, context=LoadContext(dims=dims)
    ).stress_period_data == (wel.stress_period_data)


def test_dumps_wel():
    from flopy4.mf6.gwf import Wel

    wel = Wel(
        print_input=True,
        save_flows=True,
        stress_period_data={
            0: [
                ((0, 2, 3), -100.0),
                ((1, 5, 7), -50.0),
                ((2, 8, 1), 25.0),
            ]
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL dump:")
    print(dumped)

    assert "BEGIN PERIOD 1" in dumped
    assert "END PERIOD 1" in dumped

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 3
    assert "1 3 4 -100.0" in dumped
    assert "2 6 8 -50.0" in dumped
    assert "3 9 2 25.0" in dumped
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("WEL load:")
    pprint(loaded)


def test_dumps_drn():
    from flopy4.mf6.gwf import Drn

    drn = Drn(
        print_flows=True,
        stress_period_data={
            0: [((0, 0, 4), 10.0, 1.0), ((1, 4, 0), 8.0, 2.0)],
            1: [((0, 1, 1), 12.0, 1.5), ((0, 2, 3), 9.0, 0.8), ((1, 3, 2), 7.0, 2.2)],
        },
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

    assert "1 1 5 10.0 1.0" in dumped
    assert "2 5 1 8.0 2.0" in dumped
    assert "1 2 2 12.0 1.5" in dumped
    assert "1 3 4 9.0 0.8" in dumped
    assert "2 4 3 7.0 2.2" in dumped
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
    from flopy4.mf6.gwf import Chd

    rows_left = [((0, row, 0), 100.0) for row in range(5, 15)]
    rows_right = [((0, row, 29), 95.0) for row in range(8, 12)]
    rows_bottom = [((0, 19, col), 98.0) for col in range(10, 20)]
    all_rows = rows_left + rows_right + rows_bottom

    chd = Chd(print_input=True, save_flows=True, stress_period_data={0: all_rows})

    dumped = dumps(COMPONENT_CONVERTER.unstructure(chd))
    print("CHD dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 24
    assert "100.0" in dumped
    assert "95.0" in dumped
    assert "98.0" in dumped
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("CHD load:")
    pprint(loaded)


def test_dumps_wel_with_aux():
    from flopy4.mf6.gwf import Wel

    wel = Wel(
        auxiliary=["well_id"],
        print_input=True,
        stress_period_data={
            0: [
                ((0, 1, 2), -75.0, 1.0),
                ((1, 3, 4), -25.0, 2.0),
            ]
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    print("WEL+aux dump:")
    print(dumped)

    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]

    assert len(lines) == 2
    assert "1 2 3 -75.0 1.0" in dumped
    assert "2 4 5 -25.0 2.0" in dumped
    assert "3e+30" not in dumped
    assert "3.0e+30" not in dumped

    loaded = loads(dumped)
    print("WEL+aux load:")
    pprint(loaded)


def test_dumps_wel_double_aux():
    """Two auxiliary variables in WEL period block round-trip correctly."""
    from flopy4.mf6.gwf import Wel

    wel = Wel(
        auxiliary=["well_id", "temp"],
        stress_period_data={
            0: [
                ((0, 1, 2), -75.0, 1.0, 25.0),
            ]
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(wel))
    period_section = dumped.split("BEGIN PERIOD 1")[1].split("END PERIOD 1")[0].strip()
    lines = [line.strip() for line in period_section.split("\n") if line.strip()]
    assert len(lines) == 1
    # cellid q aux1 aux2
    assert "1 2 3 -75.0 1.0 25.0" in dumped


def test_dumps_gwf():
    from flopy4.mf6.gwf import Dis, Gwf, Ic, Npf, Oc

    dis = Dis(nlay=1, nrow=10, ncol=10, delr=100.0, delc=100.0)
    gwf = Gwf(name="test_model", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)
    oc = Oc(parent=gwf, head_file="test.hds", budget_file="test.bud", dims={"nper": 1})
    gwf = Gwf(
        name="test_model",
        dis=dis,
        ic=ic,
        npf=npf,
        oc=oc,
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
        solutiongroup={},
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

    Each has a _keyword token before its value(s) in the ATTRIBUTES block.
    TimeSeriesName/Sfac's data children are inline arrays nested in a
    record, not scalars -- MF6 allows multiple names/scale factors on one
    line.
    """
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(
        time_series_name=Tas.TimeSeriesName(time_series_name=["my_ts"]),
        interpolation_method=Tas.InterpolationMethod(interpolation_method="linear"),
        sfac=Tas.Sfac(sfacval=[1.5]),
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


def test_dumps_tas_inner_classes_multi_value():
    """TimeSeriesName/Sfac accept more than one value on the line, per MF6 syntax."""
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(
        time_series_name=Tas.TimeSeriesName(time_series_name=["ts1", "ts2"]),
        sfac=Tas.Sfac(sfacval=[1.5, 2.0]),
    )

    unstructured = COMPONENT_CONVERTER.unstructure(tas)
    assert unstructured["attributes"]["time_series_name"] == ("NAME", "ts1", "ts2")
    assert unstructured["attributes"]["sfac"] == ("SFAC", 1.5, 2.0)

    dumped = dumps(unstructured)
    assert "NAME ts1 ts2" in dumped
    assert "SFAC 1.5 2.0" in dumped


def test_load_tas_inner_classes_name_collision():
    """A record keyword ("NAME"/"SFAC") must never be shadowed by an
    unrelated field (Package.name) or the record's own outer field name."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(
        time_series_name=Tas.TimeSeriesName(time_series_name=["ts1", "ts2"]),
        sfac=Tas.Sfac(sfacval=[1.5, 2.0]),
    )
    dumped = dumps(COMPONENT_CONVERTER.unstructure(tas))
    structured = structure_component(loads(dumped), Tas)
    assert structured.name == "tas"  # not clobbered by the "NAME ts1 ts2" row
    assert structured.time_series_name.time_series_name == ["ts1", "ts2"]
    assert structured.sfac.sfacval == [1.5, 2.0]


def test_tas_array_roundtrip():
    """tas_array: a griddata-style array whose own block ("time") repeats
    per header value (BEGIN TIME <t> ... END TIME), dict[float, ndarray]."""
    import numpy as np

    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(tas_array={0.0: np.array([0.02, 0.03, 0.04]), 4.0: np.array([0.05, 0.06, 0.07])})

    unstructured = COMPONENT_CONVERTER.unstructure(tas)
    dumped = dumps(unstructured)
    assert "BEGIN TIME 0.0" in dumped
    assert "END TIME 0.0" in dumped
    assert "BEGIN TIME 4.0" in dumped

    structured = structure_component(
        loads(dumped), Tas, context=LoadContext(dims={"nodes": 3, "nlay": 1})
    )
    assert structured.tas_array[0.0].tolist() == [0.02, 0.03, 0.04]
    assert structured.tas_array[4.0].tolist() == [0.05, 0.06, 0.07]


def test_tas_array_constant_roundtrip():
    """tas_array's U2DREL control record also accepts CONSTANT (broadcast)."""
    import numpy as np

    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl.tas import Tas

    tas = Tas(tas_array={0.0: np.array([0.02, 0.02, 0.02])})
    dumped = dumps(COMPONENT_CONVERTER.unstructure(tas))
    assert "CONSTANT" in dumped

    structured = structure_component(
        loads(dumped), Tas, context=LoadContext(dims={"nodes": 3, "nlay": 1})
    )
    assert structured.tas_array[0.0].tolist() == [0.02, 0.02, 0.02]


def test_tas_array_ncpl_not_nodes():
    """tas_array is only ever consumed by single-layer array packages
    (gwf-rcha, gwf-evta, utl-spca) with no `layered` form of their own --
    its flat length is ncpl (one layer), not the full-grid nodes count.
    Regression test: with nlay=2 (nodes=6, ncpl=3) and 6 values physically
    present in the TIME block (e.g. a neighboring, unrelated INTERNAL run
    of numbers), a nodes-sized read would wrongly consume all 6."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.utl.tas import Tas

    loaded = {"TIME 0.0": [["INTERNAL"], [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]]}
    structured = structure_component(loaded, Tas, context=LoadContext(dims={"nodes": 6, "nlay": 2}))
    assert structured.tas_array[0.0].tolist() == [0.1, 0.2, 0.3]


def test_dumps_zero_field_exg():
    """Zero-field exchange classes (gwfprt, gwfgwe, gwfgwt) instantiate and unstructure
    to empty dicts, producing no output — the pass-only class body must not interfere
    with the converter.
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
    """gwt-oc stress_period_data writes SAVE CONCENTRATION and SAVE BUDGET per period."""
    from flopy4.mf6.gwt.oc import Oc

    oc = Oc(
        dims={"nper": 2},
        budget_file="gwt.bud",
        concentration_file="gwt.conc",
        stress_period_data={
            0: [("SAVE", "CONCENTRATION", "LAST"), ("SAVE", "BUDGET", "LAST")],
            1: [("SAVE", "CONCENTRATION", "ALL")],
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    assert "SAVE CONCENTRATION LAST" in dumped
    assert "SAVE CONCENTRATION ALL" in dumped
    assert "SAVE BUDGET LAST" in dumped


def test_dumps_gwt_oc_wildcard():
    """gwt-oc wildcard '*' maps to period 0, producing one period block (MF6 fill-forward)."""
    from flopy4.mf6.gwt.oc import Oc

    oc = Oc(
        budget_file="gwt.bud",
        concentration_file="gwt.conc",
        stress_period_data={"*": [("SAVE", "CONCENTRATION", "LAST"), ("SAVE", "BUDGET", "ALL")]},
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))
    assert "SAVE CONCENTRATION LAST" in dumped
    assert "SAVE BUDGET ALL" in dumped


def test_dumps_prt_prp_release_setting():
    """prt-prp period release settings write correct MF6 keywords via stress_period_data.

    PRP's `releasesetting` keystring union has no per-row index (unlike LAK/
    LKE/SFR) -- the v1 DFN declares it a bare `recarray releasesetting` with
    no feature-id column, and dev3 confirms no arm carries a pk/fk field, so
    rows are typed per-arm classes: `Frequency` carries an Integer payload;
    `First` is a bare keyword with no payload at all.
    """
    from flopy4.mf6.prt.prp import Prp

    prp = Prp(
        dims={"nper": 2},
        stress_period_data={
            0: [("FREQUENCY", 2)],
            1: [("FIRST",)],
        },
    )

    dumped = dumps(COMPONENT_CONVERTER.unstructure(prp))
    assert "FREQUENCY" in dumped
    assert "FIRST" in dumped


def test_prt_prp_period_roundtrip():
    """PRT-PRP release settings survive a dump→load→structure_component cycle."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.prt.prp import Prp

    prp = Prp(
        dims={"nper": 2},
        stress_period_data={
            0: [("FREQUENCY", 2)],
            1: [("FIRST",)],
        },
    )
    text = dumps(unstructure_component(prp))
    raw = loads(text)
    prp2 = structure_component(raw, Prp)

    spd = prp2.stress_period_data
    assert spd is not None
    assert 0 in spd and 1 in spd

    p0 = spd[0]
    assert len(p0) == 1
    assert isinstance(p0[0], Prp.Frequency)
    assert p0[0].frequency == 2

    p1 = spd[1]
    assert len(p1) == 1
    assert isinstance(p1[0], Prp.First)


def test_oc_ocsetting_typed_dispatch():
    """OC's nested ocsetting union (Save/Print's own All/First/Last/
    Frequency/Steps arms) dispatches to real typed instances, not a raw
    tuple, and survives a dump->load->structure_component cycle -- same
    coverage as test_prt_prp_period_roundtrip for the top-level case."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 1},
        stress_period_data={
            0: [
                ("SAVE", "BUDGET", "STEPS", 1, 3, 5),
                ("PRINT", "HEAD", "ALL"),
            ]
        },
    )
    text = dumps(unstructure_component(oc))
    raw = loads(text)
    oc2 = structure_component(raw, Oc)

    spd = oc2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert len(rows) == 2

    save_row = next(r for r in rows if isinstance(r, Oc.Save))
    assert isinstance(save_row.ocsetting, Oc.Steps)
    assert save_row.ocsetting.steps == (1.0, 3.0, 5.0)

    print_row = next(r for r in rows if isinstance(r, Oc.Print))
    assert isinstance(print_row.ocsetting, Oc.All)


def test_oc_ocsetting_construct_item_positional():
    """A user-supplied positional tuple (construct_item's code path, e.g.
    via COMPONENT_CONVERTER structuring) dispatches ocsetting the same way
    from_tokens does."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(stress_period_data={0: [("SAVE", "HEAD", "ALL")]})
    row = oc.stress_period_data[0][0]
    assert isinstance(row, Oc.Save)
    assert isinstance(row.ocsetting, Oc.All)


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
    oc_int = Oc(
        dims=dims,
        stress_period_data={0: [("SAVE", "BUDGET", "ALL")], 1: [("SAVE", "BUDGET", "LAST")]},
    )
    oc_str = Oc(
        dims=dims,
        stress_period_data={"0": [("SAVE", "BUDGET", "ALL")], "1": [("SAVE", "BUDGET", "LAST")]},
    )

    pb_int = _period_blocks(oc_int)
    pb_str = _period_blocks(oc_str)

    assert pb_int == pb_str
    assert pb_int["period 1"]["period"] == [("SAVE", "BUDGET", "ALL")]
    assert pb_int["period 2"]["period"] == [("SAVE", "BUDGET", "LAST")]
    # No fill-forward: period 3 was not specified so it produces no block.
    assert "period 3" not in pb_int


def test_oc_period_wildcard_fillforward():
    """Explicit per-period keys each produce an independent period block."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        stress_period_data={
            i: [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "LAST")] for i in range(4)
        },
    )
    pb = _period_blocks(oc)

    assert len(pb) == 4
    for i in range(1, 5):
        assert pb[f"period {i}"]["period"] == [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "LAST")]


def test_oc_period_steps_syntax():
    """STEPS values with step numbers pass through verbatim to the period block."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 2},
        stress_period_data={
            0: [("SAVE", "BUDGET", "STEPS", 1, 3, 5), ("PRINT", "BUDGET", "STEPS", 1)],
            1: [("PRINT", "BUDGET", "LAST")],
        },
    )
    pb = _period_blocks(oc)

    assert ("SAVE", "BUDGET", "STEPS", 1, 3, 5) in pb["period 1"]["period"]
    assert ("PRINT", "BUDGET", "STEPS", 1) in pb["period 1"]["period"]
    # no fill-forward: period 2 doesn't re-emit SAVE BUDGET
    assert not any(t[:2] == ("SAVE", "BUDGET") for t in pb["period 2"]["period"])
    assert ("PRINT", "BUDGET", "LAST") in pb["period 2"]["period"]


def test_oc_period_stop_sentinel():
    """Omitting a setting from a later period's list is how it "stops" --
    no special empty-string sentinel needed under stress_period_data, unlike
    the old per-rtype dict API. Matches every other stress-period-data
    package's semantics: each kper's list is exactly what gets written."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        stress_period_data={
            0: [("SAVE", "HEAD", "ALL"), ("SAVE", "BUDGET", "STEPS", 1)],
            1: [("SAVE", "HEAD", "ALL")],
            2: [("SAVE", "HEAD", "ALL")],
        },
    )
    pb = _period_blocks(oc)

    assert len(pb) == 3
    for i in range(1, 4):
        assert ("SAVE", "HEAD", "ALL") in pb[f"period {i}"]["period"]

    assert ("SAVE", "BUDGET", "STEPS", 1) in pb["period 1"]["period"]
    assert not any(t[:2] == ("SAVE", "BUDGET") for t in pb["period 2"]["period"])
    assert not any(t[:2] == ("SAVE", "BUDGET") for t in pb["period 3"]["period"])


def test_oc_period_mixed_keys_no_silent_drop():
    """Mixed string-int and int keys all take effect — none are silently dropped."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        dims={"nper": 3},
        stress_period_data={
            "0": [("SAVE", "HEAD", "FIRST")],
            1: [("SAVE", "HEAD", "LAST")],
            2: [("SAVE", "HEAD", "ALL")],
        },
    )
    pb = _period_blocks(oc)

    assert ("SAVE", "HEAD", "FIRST") in pb["period 1"]["period"]
    assert ("SAVE", "HEAD", "LAST") in pb["period 2"]["period"]
    assert ("SAVE", "HEAD", "ALL") in pb["period 3"]["period"]


def test_oc_dumps_steps_in_output():
    """Round-trip: STEPS syntax appears correctly in the serialised OC text."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        budget_file="t.bud",
        head_file="t.hds",
        stress_period_data={
            0: [
                ("SAVE", "HEAD", "ALL"),
                ("SAVE", "BUDGET", "STEPS", 1, 5),
                ("PRINT", "BUDGET", "LAST"),
            ],
            1: [("SAVE", "HEAD", "ALL"), ("PRINT", "BUDGET", "LAST")],
        },
    )
    dumped = dumps(COMPONENT_CONVERTER.unstructure(oc))

    assert "SAVE HEAD ALL" in dumped
    assert "SAVE BUDGET STEPS 1 5" in dumped
    assert "PRINT BUDGET LAST" in dumped
    # Period 2 must not re-emit SAVE BUDGET
    lines = dumped.splitlines()
    period2_start = next(i for i, l in enumerate(lines) if "BEGIN PERIOD 2" in l)
    period2_block = "\n".join(lines[period2_start:])
    assert "SAVE BUDGET" not in period2_block


def test_oc_period_frequency():
    """FREQUENCY n ocsetting is emitted and preserved in the period block."""
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        stress_period_data={
            0: [("SAVE", "HEAD", "FREQUENCY", 2), ("SAVE", "BUDGET", "ALL")],
            1: [("SAVE", "HEAD", "FREQUENCY", 2)],
            2: [("SAVE", "HEAD", "FREQUENCY", 2)],
        },
    )
    pb = _period_blocks(oc)

    assert ("SAVE", "HEAD", "FREQUENCY", 2) in pb["period 1"]["period"]
    assert ("SAVE", "HEAD", "FREQUENCY", 2) in pb["period 2"]["period"]
    assert ("SAVE", "HEAD", "FREQUENCY", 2) in pb["period 3"]["period"]
    assert ("SAVE", "BUDGET", "ALL") in pb["period 1"]["period"]


# ---------------------------------------------------------------------------
# LAK period tests
# ---------------------------------------------------------------------------


def _lak_period_blocks(lak):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    blocks = unstructure_component(lak)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_lak_period_lake_keywords():
    """LAK lake-keyword period rows: number KEYWORD value."""
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (1, "STAGE", 5.0),
                # lake 0 STAGE intentionally omitted
            ]
        }
    )
    pb = _lak_period_blocks(lak)

    rows_p1 = pb["period 1"]["period"]
    assert (1, "STATUS", "ACTIVE") in rows_p1  # emitted 1-based
    assert (2, "STATUS", "CONSTANT") in rows_p1
    assert (2, "STAGE", 5.0) in rows_p1
    # lake 0 (→1 in file) STAGE was not provided → no row
    assert not any(r[0] == 1 and r[1] == "STAGE" for r in rows_p1)


def test_lak_period_outlet_keywords():
    """LAK outlet-keyword period rows: number KEYWORD value."""
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        stress_period_data={
            0: [
                (0, "RATE", 100.0),
                (1, "RATE", 200.0),
                (0, "INVERT", 4.5),
                (1, "INVERT", 3.5),
            ]
        }
    )
    pb = _lak_period_blocks(lak)

    rows = pb["period 1"]["period"]
    assert (1, "RATE", 100.0) in rows  # emitted 1-based
    assert (2, "RATE", 200.0) in rows
    assert (1, "INVERT", 4.5) in rows
    assert (2, "INVERT", 3.5) in rows


def test_lak_period_dumps():
    """LAK period rows are written in the expected MF6 format."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (1, "STAGE", 5.0),
            ]
        }
    )
    dumped = dumps(unstructure_component(lak))
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
    """IMS construction with required fields works; fields default=None, not TypeError."""
    from flopy4.mf6.ims import Ims

    # Every field defaults to None, so Ims() doesn't raise TypeError
    ims_empty = Ims()
    assert ims_empty.outer_dvclose is None

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


def test_prt_fmi_packagedata_dump():
    """prt.Fmi packagedata writes flowtype and FILEIN fname tokens, like gwt.Fmi."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.prt.fmi import Fmi

    fmi = Fmi(
        packagedata={
            "flowtype": np.array(["GWFHEAD", "GWFBUDGET"]),
            "fname": np.array(["gwf.hds", "gwf.cbc"]),
        }
    )
    text = dumps(unstructure_component(fmi))
    assert "BEGIN PACKAGEDATA" in text
    assert "GWFHEAD FILEIN gwf.hds" in text
    assert "GWFBUDGET FILEIN gwf.cbc" in text
    assert "GWFGRID" not in text


def test_prt_fmi_packagedata_roundtrip():
    """prt.Fmi packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.prt.fmi import Fmi

    fmi = Fmi(
        packagedata={
            "flowtype": np.array(["GWFHEAD", "GWFBUDGET"]),
            "fname": np.array(["gwf.hds", "gwf.cbc"]),
        }
    )
    raw = loads(dumps(unstructure_component(fmi)))
    pd = structure_component(raw, Fmi).packagedata
    assert [r.flowtype for r in pd] == ["GWFHEAD", "GWFBUDGET"]
    assert [str(r.fname) for r in pd] == ["gwf.hds", "gwf.cbc"]


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


def test_file_records_roundtrip(tmp_path):
    """Options-block file records are keyed by their trigger keyword (TS6,
    OBS6, HEAD), not the py field name (ts, obs, head_file) -- both on
    load and on write. A record naming a child (TS6, OBS6) loads the child."""
    from pathlib import Path

    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Oc, Wel
    from flopy4.mf6.utl.obs import Obs
    from flopy4.mf6.utl.ts import Ts

    (tmp_path / "w.obs").write_text(
        "BEGIN CONTINUOUS FILEOUT w.obs.csv\n  q1 wel 1\nEND CONTINUOUS\n"
    )
    raw = loads("BEGIN OPTIONS\n  OBS6 FILEIN 'w.obs'\nEND OPTIONS\n")
    wel = structure_component(
        raw, Wel, context=LoadContext(workspace=tmp_path, dims={"nlay": 1, "nodes": 10, "ncpl": 10})
    )
    assert isinstance(wel.obs, Obs)
    assert wel.obs.filename == Path("w.obs")
    assert wel.obs.name == "obs"  # not its block's name
    assert "OBS6 FILEIN w.obs" in dumps(unstructure_component(wel))

    for name in ("a", "b"):
        (tmp_path / f"{name}.ts").write_text(
            f"BEGIN ATTRIBUTES\n  NAMES {name}\n  METHODS linear\nEND ATTRIBUTES\n"
            "BEGIN TIMESERIES\n  0.0 1.0\n  1.0 2.0\nEND TIMESERIES\n"
        )
    raw = loads(
        "BEGIN OPTIONS\n  TS6 FILEIN a.ts\n  OBS6 FILEIN w.obs\n  TS6 FILEIN b.ts\nEND OPTIONS\n"
    )
    wel = structure_component(
        raw, Wel, context=LoadContext(workspace=tmp_path, dims={"nlay": 1, "nodes": 10, "ncpl": 10})
    )
    assert all(isinstance(ts, Ts) for ts in wel.ts)
    assert [ts.filename for ts in wel.ts] == [Path("a.ts"), Path("b.ts")]
    assert [ts.time_series_name.time_series_names for ts in wel.ts] == [["a"], ["b"]]
    lines = [line.strip() for line in dumps(unstructure_component(wel)).splitlines()]
    ts_lines = [line for line in lines if line.startswith("TS6")]
    assert ts_lines == ["TS6 FILEIN a.ts", "TS6 FILEIN b.ts"]

    raw = loads("BEGIN OPTIONS\n  HEAD FILEOUT m.hds\n  BUDGET FILEOUT m.cbc\nEND OPTIONS\n")
    oc = structure_component(raw, Oc)
    assert oc.head_file == Path("m.hds")
    assert oc.budget_file == Path("m.cbc")


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
    """fileinput rows must serialise as 'pname SPC6 FILEIN <spc file> [MIXED]'."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.ssm import Ssm
    from flopy4.mf6.utl.spc import Spc

    ssm = Ssm(
        fileinput={
            "pname": np.array(["rch-1", "wel-1"]),
            "spc": [Spc(filename=Path("rch.spc6")), Spc(filename=Path("wel.spc6"))],
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
    from flopy4.mf6.utl.spc import Spc

    ssm = Ssm(
        fileinput={
            "pname": np.array(["rch-1"]),
            "spc": [Spc(filename=Path("rch.spc6"))],
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
    from flopy4.mf6.utl.spc import Spc

    ssm = Ssm(
        sources={
            "pname": np.array(["chd-1"]),
            "srctype": np.array(["AUX"]),
            "auxname": np.array(["conc"]),
        },
        fileinput={
            "pname": np.array(["rch-1"]),
            "spc": [Spc(filename=Path("rch.spc6"))],
        },
    )
    text = dumps(unstructure_component(ssm))
    assert "BEGIN SOURCES" in text
    assert "chd-1 AUX conc" in text
    assert "BEGIN FILEINPUT" in text
    assert "rch-1 SPC6 FILEIN rch.spc6" in text
    # block order: SOURCES before FILEINPUT
    assert text.index("BEGIN SOURCES") < text.index("BEGIN FILEINPUT")


def test_ssm_fileinput_children(tmp_path):
    """Each FILEINPUT row's SPC6 file loads as an Spc, or an Spca if it reads
    arrays, and is written back with its parent."""
    from flopy4.mf6.gwt.ssm import Ssm
    from flopy4.mf6.utl.spc import Spc
    from flopy4.mf6.utl.spca import Spca

    (tmp_path / "gwt.ssm").write_text(
        "BEGIN FILEINPUT\n  wel-1 SPC6 FILEIN wel.spc MIXED\n  rch-1 SPC6 FILEIN rch.spc\n"
        "END FILEINPUT\n"
    )
    (tmp_path / "wel.spc").write_text(
        "BEGIN DIMENSIONS\n  MAXBOUND 1\nEND DIMENSIONS\n"
        "BEGIN PERIOD 1\n  1 CONCENTRATION 100.0\nEND PERIOD\n"
    )
    (tmp_path / "rch.spc").write_text(
        "BEGIN OPTIONS\n  READASARRAYS\nEND OPTIONS\n"
        "BEGIN PERIOD 1\n  CONCENTRATION\n    CONSTANT 2.0\nEND PERIOD\n"
    )
    ssm = Ssm.load(tmp_path / "gwt.ssm", dims={"nlay": 1, "nrow": 1, "ncol": 2, "ncpl": 2})
    wel, rch = ssm.fileinput
    assert isinstance(wel.spc, Spc) and wel.mixed
    assert isinstance(rch.spc, Spca)
    assert wel.spc.filename == Path("wel.spc")
    assert [r.concentration for r in wel.spc.stress_period_data[0]] == [100.0]
    assert sorted(ssm._children) == ["fileinput0", "fileinput1"]
    assert wel.spc.parent is ssm

    text = dumps(COMPONENT_CONVERTER.unstructure(ssm))
    assert "wel-1 SPC6 FILEIN wel.spc MIXED" in text
    assert "rch-1 SPC6 FILEIN rch.spc" in text


# ---------------------------------------------------------------------------
# Record.from_tokens tests
# ---------------------------------------------------------------------------


def test_headprint_from_tokens_full_string():
    """Full DFN string including keyword and extra tokens is parsed correctly."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("HEAD PRINT_FORMAT COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
    assert hp.formatrecord.format_ == "exponential"
    assert hp.formatrecord.columns == 10
    assert hp.formatrecord.width == 12
    assert hp.formatrecord.digits == 6


def test_headprint_from_tokens_no_prefix():
    """Tokens without the leading keyword/extra_tokens prefix are parsed correctly."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("COLUMNS 10 WIDTH 12 DIGITS 6 exponential")
    assert hp.formatrecord.format_ == "exponential"
    assert hp.formatrecord.columns == 10
    assert hp.formatrecord.width == 12
    assert hp.formatrecord.digits == 6


def test_headprint_from_tokens_format_only():
    """A single untagged token populates the required positional field."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("exponential")
    assert hp.formatrecord.format_ == "exponential"
    assert hp.formatrecord.columns is None
    assert hp.formatrecord.width is None
    assert hp.formatrecord.digits is None


def test_headprint_from_tokens_list():
    """Token list form works the same as the string form."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens(["COLUMNS", "10", "exponential"])
    assert hp.formatrecord.format_ == "exponential"
    assert hp.formatrecord.columns == 10
    assert hp.formatrecord.width is None
    assert hp.formatrecord.digits is None


def test_headprint_from_tokens_tagged_types():
    """Tagged integer fields are coerced from string tokens to int."""
    from flopy4.mf6.gwf.oc import Oc

    hp = Oc.Headprint.from_tokens("WIDTH 15 DIGITS 4 fixed")
    assert isinstance(hp.formatrecord.width, int)
    assert hp.formatrecord.width == 15
    assert isinstance(hp.formatrecord.digits, int)
    assert hp.formatrecord.digits == 4
    assert hp.formatrecord.columns is None


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
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwf.lak import Lak

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
        surfdep=1.0,
        print_input=True,
        print_stage=True,
        print_flows=True,
        save_flows=True,
        boundnames=True,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([100.0]),
            "nlakeconn": np.array([nconn]),
            "boundname": np.array(["lake1"], dtype=object),
        },
        connectiondata={
            "ifno": np.zeros(nconn, dtype=int),
            "iconn": np.arange(nconn, dtype=int),
            "cellid": cellids,
            "claktype": np.full(nconn, "vertical", dtype=object),
            "bedleak": np.full(nconn, 1.0, dtype=object),
            "belev": np.zeros(nconn),
            "telev": np.zeros(nconn),
            "connlen": np.zeros(nconn),
            "connwidth": np.zeros(nconn),
        },
        stress_period_data={
            0: [(0, "RAINFALL", 0.1)],
            1: [(0, "STATUS", "inactive")],
            2: [(0, "STATUS", "active")],
        },
    )

    dumped = dumps(unstructure_component(lak))
    print("LAK status input:")
    print(dumped)

    # --- period block checks ---
    assert "BEGIN PERIOD 1" in dumped
    assert "1 RAINFALL 0.1" in dumped
    assert "BEGIN PERIOD 2" in dumped
    assert "1 STATUS inactive" in dumped
    assert "BEGIN PERIOD 3" in dumped
    assert "1 STATUS active" in dumped

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
        boundnames=True,
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
    assert [r.strt for r in pd] == [5.0]
    assert [r.boundname for r in pd] == ["lake1"]
    cd = lak2.connectiondata
    assert [r.ifno for r in cd] == [0, 0, 0]
    assert [r.iconn for r in cd] == [0, 1, 2]
    assert tuple(cd[0].cellid) == (0, 0, 0)
    assert tuple(cd[1].cellid) == (0, 0, 1)
    assert tuple(cd[2].cellid) == (0, 1, 0)
    assert [r.claktype for r in cd] == ["vertical", "vertical", "vertical"]


def test_lak_packagedata_single_aux_roundtrip():
    """LAK packagedata with one aux variable round-trips through dump→load→structure."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        auxiliary=["CONCENTRATION"],
        nlakes=1,
        boundnames=True,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([5.0]),
            "nlakeconn": np.array([2]),
            "aux": [(100.0,)],
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
    assert [r.strt for r in pd] == [5.0]
    assert float(pd[0].aux[0]) == pytest.approx(100.0)
    assert [r.boundname for r in pd] == ["lake1"]


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
        boundnames=True,
        packagedata={
            "ifno": np.array([0, 1]),
            "strt": np.array([-0.4, -0.5]),
            "nlakeconn": np.array([3, 2]),
            "aux": [(0.0, 1025.0), (5.0, 1010.0)],
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
    assert float(pd[0].aux[0]) == pytest.approx(0.0)
    assert float(pd[0].aux[1]) == pytest.approx(1025.0)
    assert float(pd[1].aux[0]) == pytest.approx(5.0)
    assert float(pd[1].aux[1]) == pytest.approx(1010.0)


def test_lkt_packagedata_double_aux_roundtrip():
    """LKT packagedata with two aux variables round-trips."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        auxiliary=["aux1", "aux2"],
        boundnames=True,
        packagedata={
            "ifno": np.array([0]),
            "strt": np.array([35.0]),
            "aux": [(99.0, 999.0)],
            "boundname": np.array(["mylake"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lkt))
    print("LKT double-aux dump:")
    print(text)

    assert "99" in text
    assert "999" in text
    assert "mylake" in text
    # aux must precede boundname in the emitted row
    assert text.index("99") < text.index("mylake")

    raw = loads(text)
    lkt2 = structure_component(raw, Lkt)
    pd = lkt2.packagedata
    assert float(pd[0].aux[0]) == pytest.approx(99.0)
    assert float(pd[0].aux[1]) == pytest.approx(999.0)
    assert [r.boundname for r in pd] == ["mylake"]


def test_lak_keystring_period_roundtrip():
    """LAK keystring period data round-trips through dump→load→structure."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.lak import Lak

    lak = Lak(
        nlakes=2,
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (0, "RAINFALL", 0.1),
                (1, "STATUS", "CONSTANT"),
                (1, "STAGE", 5.0),
            ],
            1: [
                (0, "STATUS", "INACTIVE"),
            ],
            2: [
                (0, "STATUS", "ACTIVE"),
                (1, "WITHDRAWAL", 100.0),
            ],
        },
    )

    text = dumps(unstructure_component(lak))
    # Verify dump contains expected period content
    assert "BEGIN PERIOD 1" in text
    assert "BEGIN PERIOD 2" in text
    assert "BEGIN PERIOD 3" in text

    raw = loads(text)
    lak2 = structure_component(raw, Lak)

    spd = lak2.stress_period_data
    assert spd is not None
    assert set(spd.keys()) == {0, 1, 2}

    # Period 0: 4 rows
    p0 = spd[0]
    assert len(p0) == 4
    assert isinstance(p0[0], Lak.Status) and p0[0].lakeno == 0  # 0-based feature id
    assert p0[0].status == "ACTIVE"
    assert isinstance(p0[1], Lak.Rainfall) and p0[1].lakeno == 0
    assert float(p0[1].rainfall) == pytest.approx(0.1)
    assert isinstance(p0[2], Lak.Status) and p0[2].lakeno == 1
    assert p0[2].status == "CONSTANT"
    assert isinstance(p0[3], Lak.Stage) and p0[3].lakeno == 1
    assert float(p0[3].stage) == pytest.approx(5.0)

    # Period 1: 1 row
    p1 = spd[1]
    assert len(p1) == 1
    assert isinstance(p1[0], Lak.Status) and p1[0].lakeno == 0
    assert p1[0].status == "INACTIVE"

    # Period 2: 2 rows
    p2 = spd[2]
    assert len(p2) == 2
    assert isinstance(p2[0], Lak.Status) and p2[0].lakeno == 0
    assert p2[0].status == "ACTIVE"
    assert isinstance(p2[1], Lak.Withdrawal) and p2[1].lakeno == 1
    assert float(p2[1].withdrawal) == pytest.approx(100.0)


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
    assert [r.flowtype for r in pd] == ["HEAD"]
    assert [str(r.fname) for r in pd] == ["gwf.hds"]


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
    assert [r.mname for r in parts] == ["model1", "model2"]
    assert [r.mrank for r in parts] == [0, 1]


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
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (0, "CONCENTRATION", 10.0),
                (1, "CONCENTRATION", 20.0),
            ]
        }
    )
    pb = _lkt_period_blocks(lkt)
    rows = pb["period 1"]["period"]
    assert (1, "STATUS", "ACTIVE") in rows  # emitted 1-based
    assert (2, "STATUS", "CONSTANT") in rows
    assert (1, "CONCENTRATION", 10.0) in rows
    assert (2, "CONCENTRATION", 20.0) in rows


def test_lkt_period_dumps():
    """LKT period block is written in the expected MF6 format."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (0, "CONCENTRATION", 10.0),
            ]
        }
    )
    text = dumps(unstructure_component(lkt))
    assert "BEGIN PERIOD 1" in text
    assert "1 STATUS ACTIVE" in text
    assert "2 STATUS CONSTANT" in text
    assert "1 CONCENTRATION 10.0" in text
    assert not any("CONCENTRATION" in line and "2 " in line for line in text.splitlines())


def test_lkt_period_roundtrip():
    """LKT keystring period data round-trips through dump→load→structure."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (0, "CONCENTRATION", 10.0),
            ],
            1: [
                (0, "STATUS", "INACTIVE"),
            ],
        }
    )
    text = dumps(unstructure_component(lkt))
    raw = loads(text)
    lkt2 = structure_component(raw, Lkt)

    spd = lkt2.stress_period_data
    assert spd is not None
    assert set(spd.keys()) == {0, 1}

    p0 = spd[0]
    assert len(p0) == 3
    assert isinstance(p0[0], Lkt.Status) and p0[0].ifno == 0
    assert p0[0].status == "ACTIVE"
    assert isinstance(p0[1], Lkt.Status) and p0[1].ifno == 1
    assert p0[1].status == "CONSTANT"
    assert isinstance(p0[2], Lkt.Concentration) and p0[2].ifno == 0
    assert float(p0[2].concentration) == pytest.approx(10.0)

    p1 = spd[1]
    assert len(p1) == 1
    assert isinstance(p1[0], Lkt.Status) and p1[0].ifno == 0
    assert p1[0].status == "INACTIVE"


def test_lkt_packagedata_roundtrip():
    """LKT packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.lkt import Lkt

    lkt = Lkt(
        boundnames=True,
        packagedata={
            "ifno": np.array([0, 1]),
            "strt": np.array([1.0, 2.0]),
            "boundname": np.array(["lake_a", "lake_b"], dtype=object),
        },
    )
    text = dumps(unstructure_component(lkt))
    raw = loads(text)
    lkt2 = structure_component(raw, Lkt)

    pd = lkt2.packagedata
    assert len(pd) == 2
    assert [r.strt for r in pd] == [1.0, 2.0]
    assert [r.boundname for r in pd] == ["lake_a", "lake_b"]


def _lke_period_blocks(lke):
    from flopy4.mf6.converter.egress.unstructure import unstructure_component

    blocks = unstructure_component(lke)
    return {k: v for k, v in blocks.items() if k.startswith("period")}


def test_lke_period_keywords():
    """LKE period rows: lakeno KEYWORD value (STATUS and TEMPERATURE)."""
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (0, "TEMPERATURE", 15.0),
                (1, "TEMPERATURE", 20.0),
            ]
        }
    )
    pb = _lke_period_blocks(lke)
    rows = pb["period 1"]["period"]
    assert (1, "STATUS", "ACTIVE") in rows  # emitted 1-based
    assert (2, "STATUS", "CONSTANT") in rows
    assert (1, "TEMPERATURE", 15.0) in rows
    assert (2, "TEMPERATURE", 20.0) in rows


def test_lke_period_dumps():
    """LKE period block is written in the expected MF6 format."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        stress_period_data={
            0: [
                (0, "TEMPERATURE", 18.5),
            ]
        }
    )
    text = dumps(unstructure_component(lke))
    assert "BEGIN PERIOD 1" in text
    assert "1 TEMPERATURE 18.5" in text


def test_lke_period_roundtrip():
    """LKE keystring period data round-trips through dump→load→structure."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        stress_period_data={
            0: [
                (0, "STATUS", "ACTIVE"),
                (1, "STATUS", "CONSTANT"),
                (0, "TEMPERATURE", 18.5),
            ],
            1: [
                (0, "STATUS", "INACTIVE"),
            ],
        }
    )
    text = dumps(unstructure_component(lke))
    raw = loads(text)
    lke2 = structure_component(raw, Lke)

    spd = lke2.stress_period_data
    assert spd is not None
    assert set(spd.keys()) == {0, 1}

    p0 = spd[0]
    assert len(p0) == 3
    assert isinstance(p0[0], Lke.Status) and p0[0].lakeno == 0
    assert p0[0].status == "ACTIVE"
    assert isinstance(p0[1], Lke.Status) and p0[1].lakeno == 1
    assert p0[1].status == "CONSTANT"
    assert isinstance(p0[2], Lke.Temperature) and p0[2].lakeno == 0
    assert float(p0[2].temperature) == pytest.approx(18.5)

    p1 = spd[1]
    assert len(p1) == 1
    assert isinstance(p1[0], Lke.Status) and p1[0].lakeno == 0
    assert p1[0].status == "INACTIVE"


def test_lke_packagedata_roundtrip():
    """LKE packagedata survives a dump→load→structure_component cycle."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        boundnames=True,
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

    pd = lke2.packagedata
    assert len(pd) == 2
    assert [r.strt for r in pd] == [12.0, 14.0]
    assert [r.ktf for r in pd] == [0.6, 0.6]
    assert [r.boundname for r in pd] == ["lakeA", "lakeB"]


def test_lke_packagedata_double_aux_roundtrip():
    """LKE packagedata with two aux variables round-trips through dump→load→structure."""
    from flopy4.mf6.codec.writer import dumps
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.lke import Lke

    lke = Lke(
        auxiliary=["aux1", "aux2"],
        boundnames=True,
        packagedata={
            "lakeno": np.array([0, 1]),
            "strt": np.array([12.0, 14.0]),
            "ktf": np.array([0.6, 0.7]),
            "rbthcnd": np.array([0.1, 0.2]),
            "aux": [(10.0, 20.0), (30.0, 40.0)],
            "boundname": np.array(["lakeA", "lakeB"], dtype=object),
        },
    )

    text = dumps(unstructure_component(lke))

    assert "10" in text
    assert "20" in text
    assert "lakeA" in text
    assert "lakeB" in text
    # aux values must precede boundnames in each emitted row
    assert text.index("lakeA") > text.index("10")

    raw = loads(text)
    lke2 = structure_component(raw, Lke)

    pd = lke2.packagedata
    assert len(pd) == 2
    assert float(pd[0].aux[0]) == pytest.approx(10.0)
    assert float(pd[0].aux[1]) == pytest.approx(20.0)
    assert float(pd[1].aux[0]) == pytest.approx(30.0)
    assert float(pd[1].aux[1]) == pytest.approx(40.0)
    assert [r.boundname for r in pd] == ["lakeA", "lakeB"]


# ---------------------------------------------------------------------------
# Period block roundtrip — CHD / WEL / DRN
# ---------------------------------------------------------------------------


def test_chd_period_roundtrip():
    """structure_component reconstructs CHD head values from loads(dumps(...))."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd

    chd = Chd(
        stress_period_data={
            0: [((0, 0, 0), 10.0), ((0, 9, 9), 0.0)],
        }
    )

    text = dumps(unstructure_component(chd))
    raw = loads(text)
    chd2 = structure_component(raw, Chd)

    spd = chd2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    head_by_cellid = {tuple(rows[i].cellid): float(rows[i].head) for i in range(len(rows))}
    assert head_by_cellid[(0, 0, 0)] == pytest.approx(10.0)
    assert head_by_cellid[(0, 9, 9)] == pytest.approx(0.0)


def test_chd_period_multi_stress_period_roundtrip():
    """CHD with two stress periods reconstructs correctly."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd

    chd = Chd(
        stress_period_data={
            0: [((0, 0, 0), 10.0), ((0, 4, 4), 5.0)],
            1: [((0, 0, 0), 8.0), ((0, 4, 4), 3.0)],
        }
    )

    text = dumps(unstructure_component(chd))
    raw = loads(text)
    chd2 = structure_component(raw, Chd)

    spd = chd2.stress_period_data
    assert spd is not None
    for kper, expected in {
        0: {(0, 0, 0): 10.0, (0, 4, 4): 5.0},
        1: {(0, 0, 0): 8.0, (0, 4, 4): 3.0},
    }.items():
        rows = spd[kper]
        actual = {tuple(rows[i].cellid): float(rows[i].head) for i in range(len(rows))}
        for cellid, val in expected.items():
            assert actual[cellid] == pytest.approx(val)


def test_wel_period_roundtrip():
    """structure_component reconstructs WEL q values from loads(dumps(...))."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Wel

    wel = Wel(
        stress_period_data={
            0: [((0, 1, 2), -75.0), ((1, 3, 4), -25.0)],
        }
    )

    text = dumps(unstructure_component(wel))
    raw = loads(text)
    wel2 = structure_component(raw, Wel)

    spd = wel2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    q_by_cellid = {tuple(rows[i].cellid): float(rows[i].q) for i in range(len(rows))}
    assert q_by_cellid[(0, 1, 2)] == pytest.approx(-75.0)
    assert q_by_cellid[(1, 3, 4)] == pytest.approx(-25.0)


def test_drn_period_roundtrip():
    """structure_component reconstructs DRN elev+cond values."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Drn

    drn = Drn(
        stress_period_data={
            0: [((0, 2, 2), 5.0, 1.0)],
        }
    )

    text = dumps(unstructure_component(drn))
    raw = loads(text)
    drn2 = structure_component(raw, Drn)

    spd = drn2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 2, 2)
    assert float(rows[0].elev) == pytest.approx(5.0)
    assert float(rows[0].cond) == pytest.approx(1.0)


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
    wel = structure_component(raw, Wel)

    spd = wel.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 1, 2)
    assert float(rows[0].q) == pytest.approx(-75.0)
    assert float(rows[0].aux[0]) == pytest.approx(1.0)


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
    wel = structure_component(raw, Wel)

    spd = wel.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 1, 2)
    assert float(rows[0].q) == pytest.approx(-75.0)
    assert float(rows[0].aux[0]) == pytest.approx(1.0)
    assert float(rows[0].aux[1]) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Period-block aux for GWT/GWE transport and GWF array-recharge packages
# ---------------------------------------------------------------------------


def test_cnc_period_aux_roundtrip():
    """GWT CNC: conc + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.cnc import Cnc

    cnc = Cnc(
        auxiliary=["tracer_id"],
        stress_period_data={0: [((0, 0, 2), 35.0, 99.0)]},
    )

    text = dumps(unstructure_component(cnc))
    assert "35" in text
    assert "99" in text

    raw = loads(text)
    cnc2 = structure_component(raw, Cnc)

    spd = cnc2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 0, 2)
    assert float(rows[0].conc) == pytest.approx(35.0)
    assert float(rows[0].aux[0]) == pytest.approx(99.0)


def test_src_period_aux_roundtrip():
    """GWT SRC: smassrate + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwt.src import Src

    src = Src(
        auxiliary=["src_id"],
        stress_period_data={0: [((0, 0, 3), 0.5, 7.0)]},
    )

    text = dumps(unstructure_component(src))
    assert "0.5" in text
    assert "7" in text

    raw = loads(text)
    src2 = structure_component(raw, Src)

    spd = src2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 0, 3)
    assert float(rows[0].smassrate) == pytest.approx(0.5)
    assert float(rows[0].aux[0]) == pytest.approx(7.0)


def test_ctp_period_aux_roundtrip():
    """GWE CTP: temp + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.ctp import Ctp

    ctp = Ctp(
        auxiliary=["zone"],
        stress_period_data={0: [((0, 0, 1), 20.0, 3.0)]},
    )

    text = dumps(unstructure_component(ctp))
    assert "20" in text
    assert "3" in text

    raw = loads(text)
    ctp2 = structure_component(raw, Ctp)

    spd = ctp2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 0, 1)
    assert float(rows[0].temp) == pytest.approx(20.0)
    assert float(rows[0].aux[0]) == pytest.approx(3.0)


def test_esl_period_aux_roundtrip():
    """GWE ESL: senerrate + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwe.esl import Esl

    esl = Esl(
        auxiliary=["esl_id"],
        stress_period_data={0: [((0, 0, 4), 1.25, 55.0)]},
    )

    text = dumps(unstructure_component(esl))
    assert "1.25" in text
    assert "55" in text

    raw = loads(text)
    esl2 = structure_component(raw, Esl)

    spd = esl2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 0, 4)
    assert float(rows[0].senerrate) == pytest.approx(1.25)
    assert float(rows[0].aux[0]) == pytest.approx(55.0)


def test_rch_period_aux_roundtrip():
    """GWF RCH: recharge + aux round-trip through dumps/loads/structure_component."""
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.rch import Rch

    rch = Rch(
        auxiliary=["rch_id"],
        stress_period_data={0: [((0, 0, 0), 0.001, 42.0)]},
    )

    text = dumps(unstructure_component(rch))
    assert "0.001" in text
    assert "42" in text

    raw = loads(text)
    rch2 = structure_component(raw, Rch)

    spd = rch2.stress_period_data
    assert spd is not None and 0 in spd
    rows = spd[0]
    assert tuple(rows[0].cellid) == (0, 0, 0)
    assert float(rows[0].recharge) == pytest.approx(0.001)
    assert float(rows[0].aux[0]) == pytest.approx(42.0)


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
        aux={"tracer": np.expand_dims(aux, axis=0)},  # name -> (nper, ncpl)
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
        aux={"well_id": np.expand_dims(aux, axis=0)},
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
        aux={"tracer_a": aux[None, :, 0], "tracer_b": aux[None, :, 1]},
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


def test_rcha_period_aux_roundtrip():
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Rcha

    rch = Rcha(
        auxiliary=["conc", "temp"],
        recharge=np.full((2, 4), 1e-3),
        aux={"conc": np.full((2, 4), 10.0), "temp": np.array([[15.0] * 4, [FILL_DNODATA] * 4])},
    )
    text = dumps(unstructure_component(rch))
    assert "TEMP" not in text.split("BEGIN PERIOD 2")[1]
    rch2 = structure_component(loads(text), Rcha, context=LoadContext(dims={"nlay": 1, "nodes": 4}))
    # temp's all-DNODATA period 2 isn't given: aux[kper][name]
    assert {k: sorted(v) for k, v in rch2.aux.items()} == {0: ["conc", "temp"], 1: ["conc"]}
    for kper, arrays in rch.aux.items():
        for name, arr in arrays.items():
            np.testing.assert_array_equal(rch2.aux[kper][name], arr)


def test_rcha_period_aux_unknown_name():
    from flopy4.mf6.gwf import Rcha

    with pytest.raises(ValueError, match=r"\['tmp'\] not in auxiliary"):
        Rcha(auxiliary=["conc"], aux={"tmp": np.zeros((1, 4))})


def test_evt_period_aux_roundtrip():
    """EVT aux column round-trips through dumps/loads/structure_component.

    EVT is list-based: aux is a trailing inline column in each period row.
    Construct using the dict-row API to avoid positional ambiguity with
    optional columns (pxdp/petm/petm0).
    """
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Evt

    nlay = 1
    nrow = 3
    ncol = 3

    evt = Evt(
        auxiliary=["et_zone"],
        stress_period_data={
            0: [
                {
                    "cellid": (0, 1, 1),
                    "surface": 10.0,
                    "rate": 1.5e-3,
                    "depth": 2.0,
                    "aux": (3.14,),
                },
            ]
        },
    )

    text = dumps(unstructure_component(evt))
    assert "AUXILIARY ET_ZONE" in text.upper()
    assert "3.14" in text

    raw = loads(text)
    evt2 = structure_component(raw, Evt)

    spd = evt2.stress_period_data
    assert spd is not None
    assert 0 in spd
    arr = spd[0]
    assert hasattr(arr[0], "surface")
    assert float(arr[0].surface) == pytest.approx(10.0)
    assert float(arr[0].aux[0]) == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# SPC / TVK / TVS — options-only packages with path(inout="filein")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1970-01-01T00:00:00", "1970-01-01T00:00:00"),
        ("1997-01-01", "1997-01-01"),
        ("1997", "1997"),
    ],
)
def test_tdis_start_date_time_is_str(text, expected):
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.tdis import Tdis

    raw = loads(
        f"BEGIN OPTIONS\n  START_DATE_TIME {text}\nEND OPTIONS\n"
        "BEGIN DIMENSIONS\n  NPER 1\nEND DIMENSIONS\n"
        "BEGIN PERIODDATA\n  1.0 1 1.0\nEND PERIODDATA\n"
    )
    tdis = structure_component(raw, Tdis)
    assert isinstance(tdis.start_date_time, str)
    assert tdis.start_date_time == expected


def test_bang_comment_and_block_keyword_remarks():
    """`!` starts a comment, like `#`, and begin/end after a line's first
    token are data (a remark), not a block boundary."""
    from flopy4.mf6.codec.reader import loads

    raw = loads("BEGIN TIMESERIES\n! time rate\n0.0 1.0 begin SP 1\n1.0 2.0 end\nEND TIMESERIES\n")
    rows = [r for r in raw["TIMESERIES"] if r]
    assert rows == [[0.0, 1.0, "begin", "SP", 1], [1.0, 2.0, "end"]]


@pytest.mark.parametrize(
    "line,single,multi", [("SFAC 1.5", 1.5, None), ("SFACS 2.0 3.0", None, [2.0, 3.0])]
)
def test_ts_sfac_load(tmp_path, line, single, multi):
    """SFAC and SFACS load into their own records, and a loaded Ts keeps
    its default name."""
    from flopy4.mf6.utl.ts import Ts

    path = tmp_path / "a.ts"
    path.write_text(
        f"BEGIN ATTRIBUTES\n  NAMES a b\n  METHODS linear linear\n  {line}\nEND ATTRIBUTES\n"
        "BEGIN TIMESERIES\n  0.0 1.0 2.0\nEND TIMESERIES\n"
    )
    ts = Ts.load(path)
    assert ts.name == "ts"
    assert (ts.sfacrecord_single.sfacval if ts.sfacrecord_single else None) == single
    assert (ts.sfac.sfacval if ts.sfac else None) == multi


@pytest.mark.parametrize("keyword", ["NAMES", "NAME"])
def test_ts_names_alias_load(tmp_path, keyword):
    """MF6 takes NAME for NAMES."""
    from flopy4.mf6.utl.ts import Ts

    path = tmp_path / "a.ts"
    path.write_text(
        f"BEGIN ATTRIBUTES\n  {keyword} a b\n  METHODS linear linear\nEND ATTRIBUTES\n"
        "BEGIN TIMESERIES\n  0.0 1.0 2.0\nEND TIMESERIES\n"
    )
    assert Ts.load(path).time_series_name.time_series_names == ["a", "b"]


def test_ats_hpc_children_load_and_write(tmp_path):
    """TDIS's ATS6 and the simulation's HPC6 and TDIS6 files load as children
    and are written back."""
    from flopy4.mf6.simulation import Simulation

    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "mfsim.nam").write_text(
        "BEGIN OPTIONS\n  HPC6 FILEIN sim.hpc\nEND OPTIONS\n"
        "BEGIN TIMING\n  TDIS6 sim.tdis\nEND TIMING\n"
    )
    (src / "sim.tdis").write_text(
        "BEGIN OPTIONS\n  ATS6 FILEIN sim.ats\nEND OPTIONS\n"
        "BEGIN DIMENSIONS\n  NPER 1\nEND DIMENSIONS\n"
        "BEGIN PERIODDATA\n  1.0 1 1.0\nEND PERIODDATA\n"
    )
    (src / "sim.ats").write_text(
        "BEGIN DIMENSIONS\n  MAXATS 1\nEND DIMENSIONS\n"
        "BEGIN PERIODDATA\n  1 0.5 0.1 1.0 2.0 2.0\nEND PERIODDATA\n"
    )
    (src / "sim.hpc").write_text("BEGIN PARTITIONS\n  gwf 0\nEND PARTITIONS\n")

    sim = Simulation.load(src / "mfsim.nam")
    assert [r.dt0 for r in sim.tdis.ats.perioddata] == [0.5]
    assert [r.mname for r in sim.hpc.partitions] == ["gwf"]

    out.mkdir()
    sim.workspace = out
    sim.write()
    simnam = (out / "mfsim.nam").read_text()
    assert "HPC6 FILEIN sim.hpc" in simnam
    assert "TDIS6 sim.tdis\n" in simnam
    assert "ATS6 FILEIN sim.ats" in (out / "sim.tdis").read_text()
    reloaded = Simulation.load(out / "mfsim.nam")
    assert [r.dt0 for r in reloaded.tdis.ats.perioddata] == [0.5]
    assert [r.mname for r in reloaded.hpc.partitions] == ["gwf"]


def test_spc_round_trip(tmp_path):
    """SPC's `bndno CONCENTRATION value` rows load and dump."""
    from flopy4.mf6.utl.spc import Spc

    path = tmp_path / "gwt.spc"
    path.write_text(
        "BEGIN OPTIONS\n  PRINT_INPUT\nEND OPTIONS\n"
        "BEGIN DIMENSIONS\n  MAXBOUND 2\nEND DIMENSIONS\n"
        "BEGIN PERIOD 1\n  1 CONCENTRATION 100.0\n  2 CONCENTRATION myts\nEND PERIOD\n"
        "BEGIN PERIOD 3\n  1 CONCENTRATION 0.0\nEND PERIOD\n"
    )
    spc = Spc.load(path)
    rows = spc.stress_period_data
    assert [(r.bndno, r.concentration) for r in rows[0]] == [(0, 100.0), (1, "myts")]
    assert [(r.bndno, r.concentration) for r in rows[2]] == [(0, 0.0)]
    assert spc.maxbound == 2

    dumped = dumps(COMPONENT_CONVERTER.unstructure(spc))
    assert "MAXBOUND 2" in dumped
    assert "1 CONCENTRATION 100.0" in dumped
    assert "2 CONCENTRATION myts" in dumped
    path.write_text(dumped)
    assert Spc.load(path).stress_period_data == rows


OBS_TEXT = """BEGIN OPTIONS
  DIGITS 10
END OPTIONS

BEGIN CONTINUOUS FILEOUT Heads.csv
  h1 HEAD well-a
  h2 HEAD well-b
END CONTINUOUS

BEGIN CONTINUOUS FILEOUT flows.bsv BINARY
  w1 WEL well-a
END CONTINUOUS FILEOUT flows.bsv BINARY
"""


def test_obs_header_blocks_round_trip(tmp_path):
    """Each CONTINUOUS block keeps its own header (file name case, BINARY)
    and rows through load and write."""
    from flopy4.mf6.utl import Obs

    path = tmp_path / "a.obs"
    path.write_text(OBS_TEXT)
    obs = Obs.load(path)
    first, second = obs.continuous
    assert first.output == Obs.Output(obs_output_file_name=Path("Heads.csv"))
    assert second.output.binary
    assert [r.obsname for r in first.continuous] == ["h1", "h2"]
    assert [r.obsname for r in second.continuous] == ["w1"]

    dumped = dumps(COMPONENT_CONVERTER.unstructure(obs))
    assert "BEGIN CONTINUOUS FILEOUT Heads.csv\n" in dumped
    assert "BEGIN CONTINUOUS FILEOUT flows.bsv BINARY\n" in dumped
    assert "END CONTINUOUS FILEOUT" not in dumped
    path.write_text(dumped)
    assert Obs.load(path).continuous == obs.continuous


@pytest.mark.parametrize(
    "tokens, ncelldim, union_arm, id_, id2",
    [
        # a boundname, whatever the parent
        (["well-a"], 3, "cellid", "well-a", None),
        (["well-a"], 0, "index", "well-a", None),
        # a model's or stress package's cellids
        (["1", "2", "3"], 3, "cellid", (0, 1, 2), None),
        (["1", "2", "3", "1", "2", "4"], 3, "cellid", (0, 1, 2), (0, 1, 3)),
        (["1", "5", "1", "6"], 2, "cellid", (0, 4), (0, 5)),
        # an advanced package's or exchange's indexes
        (["1"], 3, "index", 0, None),
        (["2", "3"], 3, "index", 1, 2),
        (["lake-1", "3"], 3, "index", "lake-1", 2),
        # CSUB: indexes by default, but a row as wide as a cellid is one
        (["1", "2", "3"], 3, "index", (0, 1, 2), None),
        # UZF's water-content depth fits no arm: kept as is
        (["2", "0.5"], 3, "index", 1, 0.5),
        # no grid: a cellid as wide as the row
        (["1", "2", "3"], 0, "cellid", (0, 1, 2), None),
    ],
)
def test_obs_ids(tokens, ncelldim, union_arm, id_, id2):
    """An OBS id is a cellid, an index or a boundname, by the parent's kind
    and the row's width."""
    from flopy4.mf6.utl import Obs

    row = Obs.Continuous.from_tokens(
        ["o1", "head", *tokens], ncelldim=ncelldim, union_arm=union_arm
    )
    assert (row.id_, row.id2) == (id_, id2)
    assert [str(t) for t in row.to_tokens()[2:]] == tokens


def test_obs_ids_ignore_trailing_tokens():
    """Like MF6, tokens past the ids are ignored (test051's notes)."""
    from flopy4.mf6.utl import Obs

    tokens = ["o1", "water-content", "1", "1.0", "(UZF", "CELL", "1)"]
    row = Obs.Continuous.from_tokens(tokens, ncelldim=3, union_arm="index")
    assert (row.id_, row.id2) == (0, 0)


def test_obs_ids_by_parent(tmp_path):
    """A package keyed by an index (LAK) reads its OBS ids as indexes; one
    keyed by cellids (WEL) as cellids."""
    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Lak, Wel

    (tmp_path / "p.obs").write_text("BEGIN CONTINUOUS FILEOUT p.csv\n  o1 x 1 2\nEND CONTINUOUS\n")
    raw = loads("BEGIN OPTIONS\n  OBS6 FILEIN p.obs\nEND OPTIONS\n")
    dims = {"nlay": 1, "ncpl": 10, "nodes": 10}
    lak = structure_component(
        raw, Lak, context=LoadContext(workspace=tmp_path, dims={**dims, "nrow": 2, "ncol": 5})
    )
    wel = structure_component(raw, Wel, context=LoadContext(workspace=tmp_path, dims=dims))
    (lak_row,) = lak.obs.continuous[0].continuous
    (wel_row,) = wel.obs.continuous[0].continuous
    assert (lak_row.id_, lak_row.id2) == (0, 1)
    assert (wel_row.id_, wel_row.id2) == ((0, 1), None)


_DISV = {"nlay": 1, "ncpl": 10, "nodes": 10}
_DISU = {"nodes": 10}


@pytest.mark.parametrize(
    "parent,dims,row,ids",
    [
        ("Csub", _DISV, "csub-cell 1 5", ((0, 4), None)),
        ("Csub", _DISU, "csub-cell 7", ((6,), None)),
        ("Csub", _DISV, "csub 3", (2, None)),
        ("Csub", _DISV, "delay-head 1 2", (0, 1)),
        ("Uzf", _DISV, "water-content 2 3", (1, 3.0)),  # a whole-number depth
        ("Uzf", _DISV, "uzf-gwrch 4 (UZF CELLS 16-24)", (3, None)),  # a note
        ("Lak", _DISV, "stage lake-a", ("lake-a", None)),
    ],
)
def test_obs_ids_by_obstype(tmp_path, parent, dims, row, ids):
    """OBS ids read as the parent's observation type takes them."""
    from flopy4.mf6 import gwf
    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.converter.ingress.structure import structure_component

    (tmp_path / "p.obs").write_text(f"BEGIN CONTINUOUS FILEOUT p.csv\n  o1 {row}\nEND CONTINUOUS\n")
    raw = loads("BEGIN OPTIONS\n  OBS6 FILEIN p.obs\nEND OPTIONS\n")
    pkg = structure_component(
        raw, getattr(gwf, parent), context=LoadContext(workspace=tmp_path, dims=dims)
    )
    (obs_row,) = pkg.obs.continuous[0].continuous
    assert (obs_row.id_, obs_row.id2) == ids


def test_block_end_keeps_only_an_index():
    assert writer.filters.block_begin("continuous FILEOUT Heads.csv") == (
        "CONTINUOUS FILEOUT Heads.csv"
    )
    assert writer.filters.block_end("continuous FILEOUT Heads.csv") == "CONTINUOUS"
    assert writer.filters.block_end("period 1") == "PERIOD 1"
    assert writer.filters.block_end("time 0.5") == "TIME 0.5"
    assert writer.filters.block_end("options") == "OPTIONS"


def test_unknown_option_warns():
    """A row no field takes, in a block with other fields, warns: MF6 would
    reject it, so it's likely one flopy4 doesn't support yet."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Npf

    raw = loads("BEGIN OPTIONS\n  SAVE_FLOWS\n  NOT_AN_OPTION 1\nEND OPTIONS\n")
    with pytest.warns(UserWarning, match="Npf: no field takes OPTIONS entry NOT_AN_OPTION"):
        npf = structure_component(raw, Npf)
    assert npf.save_flows


def test_computed_dimension_does_not_warn():
    """A list package's MAXBOUND is computed from its rows, not read."""
    import warnings

    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd

    raw = loads("BEGIN DIMENSIONS\n  MAXBOUND 1\nEND DIMENSIONS\n")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        structure_component(raw, Chd)


def test_options_open_close(tmp_path):
    """An options block can be OPEN/CLOSE-redirected to a file."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Npf

    (tmp_path / "npf_options.ref").write_text("SAVE_FLOWS\nPERCHED\n")
    raw = loads("BEGIN OPTIONS\n  OPEN/CLOSE npf_options.ref\nEND OPTIONS\n")
    npf = structure_component(raw, Npf, context=LoadContext(workspace=tmp_path))
    assert npf.save_flows and npf.perched


def test_netcdf_dump_only_netcdf_fields():
    """With use_netcdf, only arrays of netcdf-capable (dfn) fields are written
    `NETCDF`; others keep their data, as MF6 has no variable to read."""
    from flopy4.mf6.gwf import Npf
    from flopy4.mf6.prt.mip import Mip
    from flopy4.mf6.write_context import WriteContext

    ctx = WriteContext(use_netcdf=True)
    mip = dumps(COMPONENT_CONVERTER.unstructure(Mip(porosity=np.array([0.1, 0.2]))), context=ctx)
    npf = dumps(
        COMPONENT_CONVERTER.unstructure(Npf(k=np.array([1.0, 2.0]), icelltype=np.array([0, 0]))),
        context=ctx,
    )

    assert "NETCDF" not in mip.upper()
    assert "0.1 0.2" in mip
    assert "K NETCDF" in npf.upper()

    # opt-in: an array egress did not mark keeps its data
    from flopy4.mf6.codec.writer.filters import array_how

    assert array_how(xr.DataArray([1.0, 2.0]), netcdf=True) == "internal"
