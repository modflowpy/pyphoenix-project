"""Tests for flopy4.mf6.filters module."""

import numpy as np
import xarray as xr

from flopy4.mf6.filters import array2list, keystring2list


def test_array2list():
    data = np.zeros((3, 4, 5))
    data[0, 1, 2] = 100.0
    data[1, 3, 0] = -50.0
    data[2, 0, 4] = 25.5

    arr = xr.DataArray(data, dims=["layer", "row", "col"])
    sparse_data = list(array2list(arr))
    assert len(sparse_data) == 3
    expected = {(1, 2, 3, 100.0), (2, 4, 1, -50.0), (3, 1, 5, 25.5)}
    assert set(sparse_data) == expected


def test_array2list_with_zeros():
    data = np.array([[0.0, 1.0], [2.0, 0.0]])
    arr = xr.DataArray(data, dims=["row", "col"])

    sparse_no_zeros = list(array2list(arr))
    assert len(sparse_no_zeros) == 2
    assert set(sparse_no_zeros) == {(1, 2, 1.0), (2, 1, 2.0)}

    sparse_with_zeros = list(array2list(arr, include_zeros=True))
    assert len(sparse_with_zeros) == 4
    expected_with_zeros = {(1, 1, 0.0), (1, 2, 1.0), (2, 1, 2.0), (2, 2, 0.0)}
    assert set(sparse_with_zeros) == expected_with_zeros


def test_array2list_nan_handling():
    data = np.array([[1.0, np.nan], [0.0, 2.0]])
    arr = xr.DataArray(data, dims=["row", "col"])
    sparse_data = list(array2list(arr, include_zeros=True))
    expected = {(1, 1, 1.0), (2, 1, 0.0), (2, 2, 2.0)}
    assert set(sparse_data) == expected


def test_keystring2list():
    data = np.full((2, 3), None, dtype=object)
    data[0, 1] = {"rate": -100.0, "aux1": 1, "aux2": 2}
    data[1, 2] = {"rate": -200.0, "aux1": 3, "aux2": 4}

    arr = xr.DataArray(data, dims=["row", "col"])
    sparse_data = list(keystring2list(arr))
    assert len(sparse_data) == 2

    rows = {entry[:2] for entry in sparse_data}
    assert rows == {(1, 2), (2, 3)}

    for entry in sparse_data:
        if entry[:2] == (1, 2):
            assert entry[2:] == (-100.0, 1, 2)
        elif entry[:2] == (2, 3):
            assert entry[2:] == (-200.0, 3, 4)


def test_keystring2list_with_namedtuple():
    from collections import namedtuple

    WelData = namedtuple("WelData", ["rate", "aux1", "aux2"])

    data = np.full((2, 2), None, dtype=object)
    data[0, 0] = WelData(-100.0, 1, 2)
    data[1, 1] = WelData(-200.0, 3, 4)

    arr = xr.DataArray(data, dims=["row", "col"])
    sparse_data = list(keystring2list(arr))

    assert len(sparse_data) == 2
    expected = {(1, 1, -100.0, 1, 2), (2, 2, -200.0, 3, 4)}
    assert set(sparse_data) == expected


def test_array2list_1d():
    """Test sparse iteration with 1D arrays."""
    data = np.array([0, 5, 0, 10])
    arr = xr.DataArray(data, dims=["index"])

    sparse_data = list(array2list(arr))
    expected = {(2, 5), (4, 10)}  # 1-based indexing
    assert set(sparse_data) == expected


def test_array2list_2d():
    """Test sparse iteration with 2D arrays."""
    data = np.array([[1, 0], [0, 2]])
    arr = xr.DataArray(data, dims=["row", "col"])

    sparse_data = list(array2list(arr))
    expected = {(1, 1, 1), (2, 2, 2)}  # 1-based indexing
    assert set(sparse_data) == expected
