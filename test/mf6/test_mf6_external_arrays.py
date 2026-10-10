"""Tests for writing arrays to files of their own, as OPEN/CLOSE."""

import textwrap
import warnings
from pathlib import Path

import numpy as np
import pytest

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.gwf.rcha import Rcha
from flopy4.mf6.ims import Ims
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import ArrayIO, WriteContext


def _lines(path: Path, *words: str) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines() if any(w in ln for w in words)]


@pytest.fixture
def loaded_dis(tmp_path):
    """A DIS whose arrays are in files: one beside it, one outside its
    workspace, one per layer of a LAYERED array."""
    ws, data = tmp_path / "ws", tmp_path / "data"
    ws.mkdir()
    data.mkdir()
    (ws / "delr.txt").write_text("1 2 3\n")
    (data / "top.txt").write_text("5 6 7\n")
    (ws / "botm2.txt").write_text("-2 -3 -4\n")
    (ws / "m.dis").write_text(
        textwrap.dedent("""\
            BEGIN DIMENSIONS
              NLAY 2
              NROW 1
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                OPEN/CLOSE delr.txt IPRN 2
              DELC
                CONSTANT 1.0
              TOP
                OPEN/CLOSE ../data/top.txt
              BOTM LAYERED
                INTERNAL
                  0.0 -1.0 0.5
                OPEN/CLOSE botm2.txt
            END GRIDDATA
        """)
    )
    dis = Dis.load(ws / "m.dis", context=LoadContext(workspace=ws))
    out = tmp_path / "out"
    out.mkdir()
    dis.filename = str(out / "out.dis")
    return dis, out


def test_load_records_files(loaded_dis):
    dis, _ = loaded_dis
    assert dis.write_context.arrays == {
        "delr": ArrayIO(iprn=2, path=Path("delr.txt")),
        "top": ArrayIO(path=Path("../data/top.txt")),
        ("botm", 1): ArrayIO(path=Path("botm2.txt")),
    }


def test_write_keeps_files(loaded_dis):
    """Loaded files are written back as files, a LAYERED array's per
    layer; one outside the workspace is copied in, with a warning."""
    dis, out = loaded_dis
    with pytest.warns(UserWarning, match="top.txt is outside"):
        dis.write()
    assert _lines(dis.path, "OPEN/CLOSE", "INTERNAL") == [
        "OPEN/CLOSE delr.txt IPRN 2",
        "OPEN/CLOSE top.txt",
        "INTERNAL",
        "OPEN/CLOSE botm2.txt",
    ]
    assert (out / "delr.txt").read_text().split() == ["1.0", "2.0", "3.0"]
    assert (out / "top.txt").read_text().split() == ["5.0", "6.0", "7.0"]
    assert (out / "botm2.txt").read_text().split() == ["-2.0", "-3.0", "-4.0"]


def test_write_file_with_edited_values(loaded_dis):
    """A file holds the array's values when written, not when loaded."""
    dis, out = loaded_dis
    dis.delr[:] = 9.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dis.write()
    assert (out / "delr.txt").read_text().split() == ["9.0"] * 3


def test_internal_overrides_loaded_files(loaded_dis):
    """A higher context's array_format="internal" beats loaded paths."""
    dis, out = loaded_dis
    dis.write(context=WriteContext(array_format="internal"))
    assert _lines(dis.path, "OPEN/CLOSE") == []
    assert not (out / "delr.txt").exists()


def test_array_path_beats_whole_write_format_of_same_context(loaded_dis):
    dis, out = loaded_dis
    dis.write_context = None
    dis.write(context=WriteContext(array_format="internal", arrays={"delr": ArrayIO(path="d.txt")}))
    assert _lines(dis.path, "OPEN/CLOSE") == ["OPEN/CLOSE d.txt"]


def test_open_close_writes_every_array(loaded_dis):
    """array_format="open/close" writes each array to a file named for its
    component and field, and each layer of a layered one to its own."""
    dis, out = loaded_dis
    dis.write_context = None
    dis.write(context=WriteContext(array_format="open/close"))
    assert _lines(dis.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE out_dis_delr.txt",
        "OPEN/CLOSE out_dis_delc.txt",
        "OPEN/CLOSE out_dis_top.txt",
        "OPEN/CLOSE out_dis_botm_l1.txt",
        "OPEN/CLOSE out_dis_botm_l2.txt",
    ]
    assert (out / "out_dis_botm_l1.txt").read_text().split() == ["0.0", "-1.0", "0.5"]


def test_whole_array_path_for_layered_array(tmp_path):
    """A layered array's whole-array path holds every layer, not LAYERED."""
    dis = Dis(nlay=2, nrow=1, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=[0.0, 0.5, -1.0, -2.0])
    dis.filename = str(tmp_path / "m.dis")
    dis.write_context = WriteContext(arrays={"botm": ArrayIO(path="botm.txt")})
    dis.write()
    assert _lines(dis.path, "BOTM", "OPEN/CLOSE") == ["BOTM", "OPEN/CLOSE botm.txt"]
    assert np.loadtxt(tmp_path / "botm.txt").tolist() == [[0.0, 0.5], [-1.0, -2.0]]


@pytest.fixture
def shared_rcha(tmp_path):
    """RCHA periods 1 and 3 from one file."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "rch.txt").write_text("0.1 0.1 0.1 0.1\n")
    (ws / "m.rcha").write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
              READASARRAYS
            END OPTIONS
            BEGIN PERIOD 1
             RECHARGE
              OPEN/CLOSE rch.txt
            END PERIOD 1
            BEGIN PERIOD 3
             RECHARGE
              OPEN/CLOSE rch.txt
            END PERIOD 3
        """)
    )
    rcha = Rcha.load(ws / "m.rcha", dims={"nlay": 1, "nodes": 4}, context=LoadContext(workspace=ws))
    out = tmp_path / "out"
    out.mkdir()
    rcha.filename = str(out / "out.rcha")
    return rcha


def test_shared_file_kept_while_arrays_agree(shared_rcha):
    shared_rcha.write()
    assert _lines(shared_rcha.path, "OPEN/CLOSE") == ["OPEN/CLOSE rch.txt"] * 2


def test_shared_file_inlined_when_arrays_disagree(shared_rcha):
    """Edit one period of a shared file and every array using it is
    written inline, with a warning naming them."""
    shared_rcha.recharge[0][:] = 0.5
    with pytest.warns(UserWarning, match="period 1, rcha.recharge period 3 use this file"):
        shared_rcha.write()
    assert _lines(shared_rcha.path, "OPEN/CLOSE") == []
    assert _lines(shared_rcha.path, "CONSTANT") == ["CONSTANT 0.5", "CONSTANT 0.1"]


def test_shared_outside_file_copied_once(tmp_path):
    """Arrays sharing a file outside the workspace share one copy in it;
    another outside file with the same name gets a suffix."""
    ws = tmp_path / "ws"
    for d in ("ws", "a", "b"):
        (tmp_path / d).mkdir()
    (tmp_path / "a" / "rch.txt").write_text("0.1 0.1 0.1 0.1\n")
    (tmp_path / "b" / "rch.txt").write_text("0.2 0.2 0.2 0.2\n")
    (ws / "m.rcha").write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
              READASARRAYS
            END OPTIONS
            BEGIN PERIOD 1
             RECHARGE
              OPEN/CLOSE ../a/rch.txt
            END PERIOD 1
            BEGIN PERIOD 2
             RECHARGE
              OPEN/CLOSE ../a/rch.txt
            END PERIOD 2
            BEGIN PERIOD 3
             RECHARGE
              OPEN/CLOSE ../b/rch.txt
            END PERIOD 3
        """)
    )
    rcha = Rcha.load(ws / "m.rcha", dims={"nlay": 1, "nodes": 4}, context=LoadContext(workspace=ws))
    out = tmp_path / "out"
    out.mkdir()
    rcha.filename = str(out / "out.rcha")
    with pytest.warns(UserWarning, match="outside"):
        rcha.write()
    assert _lines(rcha.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE rch.txt",
        "OPEN/CLOSE rch.txt",
        "OPEN/CLOSE rch_1.txt",
    ]
    assert (out / "rch_1.txt").read_text().split() == ["0.2"] * 4


def _sim(workspace: Path) -> Simulation:
    sim = Simulation(
        name="sim",
        workspace=workspace,
        tdis=Time(perlen=[1.0], nstp=[1]),
        solutiongroup=[
            Ims(
                models=["gwf"],
                outer_dvclose=1e-9,
                outer_maximum=100,
                inner_maximum=300,
                inner_dvclose=1e-9,
                linear_acceleration="cg",
            )
        ],
    )
    dis = Dis(
        nlay=2,
        nrow=3,
        ncol=4,
        delr=[1.0, 2.0, 3.0, 4.0],
        delc=1.0,
        top=10.0,
        botm=np.repeat([5.0, 0.0], 12) + np.tile(np.linspace(0, 0.3, 12), 2),
    )
    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    Ic(parent=gwf, strt=10.0)
    Npf(parent=gwf, k=np.linspace(1.0, 2.0, 24), icelltype=0)
    Chd(parent=gwf, stress_period_data={0: [[(0, 0, 0), 10.0], [(1, 2, 3), 2.0]]})
    Oc(parent=gwf, head_file="gwf.hds", stress_period_data={0: [("SAVE", "HEAD", "LAST")]})
    return sim


def test_mf6_reads_open_close_arrays(function_tmpdir):
    """MF6 runs a simulation written with every array in a file of its own
    and gets the same heads as from the inline write."""
    inline, external = function_tmpdir / "inline", function_tmpdir / "external"
    sim = _sim(inline)
    sim.write()
    sim.run()
    sim = _sim(external)
    sim.write(context=WriteContext(array_format="open/close"))
    assert "OPEN/CLOSE gwf_npf_k.txt" in (external / "gwf.npf").read_text()
    assert "OPEN/CLOSE gwf_dis_botm_l2.txt" in (external / "gwf.dis").read_text()
    sim.run()
    assert (inline / "gwf.hds").read_bytes() == (external / "gwf.hds").read_bytes()
