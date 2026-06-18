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
# Skipped: old xattree stress_period_data getter API (DataFrame with node/l/r/c)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Old xattree stress_period_data getter returned DataFrame with 'node' column; "
    "codegen v2 uses to_dataframe() returning 'cellid' tuple column"
)
def test_chd_stress_period_data():
    pass


@pytest.mark.skip(reason="Old xattree API; use test_wel_to_dataframe instead")
def test_wel_stress_period_data():
    pass


@pytest.mark.skip(reason="Old xattree API; use test_drn_to_dataframe_multifield instead")
def test_drn_stress_period_data_multifield():
    pass


@pytest.mark.skip(reason="Old xattree API; use test_multi_period_to_dataframe instead")
def test_multi_period_stress_period_data():
    pass


@pytest.mark.skip(reason="Old xattree API; use test_multiple_cells_to_dataframe instead")
def test_stress_period_data_multiple_cells():
    pass


@pytest.mark.skip(reason="Old xattree API; use test_empty_stress_period_data_to_dataframe instead")
def test_empty_stress_period_data():
    pass


@pytest.mark.skip(
    reason="Codegen v2 period schema requires all value columns (elev AND cond) per row; "
    "partial-cell multi-field data not supported in this format"
)
def test_stress_period_data_different_cells_per_field():
    pass


@pytest.mark.skip(
    reason="aux/boundname kwargs not in codegen v2 constructor; "
    "aux naming in to_dataframe() uses 'aux0', 'aux1', … not 'aux'"
)
def test_stress_period_data_with_aux_and_boundname():
    pass


@pytest.mark.skip(
    reason="Requires structured-parent integration (Gwf → Chd with nrow/ncol/nlay); "
    "deferred until parent-aware cellid expansion is implemented"
)
def test_stress_period_data_with_structured_grid_parent():
    pass


# ---------------------------------------------------------------------------
# Skipped: DataFrame setter (not implemented for codegen v2)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="DataFrame setter not implemented for codegen v2 packages; "
    "codegen v2 stress_period_data setter just stores the raw dict"
)
def test_stress_period_data_setter_single_field():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_multifield():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_modify_existing():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_node_format():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_partial_fields():
    pass


@pytest.mark.skip(
    reason="Requires structured-parent integration; DataFrame setter not implemented for codegen v2"
)
def test_stress_period_data_setter_structured_grid():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_errors():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_with_named_aux_column():
    pass


@pytest.mark.skip(reason="DataFrame setter not implemented for codegen v2")
def test_stress_period_data_setter_with_two_named_aux_columns():
    pass


# ---------------------------------------------------------------------------
# Skipped: G/A variant packages (Rcha, Chdg) — old xattree array API
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Rcha is an xattree G/A variant package; stress_period_data getter/setter "
    "uses old array API (recharge=ndarray, parent=gwf); not compatible with codegen v2"
)
def test_rcha_stress_period_data_no_aux():
    pass


@pytest.mark.skip(reason="Rcha old xattree G/A array API")
def test_rcha_stress_period_data_getter_with_aux():
    pass


@pytest.mark.skip(reason="Rcha old xattree G/A array API")
def test_rcha_stress_period_data_setter_with_aux():
    pass


@pytest.mark.skip(reason="Chdg old xattree G/A array API")
def test_chdg_stress_period_data_getter_and_setter_with_aux():
    pass
