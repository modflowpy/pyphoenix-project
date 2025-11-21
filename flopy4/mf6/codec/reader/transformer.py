from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import xarray as xr
from lark import Token, Transformer

if TYPE_CHECKING:
    from flopy4.mf6.component import Component


def _parse_number(value: str) -> int | float:
    """Parse a string into int or float based on its content."""
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        else:
            return int(value)
    except ValueError:
        return float(value)


class BasicTransformer(Transformer):
    """
    Basic transformer for MF6 input files. Works only with the basic
    grammar. Yields blocks simply as collections of lines of tokens.
    """

    def __getattr__(self, name):
        """Handle typed__ prefixed methods by delegating to the unprefixed version."""
        if name.startswith("typed__"):
            unprefixed = name[7:]  # Remove "typed__" prefix
            if hasattr(self, unprefixed):
                return getattr(self, unprefixed)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def start(self, items: list[Any]) -> dict[str, Any]:
        blocks = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            block_name = next(iter(item.keys()))
            blocks[block_name] = next(iter(item.values()))
        return blocks

    def block(self, items: list[Any]) -> dict[str, Any]:
        """
        Transform a block using pattern-based detection and structuring.

        Items structure: [block_name, ...lines..., block_name]
        Returns: {block_name: structured_data}

        Two block types:
        - List blocks (recarrays) → list of records
        - Dict blocks (keywords, arrays, dimensions) → dict with field names
        """
        block_name = items[0]
        lines = items[1 : (len(items) - 1)]

        # Empty block
        if not lines:
            return {block_name: {}}

        # Pattern-based detection and structuring
        if self._looks_like_list_block(lines):
            # List blocks (recarrays): vertices, cell2d, period data
            return {block_name: lines}
        else:
            # Dict blocks (keywords, arrays, dimensions): have field names
            return {block_name: self._structure_dict_block(lines)}

    def block_name(self, items: list[Any]) -> str:
        return " ".join([str(item) for item in items if item is not None])

    def _list(self, items: list[Any]) -> list[Any]:
        return items[0] if items else []

    def line(self, items: list[Any]) -> list[Any]:
        return items[1:]

    def item(self, items: list[Any]) -> str | float | int:
        return items[0]

    def word(self, items: list[Token]) -> str:
        return str(items[0])

    def NUMBER(self, token: Token) -> int | float:
        return _parse_number(str(token))

    def CNAME(self, token: Token) -> str:
        return str(token)

    def INT(self, token: Token) -> int:
        return int(token)

    def token(self, items: list[Any]) -> Any:
        """
        Handle generic token items. Extracts the actual value from token items.

        Args:
            items: List of token values

        Returns:
            The first item's value, or the item itself if not a token
        """
        if not items:
            return None
        item = items[0]
        # If item is a Token, extract its value
        if isinstance(item, Token):
            # Try to parse as number if applicable
            if item.type in ("NUMBER", "INT"):
                return _parse_number(str(item))
            return str(item)
        return item

    @staticmethod
    def _looks_like_list_block(lines: list[list]) -> bool:
        """
        Detect list blocks (recarrays with no field names).

        List blocks have:
        - Uniform row length
        - No string field names (rows start with numeric IDs)

        Examples:
            [[1, 1, 1, 7.5], [1, 2, 1, 7.5], ...]  # CHD period data
            [[1, 135.0, 0.0], [2, 135.0, 15.0], ...]  # DISV vertices
        """
        if not lines:
            return False

        # All rows must be lists/tuples
        if not all(isinstance(row, (list, tuple)) for row in lines):
            return False

        # Check for uniform row length
        row_lengths = [len(row) for row in lines]
        if len(set(row_lengths)) > 1:
            return False  # Variable length suggests dict block

        # List blocks have NO string field names - rows start with numeric IDs
        for row in lines:
            if row and isinstance(row[0], str):
                return False  # Has field names - it's a dict block

        return True

    @staticmethod
    def _structure_dict_block(lines: list[list]) -> dict[str, Any]:
        """
        Structure dict block data - handles both keywords and arrays.

        Dict blocks have field names as first element:
        - Keywords: [['LENGTH_UNITS', 'meters'], ['NOGRB']]
        - Arrays: [['top'], ['CONSTANT', 100.0], ['botm'], ['CONSTANT', 95.0]]
        - Dimensions: [['nlay', 1], ['nrow', 2], ['ncol', 2]]

        Returns dict with field names as keys.
        """
        result: dict[str, Any] = {}
        current_array = None
        array_data: list[list] = []

        for row in lines:
            if not row:
                continue

            # Array name: single lowercase element
            # These are followed by control/data lines
            if len(row) == 1 and isinstance(row[0], str) and row[0].islower():
                # Save previous array if exists
                if current_array:
                    result[current_array] = BasicTransformer._parse_array_control(array_data)
                # Start new array
                current_array = row[0]
                array_data = []

            # Array control/data line (for current array)
            elif current_array:
                array_data.append(row)

            # Regular field assignment
            elif isinstance(row[0], str):
                key = row[0].lower()

                # FILEOUT/FILEIN qualifier
                if (
                    len(row) >= 3
                    and isinstance(row[1], str)
                    and row[1].upper() in ("FILEOUT", "FILEIN")
                ):
                    result[key] = (row[1].upper(), row[2])
                # Single keyword (flag)
                elif len(row) == 1:
                    result[key] = True
                # Single value
                elif len(row) == 2:
                    result[key] = row[1]
                # Multiple values
                else:
                    result[key] = tuple(row[1:])

        # Save final array if exists
        if current_array:
            result[current_array] = BasicTransformer._parse_array_control(array_data)

        return result

    @staticmethod
    def _parse_array_control(lines: list[list]) -> xr.DataArray | list:
        """
        Parse array control lines and create xr.DataArray.

        Handles:
        - CONSTANT value → scalar DataArray with control metadata
        - INTERNAL [FACTOR f] [IPRN i] → DataArray with data and control metadata
        - Other formats → return raw list for downstream handling

        This mimics what TypedTransformer does with its constant/internal/external methods.
        """
        if not lines:
            return xr.DataArray(np.nan)

        # Get control line (first line)
        control_line = lines[0]
        if not control_line or not isinstance(control_line[0], str):
            # Not a control line - just return lines as-is
            # Converter will handle raw data
            return lines

        control_type = control_line[0].upper()

        if control_type == "CONSTANT":
            # CONSTANT value
            value = control_line[1] if len(control_line) > 1 else np.nan
            return xr.DataArray(
                data=value, attrs={"control_type": "constant", "control_value": value}
            )

        elif control_type == "INTERNAL":
            # INTERNAL [FACTOR f] [IPRN i] + optional data lines
            attrs = {"control_type": "internal"}

            # Parse optional FACTOR and IPRN
            i = 1
            while i < len(control_line):
                # Make sure we're dealing with strings before calling .upper()
                if (
                    isinstance(control_line[i], str)
                    and control_line[i].upper() == "FACTOR"
                    and i + 1 < len(control_line)
                ):
                    attrs["control_factor"] = control_line[i + 1]
                    i += 2
                elif (
                    isinstance(control_line[i], str)
                    and control_line[i].upper() == "IPRN"
                    and i + 1 < len(control_line)
                ):
                    attrs["control_iprn"] = control_line[i + 1]
                    i += 2
                else:
                    i += 1

            # If there are data lines, convert to array
            if len(lines) > 1:
                data_lines = lines[1:]
                data = np.array(data_lines)
                return xr.DataArray(data=data, attrs=attrs)
            else:
                # No data yet (will be filled later)
                return xr.DataArray(data=np.nan, attrs=attrs)

        else:
            # Unknown control type - return raw lines
            # This handles OPEN/CLOSE, external files, etc.
            return lines


class TypedTransformer(Transformer):
    """Type-aware transformer for MF6 input files using attrs specifications."""

    def __init__(self, visit_tokens=False, component_type: type["Component"] | None = None):
        super().__init__(visit_tokens)
        from flopy4.mf6.spec import blocks_dict, fields_dict

        self.component_type: type["Component"] | None
        self.blocks: dict[str, dict[str, Any]] | None
        self.fields: dict[str, Any] | None

        if component_type is not None:
            self.component_type = component_type
            self.blocks = blocks_dict(component_type)
            self.fields = fields_dict(component_type)
        else:
            self.component_type = None
            self.blocks = None
            self.fields = None

        self._flat_fields = self._flatten_fields(self.fields) if self.fields else None
        self._field_dims = self._extract_field_dims(self._flat_fields) if self._flat_fields else {}

    def __getattr__(self, name):
        """Handle typed__ prefixed methods by delegating to the unprefixed version."""
        if name.startswith("typed__"):
            unprefixed = name[7:]  # Remove "typed__" prefix
            if hasattr(self, unprefixed):
                return getattr(self, unprefixed)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def token(self, items: list[Any]) -> Any:
        """
        Handle generic token items. Extracts the actual value from token items.

        Args:
            items: List of token values

        Returns:
            The first item's value, or the item itself if not a token
        """
        if not items:
            return None
        item = items[0]
        # If item is a Token, extract its value
        if isinstance(item, Token):
            # Try to parse as number if applicable
            if item.type in ("NUMBER", "INT"):
                return _parse_number(str(item))
            return str(item)
        return item

    def _get_record_columns(self, block_name: str):
        """
        Get column names for a structured list record in the given block.

        Returns a list of ColumnInfo objects in order, or None if not available.
        Column info is derived from the generated grammar files at import time.
        """
        from flopy4.mf6.codec.reader.grammar.columns import get_record_columns

        return get_record_columns(block_name)

    def _flatten_fields(self, fields: dict) -> dict:
        """Recursively flatten fields dict to include children of records and unions."""
        from inspect import isclass

        from flopy4.mf6.spec import fields_dict as get_fields_dict
        from flopy4.mf6.spec import get_field_type

        flat = dict(fields)
        for field in fields.values():
            field_type = get_field_type(field)
            if field_type in ("record", "list"):
                try:
                    if field.type and isclass(field.type):
                        children = get_fields_dict(field.type)
                        if children:
                            for child_name, child_field in children.items():
                                flat[child_name] = child_field
                                child_field_type = get_field_type(child_field)
                                if child_field_type in ("record", "list"):
                                    try:
                                        if child_field.type and isclass(child_field.type):
                                            nested_children = get_fields_dict(child_field.type)
                                            if nested_children:
                                                nested_flat = self._flatten_fields(nested_children)
                                                flat.update(nested_flat)
                                    except (ValueError, AttributeError, TypeError):
                                        pass
                except (ValueError, AttributeError, TypeError):
                    pass
        return flat

    def _extract_field_dims(self, fields: dict) -> dict[str, list[str]]:
        """Extract dimension names from array fields for quick lookup."""
        if not self.component_type:
            return {}

        from xattree import get_xatspec

        result = {}
        try:
            spec = get_xatspec(self.component_type).flat
            for field_name, field in spec.items():
                if hasattr(field, "dims") and field.dims:
                    result[field_name] = list(field.dims)
        except (AttributeError, ValueError, TypeError):
            # If xatspec isn't available, fall back to empty dict
            pass
        return result

    def start(self, items: list[Any]) -> dict | Any:
        """
        Collect and merge blocks, handling indexed blocks specially.

        For simple cases (e.g., "start: array"), returns the item directly.
        For full component files with blocks, returns a dict of blocks.
        """
        merged = {}
        period_blocks = {}

        for item in items:
            if not isinstance(item, dict):
                if len(items) == 1:
                    return item
                continue

            for block_name, block_data in item.items():
                if isinstance(block_data, dict) and all(
                    isinstance(k, int) for k in block_data.keys()
                ):
                    if block_name == "period":
                        period_blocks.update(block_data)
                    else:
                        for index, data in block_data.items():
                            indexed_key = f"{block_name} {index}"
                            merged[indexed_key] = data
                elif block_name not in merged:
                    merged[block_name] = block_data

        # Keep period blocks as indexed keys for now
        # Dataset conversion happens in converter layer
        for index, data in period_blocks.items():
            indexed_key = f"period {index}"
            merged[indexed_key] = data

        return merged

    def block(self, items: list[Any]) -> dict:
        return items[0]

    def array(self, items: list[Any]) -> xr.DataArray:
        """Handle array field - single or layered."""
        arrs = items[0]
        if isinstance(arrs, list):
            controls = []
            data_arrays = []
            for arr in arrs:
                if isinstance(arr, xr.DataArray):
                    data_arrays.append(arr)
                    control = {
                        k.replace("control_", ""): v
                        for k, v in arr.attrs.items()
                        if k.startswith("control_")
                    }
                    controls.append(control)

            if data_arrays:
                result = xr.concat(data_arrays, dim="layer")
                result.attrs["controls"] = controls
                return result
        return arrs

    def single_array(self, items: list[Any]) -> xr.DataArray:
        """Handle single array (not layered)."""
        netcdf = items[0]
        arr = items[-1]
        result = TypedTransformer.try_create_dataarray(arr)
        if netcdf:
            result.attrs["netcdf"] = True
        return result

    def layered_array(self, items: list[Any]) -> list[xr.DataArray]:
        """Handle layered array - returns list of DataArrays (one per layer)."""
        netcdf = items[0]
        layers = []
        for arr in items[2:]:
            if arr is None:
                continue
            result = TypedTransformer.try_create_dataarray(arr)
            if netcdf:
                result.attrs["netcdf"] = True
            layers.append(result)
        return layers

    def readarray(self, items: list[Any]) -> dict[str, Any]:
        control = items[0]
        data = items[1] if len(items) > 1 else None
        if (value := control.get("value", None)) is not None:
            data = value
        return {"control": control, "data": data}

    def control(self, items: list[Any]) -> dict[str, Any]:
        return items[0]

    def constant(self, items: list[Any]) -> dict[str, Any]:
        return {"type": "constant", "value": items[0]}

    def internal(self, items: list[Any]) -> dict[str, Any]:
        result = {"type": "internal"}
        for item in items:
            if item is not None:
                result.update(item)
        return result

    def external(self, items: list[Any]) -> dict[str, Any]:
        result = {"type": "external", "value": items[0]}
        for item in items[1:]:
            if item is not None:
                result.update(item)
        return result

    def factor(self, items: list[Any]) -> dict[str, float]:
        return {"factor": items[0]}

    def iprn(self, items: list[Any]) -> dict[str, int]:
        return {"iprn": items[0]}

    def binary(self, _) -> dict[str, bool]:
        return {"binary": True}

    def filename(self, items: list[Any]) -> Path:
        return Path(items[0].strip("\"'"))

    def string(self, items: list[Any]) -> str:
        value = items[0]
        if hasattr(value, "strip"):
            return value.strip("\"'")
        return str(value.children[0]) if hasattr(value, "children") else str(value)

    def simple_string(self, items: list[Any]) -> str:
        """Handle simple string (unquoted word or escaped string)."""
        return str(items[0]).strip("\"'")

    def word(self, items: list[Token]) -> str:
        """Handle word token."""
        return str(items[0])

    def integer(self, items: list[Any]) -> int:
        return int(items[0])

    def double(self, items: list[Any]) -> float:
        return float(items[0])

    def number(self, items: list[Any]) -> int | float:
        """Handle generic number (could be int or float)."""
        return _parse_number(str(items[0]))

    def data(self, items: list[Any]) -> np.ndarray:
        return np.array(items)

    def netcdf(self, _) -> dict[str, bool]:
        return {"netcdf": True}

    def block_index(self, items: list[Any]) -> int:
        """Extract block index (e.g., period number)."""
        return items[0]

    def stress_period_data(self, items: list[Any]) -> list[Any]:
        """Handle stress period data records."""
        return items

    def record(self, items: list[Any]) -> list[Any]:
        """Handle a single stress period data record."""
        values = []
        for item in items:
            if self._is_newline_token(item):
                continue
            if hasattr(item, "children") and len(item.children) > 0:
                token_child = item.children[0]
                if hasattr(token_child, "children") and len(token_child.children) > 0:
                    values.append(token_child.children[0])
                else:
                    values.append(token_child)
            else:
                values.append(item)
        return values

    def list(self, items: list[Any]) -> list[Any]:
        """Handle list content (zero or more records)."""
        # items are the transformed records from the list rule
        return items

    @staticmethod
    def _is_newline_token(item: Any) -> bool:
        """Check if an item is a NEWLINE token."""
        return isinstance(item, Token) and item.type == "NEWLINE"

    @staticmethod
    def try_create_dataarray(array_info: dict) -> xr.DataArray:
        """Create xarray DataArray with control metadata in attrs."""
        control = array_info["control"]
        attrs = {f"control_{k}": v for k, v in control.items()}

        match control["type"]:
            case "constant":
                return xr.DataArray(data=control["value"], attrs=attrs)
            case "internal":
                return xr.DataArray(data=array_info["data"], attrs=attrs)
            case "external":
                path = array_info["data"]
                attrs["external_path"] = str(path)
                return xr.DataArray(data=np.nan, attrs=attrs)
            case _:
                raise ValueError(f"Unknown array type: {control['type']}")

    def __default__(self, data, children, meta):
        from flopy4.mf6.spec import fields_dict as get_fields_dict
        from flopy4.mf6.spec import get_field_type

        # Reconstruct DataArrays with proper dimension names if this is a field with dims
        if self._field_dims and data in self._field_dims:
            expected_dims = self._field_dims[data]
            for i, child in enumerate(children):
                if isinstance(child, xr.DataArray):
                    # Skip reconstruction for scalar/0-D arrays (e.g., CONSTANT arrays)
                    # These will be broadcast during structuring
                    if child.ndim == 0:
                        continue

                    # For layered arrays, only use as many dims as the array has
                    # (e.g., botm comes in as (nlay,) but will be broadcast to (nlay, nrow, ncol))
                    dims_to_use = expected_dims[: child.ndim]

                    # Reconstruct with proper dims
                    children[i] = xr.DataArray(data=child.data, dims=dims_to_use, attrs=child.attrs)
                    break

        # Handle structured list record rules (e.g., models_record, exchanges_record)
        # These are generated from DFN list fields with column definitions
        # Column names come from the grammar via _get_record_columns
        if data.endswith("_record"):
            block_name = data[:-7]  # e.g., "models_record" -> "models"
            columns = self._get_record_columns(block_name)
            # Extract values from (name, value) tuples, filter out newlines
            values = []
            for c in children:
                if isinstance(c, tuple) and len(c) == 2:
                    values.append(c[1])  # Extract value from (name, value)
                elif isinstance(c, str) and c.strip() == "":
                    continue  # Skip newlines
                elif isinstance(c, (str, int, float)):
                    values.append(c)  # Raw value (shouldn't happen but handle it)

            if columns:
                # Check if last column is variadic (accepts multiple values)
                has_variadic = columns[-1].variadic if columns else False

                if has_variadic and len(values) >= len(columns):
                    # Fixed columns get single values, variadic column gets the rest
                    result = {}
                    for i, col in enumerate(columns[:-1]):
                        result[col.name] = values[i]
                    # Last column gets remaining values as a list
                    result[columns[-1].name] = values[len(columns) - 1 :]
                    return result
                elif len(columns) == len(values):
                    # Exact match - simple dict mapping
                    return {col.name: val for col, val in zip(columns, values)}

            # Fallback: return as list if column info unavailable or count mismatch
            return values

        # Handle simple scalar rules (single child that's a primitive value)
        # Returns (rule_name, value) tuple for _fields to collect as named fields
        # For column rules in records, _record will extract just the values
        if children and len(children) == 1:
            child = children[0]
            if isinstance(child, (str, int, float)):
                return (data, child)

        # Handle keyword rules (no children) - return (name, True)
        # But not for _fields rules which may legitimately be empty
        if not children and not data.endswith("_fields"):
            return (data, True)

        # Handle block rules (e.g., options_block, dimensions_block)
        # This works without spec - just wraps fields in a dict
        if data.endswith("_block"):
            block_name = data[:-6]
            if len(children) == 3 and isinstance(children[0], int) and isinstance(children[2], int):
                # Indexed block: [index, fields, index]
                return {block_name: {children[0]: children[1]}}
            elif len(children) == 1:
                # Non-indexed block: [fields]
                return {block_name: children[0]}
            return super().__default__(data, children, meta)

        # Handle fields rules - this works without spec for basic record collection
        if data.endswith("_fields"):
            block_name = data[:-7]

            # Separate records (dicts or lists) from named field tuples
            records = []
            field_tuples = []
            for item in children:
                if isinstance(item, dict):
                    records.append(item)
                elif isinstance(item, list):
                    records.append(item)
                elif isinstance(item, tuple):
                    field_tuples.append(item)

            # For binding blocks (models, exchanges, solutiongroup), always return
            # a list (possibly empty). The _block handler will wrap it as
            # {block_name: list}, which is what the converter expects.
            # Note: solutiongroup has mxiter, but we ignore it here since the
            # Simulation class doesn't have a place for it yet.
            if block_name in ("models", "exchanges", "solutiongroup"):
                return records

            # For other blocks with only records (no scalar fields), return list
            if records and not field_tuples:
                return records

            # Build result dict from scalar fields
            result = {}
            for item in field_tuples:
                field_name = item[0].lower() if isinstance(item[0], str) else str(item[0]).lower()
                field_value = item[1]
                if field_name in result:
                    if not isinstance(result[field_name], list):
                        result[field_name] = [result[field_name]]
                    result[field_name].append(field_value)
                else:
                    result[field_name] = field_value

            # Add records if present (mixed block with both scalars and records)
            if records:
                result["stress_period_data"] = records

            return result

        # Spec-dependent handling below
        if self.blocks is None or self._flat_fields is None:
            return super().__default__(data, children, meta)

        # Handle union alternatives (e.g., ocsetting_all)
        if "_" in data:
            parts = data.rsplit("_", 1)
            if len(parts) == 2:
                field_name, alternative_name = parts
                parent_field = self._flat_fields.get(field_name)
                if parent_field is not None and get_field_type(parent_field) == "union":
                    try:
                        field_children = get_fields_dict(parent_field.type)
                        if field_children and alternative_name in field_children:
                            alt_field = field_children[alternative_name]
                            if get_field_type(alt_field) == "keyword":
                                return alternative_name
                            return children[0] if len(children) == 1 else children
                    except (ValueError, AttributeError):
                        pass

        # Handle individual fields
        field = self._flat_fields.get(data)
        if field is None and "-" in data:
            field = self._flat_fields.get(data.replace("_", "-"))
        # Handle version suffix (e.g., tdis6 -> tdis, gwf6 -> gwf)
        if field is None and data.endswith("6"):
            stripped = data[:-1]  # Remove "6" suffix
            field = self._flat_fields.get(stripped)
            if field is not None:
                data = stripped
        # TODO: Remove this workaround once DFN spec files are updated to remove
        # "record" suffix from variable names (e.g., budget_filerecord → budget_file)
        if field is None and data.endswith("record"):
            # Try stripping "record" suffix (e.g., "budget_filerecord" → "budget_file")
            stripped = data[:-6]  # Remove "record"
            field = self._flat_fields.get(stripped)
            if field is None and stripped.endswith("file"):
                # Also try without "file" for cases like "budgetfile" → "budget"
                field = self._flat_fields.get(stripped[:-4])
            if field is not None:
                data = stripped  # Use the stripped name for the return value

        if field is not None:
            field_type = get_field_type(field)

            if field_type == "keyword":
                return data, True

            if field_type == "record":
                try:
                    field_children = get_fields_dict(field.type)
                    if field_children:
                        record_dict = {}
                        non_keyword_children = [
                            (name, child)
                            for name, child in field_children.items()
                            if get_field_type(child) != "keyword"
                        ]
                        for i, (child_name, _) in enumerate(non_keyword_children):
                            if i < len(children):
                                if isinstance(children[i], tuple) and children[i][0] == child_name:
                                    record_dict[child_name] = children[i][1]
                                else:
                                    record_dict[child_name] = children[i]
                        return data, record_dict
                except (ValueError, AttributeError):
                    pass

            if field_type == "union":
                return data, children[0] if len(children) == 1 else children

            # Default: return as tuple
            return data, children[0] if len(children) == 1 else children

        # Generic handlers for grammar-spec mismatches
        # These handle rules that exist in grammar but not in spec

        # GENERIC HANDLER 1: Unwrap grammar-only wrapper rules
        # If rule isn't in spec and has exactly one child, unwrap it (passthrough)
        # Example: ocsetting wraps ocsetting_all, should just return the child
        if self._flat_fields and data not in self._flat_fields:
            if len(children) == 1:
                return children[0]

        # GENERIC HANDLER 2: Record pattern - {prefix}record + keyword → {prefix}_{keyword}
        # Handles saverecord/printrecord and similar patterns across all packages
        # Example: saverecord with children ['HEAD', 'ALL'] → ('save_head', 'ALL')
        if data.endswith("record") and self._flat_fields and data not in self._flat_fields:
            if children and isinstance(children[0], str):
                prefix = data[:-6]  # Remove "record" suffix
                keyword = children[0].lower().replace("-", "_")
                field_name = f"{prefix}_{keyword}"

                if field_name in self._flat_fields:
                    # Extract value from remaining children
                    if len(children) == 2:
                        value = children[1]
                    elif len(children) > 2:
                        value = children[1:]
                    else:
                        value = True

                    return (field_name, value)

        return super().__default__(data, children, meta)
