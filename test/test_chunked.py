"""Tests for chunked (dask-backed) loading of codegen v2 packages.

``Package.load(path, dims, chunks)`` is the primary interface.
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
# Chunked (dask) loading
# ---------------------------------------------------------------------------


def test_load_npf_chunked_returns_dask(npf_file):
    da = pytest.importorskip("dask.array")
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    assert isinstance(npf.k, da.Array), "k should be a dask Array with chunks='auto'"
    assert isinstance(npf.icelltype, da.Array)


def test_load_npf_chunked_shape_preserved(npf_file):
    pytest.importorskip("dask.array")
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    assert npf.k.shape == (100,)
    assert npf.icelltype.shape == (100,)


def test_load_npf_chunked_values_correct(npf_file):
    pytest.importorskip("dask.array")
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    k_computed = npf.k.compute()
    assert k_computed.shape == (100,)
    assert np.all(k_computed == 2.5)


def test_load_npf_chunked_one_chunk_per_layer(npf_file):
    """With chunks='auto' and 1 layer, k should have exactly 1 chunk."""
    da = pytest.importorskip("dask.array")
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    # quickstart GRB: nlay=1, ncpl=100 → reshape to (1,100) with chunks (1,100)
    # After reshape(-1) the dask graph has 1 chunk of 100 elements.
    assert npf.k.npartitions == 1


def test_load_npf_chunked_absent_fields_stay_none(npf_file):
    """Optional absent fields remain None even after chunking."""
    pytest.importorskip("dask.array")
    npf = Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    assert npf.k22 is None
    assert npf.angle1 is None


def test_load_npf_lazy_no_compute_on_load(npf_file, monkeypatch):
    """Chunked load must not trigger a .compute() call."""
    da = pytest.importorskip("dask.array")
    computed = []
    original_compute = da.Array.compute

    def spy_compute(self, **kw):
        computed.append(self.name)
        return original_compute(self, **kw)

    monkeypatch.setattr(da.Array, "compute", spy_compute)
    Npf.load(npf_file, dims=dims_from_grb(GRB_PATH), chunks="auto")
    assert not computed, f"compute() was called during load: {computed}"


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


def test_load_npf_layered_chunked_three_chunks(npf_layered_file, tmp_path):
    """chunks='auto' on a 3-layer grid → 3 dask chunks for k."""
    da = pytest.importorskip("dask.array")

    class _FakeGrid:
        nlay, nrow, ncol = 3, 5, 5

    from unittest.mock import patch

    with patch("flopy4.adapters.read_binary_grid_file") as mock_grb:
        mock_grb.return_value = {"grid_type": "DIS", "grid": _FakeGrid()}
        npf = Npf.load(
            npf_layered_file,
            dims=dims_from_grb(tmp_path / "fake.grb"),
            chunks="auto",
        )

    assert npf.k.npartitions == 3
    k_computed = npf.k.compute()
    assert np.allclose(k_computed[:25], 1.0e-3)
    assert np.allclose(k_computed[25:50], 1.0e-4)
    assert np.allclose(k_computed[50:], 2.0e-4)


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


def test_npf_load_classmethod_chunked(npf_file):
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_file, dims=DIMS_1L_10X10, chunks="auto")
    assert isinstance(npf.k, da.Array)
    assert npf.k.shape == (100,)
    assert np.all(npf.k.compute() == 2.5)


def test_npf_load_classmethod_chunked_lazy(npf_file, monkeypatch):
    """Package.load() must not trigger compute() during loading."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    computed = []
    original_compute = da.Array.compute

    def spy_compute(self, **kw):
        computed.append(self.name)
        return original_compute(self, **kw)

    monkeypatch.setattr(da.Array, "compute", spy_compute)
    Npf.load(npf_file, dims=DIMS_1L_10X10, chunks="auto")
    assert not computed, f"compute() was triggered during load: {computed}"


# ---------------------------------------------------------------------------
# Round-trip: load chunked → write → values match
# ---------------------------------------------------------------------------


def test_npf_chunked_roundtrip_write(npf_file, tmp_path):
    """Dask-backed NPF writes out correctly (dask arrays compute at write time)."""
    pytest.importorskip("dask.array")
    from flopy4.mf6.codec import dumps
    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.converter import COMPONENT_CONVERTER
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_file, dims=DIMS_1L_10X10, chunks="auto")

    # Unstructure → dumps → loads → structure (full round-trip via text)
    text = dumps(COMPONENT_CONVERTER.unstructure(npf))
    assert "BEGIN GRIDDATA" in text, "expected GRIDDATA block in output"

    raw2 = loads(text)
    npf2 = structure_component(raw2, Npf, dims=DIMS_1L_10X10)

    assert np.allclose(npf2.k, 2.5)
    assert np.allclose(npf2.k33, 0.25)
    assert np.all(npf2.icelltype == 0)
