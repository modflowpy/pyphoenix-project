"""Tests for DataFrame API for period data."""

import numpy as np
import pandas as pd
import pytest

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.gwf import Chd, Drn, Gwf, Wel
from flopy4.mf6.utils.grid import StructuredGrid
from flopy4.mf6.utils.time import Time


def test_chd_to_dataframe():
    """Test converting CHD package to DataFrame."""
    time = Time(perlen=[1.0], nstp=[1])
    grid = StructuredGrid(nlay=1, nrow=10, ncol=10)
    dims = {
        "nlay": grid.nlay,
        "nrow": grid.nrow,
        "ncol": grid.ncol,
        "nper": time.nper,
        "nodes": grid.nnodes,
    }

    chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
    df = chd.to_dataframe("head")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["per", "layer", "row", "col", "head"]

    # Check first record
    assert df.iloc[0]["per"] == 0
    assert df.iloc[0]["layer"] == 0
    assert df.iloc[0]["row"] == 0
    assert df.iloc[0]["col"] == 0
    assert df.iloc[0]["head"] == 1.0

    # Check second record
    assert df.iloc[1]["per"] == 0
    assert df.iloc[1]["layer"] == 0
    assert df.iloc[1]["row"] == 9
    assert df.iloc[1]["col"] == 9
    assert df.iloc[1]["head"] == 0.0


def test_chd_from_dataframe():
    """Test creating CHD package from DataFrame."""
    df = pd.DataFrame(
        {
            "per": [0, 0],
            "layer": [0, 0],
            "row": [0, 9],
            "col": [0, 9],
            "head": [1.0, 0.0],
        }
    )

    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}
    chd = Chd.from_dataframe(df, "head", dims=dims)

    assert chd.head is not None
    assert chd.head.shape == (1, 100)

    # Check that the correct cells have values
    assert chd.head[0, 0] == 1.0  # (0, 0, 0) -> node 0
    assert chd.head[0, 99] == 0.0  # (0, 9, 9) -> node 99


def test_chd_roundtrip():
    """Test round-trip conversion: dict -> to_dataframe -> from_dataframe."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    # Create original package
    chd1 = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})

    # Convert to DataFrame
    df = chd1.to_dataframe("head")

    # Create new package from DataFrame
    chd2 = Chd.from_dataframe(df, "head", dims=dims)

    # Compare
    assert np.allclose(chd1.head, chd2.head, equal_nan=True)


def test_wel_to_dataframe():
    """Test converting WEL package to DataFrame."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    wel = Wel(
        dims=dims,
        q={0: {(0, 5, 5): -100.0, (0, 8, 8): 50.0}},
    )
    df = wel.to_dataframe("q")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["per", "layer", "row", "col", "q"]

    # Check records
    assert df.iloc[0]["q"] == -100.0
    assert df.iloc[1]["q"] == 50.0


def test_wel_from_dataframe():
    """Test creating WEL package from DataFrame."""
    df = pd.DataFrame(
        {
            "per": [0, 0],
            "layer": [0, 0],
            "row": [5, 8],
            "col": [5, 8],
            "q": [-100.0, 50.0],
        }
    )

    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}
    wel = Wel.from_dataframe(df, "q", dims=dims)

    assert wel.q is not None
    assert wel.q.shape == (1, 100)

    # Node for (0, 5, 5) = 5*10 + 5 = 55
    assert wel.q[0, 55] == -100.0
    # Node for (0, 8, 8) = 8*10 + 8 = 88
    assert wel.q[0, 88] == 50.0


def test_drn_to_dataframe():
    """Test converting DRN package to DataFrame (multi-field)."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    drn = Drn(
        dims=dims,
        elev={0: {(0, 7, 5): 10.0}},
        cond={0: {(0, 7, 5): 1.0}},
    )

    # Test elevation field
    df_elev = drn.to_dataframe("elev")
    assert len(df_elev) == 1
    assert df_elev.iloc[0]["elev"] == 10.0

    # Test conductance field
    df_cond = drn.to_dataframe("cond")
    assert len(df_cond) == 1
    assert df_cond.iloc[0]["cond"] == 1.0


def test_multi_period_dataframe():
    """Test DataFrame conversion with multiple stress periods."""
    dims = {"nper": 3, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(
        dims=dims,
        head={
            0: {(0, 0, 0): 1.0},
            1: {(0, 0, 0): 0.9},
            2: {(0, 0, 0): 0.8},
        },
    )

    df = chd.to_dataframe("head")

    assert len(df) == 3
    assert df[df["per"] == 0].iloc[0]["head"] == 1.0
    assert df[df["per"] == 1].iloc[0]["head"] == 0.9
    assert df[df["per"] == 2].iloc[0]["head"] == 0.8


def test_dataframe_with_multiple_cells():
    """Test DataFrame conversion with multiple cells per period."""
    df = pd.DataFrame(
        {
            "per": [0, 0, 0, 1, 1, 1],
            "layer": [0, 0, 0, 0, 0, 0],
            "row": [0, 5, 9, 0, 5, 9],
            "col": [0, 5, 9, 0, 5, 9],
            "head": [1.0, 0.5, 0.0, 0.9, 0.45, 0.0],
        }
    )

    dims = {"nper": 2, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}
    chd = Chd.from_dataframe(df, "head", dims=dims)

    # Verify period 0
    assert chd.head[0, 0] == 1.0
    assert chd.head[0, 55] == 0.5
    assert chd.head[0, 99] == 0.0

    # Verify period 1
    assert chd.head[1, 0] == 0.9
    assert chd.head[1, 55] == 0.45
    assert chd.head[1, 99] == 0.0


def test_to_dataframe_auto_detect_field():
    """Test automatic field detection in to_dataframe."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0}})

    # Should auto-detect 'head' field
    df = chd.to_dataframe()
    assert "head" in df.columns
    assert len(df) == 1


def test_empty_dataframe():
    """Test converting empty package to DataFrame."""
    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}

    chd = Chd(dims=dims)  # No head data
    df = chd.to_dataframe("head")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_from_dataframe_with_kwargs():
    """Test from_dataframe with additional package parameters."""
    df = pd.DataFrame(
        {
            "per": [0, 0],
            "layer": [0, 0],
            "row": [0, 9],
            "col": [0, 9],
            "head": [1.0, 0.0],
        }
    )

    dims = {"nper": 1, "nlay": 1, "nrow": 10, "ncol": 10, "nodes": 100}
    chd = Chd.from_dataframe(
        df, "head", dims=dims, print_input=True, print_flows=True
    )

    assert chd.print_input is True
    assert chd.print_flows is True
    assert chd.head is not None
