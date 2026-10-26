"""
Scoped load-support fix for OPEN/CLOSE (BINARY) period-block list data
(e.g. CHD's). flopy3 generates a real binary stress-period file here, for
an honest round-trip (not a hand-crafted byte string).
"""

import flopy
import pytest


def _write_flopy3_binary_chd(tmp_path):
    sim = flopy.mf6.MFSimulation(sim_name="m", sim_ws=str(tmp_path), exe_name="mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)])
    flopy.mf6.ModflowIms(sim)
    gwf = flopy.mf6.ModflowGwf(sim, modelname="m", save_flows=True)
    flopy.mf6.ModflowGwfdis(gwf, nlay=1, nrow=2, ncol=2, top=1.0, botm=0.0)
    flopy.mf6.ModflowGwfic(gwf, strt=0.0)
    flopy.mf6.ModflowGwfnpf(gwf, k=1.0)
    flopy.mf6.ModflowGwfchd(
        gwf,
        auxiliary=["conc"],
        stress_period_data={
            0: {
                "filename": "m.chd.bin",
                "binary": True,
                "data": [
                    ((0, 0, 0), 1.0, 5.0),
                    ((0, 1, 1), 2.0, 6.0),
                ],
            }
        },
        filename="m.chd",
    )
    sim.write_simulation()
    return tmp_path / "m.chd"


def _write_flopy3_binary_chd_no_aux(tmp_path):
    sim = flopy.mf6.MFSimulation(sim_name="m", sim_ws=str(tmp_path), exe_name="mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)])
    flopy.mf6.ModflowIms(sim)
    gwf = flopy.mf6.ModflowGwf(sim, modelname="m", save_flows=True)
    flopy.mf6.ModflowGwfdis(gwf, nlay=1, nrow=2, ncol=2, top=1.0, botm=0.0)
    flopy.mf6.ModflowGwfic(gwf, strt=0.0)
    flopy.mf6.ModflowGwfnpf(gwf, k=1.0)
    flopy.mf6.ModflowGwfchd(
        gwf,
        stress_period_data={
            0: {
                "filename": "m.chd.bin",
                "binary": True,
                "data": [((0, 0, 0), 1.0), ((0, 1, 1), 2.0)],
            }
        },
        filename="m.chd",
    )
    sim.write_simulation()
    return tmp_path / "m.chd"


def test_structure_component_reads_binary_period_rows_without_aux(tmp_path):
    """The common case (no AUXILIARY option) -- the aux field's dimension
    never resolves, which must not reject the whole row layout."""
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd
    from flopy4.mf6.load_context import LoadContext

    path = _write_flopy3_binary_chd_no_aux(tmp_path)
    from flopy4.mf6.codec.reader import loads

    raw = loads(path.read_text(errors="ignore"))
    context = LoadContext(workspace=tmp_path, dims={"nlay": 1, "nrow": 2, "ncol": 2})
    chd = structure_component(raw, Chd, context=context)

    rows = chd.stress_period_data[0]
    assert len(rows) == 2
    assert tuple(rows[0].cellid) == (0, 0, 0)
    assert rows[0].head == pytest.approx(1.0)
    assert tuple(rows[1].cellid) == (0, 1, 1)
    assert rows[1].head == pytest.approx(2.0)


def test_structure_component_reads_binary_period_rows(tmp_path):
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf import Chd
    from flopy4.mf6.load_context import LoadContext

    path = _write_flopy3_binary_chd(tmp_path)
    text = path.read_text(errors="ignore")
    assert "BINARY" in text.upper(), "flopy3 didn't write OPEN/CLOSE (BINARY)"

    from flopy4.mf6.codec.reader import loads

    raw = loads(text)
    context = LoadContext(workspace=tmp_path, dims={"nlay": 1, "nrow": 2, "ncol": 2})
    chd = structure_component(raw, Chd, context=context)

    rows = chd.stress_period_data[0]
    assert len(rows) == 2
    assert tuple(rows[0].cellid) == (0, 0, 0)
    assert rows[0].head == pytest.approx(1.0)
    assert rows[0].aux == (pytest.approx(5.0),)
    assert tuple(rows[1].cellid) == (0, 1, 1)
    assert rows[1].head == pytest.approx(2.0)
    assert rows[1].aux == (pytest.approx(6.0),)


def test_binary_list_row_spec_rejects_complex_layout():
    from flopy4.mf6.converter.ingress.structure import _binary_list_row_spec
    from flopy4.mf6.gwf import Maw
    from flopy4.mf6.load_context import LoadContext

    context = LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 1})
    # MAW's stress_period_data row has a union field (mawsetting) --
    # not representable in MF6's fixed-width binary list format
    assert _binary_list_row_spec(Maw.StressPeriodData, context, {}) is None


def test_binary_list_row_spec_simple_chd():
    from flopy4.mf6.converter.ingress.structure import _binary_list_row_spec
    from flopy4.mf6.gwf import Chd
    from flopy4.mf6.load_context import LoadContext

    context = LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 1})
    # cellid (3 ints), head (1 double), aux (1 double, from sizes)
    assert _binary_list_row_spec(Chd.StressPeriodData, context, {"auxiliary": 1}) == [
        ("<i4", 3),
        ("<f8", 1),
        ("<f8", 1),
    ]
    # no AUXILIARY given at all -- aux contributes nothing, not an unsupported layout
    assert _binary_list_row_spec(Chd.StressPeriodData, context, {}) == [
        ("<i4", 3),
        ("<f8", 1),
    ]


def test_binary_list_row_spec_when_gated_field():
    from flopy4.mf6.converter.ingress.structure import _binary_list_row_spec
    from flopy4.mf6.gwf import Evt
    from flopy4.mf6.load_context import LoadContext

    context = LoadContext(dims={"nlay": 1, "nrow": 1, "ncol": 1})
    # cellid (3) + surface, rate, depth (1 each); pxdp/petm (nseg-1=0) and
    # aux (no AUXILIARY) contribute nothing; petm0 only when its option is on
    assert _binary_list_row_spec(Evt.StressPeriodData, context, {"nseg-1": 0}) == [
        ("<i4", 3),
        ("<f8", 1),
        ("<f8", 1),
        ("<f8", 1),
    ]
    assert _binary_list_row_spec(
        Evt.StressPeriodData, context, {"nseg-1": 0}, frozenset({"surf_rate_specified"})
    ) == [
        ("<i4", 3),
        ("<f8", 1),
        ("<f8", 1),
        ("<f8", 1),
        ("<f8", 1),
    ]


def test_binary_list_row_spec_two_cellids_and_an_integer_field():
    """GWFGWF's Exchangedata: two cellid fields (one per connected model)
    and a plain integer field (ihc) ahead of the double fields -- not
    just "cellid ints then all doubles"."""
    from flopy4.mf6.converter.ingress.structure import _binary_list_row_spec
    from flopy4.mf6.exg.gwfgwf import Gwfgwf
    from flopy4.mf6.gwf import Dis, Gwf
    from flopy4.mf6.load_context import LoadContext

    model1 = Gwf(name="m1", dis=Dis(nlay=1, nrow=1, ncol=1))
    model2 = Gwf(name="m2", dis=Dis(nlay=1, nrow=1, ncol=1))
    context = LoadContext(exchange=(model1, model2))
    assert _binary_list_row_spec(Gwfgwf.Exchangedata, context, {}) == [
        ("<i4", 3),  # cellidm1 (model 1's DIS)
        ("<i4", 3),  # cellidm2 (model 2's DIS)
        ("<i4", 1),  # ihc
        ("<f8", 1),  # cl1
        ("<f8", 1),  # cl2
        ("<f8", 1),  # hwva
    ]
