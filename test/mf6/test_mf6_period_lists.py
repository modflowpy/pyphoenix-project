import numpy as np
import pytest

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Evt, Hfb, Sfr, Uzf, Wel

NODATA = FILL_DNODATA
DIMS = {"nlay": 1, "nrow": 2, "ncol": 3, "nper": 3}


def test_chd_on_grid_carries_periods_forward():
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0), ((0, 1, 2), 2.0)], 2: []}, dims=DIMS)
    ds = chd.to_xarray()
    head = ds["head"]
    assert head.dims == ("per", "layer", "y", "x")
    expected = np.full((2, 3), NODATA)
    expected[0, 0], expected[1, 2] = 1.0, 2.0
    np.testing.assert_array_equal(head.values[0, 0], expected)
    np.testing.assert_array_equal(head.values[1, 0], expected)  # no block: carried
    assert (head.values[2] == NODATA).all()  # empty block: cleared


def test_chd_round_trips():
    spd = {0: [((0, 0, 0), 1.0), ((0, 1, 2), 2.0)], 1: [((0, 0, 1), 3.0)], 2: []}
    chd = Chd(stress_period_data=spd, dims=DIMS)
    expected = chd.stress_period_data
    chd.from_xarray(chd.to_xarray())
    assert chd.stress_period_data == expected


def test_unchanged_periods_load_as_carried():
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0)]}, dims=DIMS)
    chd.from_xarray(chd.to_xarray())
    assert list(chd.stress_period_data) == [0]


def test_aux_is_a_variable_per_name():
    wel = Wel(
        auxiliary=["conc", "temp"],
        stress_period_data={0: [((0, 0, 1), -5.0, (1.0, 2.0))]},
        dims=DIMS,
    )
    ds = wel.to_xarray()
    assert set(ds.data_vars) == {"q", "conc", "temp"}
    assert ds["temp"].values[0, 0, 0, 1] == 2.0
    expected = wel.stress_period_data
    wel.from_xarray(ds)
    assert wel.stress_period_data == expected


def test_array_column_gets_an_extra_dim():
    evt = Evt(
        nseg=3,
        stress_period_data={0: [((0, 0, 0), 1.0, 0.1, 2.0, (0.3, 0.6), (0.5, 0.2))]},
        dims=DIMS,
    )
    ds = evt.to_xarray()
    assert ds["pxdp"].dims == ("per", "pxdp_dim0", "layer", "y", "x")
    assert "petm0" not in ds  # optional, and no row gives it
    expected = evt.stress_period_data
    evt.from_xarray(ds)
    assert evt.stress_period_data == expected


def test_disv_grid():
    chd = Chd(stress_period_data={0: [((1, 2), 1.0)]}, dims={"nlay": 2, "ncpl": 4, "nper": 1})
    head = chd.to_xarray()["head"]
    assert head.dims == ("per", "layer", "face")
    assert head.values[0, 1, 2] == 1.0


def test_uzf_finds_cells_through_packagedata():
    uzf = Uzf(
        packagedata=[
            (0, (0, 0, 2), 1, -1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
            (1, (0, 1, 0), 1, -1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
        ],
        stress_period_data={0: [(1, 0.01, 0.001, 2.25, 0.05, 0.0, 0.0, 0.0)]},
        dims=DIMS,
    )
    ds = uzf.to_xarray()
    assert ds["finf"].values[0, 0, 1, 0] == 0.01
    expected = uzf.stress_period_data
    uzf.from_xarray(ds)
    assert uzf.stress_period_data == expected


def test_boundnames_are_dropped_with_a_warning():
    chd = Chd(boundnames=True, stress_period_data={0: [((0, 0, 0), 1.0, (), "a")]}, dims=DIMS)
    with pytest.warns(UserWarning, match="boundnames"):
        ds = chd.to_xarray()
    assert set(ds.data_vars) == {"head"}


def test_two_rows_in_a_cell_raise():
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0), ((0, 0, 0), 2.0)]}, dims=DIMS)
    with pytest.raises(ValueError, match="two rows at cell"):
        chd.to_xarray()


def test_time_series_value_raises():
    chd = Chd(stress_period_data={0: [((0, 0, 0), "ts1")]}, dims=DIMS)
    with pytest.raises(ValueError, match="time series 'ts1'"):
        chd.to_xarray()


def test_no_grid_dims_raises():
    with pytest.raises(ValueError, match="needs the grid's nlay, nrow, ncol"):
        Chd(stress_period_data={0: [((0, 0, 0), 1.0)]}).to_xarray()


@pytest.mark.parametrize(
    "pkg",
    [
        pytest.param(
            lambda: Sfr(stress_period_data={0: [Sfr.Inflow(0, 1.0)]}, dims=DIMS), id="keystring"
        ),
        pytest.param(
            lambda: Hfb(stress_period_data={0: [((0, 0, 0), (0, 0, 1), 1e-3)]}, dims=DIMS),
            id="two cellids",
        ),
    ],
)
def test_no_grid_form_raises(pkg):
    with pytest.raises(ValueError, match="use to_dataframe"):
        pkg().to_xarray()
