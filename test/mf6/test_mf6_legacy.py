"""flopy3's period-data constructor keywords and attributes."""

import warnings

import attrs
import pytest

from flopy4.mf6.component import get_fnames
from flopy4.mf6.gwf import Lak, Oc, Sto
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.legacy import oc_period_data, sto_period_data


def _renames():
    return sorted(
        (cls.dfn_name, old)
        for cls in set(get_fnames().values())
        for old, legacy in cls.legacy_kwargs.items()
        if legacy.convert is None
    )


@pytest.mark.parametrize(("dfn_name", "old"), _renames())
def test_rename(dfn_name, old):
    cls = get_fnames()[dfn_name]
    with pytest.warns(DeprecationWarning, match=f"{old}=.*use stress_period_data=") as record:
        legacy = cls(**{old: {}})
    assert len(record) == 1
    assert legacy == cls(stress_period_data={})


def test_renames():
    assert {
        ("gwf-lak", "perioddata"),
        ("gwt-lkt", "lakeperioddata"),
        ("gwe-sfe", "reachperioddata"),
        ("gwt-mwt", "mwtperioddata"),
        ("gwe-uze", "uzeperioddata"),
    } <= set(_renames())


def test_attribute_reads_and_assigns_stress_period_data():
    lak = Lak(stress_period_data={})
    match = "perioddata is deprecated; use stress_period_data"
    with pytest.warns(DeprecationWarning, match=match) as record:
        assert lak.perioddata is lak.stress_period_data
    assert record[0].filename == __file__

    with pytest.warns(DeprecationWarning, match=match) as record:
        lak.perioddata = {}
    assert record[0].filename == __file__
    assert lak.stress_period_data == {}
    assert "perioddata" not in vars(lak)


def test_attribute_assignment_is_coerced_like_stress_period_data():
    lak = Lak()
    with pytest.warns(DeprecationWarning):
        lak.perioddata = {0: [(0, "status", "active")]}
    assert lak.stress_period_data[0][0].status == "active"


@pytest.mark.parametrize(
    ("cls", "old"),
    [
        (Sto, "steady_state"),
        (Sto, "transient"),
        (Oc, "saverecord"),
        (Oc, "printrecord"),
    ],
)
def test_converted_attribute_raises(cls, old):
    pkg = cls()
    with pytest.raises(AttributeError, match=f"{old} is gone.*stress_period_data"):
        getattr(pkg, old)
    with pytest.raises(AttributeError, match=f"{old} is gone.*stress_period_data"):
        setattr(pkg, old, {})
    assert not hasattr(pkg, old)


def test_legacy_names_are_not_fields():
    for cls in set(get_fnames().values()):
        assert not set(cls.legacy_kwargs) & set(attrs.fields_dict(cls)), cls.dfn_name


def test_warning_points_at_caller():
    with pytest.warns(DeprecationWarning) as record:
        Lak(perioddata={})
    assert record[0].filename == __file__


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"steady_state": {0: True}}, {0: [("STEADY-STATE",)]}),
        ({"steady_state": True}, {0: [("STEADY-STATE",)]}),
        ({"steady_state": [0, 2]}, {0: [("STEADY-STATE",)], 2: [("STEADY-STATE",)]}),
        ({"transient": {1: True}}, {1: [("TRANSIENT",)]}),
        (
            {"steady_state": {0: True}, "transient": {1: True}},
            {0: [("STEADY-STATE",)], 1: [("TRANSIENT",)]},
        ),
        ({"steady_state": {0: True, 1: False}}, {0: [("STEADY-STATE",)]}),
    ],
)
def test_sto(kwargs, expected):
    assert sto_period_data(**kwargs) == expected
    with pytest.warns(DeprecationWarning) as record:
        sto = Sto(**kwargs)
    assert len(record) == 1
    assert sto == Sto(stress_period_data=expected)


def test_sto_conflict():
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="period 0 is both"):
        Sto(steady_state={0: True}, transient=[0])


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"saverecord": [("HEAD", "ALL")]}, {0: [("SAVE", "HEAD", "ALL")]}),
        ({"saverecord": ("HEAD", "ALL")}, {0: [("SAVE", "HEAD", "ALL")]}),
        (
            {"saverecord": {0: [("HEAD", "ALL")], 2: [("BUDGET", "FREQUENCY", 2)]}},
            {0: [("SAVE", "HEAD", "ALL")], 2: [("SAVE", "BUDGET", "FREQUENCY", 2)]},
        ),
        (
            {
                "printrecord": {0: [("BUDGET", "LAST")], 1: [("HEAD", "STEPS", 1, 2)]},
                "saverecord": [("HEAD", "ALL"), ("BUDGET", "ALL")],
            },
            {
                0: [
                    ("SAVE", "HEAD", "ALL"),
                    ("SAVE", "BUDGET", "ALL"),
                    ("PRINT", "BUDGET", "LAST"),
                ],
                1: [("PRINT", "HEAD", "STEPS", 1, 2)],
            },
        ),
    ],
)
def test_oc(kwargs, expected):
    assert oc_period_data(**kwargs) == expected
    with pytest.warns(DeprecationWarning) as record:
        oc = Oc(**kwargs)
    assert len(record) == 1
    assert oc == Oc(stress_period_data=expected)


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        (Lak, {"perioddata": {}}),
        (Sto, {"transient": True}),
        (Oc, {"printrecord": [("BUDGET", "ALL")]}),
    ],
)
def test_old_and_new(cls, kwargs):
    with pytest.raises(TypeError, match="got both .* and stress_period_data="):
        cls(stress_period_data={}, **kwargs)


def test_no_legacy_kwargs():
    assert Ic.legacy_kwargs == {}
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        Ic(strt=1.0, dims={"nodes": 1})
    with pytest.raises(TypeError, match="perioddata"):
        Ic(perioddata={}, dims={"nodes": 1})
