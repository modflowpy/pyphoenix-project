"""Dimensions counting a list's rows follow the list when it's mutated in place."""

import pytest

from flopy4.mf6.gwf import Disv
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utl.ats import Ats


def _disv() -> Disv:
    return Disv(
        nlay=1,
        vertices=[(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 1.0, 1.0), (3, 0.0, 1.0)],
        cell2d=[(0, 0.5, 0.5, 4, (0, 1, 2, 3))],
        top=1.0,
        botm=0.0,
    )


def test_get_dims_follows_appended_rows():
    d = _disv()
    assert (d.nvert, d.ncpl) == (4, 1)
    d.vertices.append(d.Vertices(iv=4, xv=2.0, yv=0.0))
    d.cell2d.append(d.Cell2d(icell2d=1, xc=1.5, yc=0.5, ncvert=3, icvert=(1, 4, 2)))
    dims = d.get_dims()
    assert (dims["nvert"], dims["ncpl"], dims["nodes"]) == (5, 2, 2)
    assert (d.nvert, d.ncpl) == (5, 2)


def test_get_dims_follows_removed_rows():
    d = _disv()
    d.vertices.pop()
    assert d.get_dims()["nvert"] == 3


def test_write_follows_appended_rows(tmp_path):
    d = _disv()
    d.vertices.append(d.Vertices(iv=4, xv=2.0, yv=0.0))
    d.filename = tmp_path / "x.disv"
    d.write()
    text = d.filename.read_text().upper()
    assert any(line.split() == ["NVERT", "5"] for line in text.splitlines())


def test_tdis_nper_follows_appended_rows():
    t = Tdis(nper=1, perioddata=[(1.0, 1, 1.0)])
    t.perioddata.append(t.Perioddata(perlen=2.0, nstp=2, tsmult=1.0))
    assert t.get_dims()["nper"] == 2


def test_bounded_dim_is_not_overwritten():
    a = Ats(maxats=3, perioddata=[(0, 1.0, 0.1, 2.0, 2.0, 2.0)])
    a.perioddata.append(a.Perioddata(1, 1.0, 0.1, 2.0, 2.0, 2.0))
    a._sync_dims()
    assert a.maxats == 3


def test_bounded_dim_raises_when_exceeded():
    a = Ats(maxats=1, perioddata=[(0, 1.0, 0.1, 2.0, 2.0, 2.0)])
    a.perioddata.append(a.Perioddata(1, 1.0, 0.1, 2.0, 2.0, 2.0))
    with pytest.raises(ValueError, match="maxats"):
        a._sync_dims()
