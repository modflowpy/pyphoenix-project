import numpy as np
import pandas as pd
import pytest

from flopy4.mf6._types import TimeSeriesRef
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Evt, Hfb, Lak, Maw, Mvr, Oc, Sfr, Uzf, Wel
from flopy4.mf6.utl import Tvk

NODATA = FILL_DNODATA
DIMS = {"nlay": 1, "nrow": 2, "ncol": 3, "nper": 3}


def round_trips(pkg, **kwargs):
    expected = pkg.stress_period_data
    pkg.from_xarray(pkg.to_xarray(**kwargs))
    assert pkg.stress_period_data == expected


# --- cellid rows on the grid ------------------------------------------------


def test_chd_on_grid_carries_periods_forward():
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0), ((0, 1, 2), 2.0)], 2: []}, dims=DIMS)
    head = chd.to_xarray()["head"]
    assert head.dims == ("per", "layer", "row", "col")
    expected = np.full((2, 3), NODATA)
    expected[0, 0], expected[1, 2] = 1.0, 2.0
    np.testing.assert_array_equal(head.values[0, 0], expected)
    np.testing.assert_array_equal(head.values[1, 0], expected)  # no block: carried
    assert (head.values[2] == NODATA).all()  # empty block: cleared


def test_chd_round_trips():
    spd = {0: [((0, 0, 0), 1.0), ((0, 1, 2), 2.0)], 1: [((0, 0, 1), 3.0)], 2: []}
    round_trips(Chd(stress_period_data=spd, dims=DIMS))


def test_unchanged_periods_load_as_carried():
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0)], 1: [((0, 0, 0), 1.0)]}, dims=DIMS)
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
    round_trips(wel)


def test_array_column_has_a_dim_named_for_its_size():
    evt = Evt(
        nseg=3,
        stress_period_data={0: [((0, 0, 0), 1.0, 0.1, 2.0, (0.3, 0.6), (0.5, 0.2))]},
        dims=DIMS,
    )
    ds = evt.to_xarray()
    assert ds["pxdp"].dims == ("per", "nseg-1", "layer", "row", "col")
    np.testing.assert_array_equal(ds["pxdp"].values[0, :, 0, 0, 0], [0.3, 0.6])
    assert "petm0" not in ds  # optional, and no row gives it
    round_trips(evt)


def test_disv_grid():
    chd = Chd(stress_period_data={0: [((1, 2), 1.0)]}, dims={"nlay": 2, "ncpl": 4, "nper": 1})
    head = chd.to_xarray()["head"]
    assert head.dims == ("per", "layer", "cell")
    assert head.values[0, 1, 2] == 1.0
    round_trips(chd)


def test_boundnames_are_a_coordinate():
    chd = Chd(
        boundnames=True,
        stress_period_data={0: [((0, 0, 0), 1.0, (), "a"), ((0, 1, 1), 2.0)]},
        dims=DIMS,
    )
    ds = chd.to_xarray()
    assert ds.coords["boundname"].dims == ("per", "layer", "row", "col")
    assert ds.coords["boundname"].values[2, 0, 0, 0] == "a"
    assert pd.isnull(ds.coords["boundname"].values[0, 0, 1, 1])
    round_trips(chd)


def test_time_series_value_is_nan_with_its_name():
    chd = Chd(stress_period_data={0: [((0, 0, 0), "ts1"), ((0, 0, 1), 2.0)]}, dims=DIMS)
    ds = chd.to_xarray()
    assert np.isnan(ds["head"].values[0, 0, 0, 0])
    assert ds.coords["head_ts"].values[0, 0, 0, 0] == "ts1"
    assert pd.isnull(ds.coords["head_ts"].values[0, 0, 0, 1])
    round_trips(chd)
    assert chd.stress_period_data[0][0].head == TimeSeriesRef("ts1")


def test_no_grid_dims_raises():
    with pytest.raises(ValueError, match="needs the grid's nlay, nrow, ncol"):
        Chd(stress_period_data={0: [((0, 0, 0), 1.0)]}).to_xarray()


# --- duplicates -------------------------------------------------------------


def two_wells():
    return Wel(stress_period_data={0: [((0, 0, 0), -1.0), ((0, 0, 0), -2.0)]}, dims=DIMS)


def test_two_rows_at_a_cell_raise():
    with pytest.raises(ValueError, match="sparse=True"):
        two_wells().to_xarray()


@pytest.mark.parametrize("how, q", [("sum", -3.0), ("first", -1.0), ("last", -2.0)])
def test_duplicates_merge(how, q):
    assert two_wells().to_xarray(duplicates=how)["q"].values[0, 0, 0, 0] == q


def test_duplicates_must_be_known():
    with pytest.raises(ValueError, match="duplicates must be"):
        two_wells().to_xarray(duplicates="mean")


def test_summing_a_time_series_raises():
    wel = Wel(stress_period_data={0: [((0, 0, 0), "ts1"), ((0, 0, 0), -2.0)]}, dims=DIMS)
    with pytest.raises(ValueError, match="can't be summed"):
        wel.to_xarray(duplicates="sum")


# --- feature rows -------------------------------------------------------------


def uzf():
    return Uzf(
        packagedata=[
            (0, (0, 0, 2), 1, -1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
            (1, (0, 1, 0), 1, -1, 0.001, 1.0, 0.05, 0.25, 0.05, 4.0),
        ],
        stress_period_data={0: [(1, 0.01, 0.001, 2.25, 0.05, 0.0, 0.0, 0.0)]},
        dims=DIMS,
    )


def test_uzf_rows_are_on_the_feature_dim():
    ds = uzf().to_xarray()
    assert ds["finf"].dims == ("per", "nuzfcells")
    np.testing.assert_array_equal(ds["finf"].values[0], [NODATA, 0.01])
    round_trips(uzf())


def test_uzf_rows_on_the_grid_through_packagedata():
    ds = uzf().to_xarray(grid=True)
    assert ds["finf"].dims == ("per", "layer", "row", "col")
    assert ds["finf"].values[0, 0, 1, 0] == 0.01
    round_trips(uzf(), grid=True)


def sfr(spd, **kwargs):
    return Sfr(nreaches=3, stress_period_data=spd, dims=DIMS, **kwargs)


def test_sfr_settings_are_variables_per_setting():
    pkg = sfr(
        {
            0: [(0, "status", "inactive"), (0, "inflow", 1.0), (2, "inflow", 3.0)],
            2: [(2, "inflow", 4.0)],
        }
    )
    ds = pkg.to_xarray()
    assert set(ds.data_vars) == {"status", "inflow"}
    assert ds["inflow"].dims == ("per", "nreaches")
    np.testing.assert_array_equal(ds["inflow"].values[0], [1.0, NODATA, 3.0])
    # settings hold until set again: reach 0's inflow carries past period 2
    np.testing.assert_array_equal(ds["inflow"].values[2], [1.0, NODATA, 4.0])
    assert ds["status"].values[2, 0] == "inactive"
    assert pd.isnull(ds["status"].values[2, 1])
    round_trips(pkg)


def test_sfr_setting_index_is_a_dim():
    pkg = sfr({0: [(0, "diversion", 1, 0.5)]})
    ds = pkg.to_xarray()
    assert ds["divflow"].dims == ("per", "idv", "nreaches")
    assert ds["divflow"].values[0, 1, 0] == 0.5
    assert ds["divflow"].values[0, 0, 0] == NODATA
    round_trips(pkg)


def test_sfr_named_settings_are_a_variable_per_name():
    pkg = sfr({0: [(1, "auxiliary", "conc", 2.0)]}, auxiliary=["conc"])
    ds = pkg.to_xarray()
    assert ds["conc"].values[0, 1] == 2.0
    round_trips(pkg)


def test_unsetting_a_setting_raises():
    pkg = sfr({0: [(0, "inflow", 1.0)]})
    ds = pkg.to_xarray()
    ds["inflow"].values[1, 0] = NODATA
    with pytest.raises(ValueError, match="can't be unset"):
        pkg.from_xarray(ds)


def test_lak_settings_are_on_their_keys_dims():
    lak = Lak(
        nlakes=2,
        noutlets=1,
        stress_period_data={0: [Lak.Stage(1, 10.0), Lak.Rate(0, 0.5)]},
        dims=DIMS,
    )
    ds = lak.to_xarray()
    assert ds["stage"].dims == ("per", "nlakes")
    assert ds["rate"].dims == ("per", "noutlets")
    round_trips(lak)


def test_maw_word_or_number_setting_is_an_object_variable():
    maw = Maw(
        nmawwells=2,
        stress_period_data={0: [(0, "head_limit", "off"), (1, "head_limit", 2.5)]},
        dims=DIMS,
    )
    ds = maw.to_xarray()
    assert ds["head_limit"].dtype == object
    assert list(ds["head_limit"].values[0]) == ["off", 2.5]
    round_trips(maw)


# --- sparse -------------------------------------------------------------------


@pytest.mark.parametrize(
    "pkg",
    [
        pytest.param(
            lambda: Chd(
                boundnames=True,
                stress_period_data={
                    0: [((0, 0, 0), 1.0, (), "a"), ((0, 0, 0), "ts1")],
                    2: [],
                },
                dims=DIMS,
            ),
            id="chd",
        ),
        pytest.param(
            lambda: Evt(
                nseg=3,
                auxiliary=["conc"],
                stress_period_data={
                    0: [((0, 0, 0), 1.0, 0.1, 2.0, (0.3, 0.6), (0.5, 0.2), None, (4.0,))]
                },
                dims=DIMS,
            ),
            id="evt",
        ),
        pytest.param(
            lambda: sfr(
                {0: [(0, "status", "inactive"), (0, "diversion", 1, 0.5)], 1: [(0, "inflow", 1.0)]}
            ),
            id="sfr",
        ),
        pytest.param(
            lambda: Lak(
                nlakes=2,
                noutlets=1,
                stress_period_data={0: [Lak.Stage(1, 10.0), Lak.Auxiliary(0, "conc", 1.0)]},
                auxiliary=["conc"],
                dims=DIMS,
            ),
            id="lak",
        ),
        pytest.param(
            lambda: Hfb(stress_period_data={0: [((0, 0, 0), (0, 0, 1), 1e-3)]}, dims=DIMS),
            id="hfb",
        ),
        pytest.param(
            lambda: Mvr(stress_period_data={0: [("wel", 0, "drn", 1, "factor", 0.5)]}, dims=DIMS),
            id="mvr",
        ),
        pytest.param(
            lambda: Oc(
                stress_period_data={0: [("save", "head", "all"), ("print", "budget", "last")]}
            ),
            id="oc",
        ),
    ],
)
def test_sparse_round_trips(pkg):
    p = pkg()
    ds = p.to_xarray(sparse=True)
    assert "entry" in ds.dims
    round_trips(p, sparse=True)


def test_sparse_cellid_columns_are_named_for_grid_dims():
    tvk = Tvk(stress_period_data={0: [((0, 1, 2), Tvk.K(5.0))]}, dims=DIMS)
    ds = tvk.to_xarray(sparse=True)
    assert [int(ds.coords[n].values[0]) for n in ("cellid_layer", "cellid_row", "cellid_col")] == [
        0,
        1,
        2,
    ]
    assert ds["k"].values[0] == 5.0  # TVK's k
    round_trips(tvk, sparse=True)


def test_rows_with_no_single_key_are_sparse():
    hfb = Hfb(stress_period_data={0: [((0, 0, 0), (0, 0, 1), 1e-3)]}, dims=DIMS)
    ds = hfb.to_xarray()
    assert ds["hydchr"].dims == ("entry",)
    assert list(ds.coords["cellid2_col"].values) == [1]


def test_aux_named_like_a_column_raises():
    wel = Wel(auxiliary=["q"], stress_period_data={0: [((0, 0, 0), -1.0, (2.0,))]}, dims=DIMS)
    with pytest.raises(ValueError, match="'q'"):
        wel.to_xarray()
    with pytest.raises(ValueError, match="name of a column"):
        wel.to_xarray(sparse=True)
