"""flopy3's period-data constructor keywords, accepted with a warning."""

import warnings

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
    renames = dict(_renames())
    assert renames["gwf-lak"] == "perioddata"
    assert renames["gwt-lkt"] == "lakeperioddata"
    assert renames["gwe-sfe"] == "reachperioddata"
    assert renames["gwt-mwt"] == "mwtperioddata"
    assert renames["gwe-uze"] == "uzeperioddata"
    assert len(renames) == 17


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
