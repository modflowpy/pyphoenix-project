from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from lark import Token, Transformer
from modflow_devtools.dfn import _SCALAR_TYPES, Dfn, get_blocks, get_fields


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

    def __init__(self, visit_tokens=True, dfn: Dfn = None):
        super().__init__(visit_tokens)
        self.dfn = dfn
        self.blocks = get_blocks(dfn) if dfn else None
        self.fields = get_fields(dfn) if dfn else None

    def start(self, items: list[Any]) -> Mapping:
        return ChainMap(*items)

    def block(self, items: list[Any]) -> dict:
        return items[0]

    def array(self, items: list[Any]) -> dict:
        infos = items[0]
        if isinstance(infos, list):
            data = xr.concat([info["data"] for info in infos if "data" in info], dim="layer")
            return {
                "control": [info["control"] for info in infos if "control" in info],
                "data": data,
                "attrs": {k: v for k, v in infos[0].items() if k not in ["data"]},
                "dims": {"layer": len(infos)},
            }
        return infos

    def single_array(self, items: list[Any]) -> dict:
        netcdf = items[0]
        info = items[-1]
        if netcdf:
            info["netcdf"] = netcdf
        return TypedTransformer.try_create_dataarray(info)

    def layered_array(self, items: list[Any]) -> list[dict]:
        netcdf = items[0]
        infos = []
        for info in items[2:]:
            if info is None:
                continue
            if netcdf:
                info["netcdf"] = netcdf
            infos.append(TypedTransformer.try_create_dataarray(info))
        return infos

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
            return {block_name: children[0]}
        elif data.endswith("_vars"):
            return {item[0].lower(): item[1] for item in children}
        elif (field := self.fields.get(data, None)) is not None:
            if field["type"] == "keyword":
                return data, True
            elif field["type"] in _SCALAR_TYPES and field.get("shape", None):
                return data, TypedTransformer.try_create_dataarray(children[0])
            else:
                return data, children[0]
        return super().__default__(data, children, meta)
