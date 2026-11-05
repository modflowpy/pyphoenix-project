"""flopy3's period-data constructor keywords and attributes."""

import inspect
import warnings

import attrs
import flopy
import pytest

from flopy4.mf6.component import get_fnames
from flopy4.mf6.gwf import Lak, Oc, Sto, Wel
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
    with pytest.warns(DeprecationWarning, match=f"{old}=.*use period_data=") as record:
        legacy = cls(**{old: {}})
    assert len(record) == 1
    assert legacy == cls(period_data={})


def test_renames():
    assert {
        ("gwf-lak", "perioddata"),
        ("gwt-lkt", "lakeperioddata"),
        ("gwe-sfe", "reachperioddata"),
        ("gwt-mwt", "mwtperioddata"),
        ("gwe-uze", "uzeperioddata"),
    } <= set(_renames())


def test_stress_period_data_matches_flopy3():
    """The alias is on each class whose flopy3 class takes the keyword, and
    on CHF's and OLF's stress packages, which flopy3 doesn't have yet."""

    def flopy3_takes(cls):
        ftype, _, name = cls.dfn_name.partition("-")
        flopy3 = getattr(flopy.mf6, f"Modflow{ftype.capitalize()}{name}", None)
        return flopy3 is not None and (
            "stress_period_data" in inspect.signature(flopy3.__init__).parameters
        )

    classes = set(get_fnames().values())
    unreleased = {f"{m}-{p}" for m in ("chf", "olf") for p in "cdb chd evp flw pcp zdg".split()}
    assert {c.dfn_name for c in classes if flopy3_takes(c)} | unreleased == {
        c.dfn_name for c in classes if "stress_period_data" in c.legacy_kwargs
    }


@pytest.mark.parametrize("cls", [Lak, Oc, Sto])
def test_stress_period_data_not_where_flopy3_has_another_name(cls):
    with pytest.raises(TypeError, match="stress_period_data"):
        cls(stress_period_data={})


def test_stress_period_data_reaches_period_data():
    rows = {0: [((0, 0, 0), -1.0)]}
    with pytest.warns(DeprecationWarning, match="use period_data="):
        wel = Wel(stress_period_data=rows)
    assert wel == Wel(period_data=rows)
    assert wel.period_data[0][0].q == -1.0


def test_stress_period_data_and_period_data_conflict():
    with pytest.raises(TypeError, match="got both"):
        Wel(stress_period_data={}, period_data={})


@pytest.mark.parametrize(
    ("cls", "old"),
    [(Wel, "stress_period_data"), (Lak, "perioddata")],
)
def test_attribute_reads_and_assigns_period_data(cls, old):
    pkg = cls(period_data={})
    match = f"{old} is deprecated; use period_data"
    with pytest.warns(DeprecationWarning, match=match) as record:
        assert getattr(pkg, old) is pkg.period_data
    assert record[0].filename == __file__

    with pytest.warns(DeprecationWarning, match=match) as record:
        setattr(pkg, old, {})
    assert record[0].filename == __file__
    assert pkg.period_data == {}
    assert old not in vars(pkg)


def test_attribute_assignment_is_coerced_like_period_data():
    wel = Wel()
    with pytest.warns(DeprecationWarning):
        wel.stress_period_data = {0: [((0, 0, 0), -1.0)]}
    assert wel.period_data[0][0].q == -1.0


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
    with pytest.raises(AttributeError, match=f"{old} is gone.*period_data"):
        getattr(pkg, old)
    with pytest.raises(AttributeError, match=f"{old} is gone.*period_data"):
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
    assert sto == Sto(period_data=expected)


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
    assert oc == Oc(period_data=expected)


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        (Lak, {"perioddata": {}}),
        (Sto, {"transient": True}),
        (Oc, {"printrecord": [("BUDGET", "ALL")]}),
    ],
)
def test_old_and_new(cls, kwargs):
    with pytest.raises(TypeError, match="got both .* and period_data="):
        cls(period_data={}, **kwargs)


def test_no_legacy_kwargs():
    assert Ic.legacy_kwargs == {}
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        Ic(strt=1.0, dims={"nodes": 1})
    with pytest.raises(TypeError, match="perioddata"):
        Ic(perioddata={}, dims={"nodes": 1})
