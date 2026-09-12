"""Tests for eager loading of codegen v2 packages via ``Package.load(path, dims)``.

``dims_from_grb(grb_path)`` resolves grid dimensions from a binary grid file
so any package can be loaded without manually constructing the dims dict.
"""

import textwrap
from pathlib import Path

import numpy as np
import pytest

from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.utils.grid import dims_from_grb

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GRB_PATH = Path(__file__).parent / "__compare__" / "test_examples" / "quickstart.grb"
# quickstart GRB: DIS 1-layer 10×10 = 100 nodes


@pytest.fixture()
def npf_file(tmp_path) -> Path:
    """Minimal NPF input file for a 1-layer 10×10 grid (100 nodes)."""
    content = textwrap.dedent("""\
        BEGIN OPTIONS
        END OPTIONS
        BEGIN GRIDDATA
         ICELLTYPE
          CONSTANT 0
         K
          CONSTANT 2.5
         K33
          CONSTANT 0.25
        END GRIDDATA
    """)
    p = tmp_path / "model.npf"
    p.write_text(content)
    return p


@pytest.fixture()
def npf_layered_file(tmp_path) -> Path:
    """NPF file with LAYERED ICELLTYPE for a 3-layer 5×5 grid (75 nodes).

    Uses the quickstart GRB (1 layer, 100 nodes) only for shape resolution
    in non-layered tests; layered tests write their own stub GRB via monkeypatch.
    """
    content = textwrap.dedent("""\
        BEGIN OPTIONS
        END OPTIONS
        BEGIN GRIDDATA
         ICELLTYPE LAYERED
          CONSTANT 1
          CONSTANT 0
          CONSTANT 0
         K LAYERED
          CONSTANT 1.0e-3
          CONSTANT 1.0e-4
          CONSTANT 2.0e-4
        END GRIDDATA
    """)
    p = tmp_path / "layered.npf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Eager (numpy) loading
# ---------------------------------------------------------------------------


def test_load_npf_eager_returns_npf(npf_file):
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH))
    assert isinstance(npf, Npf)


def test_load_npf_eager_k_constant(npf_file):
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH))
    assert isinstance(npf.k, np.ndarray)
    assert npf.k.shape == (100,)
    assert np.all(npf.k == 2.5)


def test_load_npf_eager_icelltype_constant(npf_file):
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH))
    assert isinstance(npf.icelltype, np.ndarray)
    assert npf.icelltype.dtype == np.int64
    assert np.all(npf.icelltype == 0)


def test_load_npf_eager_k33_constant(npf_file):
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH))
    assert isinstance(npf.k33, np.ndarray)
    assert np.allclose(npf.k33, 0.25)


def test_load_npf_eager_optional_absent(npf_file):
    """Fields absent from the file (k22, angle1, …) remain None."""
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH))
    assert npf.k22 is None
    assert npf.angle1 is None
    assert npf.wetdry is None


# ---------------------------------------------------------------------------
# Layered format
# ---------------------------------------------------------------------------


def test_load_npf_layered_icelltype(npf_layered_file, tmp_path):
    """LAYERED keyword produces per-layer constant values concatenated flat."""

    class _FakeGrid:
        nlay, nrow, ncol = 3, 5, 5

    from unittest.mock import patch

    with patch("flopy4.adapters.read_binary_grid_file") as mock_grb:
        mock_grb.return_value = {"grid_type": "DIS", "grid": _FakeGrid()}
        npf = Npf.load(npf_layered_file, dims=dims_from_grb(tmp_path / "fake.grb"))

    assert npf.icelltype.shape == (75,)
    # layer 0: all 1, layers 1-2: all 0
    assert np.all(npf.icelltype[:25] == 1)
    assert np.all(npf.icelltype[25:] == 0)

    assert npf.k.shape == (75,)
    assert np.allclose(npf.k[:25], 1.0e-3)
    assert np.allclose(npf.k[25:50], 1.0e-4)
    assert np.allclose(npf.k[50:], 2.0e-4)


# ---------------------------------------------------------------------------
# Package.load() classmethod — direct interface (not via load_npf wrapper)
# ---------------------------------------------------------------------------

DIMS_1L_10X10 = {"nlay": 1, "nodes": 100}


def test_npf_load_classmethod_eager(npf_file):
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_file, dims=DIMS_1L_10X10)
    assert isinstance(npf, Npf)
    assert isinstance(npf.k, np.ndarray)
    assert npf.k.shape == (100,)
    assert np.all(npf.k == 2.5)


# ---------------------------------------------------------------------------
# G/A period fields: READARRAY ingress
# ---------------------------------------------------------------------------

DIMS_1L_5X5 = {"nlay": 1, "nodes": 25}
DIMS_2L_9 = {"nlay": 2, "nodes": 18}  # 2 layers, 9 cells/layer


@pytest.fixture()
def rcha_file(tmp_path) -> Path:
    """Minimal RCHA file with 2 periods of READARRAY data (1 layer, 25 cells)."""
    rch_vals = " ".join(str(0.001) for _ in range(25))
    content = textwrap.dedent(f"""\
        BEGIN OPTIONS
          READASARRAYS
        END OPTIONS
        BEGIN PERIOD 1
         RECHARGE
          INTERNAL
            {rch_vals}
        END PERIOD 1
        BEGIN PERIOD 2
         RECHARGE
          CONSTANT 0.002
        END PERIOD 2
    """)
    p = tmp_path / "model.rcha"
    p.write_text(content)
    return p


@pytest.fixture()
def chdg_file(tmp_path) -> Path:
    """CHDG file with 2 periods of layered READARRAY head data (2 layers, 9 cells)."""
    FILL = 3.0e30
    l1 = " ".join(["1.0" if i == 0 else "0.0" if i == 8 else str(FILL) for i in range(9)])
    l2 = " ".join([str(FILL)] * 9)
    content = textwrap.dedent(f"""\
        BEGIN OPTIONS
          READARRAYGRID
        END OPTIONS
        BEGIN PERIOD 1
         HEAD LAYERED
          INTERNAL
            {l1}
          INTERNAL
            {l2}
        END PERIOD 1
        BEGIN PERIOD 2
         HEAD LAYERED
          CONSTANT {FILL}
          CONSTANT {FILL}
        END PERIOD 2
    """)
    p = tmp_path / "model.chdg"
    p.write_text(content)
    return p


def test_rcha_period_ingress_eager(rcha_file):
    """RCHA period READARRAY fields are populated by Package.load()."""
    from flopy4.mf6.gwf.rcha import Rcha

    rcha = Rcha.load(rcha_file, dims=DIMS_1L_5X5)
    assert isinstance(rcha, Rcha)
    assert isinstance(rcha.recharge, np.ndarray)
    assert rcha.recharge.shape == (2, 25)
    assert np.allclose(rcha.recharge[0], 0.001)  # period 0: INTERNAL
    assert np.allclose(rcha.recharge[1], 0.002)  # period 1: CONSTANT


def test_chdg_period_ingress_layered(chdg_file):
    """CHDG layered READARRAY period ingress produces (nper, nlay, ncpl) head array."""
    from flopy4.mf6.gwf.chdg import Chdg

    chd = Chdg.load(chdg_file, dims=DIMS_2L_9)
    assert isinstance(chd, Chdg)
    assert isinstance(chd.head, np.ndarray)
    assert chd.head.shape == (2, 2, 9)
    # period 0, layer 0: cell 0 = 1.0, cell 8 = 0.0, rest = FILL_DNODATA
    from flopy4.mf6.constants import FILL_DNODATA

    assert chd.head[0, 0, 0] == pytest.approx(1.0)
    assert chd.head[0, 0, 8] == pytest.approx(0.0)
    assert np.all(chd.head[0, 1] == FILL_DNODATA)
    # period 1: all FILL_DNODATA (CONSTANT fill)
    assert np.all(chd.head[1] == FILL_DNODATA)


# ---------------------------------------------------------------------------
# GRIDDATA: OPEN/CLOSE (BINARY) -- no corpus fixture exercises this (checked:
# 0/242 real modflow-devtools models use it), so these write a synthetic
# MF6-format binary-array file themselves rather than relying on a found one.
# ---------------------------------------------------------------------------


def _write_binary_array(path: Path, values: np.ndarray, nrow: int, ncol: int, ilay: int = 1) -> None:
    """Write one MF6 binary-array record: the same 52-byte header
    (KSTP, KPER, PERTIM, TOTIM, TEXT, NCOL, NROW, ILAY) flopy4's own
    `utils/heads_reader.py` decodes from MF6's binary head output,
    followed by the NROW*NCOL data values."""
    import struct

    header = struct.pack("<iidd16siii", 1, 1, 1.0, 1.0, b"ARRAY".ljust(16), ncol, nrow, ilay)
    with open(path, "wb") as f:
        f.write(header)
        values.tofile(f)


def test_dis_griddata_open_close_binary_real(tmp_path):
    """A GRIDDATA field OPEN/CLOSE-referencing a (BINARY) file loads the
    exact double-precision values the file contains."""
    from flopy4.mf6.gwf.dis import Dis

    top_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    _write_binary_array(tmp_path / "top.bin", top_values, nrow=2, ncol=3)
    dis_file = tmp_path / "model.dis"
    dis_file.write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
            END OPTIONS
            BEGIN DIMENSIONS
              NLAY 1
              NROW 2
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                CONSTANT 1.0
              DELC
                CONSTANT 1.0
              TOP
                OPEN/CLOSE top.bin (BINARY)
              BOTM
                CONSTANT 0.0
            END GRIDDATA
        """)
    )

    dis = Dis.load(dis_file)
    assert np.array_equal(np.asarray(dis.top), top_values)


def test_dis_griddata_open_close_binary_integer_with_factor(tmp_path):
    """An integer GRIDDATA field reads 4-byte ints from the binary file and
    still applies FACTOR scaling, same as the text OPEN/CLOSE path."""
    from flopy4.mf6.gwf.dis import Dis

    idomain_values = np.array([1, 1, 0, 1, 1, 1], dtype=np.int32)
    _write_binary_array(tmp_path / "idomain.bin", idomain_values, nrow=2, ncol=3)
    dis_file = tmp_path / "model.dis"
    dis_file.write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
            END OPTIONS
            BEGIN DIMENSIONS
              NLAY 1
              NROW 2
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                CONSTANT 1.0
              DELC
                CONSTANT 1.0
              TOP
                CONSTANT 1.0
              BOTM
                CONSTANT 0.0
              IDOMAIN
                OPEN/CLOSE idomain.bin (BINARY) FACTOR 2
            END GRIDDATA
        """)
    )

    dis = Dis.load(dis_file)
    assert np.array_equal(np.asarray(dis.idomain), idomain_values * 2)


def test_dis_griddata_open_close_binary_layered(tmp_path):
    """A LAYERED griddata field's per-layer OPEN/CLOSE (BINARY) records are
    each read and concatenated, matching the text-INTERNAL LAYERED path."""
    from flopy4.mf6.gwf.dis import Dis

    layer1 = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    layer2 = np.array([-2.0, -2.0, -2.0, -2.0, -2.0, -2.0])
    _write_binary_array(tmp_path / "botm1.bin", layer1, nrow=2, ncol=3, ilay=1)
    _write_binary_array(tmp_path / "botm2.bin", layer2, nrow=2, ncol=3, ilay=2)
    dis_file = tmp_path / "model.dis"
    dis_file.write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
            END OPTIONS
            BEGIN DIMENSIONS
              NLAY 2
              NROW 2
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                CONSTANT 1.0
              DELC
                CONSTANT 1.0
              TOP
                CONSTANT 0.0
              BOTM LAYERED
                OPEN/CLOSE botm1.bin (BINARY)
                OPEN/CLOSE botm2.bin (BINARY)
            END GRIDDATA
        """)
    )

    dis = Dis.load(dis_file)
    assert np.array_equal(np.asarray(dis.botm), np.concatenate([layer1, layer2]))


def test_dis_griddata_open_close_quoted_filename(tmp_path):
    """A single-quoted OPEN/CLOSE filename resolves to the real file,
    quotes stripped -- flopy3's own writer quotes filenames this way
    (confirmed against modflow6/autotest's test_gwf_utl01_binaryinput.py
    output: `OPEN/CLOSE 'top.bin' ...`), for both the binary and
    plain-text array path. (Double quotes aren't a confirmed MF6/flopy3
    convention and the basic grammar doesn't tokenize `"` at all, so
    aren't exercised here.)"""
    from flopy4.mf6.gwf.dis import Dis

    top_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    _write_binary_array(tmp_path / "top.bin", top_values, nrow=2, ncol=3)
    (tmp_path / "botm.txt").write_text("0.0 0.0 0.0 0.0 0.0 0.0")
    dis_file = tmp_path / "model.dis"
    dis_file.write_text(
        textwrap.dedent("""\
            BEGIN OPTIONS
            END OPTIONS
            BEGIN DIMENSIONS
              NLAY 1
              NROW 2
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                CONSTANT 1.0
              DELC
                CONSTANT 1.0
              TOP
                OPEN/CLOSE 'top.bin' (BINARY)
              BOTM
                OPEN/CLOSE 'botm.txt'
            END GRIDDATA
        """)
    )

    dis = Dis.load(dis_file)
    assert np.array_equal(np.asarray(dis.top), top_values)
    assert np.array_equal(np.asarray(dis.botm), np.zeros(6))
