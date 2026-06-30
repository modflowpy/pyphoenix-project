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


# ---------------------------------------------------------------------------
# INTERNAL (non-CONSTANT) arrays through dask round-trip
# ---------------------------------------------------------------------------

DIMS_3L_25 = {"nlay": 3, "nodes": 75}


@pytest.fixture()
def npf_internal_file(tmp_path) -> Path:
    """NPF with INTERNAL array data (real per-cell values, not CONSTANT)."""
    k_vals = " ".join(str(float(i + 1)) for i in range(75))
    content = textwrap.dedent(f"""\
        BEGIN OPTIONS
        END OPTIONS
        BEGIN GRIDDATA
         K
          INTERNAL
            {k_vals}
         ICELLTYPE
          CONSTANT 1
        END GRIDDATA
    """)
    p = tmp_path / "npf_internal.npf"
    p.write_text(content)
    return p


def test_load_internal_array_chunked(npf_internal_file):
    """INTERNAL arrays (non-constant) load correctly as dask arrays."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_internal_file, dims=DIMS_3L_25, chunks="auto")
    assert isinstance(npf.k, da.Array)
    assert npf.k.shape == (75,)
    k = npf.k.compute()
    assert k[0] == 1.0
    assert k[74] == 75.0
    assert npf.k.npartitions == 3


def test_internal_array_chunked_roundtrip_write(npf_internal_file):
    """INTERNAL dask arrays write correctly (values preserved through compute)."""
    pytest.importorskip("dask.array")
    from flopy4.mf6.codec import dumps
    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.converter import COMPONENT_CONVERTER
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_internal_file, dims=DIMS_3L_25, chunks="auto")
    text = dumps(COMPONENT_CONVERTER.unstructure(npf))
    assert "INTERNAL" in text

    raw2 = loads(text)
    npf2 = structure_component(raw2, Npf, dims=DIMS_3L_25)
    assert npf2.k[0] == 1.0
    assert npf2.k[74] == 75.0


# ---------------------------------------------------------------------------
# to_dataarray() and to_xarray() laziness with dask
# ---------------------------------------------------------------------------


def test_to_dataarray_preserves_dask(npf_internal_file):
    """to_dataarray() wraps a dask array without computing."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_internal_file, dims=DIMS_3L_25, chunks="auto")
    xda = npf.to_dataarray("k")
    assert isinstance(xda.data, da.Array), "DataArray should wrap a dask array"
    assert xda.dims == ("layer", "face")
    assert xda.shape == (3, 25)


def test_to_xarray_preserves_dask(npf_internal_file):
    """to_xarray() returns a Dataset of lazy dask-backed DataArrays."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    npf = Npf.load(npf_internal_file, dims=DIMS_3L_25, chunks="auto")
    ds = npf.to_xarray()
    assert "k" in ds
    assert isinstance(ds["k"].data, da.Array)
    assert "icelltype" in ds
    assert isinstance(ds["icelltype"].data, da.Array)


# ---------------------------------------------------------------------------
# chunks=int
# ---------------------------------------------------------------------------


def test_chunks_int_splits_correctly(npf_internal_file):
    """chunks=int produces approximate element-count chunks."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.npf import Npf

    # 75 nodes, 3 layers, ncpl=25. chunks=30 → chunk_shape=(1, 25) since
    # max(1, 30//25)=1 → same as auto for this grid.
    npf = Npf.load(npf_internal_file, dims=DIMS_3L_25, chunks=30)
    assert isinstance(npf.k, da.Array)
    assert npf.k.shape == (75,)
    assert np.allclose(npf.k.compute(), np.arange(1, 76, dtype=np.float64))


# ---------------------------------------------------------------------------
# IC package — single griddata field
# ---------------------------------------------------------------------------


@pytest.fixture()
def ic_file(tmp_path) -> Path:
    """IC file with INTERNAL strt data for 3-layer 25-cell grid."""
    strt_vals = " ".join(str(100.0 - i * 0.1) for i in range(75))
    content = textwrap.dedent(f"""\
        BEGIN OPTIONS
        END OPTIONS
        BEGIN GRIDDATA
         STRT
          INTERNAL
            {strt_vals}
        END GRIDDATA
    """)
    p = tmp_path / "model.ic"
    p.write_text(content)
    return p


def test_ic_chunked_load(ic_file):
    """IC.load(chunks='auto') produces dask array for strt."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.ic import Ic

    ic = Ic.load(ic_file, dims=DIMS_3L_25, chunks="auto")
    assert isinstance(ic.strt, da.Array)
    assert ic.strt.shape == (75,)
    assert ic.strt.npartitions == 3
    assert np.isclose(ic.strt.compute()[0], 100.0)


# ---------------------------------------------------------------------------
# STO — mixed int + float dtypes
# ---------------------------------------------------------------------------


@pytest.fixture()
def sto_file(tmp_path) -> Path:
    """STO file with mixed int (iconvert) and float (ss, sy) griddata."""
    content = textwrap.dedent("""\
        BEGIN OPTIONS
          STORAGECOEFFICIENT
        END OPTIONS
        BEGIN GRIDDATA
         ICONVERT
          CONSTANT 1
         SS
          CONSTANT 1.0e-5
         SY
          CONSTANT 0.15
        END GRIDDATA
    """)
    p = tmp_path / "model.sto"
    p.write_text(content)
    return p


def test_sto_chunked_mixed_dtypes(sto_file):
    """STO chunked load handles both int and float griddata fields."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.sto import Sto

    sto = Sto.load(sto_file, dims=DIMS_3L_25, chunks="auto")
    assert isinstance(sto.iconvert, da.Array)
    assert isinstance(sto.ss, da.Array)
    assert isinstance(sto.sy, da.Array)
    assert sto.iconvert.dtype == np.int64
    assert sto.ss.dtype == np.float64
    assert np.all(sto.iconvert.compute() == 1)
    assert np.allclose(sto.ss.compute(), 1.0e-5)
    assert np.allclose(sto.sy.compute(), 0.15)


# ---------------------------------------------------------------------------
# G/A period fields: READARRAY ingress + chunked loading
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


def test_rcha_period_ingress_chunked(rcha_file):
    """chunks='auto' wraps READARRAY period arrays in dask (1 period per chunk)."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.rcha import Rcha

    rcha = Rcha.load(rcha_file, dims=DIMS_1L_5X5, chunks="auto")
    assert isinstance(rcha.recharge, da.Array)
    assert rcha.recharge.shape == (2, 25)
    assert rcha.recharge.npartitions == 2
    computed = rcha.recharge.compute()
    assert np.allclose(computed[0], 0.001)
    assert np.allclose(computed[1], 0.002)


def test_rcha_period_ingress_lazy(rcha_file, monkeypatch):
    """Package.load() with chunks= must not trigger compute() on period arrays."""
    da = pytest.importorskip("dask.array")
    from flopy4.mf6.gwf.rcha import Rcha

    computed = []
    original = da.Array.compute

    def spy(self, **kw):
        computed.append(self.name)
        return original(self, **kw)

    monkeypatch.setattr(da.Array, "compute", spy)
    Rcha.load(rcha_file, dims=DIMS_1L_5X5, chunks="auto")
    assert not computed, f"compute() called during load: {computed}"


def test_rcha_period_roundtrip(rcha_file, tmp_path):
    """Load RCHA (chunked) → unstructure → dumps → reload → values match."""
    pytest.importorskip("dask.array")
    from flopy4.mf6.codec import dumps
    from flopy4.mf6.codec.reader import loads
    from flopy4.mf6.converter import COMPONENT_CONVERTER
    from flopy4.mf6.converter.ingress.structure import structure_component
    from flopy4.mf6.gwf.rcha import Rcha

    rcha = Rcha.load(rcha_file, dims=DIMS_1L_5X5, chunks="auto")

    text = dumps(COMPONENT_CONVERTER.unstructure(rcha))
    assert "BEGIN PERIOD 1" in text
    assert "RECHARGE" in text

    raw2 = loads(text)
    rcha2 = structure_component(raw2, Rcha, dims=DIMS_1L_5X5)

    assert isinstance(rcha2.recharge, np.ndarray)
    assert rcha2.recharge.shape == (2, 25)
    assert np.allclose(rcha2.recharge[0], 0.001)
    assert np.allclose(rcha2.recharge[1], 0.002)


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
