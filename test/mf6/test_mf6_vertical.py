import dask.array as dsa
import numpy as np
import pytest
import xarray as xr

from flopy4.mf6.utils.vertical import layer_at, mask_z, sel_z, z_coords

# Three layers on a 1x3 grid, sloping: each column is 10 lower than the last.
TOP = np.array([[30.0, 20.0, 10.0]])
BOTM = np.array([TOP - 10, TOP - 20, TOP - 30])


def _grid(data=None, chunk=False):
    """A (time, layer, row, col) array whose values are 100 * time + the
    cell's 0-based node number, with z coordinates from TOP/BOTM."""
    if data is None:
        data = np.arange(2 * 9, dtype=np.float64).reshape(2, 3, 1, 3)
        data[1] += 100 - 9
    dims = ("layer", "row", "col")
    da = xr.DataArray(
        data,
        dims=("time",) + dims,
        coords={**z_coords(TOP, BOTM, dims), "x": ("col", [0.5, 1.5, 2.5])},
    )
    return da.chunk() if chunk else da


def test_z_coords():
    """A layer's top is the bottom of the one above, and a cell's centre is
    midway; top may be flat, or a scalar, for DIS and DISV shapes alike."""
    dims = ("layer", "row", "col")
    zc = z_coords(TOP, BOTM, dims)
    assert all(zc[k][0] == dims for k in ("z", "z_top", "z_bot"))
    z, z_top, z_bot = (zc[k][1] for k in ("z", "z_top", "z_bot"))
    assert z_top.shape == z_bot.shape == z.shape == (3, 1, 3)
    np.testing.assert_array_equal(z_top[0], TOP)
    np.testing.assert_array_equal(z_top[1:], BOTM[:-1])
    np.testing.assert_array_equal(z_bot, BOTM)
    np.testing.assert_array_equal(z, (z_top + z_bot) / 2)
    np.testing.assert_array_equal(z_coords(TOP.ravel(), BOTM, dims)["z_top"][1], z_top)

    zc = z_coords(5.0, [[0.0, 1.0], [-5.0, -4.0]], ("layer", "cell"))
    assert zc["z_top"][1].tolist() == [[5.0, 5.0], [0.0, 1.0]]
    assert zc["z_bot"][1].tolist() == [[0.0, 1.0], [-5.0, -4.0]]


def test_sel_z_slice():
    """z alone picks one layer per column, keeping the layer it picked, and
    NaN where z is above the top or below the bottom."""
    da = _grid()
    # z=15 is in layer 1 of column 0 (20..10), layer 0 of column 1
    # (20..10), and above column 2's top of 10.
    out = sel_z(da, 15.0)
    assert out.dims == ("time", "row", "col")
    np.testing.assert_array_equal(out.isel(time=0).values, [[3.0, 1.0, np.nan]])
    np.testing.assert_array_equal(out.isel(time=1).values, [[103.0, 101.0, np.nan]])
    np.testing.assert_array_equal(out.layer.values, [[1.0, 0.0, np.nan]])
    np.testing.assert_array_equal(out.z_top.values, [[20.0, 20.0, np.nan]])
    np.testing.assert_array_equal(out.z_bot.values, [[10.0, 10.0, np.nan]])

    # Every column contains z=5: positions stay ints.
    out = sel_z(da, 5.0)
    assert out.layer.dtype.kind == "i"
    assert out.layer.values.tolist() == [[2, 1, 0]]


def test_sel_z_ties():
    """A z on an interface goes to the upper (lower-numbered) layer, as in
    flopy3; the model top and bottom are inclusive."""
    da = _grid()
    out = sel_z(da, 20.0)
    np.testing.assert_array_equal(out.layer.values, [[0.0, 0.0, np.nan]])
    out = sel_z(da, 10.0)
    assert out.layer.values.tolist() == [[1, 0, 0]]
    out = sel_z(da, 0.0)
    assert out.layer.values.tolist() == [[2, 1, 0]]
    out = sel_z(da, -20.0)
    np.testing.assert_array_equal(out.layer.values, [[np.nan, np.nan, 2.0]])
    with pytest.raises(KeyError):
        sel_z(da, -20.0001, outside="raise")


def test_sel_z_column_and_points():
    """On a column (as from selecting by x/y), z picks a cell; for points,
    z shares their dim and each picks its own."""
    da = _grid()
    col = da.isel(row=0, col=1)
    out = sel_z(col, 0.5)
    assert out.dims == ("time",)
    assert out.values.tolist() == [4.0, 104.0]
    assert out.layer.item() == 1

    pts = da.isel(row=xr.DataArray([0, 0], dims="point"), col=xr.DataArray([0, 2], dims="point"))
    out = sel_z(pts, xr.DataArray([25.0, -15.0], dims="point"))
    assert out.dims == ("time", "point")
    assert out.isel(time=0).values.tolist() == [0.0, 8.0]
    assert out.layer.values.tolist() == [0, 2]

    with pytest.raises(KeyError):
        sel_z(col, 31.0, outside="raise")


def test_sel_z_lazy():
    """A dask-backed array stays lazy."""
    out = sel_z(_grid(chunk=True), 15.0)
    assert isinstance(out.data, dsa.Array)
    np.testing.assert_array_equal(out.isel(time=0).values, [[3.0, 1.0, np.nan]])


def test_sel_z_dataset():
    """In a dataset, only variables on the layer dim are selected and
    masked; the rest are left alone."""
    ds = xr.Dataset({"head": _grid(), "area": (("row", "col"), [[1.0, 2.0, 3.0]])})
    out = sel_z(ds, 15.0)
    assert out["head"].dims == ("time", "row", "col")
    np.testing.assert_array_equal(out["head"].isel(time=0).values, [[3.0, 1.0, np.nan]])
    assert out.area.values.tolist() == [[1.0, 2.0, 3.0]]


def test_sel_z_explicit_bounds():
    """Bounds can be passed in instead of attached; without either, it
    says so."""
    da = _grid()
    bare = da.drop_vars(["z_top", "z_bot"])
    out = sel_z(bare, 15.0, z_top=da.z_top, z_bot=da.z_bot)
    np.testing.assert_array_equal(out.isel(time=0).values, [[3.0, 1.0, np.nan]])
    with pytest.raises(ValueError, match="z_top"):
        sel_z(bare, 15.0)
    with pytest.raises(ValueError, match="outside"):
        sel_z(da, 15.0, outside="drop")


def test_sel_z_disv():
    """DISV arrays, on (layer, cell), work the same way."""
    da = xr.DataArray(
        np.arange(4.0).reshape(2, 2),
        dims=("layer", "cell"),
        coords=z_coords([10.0, 0.0], [[5.0, -5.0], [0.0, -10.0]], ("layer", "cell")),
    )
    out = sel_z(da, -2.0)
    assert out.dims == ("cell",)
    np.testing.assert_array_equal(out.values, [np.nan, 1.0])
    np.testing.assert_array_equal(out.layer.values, [np.nan, 0.0])


def test_layer_at():
    """layer_at gives positions and whether each column has one."""
    da = _grid()
    idx, found = layer_at(15.0, da.z_top, da.z_bot)
    assert idx.values.tolist() == [[1, 0, 0]]
    assert found.values.tolist() == [[True, True, False]]


def test_mask_z():
    """Cells overlapping, within, or centred in an elevation range; open at
    a missing end."""
    da = _grid()
    # Column 0's cells span 30..20, 20..10, 10..0.
    col0 = lambda m: m.isel(row=0, col=0).values.tolist()  # noqa: E731
    assert col0(mask_z(da, 12.0, 25.0)) == [True, True, False]
    assert col0(mask_z(da, 20.0, 25.0)) == [True, False, False]  # touching isn't overlap
    assert col0(mask_z(da, 10.0, 30.0, how="within")) == [True, True, False]
    assert col0(mask_z(da, 12.0, 25.0, how="within")) == [False, False, False]
    assert col0(mask_z(da, 15.0, 25.0, how="center")) == [True, True, False]
    assert col0(mask_z(da, zmax=10.0)) == [False, False, True]
    assert col0(mask_z(da, zmin=10.0)) == [True, True, False]
    assert mask_z(da).all()
    assert mask_z(da, 12.0, 25.0).dims == ("layer", "row", "col")
    with pytest.raises(ValueError, match="above"):
        mask_z(da, 5.0, 1.0)
    with pytest.raises(ValueError, match="how"):
        mask_z(da, 1.0, 5.0, how="partial")
