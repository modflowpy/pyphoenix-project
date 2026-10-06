import numpy as np
import pytest

from flopy4.mf6 import TimeArraySeriesRef
from flopy4.mf6.constants import FILL_DNODATA, FILL_INT64
from flopy4.mf6.gwf import Rcha, Welg
from flopy4.mf6.period_arrays import (
    dense,
    split_periods,
    to_named_period_dict,
    to_period_dict,
)

NODATA = FILL_DNODATA


def test_split_periods_drops_all_nodata_float_periods():
    arr = np.full((4, 3), NODATA)
    arr[0] = [1.0, NODATA, 2.0]
    arr[2] = [NODATA, 5.0, NODATA]
    periods = split_periods(arr)
    assert list(periods) == [0, 2]
    np.testing.assert_array_equal(periods[2], [NODATA, 5.0, NODATA])


def test_split_periods_keeps_every_int_period():
    arr = np.zeros((3, 2), dtype=np.int64)
    assert list(split_periods(arr)) == [0, 1, 2]


def test_split_periods_needs_period_axis():
    with pytest.raises(ValueError, match="nper"):
        split_periods(np.ones(5))


def test_to_period_dict_keeps_dict_form():
    periods = to_period_dict({3: [1.0, 2.0], 0: np.full(2, NODATA)})
    # sorted, kept as given: an all-DNODATA period is a clear, not dropped
    assert list(periods) == [0, 3]
    assert isinstance(periods[3], np.ndarray)
    assert to_period_dict(None) is None


def test_to_named_period_dict_by_name_form():
    conc = np.full((3, 2), NODATA)
    conc[1] = [1.0, 2.0]
    temp = np.full((3, 2), NODATA)
    temp[1] = [3.0, 4.0]
    temp[2] = [5.0, 6.0]
    periods = to_named_period_dict({"conc": conc, "temp": temp})
    assert list(periods) == [1, 2]
    assert sorted(periods[1]) == ["conc", "temp"]
    assert list(periods[2]) == ["temp"]


def test_to_named_period_dict_by_period_form():
    periods = to_named_period_dict({2: {"conc": [1.0]}, 0: {"conc": [2.0]}})
    assert list(periods) == [0, 2]
    np.testing.assert_array_equal(periods[2]["conc"], [1.0])


def test_dense_carries_forward():
    out = dense({1: np.array([1.0, 2.0]), 3: np.array([3.0, 4.0])}, nper=5)
    np.testing.assert_array_equal(out[0], [NODATA, NODATA])
    np.testing.assert_array_equal(out[1:3], [[1.0, 2.0]] * 2)
    np.testing.assert_array_equal(out[3:], [[3.0, 4.0]] * 2)


def test_dense_without_carry_forward():
    out = dense({1: np.array([1, 2])}, nper=3, carry_forward=False)
    assert out.dtype == np.int64
    np.testing.assert_array_equal(out, [[FILL_INT64] * 2, [1, 2], [FILL_INT64] * 2])


def test_dense_given_period_replaces_whole_period():
    # a grid period given (by another field) without this field is empty
    out = dense({0: np.array([1.0])}, nper=4, given=[0, 2])
    np.testing.assert_array_equal(out.ravel(), [1.0, 1.0, NODATA, NODATA])


def test_welg_period_array_dense_input():
    q = np.full((3, 4), NODATA)
    q[0] = [NODATA, -1.0, NODATA, NODATA]
    welg = Welg(q=q)
    np.testing.assert_array_equal(welg.period_array("q", nper=3)[2], [NODATA, -1.0, NODATA, NODATA])
    out = welg.period_array("q", carry_forward=False)
    assert out.shape == (1, 4)  # nper defaults to one past the last given period
    np.testing.assert_array_equal(
        welg.period_array("q", nper=3, carry_forward=False)[1], [NODATA] * 4
    )


def test_welg_period_array_cleared_period():
    welg = Welg(q={0: np.array([-1.0, NODATA]), 2: np.full(2, NODATA)})
    out = welg.period_array("q", nper=4)
    np.testing.assert_array_equal(out[:, 0], [-1.0, -1.0, NODATA, NODATA])


def test_welg_aux_missing_from_given_period_is_empty():
    welg = Welg(
        auxiliary=["conc"],
        q={0: np.array([-1.0, NODATA]), 1: np.array([NODATA, -2.0])},
        aux={0: {"conc": np.array([5.0, NODATA])}},
    )
    conc = welg.period_array("aux", nper=3)["conc"]
    np.testing.assert_array_equal(conc[:, 0], [5.0, NODATA, NODATA])


def test_rcha_arrays_carry_forward_separately():
    rcha = Rcha(
        irch={0: np.array([0, 1])},
        recharge={0: np.array([0.1, 0.2]), 2: np.array([0.3, 0.4])},
    )
    irch = rcha.period_array("irch", nper=4)
    assert irch.dtype == np.int64
    np.testing.assert_array_equal(irch[3], [0, 1])
    np.testing.assert_array_equal(rcha.period_array("recharge", nper=4)[1], [0.1, 0.2])


def test_period_array_unknown_field():
    with pytest.raises(ValueError, match="no period array field"):
        Welg().period_array("auxiliary")


def test_welg_xarray_round_trip_keeps_periods():
    from flopy4.attrs_xarray import attrs_to_dataset, dataset_to_attrs

    welg = Welg(
        auxiliary=["conc"],
        q={0: np.array([-1.0, NODATA]), 2: np.full(2, NODATA)},
        aux={0: {"conc": np.array([5.0, NODATA])}},
    )
    ds = attrs_to_dataset(welg)
    assert ds["q"].dims == ("q_period", "nodes")
    assert list(ds["q_period"].values) == [0, 2]
    assert dataset_to_attrs(Welg, ds) == welg


def test_rcha_to_dataarray_carries_forward():
    rcha = Rcha(recharge={0: np.array([0.1, 0.2]), 2: np.array([0.3, 0.4])})
    da = rcha.to_dataarray("recharge")
    assert da.dims == ("per", "node")
    np.testing.assert_array_equal(da.values[1], [0.1, 0.2])


def test_dense_drops_periods_past_nper():
    with pytest.warns(UserWarning, match="past NPER"):
        out = dense({0: np.array([1.0]), 2: np.array([2.0])}, nper=2)
    np.testing.assert_array_equal(out.ravel(), [1.0, 1.0])


def test_rcha_tas_reference_round_trip():
    """A period's array can be a time-array series, by name, written as a
    reference to it. A plain name is taken as a reference."""
    from flopy4.attrs_xarray import attrs_to_dataset, dataset_to_attrs
    from flopy4.mf6.codec import dumps, loads
    from flopy4.mf6.converter.egress.unstructure import unstructure_component
    from flopy4.mf6.converter.ingress.structure import structure_component

    rcha = Rcha(
        auxiliary=["conc"],
        recharge={0: TimeArraySeriesRef("rchseries"), 2: np.array([0.3, 0.4])},
        aux={0: {"conc": "concseries"}, 1: {"conc": np.array([1.0, 2.0])}},
    )
    assert rcha.aux[0] == {"conc": TimeArraySeriesRef("concseries")}
    text = dumps(unstructure_component(rcha))
    assert "RECHARGE TIMEARRAYSERIES rchseries" in text
    assert "CONC TIMEARRAYSERIES concseries" in text

    loaded = structure_component(loads(text), Rcha, dims={"nlay": 1, "ncpl": 2, "nodes": 2})
    assert loaded.recharge[0] == TimeArraySeriesRef("rchseries")
    assert loaded.aux[0] == {"conc": TimeArraySeriesRef("concseries")}
    np.testing.assert_array_equal(loaded.recharge[2], [0.3, 0.4])

    assert dataset_to_attrs(Rcha, attrs_to_dataset(rcha)) == rcha
    with pytest.raises(ValueError, match="time-array series"):
        rcha.period_array("recharge", nper=3)


def test_tas_reference_xarray_coordinate(tmp_path):
    """In xarray a reference period stays in the stack, as FILL_DNODATA,
    naming its series in a coordinate along the period dim. The dataset
    saves to NetCDF and comes back the same."""
    import xarray as xr

    from flopy4.attrs_xarray import attrs_to_dataset, dataset_to_attrs

    rcha = Rcha(
        auxiliary=["conc"],
        recharge={0: TimeArraySeriesRef("rch"), 2: np.array([0.3, 0.4])},
        aux={0: {"conc": TimeArraySeriesRef("cs")}, 1: {"conc": np.array([1.0, 2.0])}},
    )
    ds = attrs_to_dataset(rcha)
    recharge = ds["recharge"]
    assert list(recharge["recharge_period"].values) == [0, 2]
    assert list(recharge["recharge_tas"].values) == ["rch", ""]
    assert (recharge.sel(recharge_period=0) == FILL_DNODATA).all()
    # the coordinate goes along with the data
    assert recharge.isel(recharge_period=0)["recharge_tas"].item() == "rch"
    assert ds["aux"]["aux_tas"].sel(aux_period=0, aux_name="conc").item() == "cs"

    path = tmp_path / "rcha.nc"
    ds.drop_attrs().to_netcdf(path)
    loaded = xr.load_dataset(path).assign_attrs(ds.attrs)
    assert dataset_to_attrs(Rcha, loaded) == rcha

    # every period from a series
    only = Rcha(recharge={0: TimeArraySeriesRef("rch")})
    assert dataset_to_attrs(Rcha, attrs_to_dataset(only)) == only


def test_tas_reference_needs_time_series_field():
    with pytest.raises(ValueError, match="can't come from a time-array series"):
        Welg(q={0: "qseries"})


def test_tas_reference_must_name_a_series(function_tmpdir):
    """Writing checks that each reference names a series the package's
    TAS6 files define, in any case, as MF6 needs."""
    from flopy4.mf6.utl.tas import Tas

    def tas(name):
        return Tas(
            time_series_name=Tas.TimeSeriesName(time_series_name=[name]),
            interpolation_method=Tas.InterpolationMethod(interpolation_method="linear"),
            tas_array={0.0: np.array([0.1, 0.2]), 1.0: np.array([0.3, 0.4])},
        )

    rcha = Rcha(
        auxiliary=["conc"],
        recharge={0: TimeArraySeriesRef("RchSeries")},
        aux={0: {"conc": TimeArraySeriesRef("concseries")}},
        tas=[tas("rchseries")],
        filename=function_tmpdir / "gwf.rcha",
    )
    with pytest.raises(ValueError, match=r"aux: period 0 names .*'concseries'.*\['rchseries'\]"):
        rcha.write()

    rcha.tas.append(tas("concseries"))
    rcha.write()
    assert "RECHARGE TIMEARRAYSERIES RchSeries" in (function_tmpdir / "gwf.rcha").read_text()
