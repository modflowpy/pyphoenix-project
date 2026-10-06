import numpy as np
import pytest

from flopy4.mf6.constants import FILL_DNODATA, FILL_INT64
from flopy4.mf6.gwf import Rcha, Welg
from flopy4.mf6.period_arrays import (
    dense,
    split_periods,
    to_named_period_dict,
    to_period_dict,
)

ND = FILL_DNODATA


def test_split_periods_drops_all_nodata_float_periods():
    arr = np.full((4, 3), ND)
    arr[0] = [1.0, ND, 2.0]
    arr[2] = [ND, 5.0, ND]
    periods = split_periods(arr)
    assert list(periods) == [0, 2]
    np.testing.assert_array_equal(periods[2], [ND, 5.0, ND])


def test_split_periods_keeps_every_int_period():
    arr = np.zeros((3, 2), dtype=np.int64)
    assert list(split_periods(arr)) == [0, 1, 2]


def test_split_periods_needs_period_axis():
    with pytest.raises(ValueError, match="nper"):
        split_periods(np.ones(5))


def test_to_period_dict_keeps_dict_form():
    periods = to_period_dict({3: [1.0, 2.0], 0: np.full(2, ND)})
    # sorted, kept as given: an all-DNODATA period is a clear, not dropped
    assert list(periods) == [0, 3]
    assert isinstance(periods[3], np.ndarray)
    assert to_period_dict(None) is None


def test_to_named_period_dict_by_name_form():
    conc = np.full((3, 2), ND)
    conc[1] = [1.0, 2.0]
    temp = np.full((3, 2), ND)
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
    np.testing.assert_array_equal(out[0], [ND, ND])
    np.testing.assert_array_equal(out[1:3], [[1.0, 2.0]] * 2)
    np.testing.assert_array_equal(out[3:], [[3.0, 4.0]] * 2)


def test_dense_without_carry_forward():
    out = dense({1: np.array([1, 2])}, nper=3, carry_forward=False)
    assert out.dtype == np.int64
    np.testing.assert_array_equal(out, [[FILL_INT64] * 2, [1, 2], [FILL_INT64] * 2])


def test_dense_given_period_replaces_whole_period():
    # a grid period given (by another field) without this field is empty
    out = dense({0: np.array([1.0])}, nper=4, given=[0, 2])
    np.testing.assert_array_equal(out.ravel(), [1.0, 1.0, ND, ND])


def test_welg_period_array_dense_input():
    q = np.full((3, 4), ND)
    q[0] = [ND, -1.0, ND, ND]
    welg = Welg(q=q)
    np.testing.assert_array_equal(welg.period_array("q", nper=3)[2], [ND, -1.0, ND, ND])
    out = welg.period_array("q", carry_forward=False)
    assert out.shape == (1, 4)  # nper defaults to one past the last given period
    np.testing.assert_array_equal(welg.period_array("q", nper=3, carry_forward=False)[1], [ND] * 4)


def test_welg_period_array_cleared_period():
    welg = Welg(q={0: np.array([-1.0, ND]), 2: np.full(2, ND)})
    out = welg.period_array("q", nper=4)
    np.testing.assert_array_equal(out[:, 0], [-1.0, -1.0, ND, ND])


def test_welg_aux_missing_from_given_period_is_empty():
    welg = Welg(
        auxiliary=["conc"],
        q={0: np.array([-1.0, ND]), 1: np.array([ND, -2.0])},
        aux={0: {"conc": np.array([5.0, ND])}},
    )
    conc = welg.period_array("aux", nper=3)["conc"]
    np.testing.assert_array_equal(conc[:, 0], [5.0, ND, ND])


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
        q={0: np.array([-1.0, ND]), 2: np.full(2, ND)},
        aux={0: {"conc": np.array([5.0, ND])}},
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
