from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from lark import Token, Transformer
from modflow_devtools.dfn import Dfn
from modflow_devtools.dfn.schema.v2 import SCALAR_TYPES


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
        value = str(token)
        try:
            if "." in value or "e" in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return float(value)

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

    def start(self, items: list[Any]) -> dict:
        """Collect and merge blocks, handling indexed blocks specially."""
        merged = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            for block_name, block_data in item.items():
                if block_name not in merged:
                    merged[block_name] = block_data
                else:
                    # If both are dicts with integer keys (indexed blocks), merge them
                    existing = merged[block_name]
                    if (isinstance(existing, dict) and isinstance(block_data, dict) and
                        all(isinstance(k, int) for k in existing.keys()) and
                        all(isinstance(k, int) for k in block_data.keys())):
                        existing.update(block_data)
                    # Otherwise, indexed block overwrites (shouldn't happen for well-formed input)
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

    def binary(self, items: list[Any]) -> dict[str, bool]:
        return {"binary": True}

    def filename(self, items: list[Any]) -> Path:
        return Path(items[0].strip("\"'"))

    def string(self, items: list[Any]) -> str:
        return items[0].strip("\"'")

    def integer(self, items: list[Any]) -> int:
        return int(items[0])

    def double(self, items: list[Any]) -> float:
        return float(items[0])

    def data(self, items: list[Any]) -> np.ndarray:
        return np.array(items)

    def netcdf(self, items: list[Any]) -> dict[str, bool]:
        return {"netcdf": True}

    # Handle typed__ prefixed rules from imports
    def typed__single_array(self, items: list[Any]) -> dict:
        return self.single_array(items)

    def typed__layered_array(self, items: list[Any]) -> list[dict]:
        return self.layered_array(items)

    def typed__readarray(self, items: list[Any]) -> dict[str, Any]:
        return self.readarray(items)

    def typed__control(self, items: list[Any]) -> dict[str, Any]:
        return self.control(items)

    def typed__constant(self, items: list[Any]) -> dict[str, Any]:
        return self.constant(items)

    def typed__internal(self, items: list[Any]) -> dict[str, Any]:
        return self.internal(items)

    def typed__external(self, items: list[Any]) -> dict[str, Any]:
        return self.external(items)

    def typed__factor(self, items: list[Any]) -> dict[str, float]:
        return self.factor(items)

    def typed__iprn(self, items: list[Any]) -> dict[str, int]:
        return self.iprn(items)

    def typed__binary(self, items: list[Any]) -> dict[str, bool]:
        return self.binary(items)

    def typed__filename(self, items: list[Any]) -> Path:
        return self.filename(items)

    def typed__data(self, items: list[Any]) -> np.ndarray:
        return self.data(items)

    def typed__netcdf(self, items: list[Any]) -> dict[str, bool]:
        return self.netcdf(items)

    def typed__layered(self, items: list[Any]) -> dict[str, bool]:
        return {"layered": True}

    def block_index(self, items: list[Any]) -> int:
        """Extract block index (e.g., period number)."""
        return items[0]

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
        if self.blocks is None or self.fields is None:
            return super().__default__(data, children, meta)
        if data.endswith("_block") and (block_name := data[:-6]) in self.blocks:
            # Check if this is an indexed block (period blocks have 3 children: [index, fields, index])
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
            return {item[0].lower(): item[1] for item in children}
        elif (field := self.fields.get(data, None)) is not None:
            if field.type == "keyword":
                return data, True
            else:
                # For all other fields (including arrays), return the transformed children
                return data, children[0] if len(children) == 1 else children
        return super().__default__(data, children, meta)
