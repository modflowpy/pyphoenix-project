import numpy as np
import pytest

from flopy4.mf6.utils.grid import get_nn


@pytest.mark.parametrize(
    "cellid, dims, expected",
    [
        ((7,), {"nodes": 10}, 7),
        ((1, 2), {"nlay": 2, "ncpl": 5}, 7),
        ((1, 2, 3), {"nlay": 2, "nrow": 3, "ncol": 4}, 23),
    ],
)
def test_get_nn(cellid, dims, expected):
    assert get_nn(cellid, **dims) == expected


def test_get_nn_many():
    cellids = np.array([[0, 0, 0], [0, 1, 0], [1, 2, 3]])
    nn = get_nn(cellids, nlay=2, nrow=3, ncol=4)
    np.testing.assert_array_equal(nn, [0, 4, 23])


def test_get_nn_ignores_other_dims():
    # e.g. a StructuredGrid's dims, which also has ncpl and nodes
    dims = {"nlay": 2, "nrow": 3, "ncol": 4, "ncpl": 12, "nodes": 24}
    assert get_nn((1, 2, 3), **dims) == 23
    assert get_nn((23,), **dims) == 23


def test_get_nn_out_of_range():
    with pytest.raises(ValueError):
        get_nn((0, 0, 4), nlay=2, nrow=3, ncol=4)


def test_get_nn_missing_dims():
    with pytest.raises(ValueError, match="ncpl"):
        get_nn((1, 2), nlay=2)


def test_get_nn_invalid_cellid():
    with pytest.raises(ValueError, match="Invalid cellid"):
        get_nn((1, 2, 3, 4), nlay=2, nrow=3, ncol=4)
