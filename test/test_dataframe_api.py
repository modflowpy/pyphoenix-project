"""Tests for stress_period_data property."""

import pandas as pd

from flopy4.mf6.gwf import Chd, Drn, Wel


def test_chd_stress_period_data():
    """Test stress_period_data property for CHD package."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
    df = chd.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "per" in df.columns
    assert "node" in df.columns
    assert "head" in df.columns

    # Check first record (node 0 = cell (0,0,0))
    assert df.iloc[0]["per"] == 0
    assert df.iloc[0]["node"] == 0
    assert df.iloc[0]["head"] == 1.0

    # Check second record (node 99 = cell (0,9,9))
    assert df.iloc[1]["per"] == 0
    assert df.iloc[1]["node"] == 99
    assert df.iloc[1]["head"] == 0.0


def test_wel_stress_period_data():
    """Test stress_period_data property for WEL package."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    wel = Wel(
        dims=dims,
        q={0: {(0, 5, 5): -100.0, (0, 8, 8): 50.0}},
    )
    df = wel.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "per" in df.columns
    assert "q" in df.columns

    # Check records
    assert df.iloc[0]["q"] == -100.0
    assert df.iloc[1]["q"] == 50.0


def test_drn_stress_period_data_multifield():
    """Test stress_period_data property for DRN package (multi-field)."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    drn = Drn(
        dims=dims,
        elev={0: {(0, 7, 5): 10.0}},
        cond={0: {(0, 7, 5): 1.0}},
    )

    df = drn.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1

    # Should have both elev and cond columns
    assert "node" in df.columns
    assert "elev" in df.columns
    assert "cond" in df.columns
    assert df.iloc[0]["elev"] == 10.0
    assert df.iloc[0]["cond"] == 1.0


def test_multi_period_stress_period_data():
    """Test stress_period_data property with multiple stress periods."""
    dims = {"nper": 3, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(
        dims=dims,
        head={
            0: {(0, 0, 0): 1.0},
            1: {(0, 0, 0): 0.9},
            2: {(0, 0, 0): 0.8},
        },
    )

    df = chd.stress_period_data

    assert len(df) == 3
    assert df[df["per"] == 0].iloc[0]["head"] == 1.0
    assert df[df["per"] == 1].iloc[0]["head"] == 0.9
    assert df[df["per"] == 2].iloc[0]["head"] == 0.8


def test_stress_period_data_multiple_cells():
    """Test stress_period_data property with multiple cells per period."""
    dims = {"nper": 2, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(
        dims=dims,
        head={
            0: {(0, 0, 0): 1.0, (0, 5, 5): 0.5, (0, 9, 9): 0.0},
            1: {(0, 0, 0): 0.9, (0, 5, 5): 0.45, (0, 9, 9): 0.0},
        },
    )

    df = chd.stress_period_data

    # Should have 6 records (3 cells x 2 periods)
    assert len(df) == 6

    # Verify period 0
    per0 = df[df["per"] == 0]
    assert len(per0) == 3
    assert set(per0["head"].values) == {1.0, 0.5, 0.0}

    # Verify period 1
    per1 = df[df["per"] == 1]
    assert len(per1) == 3
    assert set(per1["head"].values) == {0.9, 0.45, 0.0}


def test_empty_stress_period_data():
    """Test stress_period_data property with no data."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(dims=dims)  # No head data
    df = chd.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    # Should have coordinate and field columns even if empty
    assert "per" in df.columns
    assert "head" in df.columns


def test_stress_period_data_different_cells_per_field():
    """Test stress_period_data when different fields have data at different cells."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    # Node 75 = (0, 7, 5), Node 33 = (0, 3, 3)
    drn = Drn(
        dims=dims,
        elev={0: {(0, 7, 5): 10.0, (0, 3, 3): 12.0}},  # 2 cells
        cond={0: {(0, 7, 5): 1.0}},  # 1 cell (overlapping)
    )

    df = drn.stress_period_data

    # Should have 2 rows (one for each unique cell location)
    assert len(df) == 2

    # Node 75 (cell 0,7,5) should have both elev and cond
    row1 = df[df["node"] == 75]
    assert len(row1) == 1
    assert row1.iloc[0]["elev"] == 10.0
    assert row1.iloc[0]["cond"] == 1.0

    # Node 33 (cell 0,3,3) should have elev but NaN for cond
    row2 = df[df["node"] == 33]
    assert len(row2) == 1
    assert row2.iloc[0]["elev"] == 12.0
    assert pd.isna(row2.iloc[0]["cond"])


def test_stress_period_data_with_aux_and_boundname():
    """Test stress_period_data includes aux and boundname fields."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(
        dims=dims,
        head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
        aux={0: {(0, 0, 0): 100.0, (0, 9, 9): 200.0}},
        boundname={0: {(0, 0, 0): "INLET", (0, 9, 9): "OUTLET"}},
    )

    df = chd.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2

    # Check that all fields are present
    assert "per" in df.columns
    assert "node" in df.columns
    assert "head" in df.columns
    assert "aux" in df.columns
    assert "boundname" in df.columns

    # Check first record
    assert df.iloc[0]["per"] == 0
    assert df.iloc[0]["node"] == 0
    assert df.iloc[0]["head"] == 1.0
    assert df.iloc[0]["aux"] == 100.0
    assert df.iloc[0]["boundname"] == "INLET"

    # Check second record
    assert df.iloc[1]["per"] == 0
    assert df.iloc[1]["node"] == 99
    assert df.iloc[1]["head"] == 0.0
    assert df.iloc[1]["aux"] == 200.0
    assert df.iloc[1]["boundname"] == "OUTLET"
