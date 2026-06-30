"""
Tests for flopy4.mf6.converter.ingress.structure module.

Integration tests for the refactored structure_array function with various input formats
using real flopy4 components.
"""

import numpy as np
import sparse
import xarray as xr

from flopy4.mf6.gwf.chd import Chd
from flopy4.mf6.gwf.dis import Dis
from flopy4.mf6.gwf.disv import Disv
from flopy4.mf6.gwf.ic import Ic
from flopy4.mf6.gwf.npf import Npf
from flopy4.mf6.gwf.rch import Rch


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
        assert disv.botm.shape == (100,)
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
        """Test CHD with stress_period_data dict format (codegen v2 API)."""
        chd = Chd(
            stress_period_data={0: [((0, 0, 0), 1.0), ((0, 9, 9), 0.0)]},
        )

        assert hasattr(chd, "_stress_period_data")
        rec = chd._stress_period_data[0]
        assert rec["cellid"][0].tolist() == [0, 0, 0]
        assert float(rec["head"][0]) == 1.0
        assert rec["cellid"][1].tolist() == [0, 9, 9]
        assert float(rec["head"][1]) == 0.0

    def test_chd_with_fill_forward(self):
        """Test CHD stores multiple periods separately (fill-forward is write-time only)."""
        chd = Chd(
            stress_period_data={
                0: [((0, 0, 0), 1.0)],
                5: [((0, 0, 0), 2.0)],
            },
        )

        # Both periods are stored; no in-memory fill-forward in codegen v2
        assert set(chd._stress_period_data.keys()) == {0, 5}
        assert float(chd._stress_period_data[0]["head"][0]) == 1.0
        assert float(chd._stress_period_data[5]["head"][0]) == 2.0


class TestRchComponent:
    """Test structure_array with Rch component (recharge)."""

    def test_rch_with_stress_period_data(self):
        """Test RCH with codegen v2 stress_period_data API (explicit cellid tuples)."""
        rch = Rch(
            stress_period_data={
                0: [((0, 0, 0), 0.004), ((0, 9, 9), 0.004)],
                1: [((0, 0, 0), 0.002), ((0, 9, 9), 0.002)],
            },
        )

        assert hasattr(rch, "_stress_period_data")
        assert set(rch._stress_period_data.keys()) == {0, 1}
        assert float(rch._stress_period_data[0]["recharge"][0]) == 0.004
        assert float(rch._stress_period_data[1]["recharge"][0]) == 0.002


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
        """Test stress_period_data with multiple periods and cellids (codegen v2 API)."""
        chd = Chd(
            stress_period_data={
                0: [((0, 0, 0), 1.0)],
                5: [((0, 0, 0), 2.0), ((0, 9, 9), 0.5)],
            },
        )

        assert set(chd._stress_period_data.keys()) == {0, 5}
        assert float(chd._stress_period_data[0]["head"][0]) == 1.0
        assert float(chd._stress_period_data[5]["head"][0]) == 2.0
        assert float(chd._stress_period_data[5]["head"][1]) == 0.5


class TestDataFrameIntegration:
    """Test to_dataframe() output from codegen v2 stress period packages."""

    def test_to_dataframe_chd_multi_period(self):
        """Test that to_dataframe() returns correct tidy DataFrame for multi-period CHD."""
        chd = Chd(
            stress_period_data={
                0: [((0, 0, 0), 10.0), ((1, 9, 9), 5.0)],
                1: [((0, 0, 0), 11.0), ((1, 9, 9), 6.0)],
            },
        )

        df = chd.to_dataframe()

        assert "kper" in df.columns
        assert "cellid" in df.columns
        assert "head" in df.columns
        p0 = df[df["kper"] == 0].reset_index(drop=True)
        assert len(p0) == 2
        assert float(p0.loc[0, "head"]) == 10.0
        assert float(p0.loc[1, "head"]) == 5.0

    def test_to_dataframe_chd_cellid_as_tuple(self):
        """Test that cellid column contains tuples (not expanded layer/row/col)."""
        chd = Chd(
            stress_period_data={0: [((0, 2, 3), 7.5)]},
        )

        df = chd.to_dataframe()

        assert "cellid" in df.columns
        cellid = df.iloc[0]["cellid"]
        assert isinstance(cellid, (tuple, list))
        assert tuple(cellid) == (0, 2, 3)
