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
