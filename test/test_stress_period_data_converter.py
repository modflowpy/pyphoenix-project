"""
Proof of concept: Converting TypedTransformer output to stress_period_data setter format.

This demonstrates that we can use the existing stress_period_data setter
rather than building a complex converter layer.
"""

import pandas as pd
import pytest

from flopy4.mf6.gwf import Chd, Wel


def parsed_to_dataframe(parsed: dict, component_type: type, dfn=None) -> pd.DataFrame:
    """
    Convert TypedTransformer period block output to DataFrame format.

    Parameters
    ----------
    parsed : dict
        Output from TypedTransformer with 'period N' keys
    component_type : type
        Component class (e.g., Chd, Wel) - used to determine field order
    dfn : Dfn, optional
        Definition file for field metadata

    Returns
    -------
    pd.DataFrame
        DataFrame ready for stress_period_data setter
    """
    # Find period blocks
    period_blocks = {k: v for k, v in parsed.items() if k.startswith("period ")}

    if not period_blocks:
        return pd.DataFrame()

    # Get period block field names from DFN or component
    # For now, hardcode based on component type (would use DFN in real implementation)
    if component_type.__name__ == "Wel":
        cellid_len = 3  # layer, row, col (structured)
        field_names = ["q"]
    elif component_type.__name__ == "Chd":
        cellid_len = 3
        field_names = ["head"]
    else:
        raise NotImplementedError(f"Component {component_type.__name__} not yet supported")

    # Build records
    records = []
    for period_key, period_data in period_blocks.items():
        # Extract period number (1-indexed in MF6, convert to 0-indexed for Python)
        kper = int(period_key.split()[1]) - 1

        if "stress_period_data" not in period_data:
            continue

        spd = period_data["stress_period_data"]

        # Each record is [cellid_components..., field_values...]
        for rec in spd:
            if not rec:
                continue

            # Split cellid and values
            cellid = rec[:cellid_len]
            values = rec[cellid_len:]

            # Build record dict
            record = {"kper": kper}

            # Add spatial coordinates
            if cellid_len == 3:
                record["layer"] = cellid[0]
                record["row"] = cellid[1]
                record["col"] = cellid[2]
            elif cellid_len == 1:
                record["node"] = cellid[0]

            # Add field values
            for i, field_name in enumerate(field_names):
                if i < len(values):
                    record[field_name] = values[i]

            records.append(record)

    return pd.DataFrame(records)


class TestParsedToDataFrame:
    """Test converting parsed data to DataFrame."""

    def test_wel_simple(self):
        """Test simple WEL conversion."""
        parsed = {
            "dimensions": {"maxbound": 2},
            "period 1": {"stress_period_data": [[2, 3, 4, -35000.0], [2, 8, 4, -35000.0]]},
        }

        df = parsed_to_dataframe(parsed, Wel)

        assert len(df) == 2
        assert list(df.columns) == ["kper", "layer", "row", "col", "q"]
        assert df.iloc[0]["kper"] == 0  # 0-indexed
        assert df.iloc[0]["layer"] == 2
        assert df.iloc[0]["row"] == 3
        assert df.iloc[0]["col"] == 4
        assert df.iloc[0]["q"] == -35000.0

    def test_wel_multiple_periods(self):
        """Test WEL with multiple stress periods."""
        parsed = {
            "period 1": {"stress_period_data": [[2, 3, 4, -35000.0]]},
            "period 2": {"stress_period_data": [[2, 3, 4, -30000.0], [2, 8, 4, -30000.0]]},
        }

        df = parsed_to_dataframe(parsed, Wel)

        assert len(df) == 3
        assert df[df["kper"] == 0].iloc[0]["q"] == -35000.0
        assert df[df["kper"] == 1].iloc[0]["q"] == -30000.0

    def test_chd_simple(self):
        """Test simple CHD conversion."""
        parsed = {"period 1": {"stress_period_data": [[0, 0, 0, 1.0], [0, 9, 9, 0.0]]}}

        df = parsed_to_dataframe(parsed, Chd)

        assert len(df) == 2
        assert list(df.columns) == ["kper", "layer", "row", "col", "head"]
        assert df.iloc[0]["head"] == 1.0
        assert df.iloc[1]["head"] == 0.0


class TestIntegrationWithSetter:
    """Test that converted DataFrame works with stress_period_data setter."""

    def test_wel_roundtrip(self):
        """Test WEL: parsed → DataFrame → setter → getter → DataFrame."""
        import numpy as np

        from flopy4.mf6.gwf import Dis, Gwf

        parsed = {"period 1": {"stress_period_data": [[2, 3, 4, -35000.0], [2, 8, 4, -30000.0]]}}

        # Convert to DataFrame
        df_input = parsed_to_dataframe(parsed, Wel)

        # Create parent model with dims (setter looks for parent.data.dims)
        dis = Dis(
            nlay=3, nrow=10, ncol=10, delr=1.0, delc=1.0, top=10.0, botm=np.array([5.0, 0.0, -5.0])
        )
        gwf = Gwf(dis=dis)

        # Create package attached to parent
        wel = Wel(parent=gwf)

        # Use setter
        wel.stress_period_data = df_input

        # Use getter
        df_output = wel.stress_period_data

        # Verify roundtrip
        assert len(df_output) == 2
        assert list(df_output.columns) == ["kper", "node", "q"]

        # Values should match (node computed from layer/row/col)
        # node = layer * nrow * ncol + row * ncol + col
        # node = 2 * 100 + 3 * 10 + 4 = 234
        assert df_output.iloc[0]["kper"] == 0
        assert df_output.iloc[0]["node"] == 234
        assert df_output.iloc[0]["q"] == -35000.0

    def test_chd_roundtrip(self):
        """Test CHD: parsed → DataFrame → setter → getter → DataFrame."""
        import numpy as np

        from flopy4.mf6.gwf import Dis, Gwf

        parsed = {"period 1": {"stress_period_data": [[0, 0, 0, 1.0], [0, 9, 9, 0.0]]}}

        df_input = parsed_to_dataframe(parsed, Chd)

        dis = Dis(nlay=1, nrow=10, ncol=10, delr=1.0, delc=1.0, top=1.0, botm=np.array([0.0]))
        gwf = Gwf(dis=dis)
        chd = Chd(parent=gwf)

        chd.stress_period_data = df_input

        df_output = chd.stress_period_data

        assert len(df_output) == 2
        assert df_output.iloc[0]["head"] == 1.0
        assert df_output.iloc[1]["head"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
