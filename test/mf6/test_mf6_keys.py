"""Keys (MVR's packages and model names, HPC's model names, LAK's and SFR's
feature numbers) are checked when written: see `flopy4.mf6.keys`."""

import pytest

from flopy4.mf6.exg.gwfgwf import Gwfgwf
from flopy4.mf6.gwf import Dis, Drn, Gwf, Ic, Lak, Mvr, Npf, Wel
from flopy4.mf6.ims import Ims
from flopy4.mf6.keys import key_errors
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time


def _gwf(name):
    gwf = Gwf(name=name, dis=Dis(nlay=1, nrow=1, ncol=2))
    Ic(parent=gwf)
    Npf(parent=gwf)
    Wel(parent=gwf, name="wel", mover=True, period_data={0: [((0, 0, 0), -1.0)]})
    Drn(parent=gwf, name="drn", mover=True, period_data={0: [((0, 0, 1), 1.0, 1.0)]})
    Lak(parent=gwf, name="lak", mover=True, nlakes=1, packagedata=[(0, 1.0, 1)])
    return gwf


def _mvr(packages, moves, **kwargs):
    return Mvr(
        maxpackages=len(packages),
        maxmvr=len(moves),
        packages=packages,
        period_data={0: moves},
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
    mvr = _mvr([("wel",), ("LAK",)], [("WEL", 0, "lak", 0, "FACTOR", 1.0)])
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
            "Mvr.period_data: period 0: pname2 'riv' isn't in packages",
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


def _exchange_mvr(tmp_path, packages, moves, extra=()):
    a, b = _gwf("a"), _gwf("b")
    mvr = _mvr(packages, moves, modelnames=True)
    exg = Gwfgwf(
        exgmnamea=a,
        exgmnameb=b,
        exchangedata=[((0, 0, 1), (0, 0, 0), 1, 0.5, 0.5, 1.0)],
        mvr=mvr,
    )
    _sim(tmp_path, a, b, *extra, exchanges=[exg])
    return mvr


def test_exchange_mvr_keys(tmp_path):
    """A package name is unique within its model (its scope), and a move's
    provider and receiver name a model's package."""
    mvr = _exchange_mvr(
        tmp_path,
        [("a", "wel"), ("B", "wel"), ("b", "lak")],
        [("a", "wel", 0, "b", "LAK", 0, "FACTOR", 1.0)],
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
            "Mvr.period_data: period 0: pname2 'drn' (mname2 'a') isn't in packages",
        ),
    ],
)
def test_exchange_mvr_key_errors(tmp_path, packages, moves, error):
    mvr = _exchange_mvr(tmp_path, packages, moves)
    assert key_errors(mvr) == [error]


# Integer keys are 0-based indices in memory; an fk that may allow_zero is
# None (0 in the file) for no row.


def _lak(outlets=(), periods=()):
    from flopy4.mf6.gwf import Lak

    return Lak(
        nlakes=2,
        noutlets=len(outlets),
        packagedata=[(0, 1.0, 1), (1, 1.0, 1)],
        outlets=[(*o, "SPECIFIED", 0.0, 0.0, 0.0, 0.0) for o in outlets] or None,
        period_data={0: list(periods)} if periods else None,
    )


def test_lak_keys():
    lak = _lak(
        outlets=[(0, 0, 1), (1, 1, None)],  # lakeout None: out of the model
        periods=[(1, "STATUS", "ACTIVE"), (1, "RATE", 1.0)],
    )
    assert key_errors(lak) == []


@pytest.mark.parametrize(
    "outlets, periods, error",
    [
        ([(0, 0, 1), (0, 1, 0)], [], "Lak.outlets: outletno 0 is listed more than once"),
        ([(0, 2, 1)], [], "Lak.outlets: lakein 2 isn't in packagedata"),
        ([(0, -1, 1)], [], "Lak.outlets: lakein -1 isn't in packagedata"),
        ([(0, 0, -1)], [], "Lak.outlets: lakeout -1 isn't in packagedata"),
        ([(0, 0, 1)], [(5, "STAGE", 1.0)], "period 0: lakeno 5 isn't in packagedata"),
        ([(0, 0, 1)], [(3, "RATE", 1.0)], "period 0: outletno 3 isn't in outlets"),
    ],
)
def test_lak_key_errors(outlets, periods, error):
    (actual,) = key_errors(_lak(outlets, periods))
    assert actual.endswith(error)


@pytest.mark.parametrize(
    "ivertcon, errors", [(None, []), (1, []), (2, ["ivertcon 2"]), (-1, ["ivertcon -1"])]
)
def test_uzf_ivertcon(ivertcon, errors):
    from flopy4.mf6.gwf import Uzf

    uzf = Uzf(
        nuzfcells=2,
        packagedata=[
            (0, (0, 0, 0), 1, ivertcon, 0.1, 1.0, 0.05, 0.3, 0.2, 3.5),
            (1, (1, 0, 0), 0, None, 0.1, 1.0, 0.05, 0.3, 0.2, 3.5),
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
    cdb = Cdb(parent=chf, period_data={0: [[(0,), 0, 1.0], [(1,), 1, 1.0]]})
    assert key_errors(cdb) == [
        "Cdb.period_data: period 0: idcxs 1 isn't in packagedata of cxs 'cxs'"
    ]


@pytest.mark.parametrize(
    "move, error",
    [
        (("wel", 1, "lak", 0), "id1 1 isn't below the maxbound of wel 'wel' (1)"),
        (("lak", 0, "lak", 0), "id1 0 isn't in outlets of lak 'lak'"),
        (("wel", 0, "lak", 1), "id2 1 isn't in packagedata of lak 'lak'"),
        (("wel", 0, "wel", 0), "id2 0 is in wel 'wel', which isn't a mover receiver"),
    ],
)
def test_model_mvr_id_errors(move, error):
    gwf = _gwf("flow")
    mvr = _mvr([("wel",), ("lak",)], [(*move, "FACTOR", 1.0)])
    mvr.parent = gwf
    assert key_errors(mvr) == [f"Mvr.period_data: period 0: {error}"]


def test_exchange_mvr_model_outside_exchange(tmp_path):
    """An exchange's mover names only the exchange's models."""
    mvr = _exchange_mvr(tmp_path, [("a", "wel")], [], extra=[_gwf("c")])
    mvr.packages = [("c", "wel")]
    assert key_errors(mvr) == ["Mvr.packages: mname 'c' isn't a model of gwfgwf 'gwfgwf-1' (a, b)"]


@pytest.mark.parametrize(
    "period, also",
    [
        (
            [("wel", 0, "lak", 0, "FACTOR", 1.0)],
            ["Mvr.period_data: period 0: id1 0 is in wel 'wel', which hasn't mover on"],
        ),
        ([], []),
    ],
)
def test_model_mvr_mover_off(period, also):
    """A mover's packages need MOVER on (rule mover_enabled), whether or not
    a period row names them."""
    gwf = _gwf("flow")
    gwf.wel[0].mover = False
    mvr = _mvr([("wel",), ("lak",)], period)
    mvr.parent = gwf
    assert key_errors(mvr) == ["Mvr.packages: pname 'wel' hasn't mover on", *also]


def test_model_mvr_role_off():
    """A package plays the mover roles only with MOVER on (the key sets'
    ``when``), so a period row naming one fails too."""
    gwf = _gwf("flow")
    gwf.lak[0].mover = False
    mvr = _mvr([("wel",), ("lak",)], [("wel", 0, "lak", 0, "FACTOR", 1.0)])
    mvr.parent = gwf
    assert key_errors(mvr) == [
        "Mvr.packages: pname 'lak' hasn't mover on",
        "Mvr.period_data: period 0: id2 0 is in lak 'lak', which hasn't mover on",
    ]


def test_model_mvr_not_mover():
    """A package with no mover roles can't be listed (rule mover_enabled)."""
    from flopy4.mf6.gwf import Chd

    gwf = _gwf("flow")
    Chd(parent=gwf, name="chd", period_data={0: [((0, 0, 1), 1.0)]})
    mvr = _mvr([("wel",), ("chd",)], [])
    mvr.parent = gwf
    assert key_errors(mvr) == ["Mvr.packages: pname 'chd' isn't a mover"]


def test_exchange_mvr_mover_off(tmp_path):
    a, b = _gwf("a"), _gwf("b")
    a.wel[0].mover = False
    mvr = _mvr([("a", "wel"), ("b", "wel")], [], modelnames=True)
    exg = Gwfgwf(
        exgmnamea=a,
        exgmnameb=b,
        exchangedata=[((0, 0, 1), (0, 0, 0), 1, 0.5, 0.5, 1.0)],
        mvr=mvr,
    )
    _sim(tmp_path, a, b, exchanges=[exg])
    assert key_errors(mvr) == ["Mvr.packages: pname 'wel' (mname 'a') hasn't mover on"]


def _transport(tmp_path, pname="wel", bndno=0, exchange=True):
    from flopy4.mf6.exg.gwfgwt import Gwfgwt
    from flopy4.mf6.gwt import Dis as GwtDis
    from flopy4.mf6.gwt import Gwt, Ssm
    from flopy4.mf6.utl.spc import Spc

    gwf = _gwf("flow")
    gwt = Gwt(name="trans", dis=GwtDis(nlay=1, nrow=1, ncol=2))
    spc = Spc(maxbound=1, period_data={0: [(bndno, Spc.Concentration(1.0))]})
    ssm = Ssm(parent=gwt, fileinput=[(pname, spc)])
    exchanges = [Gwfgwt(exgmnamea=gwf, exgmnameb=gwt)] if exchange else []
    _sim(tmp_path, gwf, gwt, exchanges=exchanges)
    return ssm, spc


def test_ssm_spc_keys(tmp_path):
    ssm, spc = _transport(tmp_path)
    assert spc._parent is ssm
    assert key_errors(ssm) == []
    assert key_errors(spc) == []


def test_ssm_pname_not_in_flow_model(tmp_path):
    ssm, spc = _transport(tmp_path, pname="riv")
    assert key_errors(ssm) == ["Ssm.fileinput: pname 'riv' isn't in packages of gwf 'flow'"]
    assert key_errors(spc) == []  # reported by SSM


def test_ssm_pname_without_exchange(tmp_path):
    """Without an exchange there's no flow model to check against."""
    ssm, spc = _transport(tmp_path, pname="riv", exchange=False)
    assert key_errors(ssm) == []
    assert key_errors(spc) == []


def test_spc_bndno_past_bounds(tmp_path):
    _, spc = _transport(tmp_path, bndno=1)
    assert key_errors(spc) == [
        "Spc.period_data: period 0: bndno 1 isn't below the maxbound of wel 'wel' (1)"
    ]


# Connection and diversion numbers are unique within their feature
# (`pk = {scope = "ifno"}`), and referenced with it.


def _lak_connections(connections):
    from flopy4.mf6.gwf import Lak

    conn = ("VERTICAL", 0.1, 0.0, 0.0, 0.0, 0.0)
    return Lak(
        nlakes=2,
        packagedata=[(0, 1.0, 2), (1, 1.0, 1)],
        connectiondata=[
            (lake, iconn, (0, 0, i), *conn) for i, (lake, iconn) in enumerate(connections)
        ],
    )


def test_lak_connection_keys():
    # each lake numbers its own connections
    assert key_errors(_lak_connections([(0, 0), (0, 1), (1, 0)])) == []


def test_lak_connection_repeated():
    assert key_errors(_lak_connections([(0, 0), (0, 0), (1, 0)])) == [
        "Lak.connectiondata: iconn 0 (ifno 0) is listed more than once"
    ]


def test_maw_angle_names_a_connection():
    from flopy4.mf6.gwf import Maw

    maw = Maw(
        nmawwells=2,
        packagedata=[(0, 0.1, 0.0, 1.0, "THIEM", 2), (1, 0.1, 0.0, 1.0, "THIEM", 1)],
        connectiondata=[
            (0, 0, (0, 0, 0), 1.0, 0.0, 1.0, 0.2),
            (0, 1, (0, 0, 1), 1.0, 0.0, 1.0, 0.2),
            (1, 0, (0, 0, 1), 1.0, 0.0, 1.0, 0.2),
        ],
        angledata=[(0, 1, 30.0), (1, 1, 30.0)],  # well 2 has one connection
    )
    assert key_errors(maw) == ["Maw.angledata: icon 1 (ifno 1) isn't in connectiondata"]


def _sfr_diversions(periods=()):
    from flopy4.mf6.gwf import Sfr

    reach = (1.0, 1.0, 0.001, 0.0, 1.0, 1.0, 0.03, 1, 1.0)
    return Sfr(
        nreaches=2,
        packagedata=[(0, (0, 0, 0), *reach, 1), (1, (0, 0, 1), *reach, 0)],
        connectiondata=[(0, (-2,)), (1, (1,))],
        diversions=[(0, 0, 1, "UPTO")],
        period_data={0: [(r, Sfr.Diversion(d, 1.0)) for r, d in periods]} or None,
    )


def test_sfr_period_diversion_keys():
    assert key_errors(_sfr_diversions([(0, 0)])) == []


@pytest.mark.parametrize(
    "periods, error",
    [
        ([(0, 1)], "idv 1 (ifno 0) isn't in diversions"),
        # reach 2 has no diversions; its diversion 1 isn't reach 1's
        ([(1, 0)], "idv 0 (ifno 1) isn't in diversions"),
    ],
)
def test_sfr_period_diversion_errors(periods, error):
    assert key_errors(_sfr_diversions(periods)) == [f"Sfr.period_data: period 0: {error}"]


def test_ssm_package_in_both_lists(tmp_path):
    ssm, _ = _transport(tmp_path)
    ssm.sources = [("wel", "AUX", "conc")]
    assert key_errors(ssm) == ["Ssm.fileinput: pname 'wel' is also in sources"]


def test_spc_on_advanced_package(tmp_path):
    """SPC on an advanced package numbers its bounds: LAK's connections."""
    _, spc = _transport(tmp_path, pname="lak", bndno=1)
    assert key_errors(spc) == [
        "Spc.period_data: period 0: bndno 1 isn't below the nlakeconn of lak 'lak' (1)"
    ]


def test_spc_on_advanced_package_with_apt(tmp_path):
    """MF6 ignores SPC on a flow package an advanced transport package is
    paired with, so it isn't checked."""
    from flopy4.mf6.gwt import Lkt

    ssm, spc = _transport(tmp_path, pname="lak", bndno=5)
    Lkt(parent=ssm._parent, name="lkt", flow_package_name="lak")
    assert key_errors(spc) == []
