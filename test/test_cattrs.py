import numpy as np
import xarray as xr
from attrs import define, field
from cattrs import Converter, unstructure
from numpy.typing import NDArray


@define
class Foo:
    x: NDArray[np.float32] = field()


@define
class Bar:
    x: xr.DataArray = field()


@define
class Baz:
    x: xr.DataTree = field()


def test_unstructure_numpy_array():
    np_arr = np.array([1.0, 2.0, 3.0])
    f = Foo(x=np_arr)
    f_dict = unstructure(f)

    # We expect that the default unstructure functionality keeps
    # the numpy array as is.
    # This helps when finally converting the dictionary to MF6 input files.
    assert np_arr is f_dict["x"]


def test_unstructure_xarray():
    x_arr = xr.DataArray([1, 2, 3])
    f = Bar(x=x_arr)
    f_dict = unstructure(f)

    # We expect that the default unstructure functionality keeps
    # the xarray as is.
    # This helps when finally converting the dictionary to MF6 input files.
    assert x_arr is f_dict["x"]


def test_unstructure_xarray_tree_to_ascii():
    x_arr = xr.DataArray([1, 2, 3])
    x_set = xr.Dataset({"x": x_arr})
    x_tree = xr.DataTree(x_set)
    f = Baz(x=x_tree)

    converter = Converter()
    converter.register_unstructure_hook(
        Baz, lambda b: " ".join(b.x["x"].data.astype(str))
    )
    f_dict = converter.unstructure(f)

    # The data is formatted in ascii format.
    # The whole string will be in memory when doing this,
    # duplicating the data.
    assert f_dict == "1 2 3"


def test_unstructure_xarray_tree():
    x_arr = xr.DataArray([1, 2, 3])
    x_set = xr.Dataset({"x": x_arr})
    x_tree = xr.DataTree(x_set)
    f = Baz(x=x_tree)

    converter = Converter()
    converter.register_unstructure_hook(xr.DataTree, lambda v: v)
    f_dict = converter.unstructure(f)

    # We expect that the default unstructure functionality keeps
    # the xarray as is.
    # This helps when finally converting the dictionary to MF6 input files.
    assert x_tree is f_dict["x"]


def test_unstructure_xarray_tree_no_hook():
    x_arr = xr.DataArray([1, 2, 3])
    x_set = xr.Dataset({"x": x_arr})
    x_tree = xr.DataTree(x_set)
    f = Baz(x=x_tree)

    f_dict = unstructure(f)

    # Unfortunately the default converter seems to make a copy of the DataTree
    # and doesn't keep the original reference.
    assert x_tree is not f_dict["x"]
