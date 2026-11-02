"""Keys (MVR's packages and model names, HPC's model names, LAK's and SFR's
feature numbers) are checked when written: see `flopy4.mf6.keys`."""

import pytest

from flopy4.mf6.exg.gwfgwf import Gwfgwf
from flopy4.mf6.gwf import Dis, Drn, Gwf, Ic, Mvr, Npf, Wel
from flopy4.mf6.ims import Ims
from flopy4.mf6.keys import key_errors
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time


def _gwf(name):
    gwf = Gwf(name=name, dis=Dis(nlay=1, nrow=1, ncol=2))
    Ic(parent=gwf)
    Npf(parent=gwf)
    Wel(parent=gwf, name="wel", mover=True, stress_period_data={0: [((0, 0, 0), -1.0)]})
    Drn(parent=gwf, name="drn", mover=True, stress_period_data={0: [((0, 0, 1), 1.0, 1.0)]})
    return gwf


def _mvr(packages, moves, **kwargs):
    return Mvr(
        maxpackages=len(packages),
        maxmvr=len(moves),
        packages=packages,
        stress_period_data={0: moves},
        **kwargs,
    )


def _sim(tmp_path, *models, **kwargs):
    return Simulation(
        tdis=Time(perlen=[1.0], nstp=[1], tsmult=[1.0]),
        workspace=tmp_path,
        models=list(models),
        solutiongroup=[Ims()],
        **kwargs,
    )


def test_model_mvr_keys():
    gwf = _gwf("flow")
    mvr = _mvr([("wel",), ("DRN",)], [("WEL", 0, "drn", 0, "FACTOR", 1.0)])
    mvr.parent = gwf
    assert key_errors(mvr) == []


@pytest.mark.parametrize(
    "packages, moves, error",
    [
        (
            [("wel",), ("WEL",)],
            [],
            "Mvr.packages: pname 'WEL' is listed more than once",
        ),
        (
            [("wel",), ("riv",)],
            [],
            "Mvr.packages: pname 'riv' isn't in packages of gwf 'flow'",
        ),
        (
            [("wel",), ("drn",)],
            [("wel", 0, "riv", 0, "FACTOR", 1.0)],
            "Mvr.stress_period_data: period 0: pname2 'riv' isn't in packages",
        ),
    ],
)
def test_model_mvr_key_errors(packages, moves, error):
    gwf = _gwf("flow")
    mvr = _mvr(packages, moves)
    mvr.parent = gwf
    assert key_errors(mvr) == [error]


def test_mvr_key_error_on_write(tmp_path):
    gwf = _gwf("flow")
    _sim(tmp_path, gwf)
    _mvr([("wel",)], [("wel", 0, "drn", 0, "FACTOR", 1.0)], parent=gwf)
    with pytest.raises(ValueError, match="pname2 'drn' isn't in packages"):
        gwf.write()


def _exchange_mvr(tmp_path, packages, moves):
    a, b = _gwf("a"), _gwf("b")
    mvr = _mvr(packages, moves, modelnames=True)
    exg = Gwfgwf(
        exgmnamea=a,
        exgmnameb=b,
        exchangedata=[((0, 0, 1), (0, 0, 0), 1, 0.5, 0.5, 1.0)],
        mvr=mvr,
    )
    _sim(tmp_path, a, b, exchanges=[exg])
    return mvr


def test_exchange_mvr_keys(tmp_path):
    """A package name is unique within its model (its scope), and a move's
    provider and receiver name a model's package."""
    mvr = _exchange_mvr(
        tmp_path,
        [("a", "wel"), ("B", "wel"), ("b", "drn")],
        [("a", "wel", 0, "b", "DRN", 0, "FACTOR", 1.0)],
    )
    assert key_errors(mvr) == []


@pytest.mark.parametrize(
    "packages, moves, error",
    [
        (
            [("a", "wel"), ("A", "WEL")],
            [],
            "Mvr.packages: pname 'WEL' (mname 'A') is listed more than once",
        ),
        (
            [("c", "wel")],
            [],
            "Mvr.packages: mname 'c' isn't in models of the simulation",
        ),
        (
            [("a", "riv")],
            [],
            "Mvr.packages: pname 'riv' (mname 'a') isn't in packages of gwf 'a'",
        ),
        (
            [("a", "wel"), ("b", "drn")],
            [("a", "wel", 0, "a", "drn", 0, "FACTOR", 1.0)],
            "Mvr.stress_period_data: period 0: pname2 'drn' (mname2 'a') isn't in packages",
        ),
    ],
)
def test_exchange_mvr_key_errors(tmp_path, packages, moves, error):
    mvr = _exchange_mvr(tmp_path, packages, moves)
    assert key_errors(mvr) == [error]


# Integer keys are 0-based indices in memory; an fk that may allow_zero is
# -1 (0 in the file) for no row.


def _lak(outlets=(), periods=()):
    from flopy4.mf6.gwf import Lak

    return Lak(
        nlakes=2,
        noutlets=len(outlets),
        packagedata=[(0, 1.0, 1), (1, 1.0, 1)],
        outlets=[(*o, "SPECIFIED", 0.0, 0.0, 0.0, 0.0) for o in outlets] or None,
        stress_period_data={0: list(periods)} if periods else None,
    )


def test_lak_keys():
    lak = _lak(
        outlets=[(0, 0, 1), (1, 1, -1)],  # lakeout -1: out of the model
        periods=[(1, "STATUS", "ACTIVE"), (1, "RATE", 1.0)],
    )
    assert key_errors(lak) == []


@pytest.mark.parametrize(
    "outlets, periods, error",
    [
        ([(0, 0, 1), (0, 1, 0)], [], "Lak.outlets: outletno 0 is listed more than once"),
        ([(0, 2, 1)], [], "Lak.outlets: lakein 2 isn't in packagedata"),
        ([(0, -1, 1)], [], "Lak.outlets: lakein -1 isn't in packagedata"),
        ([(0, 0, 1)], [(5, "STAGE", 1.0)], "period 0: lakeno 5 isn't in packagedata"),
        ([(0, 0, 1)], [(3, "RATE", 1.0)], "period 0: outletno 3 isn't in outlets"),
    ],
)
def test_lak_key_errors(outlets, periods, error):
    (actual,) = key_errors(_lak(outlets, periods))
    assert actual.endswith(error)


@pytest.mark.parametrize("ivertcon, errors", [(-1, []), (1, []), (2, ["ivertcon 2"])])
def test_uzf_ivertcon(ivertcon, errors):
    from flopy4.mf6.gwf import Uzf

    uzf = Uzf(
        nuzfcells=2,
        packagedata=[
            (0, (0, 0, 0), 1, ivertcon, 0.1, 1.0, 0.05, 0.3, 0.2, 3.5),
            (1, (1, 0, 0), 0, -1, 0.1, 1.0, 0.05, 0.3, 0.2, 3.5),
        ],
    )
    assert [e.split(": ")[1].split(" isn't")[0] for e in key_errors(uzf)] == errors


def _sfr(ic):
    from flopy4.mf6.gwf import Sfr

    reach = (1.0, 1.0, 0.001, 0.0, 1.0, 1.0, 0.03, 1, 1.0, 0)
    return Sfr(
        nreaches=2,
        packagedata=[(0, (0, 0, 0), *reach), (1, (0, 0, 1), *reach)],
        connectiondata=[(0, ic), (1, (1,))],  # reach 2's upstream is reach 1
    )


def test_sfr_ic_keys():
    # -2: reach 2 (1 in memory), downstream; the fk is on the magnitude
    assert key_errors(_sfr((-2,))) == []


def test_sfr_ic_key_errors():
    assert key_errors(_sfr((-3,))) == ["Sfr.connectiondata: ic 2 isn't in packagedata"]


def test_chf_cross_section_keys(tmp_path):
    """A CDB's cross section is a row of the model's CXS, a sibling."""
    from flopy4.mf6.chf import Chf
    from flopy4.mf6.chf.cdb import Cdb
    from flopy4.mf6.chf.cxs import Cxs

    chf = Chf(name="m")
    Cxs(parent=chf, nsections=1, npoints=2, packagedata=[(0, 2)])
    cdb = Cdb(parent=chf, stress_period_data={0: [[(0,), 0, 1.0], [(1,), 1, 1.0]]})
    assert key_errors(cdb) == [
        "Cdb.stress_period_data: period 0: idcxs 1 isn't in packagedata of cxs 'cxs'"
    ]
