"""Tests for stress_period_data property."""

import pandas as pd

from flopy4.mf6.gwf import Chd, Drn, Gwf, Wel


def test_chd_stress_period_data():
    """Test stress_period_data property for CHD package."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
    df = chd.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "kper" in df.columns
    assert "node" in df.columns
    assert "head" in df.columns

    # Check first record (node 0 = cell (0,0,0))
    assert df.iloc[0]["kper"] == 0
    assert df.iloc[0]["node"] == 0
    assert df.iloc[0]["head"] == 1.0

    # Check second record (node 99 = cell (0,9,9))
    assert df.iloc[1]["kper"] == 0
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
    assert "kper" in df.columns
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
    assert df[df["kper"] == 0].iloc[0]["head"] == 1.0
    assert df[df["kper"] == 1].iloc[0]["head"] == 0.9
    assert df[df["kper"] == 2].iloc[0]["head"] == 0.8


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
    per0 = df[df["kper"] == 0]
    assert len(per0) == 3
    assert set(per0["head"].values) == {1.0, 0.5, 0.0}

    # Verify period 1
    per1 = df[df["kper"] == 1]
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
    assert "kper" in df.columns
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
    assert "kper" in df.columns
    assert "node" in df.columns
    assert "head" in df.columns
    assert "aux" in df.columns
    assert "boundname" in df.columns

    # Check first record
    assert df.iloc[0]["kper"] == 0
    assert df.iloc[0]["node"] == 0
    assert df.iloc[0]["head"] == 1.0
    assert df.iloc[0]["aux"] == 100.0
    assert df.iloc[0]["boundname"] == "INLET"

    # Check second record
    assert df.iloc[1]["kper"] == 0
    assert df.iloc[1]["node"] == 99
    assert df.iloc[1]["head"] == 0.0
    assert df.iloc[1]["aux"] == 200.0
    assert df.iloc[1]["boundname"] == "OUTLET"


def test_stress_period_data_with_structured_grid_parent():
    """Test stress_period_data uses layer/row/col when parent has grid info."""
    from flopy4.mf6 import Simulation
    from flopy4.mf6.gwf import Dis

    # Create a real model with DIS (structured grid) package
    sim = Simulation()

    # Create DIS package with structured grid dimensions
    dis = Dis(
        nlay=1,
        nrow=10,
        ncol=10,
    )

    # Create Gwf model with the DIS package
    gwf = Gwf(parent=sim, dis=dis)

    chd = Chd(
        parent=gwf,
        head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}},
    )

    df = chd.stress_period_data

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2

    # Should have layer/row/col columns, not node
    assert "kper" in df.columns
    assert "layer" in df.columns
    assert "row" in df.columns
    assert "col" in df.columns
    assert "node" not in df.columns

    # Check first record (node 0 = layer 0, row 0, col 0)
    assert df.iloc[0]["kper"] == 0
    assert df.iloc[0]["layer"] == 0
    assert df.iloc[0]["row"] == 0
    assert df.iloc[0]["col"] == 0
    assert df.iloc[0]["head"] == 1.0

    # Check second record (node 99 = layer 0, row 9, col 9)
    assert df.iloc[1]["kper"] == 0
    assert df.iloc[1]["layer"] == 0
    assert df.iloc[1]["row"] == 9
    assert df.iloc[1]["col"] == 9
    assert df.iloc[1]["head"] == 0.0


def test_stress_period_data_setter_single_field():
    """Test setting stress_period_data for single-field package (CHD)."""
    dims = {"nper": 2, "nodes": 100}

    # Create package with initial data
    chd = Chd(dims=dims, head={0: {(0,): 1.0}})

    # Create new DataFrame with node-based coordinates
    new_df = pd.DataFrame(
        {
            "kper": [0, 0, 1],
            "node": [0, 55, 0],
            "head": [10.0, 8.0, 9.0],
        }
    )

    # Set new data
    chd.stress_period_data = new_df

    # Verify data was updated
    result_df = chd.stress_period_data
    assert len(result_df) == 3
    assert result_df.iloc[0]["node"] == 0
    assert result_df.iloc[0]["head"] == 10.0
    assert result_df.iloc[1]["node"] == 55
    assert result_df.iloc[1]["head"] == 8.0
    assert result_df[result_df["kper"] == 1].iloc[0]["head"] == 9.0


def test_stress_period_data_setter_multifield():
    """Test setting stress_period_data for multi-field package (DRN)."""
    dims = {"nper": 2, "nodes": 100}

    # Create package with both fields
    drn = Drn(
        dims=dims,
        elev={0: {(55,): 10.0}},
        cond={0: {(55,): 1.0}},
    )

    # Create new DataFrame with both fields using node coordinates
    new_df = pd.DataFrame(
        {
            "kper": [0, 1, 1],
            "node": [22, 33, 44],
            "elev": [15.0, 12.0, 11.0],
            "cond": [2.0, 1.5, 1.2],
        }
    )

    # Set new data
    drn.stress_period_data = new_df

    # Verify both fields were updated
    result_df = drn.stress_period_data
    assert len(result_df) == 3
    assert result_df.iloc[0]["elev"] == 15.0
    assert result_df.iloc[0]["cond"] == 2.0
    assert result_df.iloc[1]["elev"] == 12.0
    assert result_df.iloc[1]["cond"] == 1.5


def test_stress_period_data_setter_modify_existing():
    """Test modifying existing data via DataFrame."""
    dims = {"nper": 2, "nodes": 100}

    # Create package
    chd = Chd(
        dims=dims,
        head={0: {(0,): 1.0, (55,): 2.0}, 1: {(0,): 0.9}},
    )

    # Get current data
    df = chd.stress_period_data

    # Modify values
    df["head"] = df["head"] * 2

    # Set back
    chd.stress_period_data = df

    # Verify modification
    result_df = chd.stress_period_data
    assert len(result_df) == 3
    # Values should be doubled
    assert 2.0 in result_df["head"].values
    assert 4.0 in result_df["head"].values
    assert 1.8 in result_df["head"].values


def test_stress_period_data_setter_node_format():
    """Test setter with node-based coordinates (unstructured grid)."""
    dims = {"nper": 2, "nodes": 100}

    # Create package
    chd = Chd(dims=dims, head={0: {(0,): 10.0, (99,): 5.0}})

    # Create new DataFrame with node format
    new_df = pd.DataFrame({"kper": [0, 1], "node": [50, 50], "head": [7.0, 6.0]})

    # Set new data
    chd.stress_period_data = new_df

    # Verify
    result_df = chd.stress_period_data
    assert len(result_df) == 2
    assert result_df.iloc[0]["node"] == 50
    assert result_df.iloc[0]["head"] == 7.0
    assert result_df.iloc[1]["head"] == 6.0


def test_stress_period_data_setter_partial_fields():
    """Test setting only some fields in a multi-field package."""
    dims = {"nper": 1, "nodes": 100}

    # Create package with both fields
    drn = Drn(
        dims=dims,
        elev={0: {(55,): 10.0}},
        cond={0: {(55,): 1.0}},
    )

    # Create DataFrame with only elev field
    new_df = pd.DataFrame({"kper": [0], "node": [33], "elev": [20.0]})

    # Set only elev
    drn.stress_period_data = new_df

    # Verify elev was updated, cond should be unchanged or empty
    result_df = drn.stress_period_data
    assert "elev" in result_df.columns
    # Only elev was set, so we should only see elev data
    assert len(result_df[result_df["elev"] == 20.0]) == 1


def test_stress_period_data_setter_structured_grid():
    """Test setter with structured grid coordinates (layer/row/col)."""
    import numpy as np

    from flopy4.mf6.gwf import Dis

    # Create parent model and DIS package to define grid
    dis = Dis(
        nlay=2,
        nrow=10,
        ncol=10,
        delr=1.0,
        delc=1.0,
        top=1.0,
        botm=np.array([[0.5] * 100, [0.0] * 100]).reshape(2, 10, 10),
    )
    gwf = Gwf(dis=dis)

    # Create CHD package attached to parent with initialized grid
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0}}, dims={"nper": 2})

    # Create DataFrame with structured coordinates
    new_df = pd.DataFrame(
        {
            "kper": [0, 0, 1],
            "layer": [0, 1, 0],
            "row": [0, 5, 0],
            "col": [0, 5, 0],
            "head": [10.0, 8.0, 9.0],
        }
    )

    # Set new data
    chd.stress_period_data = new_df

    # Verify data was updated with structured coordinates
    result_df = chd.stress_period_data
    assert len(result_df) == 3
    assert "layer" in result_df.columns
    assert "row" in result_df.columns
    assert "col" in result_df.columns
    assert result_df.iloc[0]["head"] == 10.0
    assert result_df.iloc[1]["head"] == 8.0
    assert result_df.iloc[2]["head"] == 9.0


def test_stress_period_data_setter_errors():
    """Test error handling in setter."""
    dims = {"nper": 1, "nodes": 100}
    chd = Chd(dims=dims, head={0: {(0,): 1.0}})

    # Test wrong type
    try:
        chd.stress_period_data = {"not": "a dataframe"}
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "Expected DataFrame" in str(e)

    # Test missing field columns
    try:
        bad_df = pd.DataFrame({"kper": [0], "node": [0]})
        chd.stress_period_data = bad_df
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must contain at least one period field column" in str(e)

    # Test structured coordinates without proper grid dimensions
    try:
        bad_df = pd.DataFrame({"kper": [0], "layer": [0], "row": [0], "col": [0], "head": [1.0]})
        chd.stress_period_data = bad_df
        assert False, "Should have raised ValueError about missing dimensions"
    except ValueError as e:
        assert "missing required dimensions" in str(e)
