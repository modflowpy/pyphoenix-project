from abc import ABC
from typing import Optional

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

    def to_dataframe(self, field_name: Optional[str] = None) -> pd.DataFrame:
        """
        Convert period data to pandas DataFrame.

        Parameters
        ----------
        field_name : str, optional
            Name of the period field to convert. If None, attempts
            to find the first period block field automatically.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns: 'per', 'layer', 'row', 'col',
            and field value column(s).

        Examples
        --------
        >>> chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0}})
        >>> df = chd.to_dataframe('head')
        >>> print(df)
           per  layer  row  col  head
        0    0      0    0    0   1.0
        """
        from attrs import fields

        # If no field name provided, find first period block field
        if field_name is None:
            for f in fields(self.__class__):
                if f.metadata and f.metadata.get("block") == "period":
                    if f.metadata.get("xattree", {}).get("dims"):
                        field_name = f.name
                        break

        if field_name is None:
            raise ValueError("No period block field found in package")

        # Get the field data
        data = getattr(self, field_name)
        if data is None:
            return pd.DataFrame()

        # Convert xarray to DataFrame
        records = []
        for per in range(data.shape[0]):
            per_data = data[per]
            # Find non-empty cells
            mask = per_data != FILL_DNODATA
            if isinstance(mask, np.ndarray):
                indices = np.where(mask)
                values = per_data[mask]

                for i in range(len(values)):
                    if len(indices) == 1:  # 1D array (nodes)
                        node = indices[0][i]
                        record = {"per": per, "node": node, field_name: values[i]}
                    elif len(indices) == 3:  # 3D array (layer, row, col)
                        layer, row, col = indices[0][i], indices[1][i], indices[2][i]
                        record = {
                            "per": per,
                            "layer": layer,
                            "row": row,
                            "col": col,
                            field_name: values[i],
                        }
                    else:
                        continue
                    records.append(record)

        return pd.DataFrame(records)

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, field_name: str, dims: dict, **kwargs
    ) -> "Package":
        """
        Create package from pandas DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with period data. Must contain 'per' column
            and spatial index columns ('layer', 'row', 'col' or 'node').
        field_name : str
            Name of the field column in the DataFrame.
        dims : dict
            Dictionary of dimension sizes (nper, nlay, nrow, ncol, nodes).
        **kwargs
            Additional package parameters.

        Returns
        -------
        Package
            Instantiated package.

        Examples
        --------
        >>> df = pd.DataFrame({
        ...     'per': [0, 0],
        ...     'layer': [0, 0],
        ...     'row': [0, 9],
        ...     'col': [0, 9],
        ...     'head': [1.0, 0.0]
        ... })
        >>> chd = Chd.from_dataframe(df, 'head', dims={'nper': 1, 'nodes': 100})
        """
        # Determine if structured or unstructured
        has_structured_coords = all(c in df.columns for c in ["layer", "row", "col"])
        has_node_coord = "node" in df.columns

        if not (has_structured_coords or has_node_coord):
            raise ValueError(
                "DataFrame must contain either (layer, row, col) or (node) columns"
            )

        # Create period data dict
        period_data = {}
        for per in df["per"].unique():
            per_df = df[df["per"] == per]
            period_data[int(per)] = {}

            for _, row in per_df.iterrows():
                if has_structured_coords:
                    cellid = (int(row["layer"]), int(row["row"]), int(row["col"]))
                else:
                    cellid = (int(row["node"]),)

                period_data[int(per)][cellid] = row[field_name]

        # Create kwargs with the period data
        package_kwargs = {field_name: period_data, "dims": dims}
        package_kwargs.update(kwargs)

        return cls(**package_kwargs)
