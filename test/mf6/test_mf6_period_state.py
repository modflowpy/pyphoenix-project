"""Tests for flopy4.mf6.period_state: the values period arrays hold in each
period, as exported to NetCDF."""

import attrs
import numpy as np
import pytest

from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.constants import FILL_DNODATA as NO
from flopy4.mf6.gwf import Dis, Gwf, Rcha, Rivg, Welg
from flopy4.mf6.netcdf import NetCDFModel
from flopy4.mf6.period_state import period_mode, period_states
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time

NPER = 4


def _model(nlay=1):
    """Four cells per layer, the last inactive; four periods."""
    sim = Simulation(tdis=Time(perlen=[1.0] * NPER, nstp=[1] * NPER, tsmult=[1.0] * NPER), name="s")
    idomain = np.broadcast_to(np.array([1, 1, 1, 0]), (nlay, 1, 4))
    dis = Dis(nlay=nlay, nrow=1, ncol=4, botm=np.arange(nlay)[::-1] - nlay, idomain=idomain)
    return Gwf(parent=sim, dis=dis, name="m")


def _periods(ds, name):
    return ds[name].values.reshape(NPER, -1)


def test_grid_boundary_cells():
    """Grid arrays hold values at the boundary cells, the active cells where
    the first array in the block has a value. Values carry forward to
    periods with no block; an empty block removes every boundary."""
    gwf = _model()
    Welg(
        parent=gwf,
        auxiliary=["m"],
        q={0: np.array([-1.0, NO, NO, -2.0]), 2: None, 3: np.array([NO, -3.0, NO, NO])},
        aux={0: {"m": np.array([0.5, 9.0, NO, 2.0])}, 3: {"m": np.array([NO, 4.0, NO, NO])}},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(
        _periods(ds, "wel-1_q"),
        [[-1.0, NO, NO, NO], [-1.0, NO, NO, NO], [NO] * 4, [NO, -3.0, NO, NO]],
    )
    np.testing.assert_array_equal(
        _periods(ds, "wel-1_m"),
        [[0.5, NO, NO, NO], [0.5, NO, NO, NO], [NO] * 4, [NO, 4.0, NO, NO]],
    )


def test_grid_aux_only_block():
    """An aux-only block sets the boundary cells, active cells only; q is
    held there."""
    gwf = _model()
    Welg(
        parent=gwf,
        auxiliary=["m"],
        q={0: np.array([-1.0, -2.0, NO, -4.0])},
        aux={0: {"m": np.array([1.0, 2.0, NO, 4.0])}, 1: {"m": np.array([5.0, 6.0, NO, 8.0])}},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(_periods(ds, "wel-1_q"), [[-1.0, -2.0, NO, NO]] * NPER)
    np.testing.assert_array_equal(
        _periods(ds, "wel-1_m"), [[1.0, 2.0, NO, NO]] + [[5.0, 6.0, NO, NO]] * 3
    )


def test_grid_values_kept_through_empty_block():
    """An empty block removes the boundary cells but MF6 keeps the values;
    an aux array not given in a later block holds them again, by position."""
    gwf = _model()
    Welg(
        parent=gwf,
        auxiliary=["m"],
        q={0: np.array([-1.0, -2.0, NO, NO]), 1: None, 2: np.array([-3.0, -4.0, NO, NO])},
        aux={0: {"m": np.array([5.0, 6.0, NO, NO])}},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(
        _periods(ds, "wel-1_q"),
        [[-1.0, -2.0, NO, NO], [NO] * 4, [-3.0, -4.0, NO, NO], [-3.0, -4.0, NO, NO]],
    )
    np.testing.assert_array_equal(
        _periods(ds, "wel-1_m"),
        [[5.0, 6.0, NO, NO], [NO] * 4, [5.0, 6.0, NO, NO], [5.0, 6.0, NO, NO]],
    )


def test_grid_position_never_written_holds_zero():
    """A block whose boundary grows past the cells an array was given at
    holds 0 there for that array, as MF6 allocates it. The input check
    skips blocks with dask arrays, so this input is accepted."""
    da = pytest.importorskip("dask.array")
    gwf = _model()
    two = np.array([10.0, 10.0, NO, NO])
    Rivg(
        parent=gwf,
        stage={0: np.array([6.0, 6.0, NO, NO]), 1: da.from_array(np.array([7.0, 7.0, 7.0, NO]))},
        cond={0: two},
        rbot={0: two / 2},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(
        _periods(ds, "riv-1_cond"), [[10.0, 10.0, NO, NO]] + [[10.0, 10.0, 0.0, NO]] * 3
    )


def test_grid_aux_never_given():
    """An auxiliary variable never given holds no values."""
    gwf = _model()
    Welg(parent=gwf, auxiliary=["m"], q={0: np.array([-1.0, -2.0, NO, NO])})
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(_periods(ds, "wel-1_m"), np.full((NPER, 4), NO))


def test_grid_aux_only_block_given_order():
    """In an aux-only block the first aux array given, not the first
    declared, sets the boundary cells."""
    gwf = _model()
    Welg(
        parent=gwf,
        auxiliary=["a", "b"],
        q={0: np.array([-1.0, -2.0, NO, NO])},
        aux={
            0: {"a": np.array([1.0, 2.0, NO, NO]), "b": np.array([3.0, 4.0, NO, NO])},
            1: {"b": np.array([5.0, 6.0, NO, NO]), "a": np.array([7.0, 8.0, 9.0, NO])},
        },
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(_periods(ds, "wel-1_q")[1], [-1.0, -2.0, NO, NO])
    np.testing.assert_array_equal(_periods(ds, "wel-1_a")[1], [7.0, 8.0, NO, NO])


def test_layer_arrays_and_series():
    """A layer array holds its values until given again, also through blocks
    that don't give it. An array given by a time-array series holds no
    values while linked. The layer index holds 1 until given."""
    gwf = _model(nlay=2)
    Rcha(
        parent=gwf,
        recharge={0: np.full(4, 0.1), 2: TimeArraySeriesRef("rts")},
        irch={1: np.ones(4, dtype=int)},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    np.testing.assert_array_equal(
        _periods(ds, "rch-1_recharge"), [[0.1] * 4, [0.1] * 4, [NO] * 4, [NO] * 4]
    )
    np.testing.assert_array_equal(_periods(ds, "rch-1_irch"), [[1] * 4] + [[2] * 4] * 3)


def test_full_grid_arrays_not_supported():
    """A grid package without MAXBOUND (full-grid arrays) isn't supported."""

    @attrs.define
    class FullGrid:
        readarraygrid: bool = True

    with pytest.raises(NotImplementedError, match="full-grid"):
        period_mode(FullGrid)


def test_period_states_from_blocks():
    """period_states works on period blocks alone, no package: an aux-only
    grid block sets the boundary, and q is held there by position."""
    blocks = {
        0: {"q": np.array([-1.0, -2.0, NO, NO]), "aux:m": np.array([1.0, 2.0, NO, NO])},
        1: {"aux:m": np.array([NO, 5.0, 6.0, NO])},
    }
    shapes = {"q": (4,), "aux:m": (4,)}
    out = period_states(blocks, "grid", 3, shapes, active=np.array([1, 1, 1, 0]) > 0)
    np.testing.assert_array_equal(
        out["q"], [[-1.0, -2.0, NO, NO], [NO, -1.0, -2.0, NO], [NO, -1.0, -2.0, NO]]
    )
    np.testing.assert_array_equal(out["aux:m"][2], [NO, 5.0, 6.0, NO])


def test_period_array_follows_grid_regime():
    """Package.period_array goes through period_states, so it agrees with
    the export: an empty block clears aux too, though no block gives it."""
    gwf = _model()
    welg = Welg(
        parent=gwf,
        auxiliary=["m"],
        q={0: np.array([-1.0, -2.0, NO, NO]), 2: None},
        aux={0: {"m": np.array([1.0, 2.0, NO, NO])}},
    )
    ds = NetCDFModel.from_model(gwf).to_xarray()
    m = welg.period_array("aux")["m"]
    np.testing.assert_array_equal(m, _periods(ds, "wel-1_m"))
    np.testing.assert_array_equal(m[:, 0], [1.0, 1.0, NO, NO])
