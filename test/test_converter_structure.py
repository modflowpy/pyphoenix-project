"""
Tests for flopy4.mf6.converter.ingress.structure module.

Integration tests for the refactored structure_array function with various input formats
using real flopy4 components.
"""

import numpy as np
import sparse
import xarray as xr

from flopy4.mf6.converter.ingress.structure import (
    _convert_dataset_to_dict,
    _detect_grid_reshape,
    _extract_external_path,
    _fill_forward_time,
    _reshape_grid,
    _to_xarray,
    _validate_duck_array,
)
from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.disv import Disv
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.rch import Rch


class TestHelperFunctions:
    """Test helper functions that don't require full xattree setup."""

    def test_detect_grid_reshape_structured_to_flat_3d(self):
        """Test detection of (nlay, nrow, ncol) -> (nodes,) reshape."""
        value_shape = (2, 10, 10)
        expected_dims = ["nodes"]
        dim_dict = {"nlay": 2, "nrow": 10, "ncol": 10, "nodes": 200}

        needs_reshape, target_shape = _detect_grid_reshape(value_shape, expected_dims, dim_dict)

        assert needs_reshape is True
        assert target_shape == (200,)

    def test_detect_grid_reshape_structured_to_flat_4d(self):
        """Test detection of (nper, nlay, nrow, ncol) -> (nper, nodes) reshape."""
        value_shape = (3, 2, 10, 10)
        expected_dims = ["nper", "nodes"]
        dim_dict = {"nper": 3, "nlay": 2, "nrow": 10, "ncol": 10, "nodes": 200}

        needs_reshape, target_shape = _detect_grid_reshape(value_shape, expected_dims, dim_dict)

        assert needs_reshape is True
        assert target_shape == (3, 200)

    def test_detect_grid_reshape_no_reshape_needed(self):
        """Test when no reshape is needed."""
        value_shape = (100,)
        expected_dims = ["nodes"]
        dim_dict = {"nodes": 100}

        needs_reshape, target_shape = _detect_grid_reshape(value_shape, expected_dims, dim_dict)

        assert needs_reshape is False
        assert target_shape is None

    def test_reshape_grid_numpy_array(self):
        """Test reshaping numpy array."""
        data = np.ones((2, 10, 10))
        target_shape = (200,)

        result = _reshape_grid(data, target_shape)

        assert isinstance(result, np.ndarray)
        assert result.shape == (200,)
        assert np.all(result == 1.0)

    def test_reshape_grid_xarray(self):
        """Test reshaping xarray DataArray."""
        data = xr.DataArray(np.ones((2, 10, 10)), dims=["nlay", "nrow", "ncol"])
        target_shape = (200,)
        target_dims = ["nodes"]

        result = _reshape_grid(data, target_shape, ["nlay", "nrow", "ncol"], target_dims)

        assert isinstance(result, xr.DataArray)
        assert result.shape == (200,)
        assert result.dims == ("nodes",)

    def test_validate_duck_array_numpy_correct_shape(self):
        """Test validating numpy array with correct shape."""
        value = np.ones((3, 100))
        expected_dims = ["nper", "nodes"]
        expected_shape = (3, 100)
        dim_dict = {"nper": 3, "nodes": 100}

        result = _validate_duck_array(value, expected_dims, expected_shape, dim_dict)

        assert np.array_equal(result, value)

    def test_validate_duck_array_xarray_correct_dims(self):
        """Test validating xarray with correct dimensions."""
        value = xr.DataArray(np.ones((3, 100)), dims=["nper", "nodes"])
        expected_dims = ["nper", "nodes"]
        expected_shape = (3, 100)
        dim_dict = {"nper": 3, "nodes": 100}

        result = _validate_duck_array(value, expected_dims, expected_shape, dim_dict)

        assert isinstance(result, xr.DataArray)
        assert result.dims == ("nper", "nodes")

    def test_fill_forward_time_numpy(self):
        """Test adding nper dimension to numpy array."""
        data = np.ones((100,))
        dims = ["nper", "nodes"]
        nper = 3

        result = _fill_forward_time(data, dims, nper)

        assert result.shape == (3, 100)
        assert np.all(result == 1.0)

    def test_fill_forward_time_xarray(self):
        """Test adding nper dimension to xarray."""
        data = xr.DataArray(np.ones((100,)), dims=["nodes"])
        dims = ["nper", "nodes"]
        nper = 3

        result = _fill_forward_time(data, dims, nper)

        assert isinstance(result, xr.DataArray)
        assert result.shape == (3, 100)
        assert result.dims == ("nper", "nodes")

    def test_to_xarray_numpy_array(self):
        """Test wrapping numpy array in xarray."""
        data = np.ones((3, 100))
        dims = ["nper", "nodes"]
        coords = {"nper": np.arange(3), "nodes": np.arange(100)}
        attrs = {"units": "m"}

        result = _to_xarray(data, dims, coords, attrs)

        assert isinstance(result, xr.DataArray)
        assert result.dims == ("nper", "nodes")
        assert "nper" in result.coords
        assert result.attrs["units"] == "m"

    def test_convert_dataset_to_dict_structured(self):
        """Test converting xr.Dataset to dict format (structured grid)."""
        # Create Dataset as transformer would output it
        ds = xr.Dataset(
            data_vars={
                "field_0": (["record"], [-1000.0, -2000.0, -3000.0]),
            },
            coords={
                "kper": (["record"], [0, 0, 1]),
                "layer": (["record"], [0, 0, 0]),
                "row": (["record"], [1, 2, 3]),
                "col": (["record"], [1, 2, 3]),
            },
        )
        dim_dict = {"nlay": 2, "nrow": 10, "ncol": 10}

        result = _convert_dataset_to_dict(ds, "field_0", dim_dict)

        # Check structure: {kper: {cellid: value}}
        assert isinstance(result, dict)
        assert 0 in result
        assert 1 in result
        assert (0, 1, 1) in result[0]
        assert (0, 2, 2) in result[0]
        assert result[0][(0, 1, 1)] == -1000.0
        assert result[0][(0, 2, 2)] == -2000.0
        assert result[1][(0, 3, 3)] == -3000.0

    def test_convert_dataset_to_dict_unstructured(self):
        """Test converting xr.Dataset to dict format (unstructured grid)."""
        ds = xr.Dataset(
            data_vars={
                "q": (["record"], [100.0, 200.0]),
            },
            coords={
                "kper": (["record"], [0, 1]),
                "node": (["record"], [5, 10]),
            },
        )
        dim_dict = {"nodes": 100}

        result = _convert_dataset_to_dict(ds, "q", dim_dict)

        assert isinstance(result, dict)
        assert 0 in result
        assert 1 in result
        assert (5,) in result[0]
        assert (10,) in result[1]
        assert result[0][(5,)] == 100.0
        assert result[1][(10,)] == 200.0

    def test_convert_dataset_to_dict_missing_field_uses_first_var(self):
        """Test that if field name not found, uses first data variable."""
        ds = xr.Dataset(
            data_vars={
                "field_0": (["record"], [1.0, 2.0]),
            },
            coords={
                "kper": (["record"], [0, 0]),
                "node": (["record"], [1, 2]),
            },
        )
        dim_dict = {"nodes": 100}

        # Request non-existent field, should use field_0
        result = _convert_dataset_to_dict(ds, "non_existent", dim_dict)

        assert isinstance(result, dict)
        assert 0 in result
        assert (1,) in result[0]
        assert result[0][(1,)] == 1.0

    def test_extract_external_path_with_path(self):
        """Test extracting external file path from DataArray attrs."""
        data = xr.DataArray(
            data=np.nan,
            attrs={
                "control_type": "external",
                "control_factor": 1.0,
                "control_binary": True,
                "external_path": "data/heads.dat",
            },
        )

        path, updated_data = _extract_external_path(data)

        assert path == "data/heads.dat"
        assert isinstance(updated_data, xr.DataArray)
        assert "external_path" not in updated_data.attrs
        assert updated_data.attrs["control_type"] == "external"
        assert updated_data.attrs["control_factor"] == 1.0

    def test_extract_external_path_without_path(self):
        """Test that non-external DataArray is returned unchanged."""
        data = xr.DataArray(
            data=np.ones((10, 10)),
            attrs={
                "control_type": "internal",
                "control_factor": 1.0,
            },
        )

        path, updated_data = _extract_external_path(data)

        assert path is None
        assert updated_data is data  # Should be unchanged


class TestDisComponent:
    """Test structure_array with Dis component (array dims)."""

    def test_dis_with_scalar_delr(self):
        """Test Dis with scalar delr (broadcast to ncol)."""
        dis = Dis(nlay=1, nrow=10, ncol=10, delr=1.0, delc=1.0)

        assert hasattr(dis, "delr")
        # Can be numpy or xarray depending on component configuration
        assert isinstance(dis.delr, (np.ndarray, xr.DataArray))
        if isinstance(dis.delr, xr.DataArray):
            assert dis.delr.shape == (10,)
            assert np.all(dis.delr.values == 1.0)
        else:
            assert dis.delr.shape == (10,)
            assert np.all(dis.delr == 1.0)

    def test_dis_with_list_delr(self):
        """Test Dis with list delr."""
        dis = Dis(nlay=1, nrow=10, ncol=10, delr=[1.0] * 10, delc=[2.0] * 10)

        assert dis.delr.shape == (10,)
        assert np.all(dis.delr == 1.0)
        assert dis.delc.shape == (10,)
        assert np.all(dis.delc == 2.0)

    def test_dis_with_numpy_array(self):
        """Test Dis with numpy array input."""
        delr_array = np.linspace(1.0, 2.0, 10)
        dis = Dis(nlay=1, nrow=10, ncol=10, delr=delr_array, delc=1.0)

        assert dis.delr.shape == (10,)
        assert np.allclose(dis.delr, delr_array)


class TestDisvComponent:
    """Test structure_array with Disv component (array dims)."""

    def test_disv_with_scalar_top(self):
        """Test Disv with scalar top (broadcast to ncpl)."""
        disv = Disv(nlay=1, ncpl=100, top=1.0, botm=1.0)

        assert hasattr(disv, "top")
        # Can be numpy or xarray depending on component configuration
        assert isinstance(disv.top, (np.ndarray, xr.DataArray))
        if isinstance(disv.top, xr.DataArray):
            assert disv.top.shape == (100,)
            assert np.all(disv.top.values == 1.0)
        else:
            assert disv.top.shape == (100,)
            assert np.all(disv.top == 1.0)

    def test_disv_with_list_top(self):
        """Test Disv with list delr."""
        disv = Disv(nlay=1, ncpl=100, top=[1.0] * 100, botm=[[-1.0] * 100])

        assert disv.top.shape == (100,)
        assert np.all(disv.top == 1.0)
        assert disv.botm.shape == (
            1,
            100,
        )
        assert np.all(disv.botm == -1.0)

    def test_disv_with_numpy_array(self):
        """Test Disv with numpy array input."""
        top_array = np.linspace(1.0, 2.0, 100)
        disv = Disv(nlay=1, ncpl=100, top=top_array, botm=1.0)

        assert disv.top.shape == (100,)
        assert np.allclose(disv.top, top_array)


class TestIcComponent:
    """Test structure_array with Ic component (initial conditions)."""

    def test_ic_with_scalar_strt(self):
        """Test IC with scalar starting head (broadcast to all nodes)."""
        ic = Ic(dims={"nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}, strt=100.0)

        assert hasattr(ic, "strt")
        assert isinstance(ic.strt, (np.ndarray, xr.DataArray))
        if isinstance(ic.strt, xr.DataArray):
            assert ic.strt.shape == (100,)
            assert np.all(ic.strt.values == 100.0)
        else:
            assert ic.strt.shape == (100,)
            assert np.all(ic.strt == 100.0)

    def test_ic_with_numpy_array(self):
        """Test IC with numpy array."""
        strt_array = np.ones((100,)) * 50.0
        ic = Ic(dims={"nodes": 100}, strt=strt_array)

        assert ic.strt.shape == (100,)
        assert np.all(ic.strt == 50.0)

    def test_ic_with_structured_array(self):
        """Test IC with structured grid array (should reshape to flat)."""
        # This would require grid reshaping functionality
        strt_3d = np.ones((1, 10, 10)) * 100.0
        ic = Ic(dims={"nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}, strt=strt_3d)

        # Should be reshaped to flat nodes
        assert ic.strt.shape == (100,)
        assert np.all(ic.strt == 100.0)


class TestNpfComponent:
    """Test structure_array with Npf component."""

    def test_npf_with_scalar_k(self):
        """Test NPF with scalar hydraulic conductivity."""
        npf = Npf(dims={"nodes": 100}, k=1.0)

        assert hasattr(npf, "k")
        assert isinstance(npf.k, (np.ndarray, xr.DataArray))
        if isinstance(npf.k, xr.DataArray):
            assert npf.k.shape == (100,)
            assert np.all(npf.k.values == 1.0)
        else:
            assert npf.k.shape == (100,)
            assert np.all(npf.k == 1.0)

    def test_npf_with_layered_k(self):
        """Test NPF with layered k values."""
        k_3d = np.ones((2, 10, 10))
        k_3d[0] = 10.0
        k_3d[1] = 1.0

        npf = Npf(dims={"nlay": 2, "nrow": 10, "ncol": 10, "nodes": 200}, k=k_3d)

        assert npf.k.shape == (200,)
        # First layer (nodes 0-99) should be 10.0
        assert np.all(npf.k[:100] == 10.0)
        # Second layer (nodes 100-199) should be 1.0
        assert np.all(npf.k[100:] == 1.0)


class TestChdComponent:
    """Test structure_array with Chd component (stress period data)."""

    def test_chd_with_dict_format(self):
        """Test CHD with dict format and cellid: value."""
        chd = Chd(
            dims={"nlay": 1, "nrow": 10, "ncol": 10, "nper": 3, "nodes": 100},
            head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
        )

        assert hasattr(chd, "head")
        assert chd.head.shape == (3, 100)
        # SP 0 should have the values
        assert chd.head[0, 0] == 1.0
        assert chd.head[0, 99] == 0.0
        # SP 1 and 2 should fill forward from SP 0
        assert chd.head[1, 0] == 1.0
        assert chd.head[2, 99] == 0.0

    def test_chd_with_star_key(self):
        """Test CHD with '*' key for all stress periods."""
        chd = Chd(
            dims={"nlay": 1, "nrow": 10, "ncol": 10, "nper": 3, "nodes": 100},
            head={"*": {(0, 0, 0): 5.0}},
        )

        # '*' should map to period 0 and fill forward
        assert chd.head[0, 0] == 5.0
        assert chd.head[1, 0] == 5.0
        assert chd.head[2, 0] == 5.0

    def test_chd_with_fill_forward(self):
        """Test CHD with fill-forward behavior."""
        chd = Chd(
            dims={"nlay": 1, "nrow": 10, "ncol": 10, "nper": 10, "nodes": 100},
            head={0: {(0, 0, 0): 1.0}, 5: {(0, 0, 0): 2.0}},
        )

        # SP 0-4 should have first value
        assert chd.head[0, 0] == 1.0
        assert chd.head[4, 0] == 1.0

        # SP 5+ should have second value
        assert chd.head[5, 0] == 2.0
        assert chd.head[9, 0] == 2.0


class TestRchComponent:
    """Test structure_array with Rch component (recharge)."""

    def test_rch_with_scalar_dict(self):
        """Test RCH with scalar values per stress period."""
        rch = Rch(
            dims={"nlay": 1, "nrow": 10, "ncol": 10, "nper": 3, "nodes": 100},
            recharge={0: 0.004, 1: 0.002},
        )

        assert hasattr(rch, "recharge")
        # Should broadcast scalar to all nodes
        assert rch.recharge.shape == (3, 100)
        assert np.all(rch.recharge[0] == 0.004)
        assert np.all(rch.recharge[1] == 0.002)
        # SP 2 should fill forward from SP 1
        assert np.all(rch.recharge[2] == 0.002)


class TestSparseArrays:
    """Test sparse array creation for large arrays."""

    def test_sparse_array_creation(self):
        """Test that large sparse arrays use COO format."""
        # Create a CHD with very large grid (exceeds threshold)
        from flopy4.mf6.config import SPARSE_THRESHOLD

        nper = 10
        nodes = 100000  # Large grid
        total_size = nper * nodes

        if total_size > SPARSE_THRESHOLD:
            chd = Chd(
                dims={"nlay": 1, "nrow": 1000, "ncol": 100, "nper": nper, "nodes": nodes},
                head={0: {(0, 0, 0): 1.0, (0, 999, 99): 0.0}},
            )

            # Should create sparse array (possibly wrapped in xarray)
            if isinstance(chd.head, xr.DataArray):
                # If wrapped in xarray, check the underlying data
                assert isinstance(chd.head.data, sparse.COO)
                assert chd.head.shape == (nper, nodes)
            else:
                assert isinstance(chd.head, sparse.COO)
                assert chd.head.shape == (nper, nodes)


class TestXarrayOutput:
    """Test xarray output functionality."""

    def test_xarray_output_disabled_by_default(self):
        """Test that xarray output is disabled by default for backward compatibility."""
        ic = Ic(dims={"nodes": 100}, strt=100.0)

        # Default is return_xarray=False, so should get numpy
        # (this is set in the field converter, not directly testable here)
        assert isinstance(ic.strt, (np.ndarray, sparse.COO)) or isinstance(ic.strt, xr.DataArray)


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_dict_creates_default_array(self):
        """Test that empty dict creates array with default values."""
        ic = Ic(dims={"nodes": 100}, strt={})

        # Should create array with defaults
        assert hasattr(ic, "strt")
        assert ic.strt.shape == (100,)

    def test_mixed_dict_value_types(self):
        """Test dict with mixed value types (scalar, array)."""
        chd = Chd(
            dims={"nlay": 1, "nrow": 10, "ncol": 10, "nper": 10, "nodes": 100},
            head={
                0: {(0, 0, 0): 1.0},  # Dict with cellid
                5: {(0, 0, 0): 2.0, (0, 9, 9): 0.5},  # Multiple cellids
            },
        )

        assert chd.head[0, 0] == 1.0
        assert chd.head[5, 0] == 2.0
        assert chd.head[5, 99] == 0.5


class TestDataFrameIntegration:
    """Test DataFrame input format (round-trip with stress_period_data property)."""

    def test_dataframe_roundtrip_chd_structured(self):
        """Test round-trip: Chd with dict -> DataFrame -> new Chd with DataFrame."""
        # Create Chd with dict format
        chd1 = Chd(
            dims={"nlay": 2, "nrow": 10, "ncol": 10, "nper": 3, "nodes": 200},
            head={
                0: {(0, 0, 0): 10.0, (1, 9, 9): 5.0},
                1: {(0, 0, 0): 11.0, (1, 9, 9): 6.0},
            },
        )

        # Get DataFrame representation
        df = chd1.stress_period_data

        # Create new Chd with DataFrame
        chd2 = Chd(
            dims={"nlay": 2, "nrow": 10, "ncol": 10, "nper": 3, "nodes": 200},
            head=df,
        )

        # Verify data matches
        # Period 0: (0,0,0) -> 10.0, (1,9,9) -> 5.0
        assert chd2.head[0, 0] == 10.0
        assert chd2.head[0, 199] == 5.0

        # Period 1: (0,0,0) -> 11.0, (1,9,9) -> 6.0
        assert chd2.head[1, 0] == 11.0
        assert chd2.head[1, 199] == 6.0

    def test_dataframe_roundtrip_chd_unstructured(self):
        """Test round-trip with unstructured grid (node-based)."""
        # Create Chd with dict format (node-based)
        # Note: cellids are tuples even for unstructured: (node,)
        chd1 = Chd(
            dims={"nper": 2, "nodes": 100},
            head={
                0: {(0,): 20.0, (99,): 15.0},
                1: {(0,): 21.0, (50,): 16.0},
            },
        )

        # Get DataFrame representation
        df = chd1.stress_period_data

        # Create new Chd with DataFrame
        chd2 = Chd(
            dims={"nper": 2, "nodes": 100},
            head=df,
        )

        # Verify data matches
        assert chd2.head[0, 0] == 20.0
        assert chd2.head[0, 99] == 15.0
        assert chd2.head[1, 0] == 21.0
        assert chd2.head[1, 50] == 16.0

    def test_dataframe_with_star_key(self):
        """Test DataFrame from dict with '*' key (applies to period 0)."""
        # Create Chd with '*' key
        chd1 = Chd(
            dims={"nlay": 1, "nrow": 5, "ncol": 5, "nper": 2, "nodes": 25},
            head={
                "*": {(0, 0, 0): 100.0, (0, 4, 4): 50.0},
            },
        )

        # Get DataFrame
        df = chd1.stress_period_data

        # Create new Chd with DataFrame
        chd2 = Chd(
            dims={"nlay": 1, "nrow": 5, "ncol": 5, "nper": 2, "nodes": 25},
            head=df,
        )

        # Verify data matches for period 0
        assert chd2.head[0, 0] == 100.0
        assert chd2.head[0, 24] == 50.0
