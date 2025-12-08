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

        Returns a DataFrame with columns: 'kper' (stress period), spatial
        coordinates, and all period data field values (e.g., 'head', 'elev', 'cond').

        Spatial coordinates are automatically determined based on grid type:
        - Structured grids: 'layer', 'row', 'col' columns
        - Unstructured grids: 'node' column

        Returns
        -------
        pd.DataFrame
            DataFrame with stress period data for all fields.

        Examples
        --------
        >>> # Structured grid - uses layer/row/col
        >>> chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0, (0, 9, 9): 0.0}})
        >>> df = chd.stress_period_data
        >>> print(df)
           kper  layer  row  col  head
        0     0      0    0    0   1.0
        1     0      0    9    9   0.0

        >>> # Multi-field package
        >>> drn = Drn(parent=gwf, elev={0: {(0, 7, 5): 10.0}}, cond={0: {(0, 7, 5): 1.0}})
        >>> df = drn.stress_period_data
        >>> print(df)
           kper  layer  row  col  elev  cond
        0     0      0    7    5  10.0   1.0

        Notes
        -----
        This property is read-only. Setting stress period data via the
        initializer or attribute assignment will be supported after PR #266.

        The coordinate format depends on grid information from the parent model:
        - If structured grid dimensions (nlay, nrow, ncol) are available from the
          parent, the DataFrame will use layer/row/col columns
        - Otherwise, it will use node indices
        """
        from attrs import fields

        # Find all period block fields
        period_fields = []
        for f in fields(self.__class__):  # type: ignore
            if f.metadata.get("block") == "period" and f.metadata.get("xattree", {}).get("dims"):
                period_fields.append(f.name)

        if not period_fields:
            raise TypeError("No period block fields found in package")

        # Determine spatial coordinate format based on available grid info
        # If parent has structured grid dims, use layer/row/col
        # Otherwise use node indices
        # TODO generalize this, maybe a `grid_type` property somewhere
        # like flopy3 has
        has_structured_grid = False
        nlay = nrow = ncol = None

        if hasattr(self, "parent") and self.parent is not None:
            # Try to get grid dimensions from parent model
            if (
                hasattr(self.parent, "nlay")
                and hasattr(self.parent, "nrow")
                and hasattr(self.parent, "ncol")
            ):
                nlay = self.parent.nlay
                nrow = self.parent.nrow
                ncol = self.parent.ncol
                has_structured_grid = True

        # Build combined DataFrame
        all_records = []
        coord_columns = None

        for field_name in period_fields:
            data = getattr(self, field_name)
            if data is None:
                continue

            # Convert field data to records
            for kper in range(data.shape[0]):
                per_data = data[kper]

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

                        # Convert to layer/row/col if structured grid info available
                        if has_structured_grid and nlay and nrow and ncol:
                            layer = node // (nrow * ncol)
                            row = (node % (nrow * ncol)) // ncol
                            col = node % ncol
                            record = {
                                "kper": kper,
                                "layer": int(layer),
                                "row": int(row),
                                "col": int(col),
                                field_name: val,
                            }
                            if coord_columns is None:
                                coord_columns = ["kper", "layer", "row", "col"]
                        else:
                            # Use node index if no structured grid info
                            record = {"kper": kper, "node": node, field_name: val}
                            if coord_columns is None:
                                coord_columns = ["kper", "node"]
                    elif len(indices) == 3:  # 3D array (layer, row, col)
                        layer, row, col = (
                            indices[0][i],
                            indices[1][i],
                            indices[2][i],
                        )
                        record = {
                            "kper": kper,
                            "layer": int(layer),
                            "row": int(row),
                            "col": int(col),
                            field_name: val,
                        }
                        if coord_columns is None:
                            coord_columns = ["kper", "layer", "row", "col"]
                    else:
                        continue
                    all_records.append(record)

        if not all_records:
            # Return empty DataFrame with appropriate columns
            cols = coord_columns or ["kper", "layer", "row", "col"]
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

    @stress_period_data.setter
    def stress_period_data(self, value: pd.DataFrame) -> None:
        """
        Set stress period data from a DataFrame.

        Parameters
        ----------
        value : pd.DataFrame
            DataFrame with columns: 'kper' (stress period), spatial coordinates
            (either 'layer'/'row'/'col' or 'node'), and field value columns.

        Examples
        --------
        >>> # Modify existing package data
        >>> chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0}})
        >>> df = chd.stress_period_data
        >>> df['head'] = df['head'] * 2  # Double all values
        >>> chd.stress_period_data = df  # Apply changes

        >>> # Create new data from scratch
        >>> df = pd.DataFrame({
        ...     'kper': [0, 0, 1],
        ...     'layer': [0, 0, 0],
        ...     'row': [0, 5, 0],
        ...     'col': [0, 5, 5],
        ...     'head': [10.0, 8.0, 9.0]
        ... })
        >>> chd.stress_period_data = df
        """
        import xarray as xr
        from xattree import get_xatspec

        from flopy4.mf6.converter.ingress.structure import structure_array

        if not isinstance(value, pd.DataFrame):
            raise TypeError(f"Expected DataFrame, got {type(value)}")

        # Get xattree field specifications
        spec = get_xatspec(type(self)).flat

        # Find all period block fields
        period_fields = []
        field_objects = {}
        for field_name, field_spec in spec.items():
            if field_spec.metadata.get("block") == "period" and hasattr(field_spec, "dims"):  # type: ignore
                period_fields.append(field_name)
                field_objects[field_name] = field_spec

        if not period_fields:
            raise TypeError("No period block fields found in package")

        # Check which fields are present in the DataFrame
        available_fields = [f for f in period_fields if f in value.columns]
        if not available_fields:
            raise ValueError(
                f"DataFrame must contain at least one period field column. "
                f"Expected one of {period_fields}, got {value.columns.tolist()}"
            )

        # Build dimension context for the converter
        # Priority: 1) parent model dims, 2) existing array data
        dim_dict = {}

        # 1. Get dims from parent if available (most common case)
        if hasattr(self, "parent") and self.parent is not None and hasattr(self.parent, "data"):
            dim_dict.update(dict(self.parent.data.dims))

        # 2. Extract dimensions from existing field data
        for field_name in period_fields:
            field_data = getattr(self, field_name, None)
            if field_data is not None and isinstance(field_data, xr.DataArray):
                # xarray stores dimension sizes
                dim_dict.update(dict(field_data.sizes))
                break  # One field is enough to get dimensions

        # 3. Check if DataFrame requires structured grid dims (nrow, ncol, nlay)
        #    but they're not available - provide helpful error
        has_structured_coords = all(col in value.columns for col in ["layer", "row", "col"])
        if has_structured_coords:
            missing_dims = [d for d in ["nrow", "ncol", "nlay"] if d not in dim_dict]
            if missing_dims:
                raise ValueError(
                    f"DataFrame has structured coordinates (layer/row/col) but package "
                    f"is missing required dimensions: {missing_dims}. "
                    f"Attach the package to a parent model with these dimensions, or use "
                    f"node-based coordinates in the DataFrame instead."
                )

        # Update each field present in the DataFrame
        # Pass dims explicitly to converter - no __dict__ manipulation needed
        for field_name in available_fields:
            field_obj = field_objects[field_name]

            # Call converter with explicit dims parameter
            converted_value = structure_array(
                value, self, field_obj, dims=dim_dict if dim_dict else None
            )

            # Set the attribute, which will trigger on_setattr hooks (e.g., update_maxbound)
            setattr(self, field_name, converted_value)
