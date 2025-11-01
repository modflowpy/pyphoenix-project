from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from lark import Token, Transformer
from modflow_devtools.dfn import Dfn


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

    def start(self, items: list[Any]) -> dict[str, Any]:
        blocks = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            block_name = next(iter(item.keys()))
            blocks[block_name] = next(iter(item.values()))
        return blocks

    def block(self, items: list[Any]) -> dict[str, Any]:
        return {items[0]: items[1 : (len(items) - 1)]}

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


class TypedTransformer(Transformer):
    """Type-aware transformer for MF6 input files."""

    def __init__(self, visit_tokens=False, dfn: Dfn = None):
        super().__init__(visit_tokens)
        self.dfn = dfn
        self.blocks = dfn.blocks if dfn else None
        self.fields = dfn.fields if dfn else None
        # Create a flattened fields dict that includes nested fields
        self._flat_fields = self._flatten_fields(self.fields) if self.fields else None

    def _flatten_fields(self, fields: dict) -> dict:
        """Recursively flatten fields dict to include children of records and unions."""
        flat = dict(fields)  # Start with top-level fields
        for field in fields.values():
            if hasattr(field, "children") and field.children:
                # Add children fields
                for child_name, child_field in field.children.items():
                    flat[child_name] = child_field
                    # Recursively flatten nested children
                    if hasattr(child_field, "children") and child_field.children:
                        nested_flat = self._flatten_fields(child_field.children)
                        flat.update(nested_flat)
        return flat

    def start(self, items: list[Any]) -> dict:
        """Collect and merge blocks, handling indexed blocks specially."""
        merged = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            for block_name, block_data in item.items():
                # Check if this is an indexed block (dict with integer keys)
                if isinstance(block_data, dict) and all(
                    isinstance(k, int) for k in block_data.keys()
                ):
                    # Flatten indexed blocks into separate keys like "period 1", "period 2"
                    for index, data in block_data.items():
                        indexed_key = f"{block_name} {index}"
                        merged[indexed_key] = data
                elif block_name not in merged:
                    merged[block_name] = block_data
                else:
                    # This shouldn't happen for well-formed input
                    pass
        return merged

    def block(self, items: list[Any]) -> dict:
        return items[0]

    def array(self, items: list[Any]) -> dict:
        arrs = items[0]
        if isinstance(arrs, list):
            data = xr.concat([arr["data"] for arr in arrs if "data" in arr], dim="layer")
            return {
                "control": [arr["control"] for arr in arrs if "control" in arr],
                "data": data,
                "attrs": {k: v for k, v in arrs[0].items() if k not in ["data"]},
                "dims": {"layer": len(arrs)},
            }
        return arrs

    def single_array(self, items: list[Any]) -> dict:
        netcdf = items[0]
        arr = items[-1]
        if netcdf:
            arr["netcdf"] = netcdf
        return TypedTransformer.try_create_dataarray(arr)

    def layered_array(self, items: list[Any]) -> list[dict]:
        netcdf = items[0]
        layers = []
        for arr in items[2:]:
            if arr is None:
                continue
            if netcdf:
                arr["netcdf"] = netcdf
            layers.append(TypedTransformer.try_create_dataarray(arr))
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
        return items[0].strip("\"'")

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
        """Handle stress period data - now a list of stress_record trees.

        Each item is a stress_record tree that has already been processed by stress_record method.
        Return the list of processed records directly.
        """
        return items  # items are already processed stress records (lists of values)

    def record(self, items: list[Any]) -> list[Any]:
        """Handle a single stress period data record.

        The parser gives us stress_token trees plus a NEWLINE token.
        Extract values from stress_token trees and filter out the NEWLINE token.
        """
        values = []
        for item in items:
            if self._is_newline_token(item):
                continue
            # Item is a stress_token tree - extract its value
            if hasattr(item, "children") and len(item.children) > 0:
                # stress_token contains either a number tree or a _stress_word
                token_child = item.children[0]
                if hasattr(token_child, "children") and len(token_child.children) > 0:
                    # This is a number tree, get the actual value
                    values.append(token_child.children[0])
                else:
                    # This is a direct value (string)
                    values.append(token_child)
            else:
                values.append(item)
        return values

    @staticmethod
    def _is_newline_token(item: Any) -> bool:
        """Check if an item is a NEWLINE token."""
        return isinstance(item, Token) and item.type == "NEWLINE"

    @staticmethod
    def try_create_dataarray(array_info: dict) -> dict:
        control = array_info["control"]
        match control["type"]:
            case "constant":
                array_info["data"] = xr.DataArray(data=control["value"])
            case "internal":
                array_info["data"] = xr.DataArray(data=array_info["data"])
            case "external":
                pass
        return array_info

    def __default__(self, data, children, meta):
        if self.blocks is None or self._flat_fields is None:
            return super().__default__(data, children, meta)
        if data.endswith("_block") and (block_name := data[:-6]) in self.blocks:
            # See if this is an indexed block (period blocks have 3 children: index, fields, index
            if len(children) == 3 and isinstance(children[0], int) and isinstance(children[2], int):
                # Indexed block: [index, fields, index]
                block_index = children[0]
                fields_data = children[1]
                return {block_name: {block_index: fields_data}}
            elif len(children) == 1:
                # Non-indexed block: [fields]
                return {block_name: children[0]}
            else:
                # Unexpected structure, fall back to default
                return super().__default__(data, children, meta)
        elif data.endswith("_fields"):
            # Check if this is a period_fields which contains list data (stress_period_data)
            # rather than named field tuples
            if children and not isinstance(children[0], tuple):
                # This is list data (e.g., stress_period_data records)
                # With the new stress_record approach, we get a list containing
                # the stress_period_data result. If there's exactly one child and
                # it's a list, unwrap it
                if len(children) == 1 and isinstance(children[0], list):
                    return {"stress_period_data": children[0]}
                else:
                    # Fallback to original behavior
                    return {"stress_period_data": children}
            # Group fields by name to handle repeated fields
            fields_dict = {}
            for item in children:
                if isinstance(item, tuple):
                    field_name = item[0].lower()
                    field_value = item[1]
                    if field_name in fields_dict:
                        # Multiple occurrences - convert to list or append
                        if not isinstance(fields_dict[field_name], list):
                            fields_dict[field_name] = [fields_dict[field_name]]
                        fields_dict[field_name].append(field_value)
                    else:
                        fields_dict[field_name] = field_value
            return fields_dict
        elif "_" in data and (parts := data.rsplit("_", 1)) and len(parts) == 2:
            # Check if this is a union alternative (e.g., ocsetting_all)
            field_name, alternative_name = parts
            if (parent_field := self._flat_fields.get(field_name, None)) is not None:
                if (
                    parent_field.type == "union"
                    and hasattr(parent_field, "children")
                    and parent_field.children
                    and alternative_name in parent_field.children
                ):
                    # This is a union alternative
                    alt_field = parent_field.children[alternative_name]
                    if alt_field.type == "keyword":
                        # Keyword alternatives return just the alternative name
                        return alternative_name
                    else:
                        # Non-keyword alternatives return the transformed children
                        return children[0] if len(children) == 1 else children
        if (field := self._flat_fields.get(data, None)) is not None:
            if field.type == "keyword":
                return data, True
            elif field.type == "record" and hasattr(field, "children") and field.children:
                # Transform record fields into dicts with child field names as keys
                # Keyword children are literals in the grammar and don't appear in children list
                # Only non-keyword children appear in the children list
                record_dict = {}
                non_keyword_children = [
                    (name, child)
                    for name, child in field.children.items()
                    if child.type != "keyword"
                ]
                for i, (child_name, child_field) in enumerate(non_keyword_children):
                    if i < len(children):
                        # Handle tuples from transformed fields
                        if isinstance(children[i], tuple) and children[i][0] == child_name:
                            record_dict[child_name] = children[i][1]
                        else:
                            record_dict[child_name] = children[i]
                return data, record_dict
            elif field.type == "union" and hasattr(field, "children") and field.children:
                # For union fields, return the transformed child
                # The parser will have selected one alternative
                return data, children[0] if len(children) == 1 else children
            else:
                # For all fields, return the transformed children
                # (arrays have already been transformed by the array method)
                return data, children[0] if len(children) == 1 else children
        return super().__default__(data, children, meta)
