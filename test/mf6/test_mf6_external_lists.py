"""Tests for writing lists to files of their own, as OPEN/CLOSE, text or
binary."""

import textwrap
import warnings
from pathlib import Path

import numpy as np
import pytest

from flopy4.mf6.external import ExternalFileError, write_external_lists
from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc, Wel
from flopy4.mf6.ims import Ims
from flopy4.mf6.item_table import Rows
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.tdis import Tdis
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import ListIO, WriteContext, list_hash

DIMS = {"nlay": 1, "nrow": 1, "ncol": 3, "nodes": 3}

# a CHD row with one aux value, as MF6 reads it from a binary file
CHD_ROW = np.dtype([("cellid", "<i4", (3,)), ("head", "<f8"), ("aux", "<f8")])


def _lines(path: Path, *words: str) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines() if any(w in ln for w in words)]


def _chd_rows(path: Path) -> list:
    records = np.frombuffer(path.read_bytes(), dtype=CHD_ROW)
    return [(tuple(r["cellid"].tolist()), float(r["head"]), float(r["aux"])) for r in records]


def _chd(tmp_path: Path, **kwargs) -> Chd:
    chd = Chd(
        auxiliary=["c"],
        stress_period_data={
            0: [[(0, 0, 0), 10.0, 1.5], [(0, 0, 2), 2.0, 2.5]],
            2: [[(0, 0, 2), 3.0, 0.0]],
        },
        **kwargs,
    )
    chd.filename = str(tmp_path / "m.chd")
    return chd


def test_list_format_binary_writes_period_files(tmp_path):
    """list_format="binary" writes each period's list to a binary file
    named for the component, field and period: each row's values back to
    back, cellids 1-based, with no header."""
    chd = _chd(tmp_path)
    chd.write(context=WriteContext(list_format="binary"))
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE m_chd_stress_period_data_p1.bin (BINARY)",
        "OPEN/CLOSE m_chd_stress_period_data_p3.bin (BINARY)",
    ]
    assert _chd_rows(tmp_path / "m_chd_stress_period_data_p1.bin") == [
        ((1, 1, 1), 10.0, 1.5),
        ((1, 1, 3), 2.0, 2.5),
    ]
    again = Chd.load(chd.path, dims=DIMS, context=LoadContext(workspace=tmp_path))
    assert again.stress_period_data == chd.stress_period_data


def test_list_format_open_close_writes_text_files(tmp_path):
    chd = _chd(tmp_path)
    chd.write(context=WriteContext(list_format="open/close"))
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE m_chd_stress_period_data_p1.txt",
        "OPEN/CLOSE m_chd_stress_period_data_p3.txt",
    ]
    assert (tmp_path / "m_chd_stress_period_data_p1.txt").read_text().splitlines() == [
        "1 1 1 10.0 1.5",
        "1 1 3 2.0 2.5",
    ]
    again = Chd.load(chd.path, dims=DIMS, context=LoadContext(workspace=tmp_path))
    assert again.stress_period_data == chd.stress_period_data


def test_list_io_path_and_format(tmp_path):
    """A list's own ListIO beats the context's list_format; a path alone
    is a text file; a field's entry is every period's."""
    chd = _chd(tmp_path)
    chd.write(
        context=WriteContext(
            list_format="internal",
            lists={
                ("stress_period_data", 0): ListIO(path="p1.dat"),
                ("stress_period_data", 2): ListIO(format="binary"),
            },
        )
    )
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE p1.dat",
        "OPEN/CLOSE m_chd_stress_period_data_p3.bin (BINARY)",
    ]
    chd.write(context=WriteContext(lists={"stress_period_data": ListIO(format="open/close")}))
    assert len(_lines(chd.path, "OPEN/CLOSE")) == 2


def test_binary_threshold(tmp_path):
    """With a threshold, only lists bigger than it are written binary:
    a CHD row with an aux value is 28 bytes."""
    chd = _chd(tmp_path)
    chd.write(context=WriteContext(list_format="binary", binary_threshold=28))
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE m_chd_stress_period_data_p1.bin (BINARY)",
    ]


@pytest.fixture
def loaded_chd(tmp_path):
    """A CHD whose periods are in files: one text, one binary, and two
    sharing a text file."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "p1.txt").write_text("1 1 1 10.0 1.5\n1 1 3 2.0 2.5\n")
    rows = np.array([((1, 1, 2), 4.0, 0.5)], dtype=CHD_ROW)
    (ws / "p2.bin").write_bytes(rows.tobytes())
    (ws / "shared.txt").write_text("1 1 2 5.0 0.0\n")
    (ws / "m.chd").write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
              AUXILIARY c
            END OPTIONS
            BEGIN DIMENSIONS
              MAXBOUND 2
            END DIMENSIONS
            BEGIN PERIOD 1
              OPEN/CLOSE p1.txt
            END PERIOD 1
            BEGIN PERIOD 2
              OPEN/CLOSE 'p2.bin' (BINARY)
            END PERIOD 2
            BEGIN PERIOD 3
              OPEN/CLOSE shared.txt
            END PERIOD 3
            BEGIN PERIOD 4
              OPEN/CLOSE shared.txt
            END PERIOD 4
        """)
    )
    chd = Chd.load(ws / "m.chd", dims=DIMS, context=LoadContext(workspace=ws))
    out = tmp_path / "out"
    out.mkdir()
    chd.filename = str(out / "out.chd")
    return chd, out


def test_load_records_list_files(loaded_chd):
    chd, _ = loaded_chd
    lists = chd.write_context.lists
    assert lists == {
        ("stress_period_data", 0): ListIO(path=Path("p1.txt"), format="open/close"),
        ("stress_period_data", 1): ListIO(path=Path("p2.bin"), format="binary"),
        ("stress_period_data", 2): ListIO(path=Path("shared.txt"), format="open/close"),
        ("stress_period_data", 3): ListIO(path=Path("shared.txt"), format="open/close"),
    }
    assert lists[("stress_period_data", 1)].hash == list_hash([[1, 1, 2, 4.0, 0.5]])


def test_write_keeps_list_files(loaded_chd):
    chd, out = loaded_chd
    chd.write()
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE p1.txt",
        "OPEN/CLOSE p2.bin (BINARY)",
        "OPEN/CLOSE shared.txt",
        "OPEN/CLOSE shared.txt",
    ]
    assert (out / "p1.txt").read_text().splitlines() == ["1 1 1 10.0 1.5", "1 1 3 2.0 2.5"]
    assert _chd_rows(out / "p2.bin") == [((1, 1, 2), 4.0, 0.5)]
    again = Chd.load(chd.path, dims=DIMS, context=LoadContext(workspace=out))
    assert again.stress_period_data == chd.stress_period_data


def test_internal_beats_loaded_list_files(loaded_chd):
    chd, out = loaded_chd
    chd.write(context=WriteContext(list_format="internal"))
    assert _lines(chd.path, "OPEN/CLOSE") == []
    assert not (out / "p1.txt").exists()


def test_open_close_writes_loaded_binary_list_as_text(loaded_chd):
    chd, out = loaded_chd
    chd.write(context=WriteContext(list_format="open/close"))
    assert _lines(chd.path, "OPEN/CLOSE")[1] == "OPEN/CLOSE p2.bin"
    assert (out / "p2.bin").read_text().split() == ["1", "1", "2", "4.0", "0.5"]


def test_shared_list_file_kept_by_unchanged_period(loaded_chd):
    """Edit one period of a shared file and it's written inline, with a
    warning naming it; the unchanged period keeps the file."""
    chd, out = loaded_chd
    chd.stress_period_data[2] = [Chd.StressPeriodData(cellid=(0, 0, 1), head=6.0, aux=(0.0,))]
    with pytest.warns(UserWarning, match="period 3 changed since loaded"):
        chd.write()
    assert _lines(chd.path, "OPEN/CLOSE")[2:] == ["OPEN/CLOSE shared.txt"]
    assert _lines(chd.path, "6.0") == ["1 1 2 6.0 0.0"]
    assert (out / "shared.txt").read_text().split() == ["1", "1", "2", "5.0", "0.0"]


def test_strict_raises_on_disagreeing_shared_list_file(loaded_chd):
    chd, out = loaded_chd
    chd.stress_period_data[2] = [Chd.StressPeriodData(cellid=(0, 0, 1), head=6.0, aux=(0.0,))]
    with pytest.raises(ExternalFileError, match="changed since loaded"):
        chd.write(context=WriteContext(strict=True))
    assert not (out / "shared.txt").exists()


def test_boundnames_written_as_text(tmp_path):
    """MF6 can't read a boundname from a binary file: list_format="binary"
    writes such rows as text, and a list's own "binary" warns too."""
    chd = Chd(
        boundnames=True,
        stress_period_data={0: [[(0, 0, 0), 10.0, "east"]], 1: [[(0, 0, 0), 9.0]]},
    )
    chd.filename = str(tmp_path / "m.chd")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        chd.write(context=WriteContext(list_format="binary"))
    assert _lines(chd.path, "OPEN/CLOSE") == [
        "OPEN/CLOSE m_chd_stress_period_data_p1.txt",
        "OPEN/CLOSE m_chd_stress_period_data_p2.txt",
    ]
    context = WriteContext(lists={"stress_period_data": ListIO(format="binary")})
    with pytest.warns(UserWarning, match="period 1: MF6 can't read these rows from a binary"):
        chd.write(context=context)
    with pytest.raises(ExternalFileError, match="period 1: MF6 can't read"):
        chd.write(context=WriteContext(strict=True).over(context))


def test_time_series_names_written_as_text(tmp_path):
    """A time series' name, where MF6 would read a number from a binary
    file, makes the rows text."""
    rows = Rows(
        3,
        field="stress_period_data",
        item_cls=Chd.StressPeriodData,
        layout=lambda: ({}, frozenset()),
    )
    rows.append([Chd.StressPeriodData(cellid=(0, 0, 0), head="myts")])
    data = {"period 1": {"period": rows}}
    context = WriteContext.resolve(
        WriteContext(lists={"stress_period_data": ListIO(format="binary")})
    )
    with pytest.warns(UserWarning, match="MF6 can't read these rows from a binary"):
        out = write_external_lists(data, tmp_path, Path("m.chd"), "chd", context)
    assert out["period 1"]["period"].open_close_binary is False
    assert (tmp_path / "m_chd_stress_period_data_p1.txt").read_text() == "1 1 1 myts\n"


def test_list_format_binary_writes_other_blocks_as_text(tmp_path):
    """MF6 reads a binary list only into a block it knows the length of,
    as a period's: list_format="binary" writes TDIS's PERIODDATA as text,
    unless its own ListIO says binary."""
    tdis = Tdis(nper=2, perioddata=[(1.0, 1, 1.0), (2.0, 2, 1.0)])
    tdis.filename = str(tmp_path / "sim.tdis")
    tdis.write(context=WriteContext(list_format="binary"))
    assert _lines(tdis.path, "OPEN/CLOSE") == ["OPEN/CLOSE sim_tdis_perioddata.txt"]
    tdis.write(context=WriteContext(lists={"perioddata": ListIO(format="binary")}))
    assert _lines(tdis.path, "OPEN/CLOSE") == ["OPEN/CLOSE sim_tdis_perioddata.bin (BINARY)"]
    data = (tmp_path / "sim_tdis_perioddata.bin").read_bytes()
    assert len(data) == 2 * (8 + 4 + 8)


def test_list_sharing_its_block_written_inline(tmp_path):
    """Only a list alone in its block can go to a file."""
    rows = Rows(field="rows")
    rows.append([Wel.StressPeriodData(cellid=(0, 0, 0), q=1.0)])
    data = {"options": {"flag": True, "rows": rows}}
    context = WriteContext.resolve(WriteContext(lists={"rows": ListIO(path="r.txt")}))
    with pytest.warns(UserWarning, match="only a list alone in its block"):
        out = write_external_lists(data, tmp_path, Path("m.pkg"), "pkg", context)
    assert out is data
    assert not (tmp_path / "r.txt").exists()


def _sim(workspace: Path) -> Simulation:
    sim = Simulation(
        name="sim",
        workspace=workspace,
        tdis=Time(perlen=[1.0, 1.0], nstp=[1, 2]),
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
    dis = Dis(nlay=2, nrow=3, ncol=4, delr=1.0, delc=1.0, top=10.0, botm=[5.0, 0.0])
    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    Ic(parent=gwf, strt=10.0)
    Npf(parent=gwf, k=1.0, icelltype=0)
    Chd(
        parent=gwf,
        auxiliary=["c"],
        stress_period_data={0: [[(0, 0, 0), 10.0, 1.0], [(1, 2, 3), 2.0, 2.0]]},
    )
    Wel(
        parent=gwf,
        stress_period_data={
            0: [[(1, 1, 1), -0.1]],
            1: [[(1, 1, 1), -0.3], [(0, 1, 2), 0.05]],
        },
    )
    Oc(parent=gwf, head_file="gwf.hds", stress_period_data={0: [("SAVE", "HEAD", "ALL")]})
    return sim


@pytest.mark.parametrize("list_format", ["open/close", "binary"])
def test_mf6_reads_list_files(function_tmpdir, list_format):
    """MF6 runs a simulation written with every list in a file of its own
    (period lists binary, with "binary"; OC's and TDIS's text) and gets
    the same heads as from the inline write."""
    inline, external = function_tmpdir / "inline", function_tmpdir / "external"
    sim = _sim(inline)
    sim.write()
    sim.run()
    sim = _sim(external)
    sim.write(context=WriteContext(list_format=list_format))
    suffix = ".bin (BINARY)" if list_format == "binary" else ".txt"
    assert f"OPEN/CLOSE gwf_wel0_wel_stress_period_data_p2{suffix}" in _lines(
        external / "gwf.wel0.wel", "OPEN/CLOSE"
    )
    assert _lines(external / "gwf.oc", "OPEN/CLOSE") == [
        "OPEN/CLOSE gwf_oc_stress_period_data_p1.txt"
    ]
    sim.run()
    assert (inline / "gwf.hds").read_bytes() == (external / "gwf.hds").read_bytes()
