from pathlib import Path
from types import SimpleNamespace

import pytest

from flopy4.mf6 import LoadContext
from flopy4.mf6.exg.gwfgwf import Gwfgwf
from flopy4.mf6.gwf import Chd


def _model(ncelldim: int | None):
    """A stand-in model whose discretization has the given cellid width,
    or none at all."""
    dis = None if ncelldim is None else SimpleNamespace(get_dims=lambda: {"ncelldim": ncelldim})
    return SimpleNamespace(dis=dis)


def test_resolve_absolute_path_as_is(tmp_path):
    assert LoadContext(workspace="sim").resolve(tmp_path / "m.dis") == tmp_path / "m.dis"


def test_resolve_relative_path_against_workspace():
    assert LoadContext(workspace="sim").resolve("gwf/m.dis") == Path("sim/gwf/m.dis")


def test_resolve_without_workspace_raises():
    with pytest.raises(ValueError, match="no workspace"):
        LoadContext().resolve("m.dis")


def test_ncelldim_from_dims():
    context = LoadContext(dims={"nlay": 1, "ncpl": 4, "nodes": 4})
    assert context.ncelldim(Chd.StressPeriodData, [[1, 2, 3, 1.0]]) == 2


def test_ncelldim_from_rows():
    assert LoadContext().ncelldim(Chd.StressPeriodData, [[1, 2, 3, 1.0]]) == 3


def test_ncelldim_per_column_under_exchange():
    """Each cellid column takes its own model's grid width, whatever the
    dims or the row length say."""
    context = LoadContext(dims={"nodes": 4}, exchange=(_model(3), _model(2)))
    rows = [[1, 1, 2, 1, 1, 1, 0.5, 0.5, 1.0]]
    assert context.ncelldim(Gwfgwf.Exchangedata, rows) == {"cellidm1": 3, "cellidm2": 2}


def test_ncelldim_under_exchange_without_dis_from_rows():
    context = LoadContext(exchange=(_model(3), _model(None)))
    rows = [[1, 1, 2, 1, 1, 1, 1, 0.5, 0.5, 1.0]]
    assert context.ncelldim(Gwfgwf.Exchangedata, rows) == 3
