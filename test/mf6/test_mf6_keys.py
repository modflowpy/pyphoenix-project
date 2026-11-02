"""String keys (MVR's packages and model names, HPC's model names) are
checked when written: see `flopy4.mf6.keys`."""

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
