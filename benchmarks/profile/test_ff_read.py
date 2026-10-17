"""Frenchman Flat binary output reads (see `_ff.py`): heads and budgets,
opened lazily and computed.

The output comes from running the model with ``mf6`` first, once per
session (about 500 time steps; slow).

- `test_hds` -- ``open_hds``: `open` only builds the lazy array; `first`
  computes the first time step of an open array; `all` opens and
  computes every time step.
- `test_cbc` -- ``open_cbc``: `open`, or `all`, which computes every
  budget term.
"""

import shutil

import pytest
from _ff import NAME, build_flopy4
from _scenario import bench

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    """The model's workspace, after a run."""
    if shutil.which("mf6") is None:
        pytest.skip("needs mf6")
    ws = tmp_path_factory.mktemp("ff")
    sim = build_flopy4(ws).sim
    sim.write()
    sim.run()
    return ws


@pytest.mark.parametrize("what", ["open", "first", "all"])
def test_hds(benchmark, quiet, output, what):
    from flopy4.mf6.utils.heads_reader import open_hds

    hds, grb = output / f"{NAME}.hds", output / f"{NAME}.dis.grb"
    benchmark.group = "ff-read-hds"
    benchmark.extra_info["n_bytes"] = hds.stat().st_size
    if what == "open":
        bench(benchmark, lambda: open_hds(hds, grb))
    elif what == "first":
        head = open_hds(hds, grb)
        bench(benchmark, lambda: head[0].compute())
    else:
        bench(benchmark, lambda: open_hds(hds, grb).compute())


@pytest.mark.parametrize("what", ["open", "all"])
def test_cbc(benchmark, quiet, output, what):
    from flopy4.mf6.utils.cbc_reader import open_cbc

    cbc, grb = output / f"{NAME}.cbc", output / f"{NAME}.dis.grb"
    benchmark.group = "ff-read-cbc"
    benchmark.extra_info["n_bytes"] = cbc.stat().st_size
    if what == "open":
        bench(benchmark, lambda: open_cbc(cbc, grb))
    else:
        bench(benchmark, lambda: open_cbc(cbc, grb).compute())
