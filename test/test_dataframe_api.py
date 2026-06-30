"""Tests for stress_period_data / to_dataframe() API.

Codegen v2 packages (Chd, Drn, Wel, …) expose:
  - ``stress_period_data`` property returning ``Optional[dict[int, np.recarray]]``
  - ``to_dataframe()`` returning a tidy DataFrame with ``kper``, ``cellid``
    (tuple column), and field value columns (head, q, elev, cond, …)

Tests that require the old xattree ``stress_period_data`` getter/setter
(DataFrame with flat ``node`` or ``layer``/``row``/``col`` columns), the
DataFrame setter, structured-parent integration, or G/A variant array
packages are individually skipped with a TODO note.
"""

import pandas as pd
import pytest

from flopy4.mf6.gwf import Chd, Drn, Wel


def test_chd_to_dataframe():
    """to_dataframe() for CHD returns kper, cellid tuple, and head columns."""
    chd = Chd(stress_period_data={0: [((0, 0, 0), 1.0), ((0, 9, 9), 0.0)]})
    df = chd.to_dataframe()

    assert isinstance(df, type(df))  # is a DataFrame
    assert len(df) == 2
    assert "kper" in df.columns
    assert "cellid" in df.columns
    assert "head" in df.columns

    # First row: cellid (0,0,0), head 1.0
    row0 = df[df["kper"] == 0].iloc[0]
    assert tuple(row0["cellid"]) == (0, 0, 0)
    assert float(row0["head"]) == 1.0

    # Second row: cellid (0,9,9), head 0.0
    row1 = df[df["kper"] == 0].iloc[1]
    assert tuple(row1["cellid"]) == (0, 9, 9)
    assert float(row1["head"]) == 0.0


def test_wel_to_dataframe():
    """to_dataframe() for WEL returns q column."""
    wel = Wel(
        stress_period_data={0: [((0, 5, 5), -100.0), ((0, 8, 8), 50.0)]},
    )
    df = wel.to_dataframe()

    assert len(df) == 2
    assert "kper" in df.columns
    assert "q" in df.columns
    qs = sorted(float(v) for v in df["q"])
    assert qs == [-100.0, 50.0]


def test_drn_to_dataframe_multifield():
    """to_dataframe() for DRN returns both elev and cond columns."""
    drn = Drn(stress_period_data={0: [((0, 7, 5), 10.0, 1.0)]})
    df = drn.to_dataframe()

    assert len(df) == 1
    assert "elev" in df.columns
    assert "cond" in df.columns
    assert float(df.iloc[0]["elev"]) == 10.0
    assert float(df.iloc[0]["cond"]) == 1.0


def test_multi_period_to_dataframe():
    """to_dataframe() includes rows for each stress period."""
    chd = Chd(
        stress_period_data={
            0: [((0, 0, 0), 1.0)],
            1: [((0, 0, 0), 0.9)],
            2: [((0, 0, 0), 0.8)],
        },
    )
    df = chd.to_dataframe()

    assert len(df) == 3
    assert float(df[df["kper"] == 0].iloc[0]["head"]) == 1.0
    assert float(df[df["kper"] == 1].iloc[0]["head"]) == 0.9
    assert float(df[df["kper"] == 2].iloc[0]["head"]) == 0.8


def test_multiple_cells_to_dataframe():
    """to_dataframe() includes all cells for each period."""
    chd = Chd(
        stress_period_data={
            0: [((0, 0, 0), 1.0), ((0, 5, 5), 0.5), ((0, 9, 9), 0.0)],
            1: [((0, 0, 0), 0.9), ((0, 5, 5), 0.45), ((0, 9, 9), 0.0)],
        },
    )
    df = chd.to_dataframe()

    assert len(df) == 6

    per0 = df[df["kper"] == 0]
    assert len(per0) == 3
    assert sorted(float(v) for v in per0["head"]) == [0.0, 0.5, 1.0]

    per1 = df[df["kper"] == 1]
    assert len(per1) == 3
    assert sorted(float(v) for v in per1["head"]) == [0.0, 0.45, 0.9]


def test_empty_stress_period_data_to_dataframe():
    """to_dataframe() returns empty DataFrame when no stress period data."""
    chd = Chd()  # No stress_period_data
    df = chd.to_dataframe()

    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


# ---------------------------------------------------------------------------
# DataFrame setter (from_dataframe)
# ---------------------------------------------------------------------------


def test_stress_period_data_setter_single_field():
    """Set CHD stress_period_data from a DataFrame with one value column."""
    chd = Chd(stress_period_data={0: [[(0, 0, 0), 1.0], [(0, 0, 1), 2.0]]})
    df = chd.to_dataframe()
    chd.from_dataframe(df)
    spd = chd.stress_period_data
    assert tuple(spd[0]["cellid"][0]) == (0, 0, 0)
    assert spd[0]["head"][0] == 1.0
    assert spd[0]["head"][1] == 2.0


def test_stress_period_data_setter_multifield():
    """Set DRN stress_period_data from a DataFrame with multiple value columns."""
    drn = Drn(stress_period_data={0: [[(0, 0, 0), 5.0, 0.01], [(0, 1, 0), 4.0, 0.02]]})
    df = drn.to_dataframe()
    drn.from_dataframe(df)
    spd = drn.stress_period_data
    assert spd[0]["elev"][0] == pytest.approx(5.0)
    assert spd[0]["cond"][1] == pytest.approx(0.02)


def test_stress_period_data_setter_modify_existing():
    """Modify a value in the DataFrame then set back."""
    chd = Chd(stress_period_data={0: [[(0, 0, 0), 1.0]]})
    df = chd.to_dataframe()
    df.loc[0, "head"] = 99.0
    chd.from_dataframe(df)
    assert chd.stress_period_data[0]["head"][0] == pytest.approx(99.0)


def test_stress_period_data_setter_node_format():
    """CHD with DISV (2D cellid) round-trips through DataFrame."""
    chd = Chd(
        dims={"ncpl": 10, "nlay": 1, "nodes": 10},
        stress_period_data={0: [[(0, 5), 1.0], [(0, 9), 2.0]]},
    )
    df = chd.to_dataframe()
    chd.from_dataframe(df)
    spd = chd.stress_period_data
    assert tuple(spd[0]["cellid"][0]) == (0, 5)
    assert spd[0]["head"][1] == pytest.approx(2.0)


def test_stress_period_data_setter_partial_fields():
    """Setting from a DataFrame with fewer rows than original replaces SPD."""
    chd = Chd(stress_period_data={0: [[(0, 0, 0), 1.0], [(0, 0, 1), 2.0]]})
    df = chd.to_dataframe()
    # Keep only first row
    df = df.iloc[:1]
    chd.from_dataframe(df)
    assert len(chd.stress_period_data[0]) == 1


def test_stress_period_data_setter_structured_grid():
    """CHD with multiple stress periods round-trips correctly."""
    chd = Chd(
        stress_period_data={
            0: [[(0, 0, 0), 1.0], [(0, 0, 1), 2.0]],
            1: [[(0, 0, 0), 3.0]],
        }
    )
    df = chd.to_dataframe()
    chd.from_dataframe(df)
    spd = chd.stress_period_data
    assert set(spd.keys()) == {0, 1}
    assert spd[1]["head"][0] == pytest.approx(3.0)


def test_stress_period_data_setter_errors():
    """from_dataframe raises on missing kper column."""
    chd = Chd(stress_period_data={0: [[(0, 0, 0), 1.0]]})
    df = pd.DataFrame({"cellid": [(0, 0, 0)], "head": [1.0]})
    with pytest.raises(ValueError, match="kper"):
        chd.from_dataframe(df)


def test_stress_period_data_setter_with_named_aux_column():
    """WEL with one aux column round-trips through DataFrame."""
    wel = Wel(
        auxiliary=["concentration"],
        stress_period_data={0: [[(0, 0, 0), -100.0, 35.0]]},
    )
    df = wel.to_dataframe()
    wel.from_dataframe(df)
    spd = wel.stress_period_data
    assert spd[0]["q"][0] == pytest.approx(-100.0)
    assert float(spd[0]["aux0"][0]) == pytest.approx(35.0)


def test_stress_period_data_setter_with_two_named_aux_columns():
    """WEL with two aux columns round-trips through DataFrame."""
    wel = Wel(
        auxiliary=["concentration", "density"],
        stress_period_data={0: [[(0, 0, 0), -100.0, 35.0, 1025.0]]},
    )
    df = wel.to_dataframe()
    wel.from_dataframe(df)
    spd = wel.stress_period_data
    assert float(spd[0]["aux0"][0]) == pytest.approx(35.0)
    assert float(spd[0]["aux1"][0]) == pytest.approx(1025.0)
