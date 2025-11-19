from abc import ABC

import numpy as np
import pandas as pd
from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import FILL_DNODATA


@xattree
class Package(Component, ABC):
    def default_filename(self) -> str:
        name = self.parent.name if self.parent else self.name  # type: ignore
        cls_name = self.__class__.__name__.lower()
        return f"{name}.{cls_name}"

    @property
    def stress_period_data(self) -> pd.DataFrame:
        """
        Get combined stress period data for all period data fields.

        Returns a DataFrame with columns: 'per', 'node', and all period
        data field values (e.g., 'head', 'elev', 'cond').

        Returns
        -------
        pd.DataFrame
            DataFrame with stress period data for all fields, using node indices
            as spatial coordinates.

        Examples
        --------
        >>> chd = Chd(dims=dims, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
        >>> df = chd.stress_period_data
        >>> print(df)
           per  node  head
        0    0     0   1.0
        1    0    99   0.0

        >>> drn = Drn(dims=dims, elev={0: {(0, 7, 5): 10.0}}, cond={0: {(0, 7, 5): 1.0}})
        >>> df = drn.stress_period_data
        >>> print(df)
           per  node  elev  cond
        0    0    75  10.0   1.0

        Notes
        -----
        This property is read-only. Setting stress period data via the
        initializer or attribute assignment will be supported after PR #266.

        The DataFrame uses node indices as spatial coordinates. To convert node
        indices to layer/row/col coordinates for structured grids, use::

            layer = node // (nrow * ncol)
            row = (node % (nrow * ncol)) // ncol
            col = node % ncol
        """
        from attrs import fields

        # Find all period block fields
        period_fields = []
        for f in fields(self.__class__):  # type: ignore
            if f.metadata and f.metadata.get("block") == "period":
                if f.metadata.get("xattree", {}).get("dims"):
                    period_fields.append(f.name)

        if not period_fields:
            raise ValueError("No period block fields found in package")

        # Build combined DataFrame
        all_records = []
        coord_columns = None

        for field_name in period_fields:
            data = getattr(self, field_name)
            if data is None:
                continue

            # Convert field data to records
            for per in range(data.shape[0]):
                per_data = data[per]

                # Handle sparse arrays
                try:
                    import sparse

                    if isinstance(per_data, sparse.COO):
                        # Convert to dense for processing
                        per_data = per_data.todense()
                except ImportError:
                    pass

                # Find non-empty cells
                # Handle different dtypes for the mask
                if np.issubdtype(per_data.dtype, np.str_) or np.issubdtype(
                    per_data.dtype, np.bytes_
                ):
                    # For string fields, check for non-empty and non-fill strings
                    mask = (per_data != "") & (per_data != str(FILL_DNODATA))
                else:
                    # For numeric fields, use standard FILL_DNODATA
                    mask = per_data != FILL_DNODATA

                indices = np.where(mask)

                if len(indices) == 0 or indices[0].size == 0:
                    continue

                values = per_data[mask]

                for i in range(len(values)):
                    # Extract scalar value from xarray if needed
                    val = values[i]
                    if hasattr(val, "item"):
                        val = val.item()

                    if len(indices) == 1:  # 1D array (nodes)
                        node = int(indices[0][i])
                        record = {"per": per, "node": node, field_name: val}
                        if coord_columns is None:
                            coord_columns = ["per", "node"]
                    elif len(indices) == 3:  # 3D array (layer, row, col)
                        layer, row, col = (
                            indices[0][i],
                            indices[1][i],
                            indices[2][i],
                        )
                        record = {
                            "per": per,
                            "layer": int(layer),
                            "row": int(row),
                            "col": int(col),
                            field_name: val,
                        }
                        if coord_columns is None:
                            coord_columns = ["per", "layer", "row", "col"]
                    else:
                        continue
                    all_records.append(record)

        if not all_records:
            # Return empty DataFrame with appropriate columns
            cols = coord_columns or ["per", "layer", "row", "col"]
            cols.extend(period_fields)
            return pd.DataFrame(columns=cols)

        # Create DataFrame from records
        df = pd.DataFrame(all_records)

        # For multi-field packages, merge fields with same coordinates
        # Single-field packages can skip the groupby for better performance
        if len(period_fields) > 1 and coord_columns:
            # Fill NaN for fields that don't have data at certain coordinates
            df = df.groupby(coord_columns, as_index=False).first()

        return df
