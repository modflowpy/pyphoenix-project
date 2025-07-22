from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from lark import Token, Transformer


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


class ArrayTransformer(Transformer):
    """
    Transformer for MF6 array input format. Returns xarray DataArrays
    for internal/constant arrays and Path objects for external arrays,
    inside a dictionary which also contains control information. This
    is a first step towards a smarter parser/transformer for the full
    MF6 input format specification.
    """

    def start(self, items: list[Any]) -> xr.DataArray | Path:
        return items[0]

    def readarray(self, items: list[Any]) -> xr.DataArray | Path:
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

    def single_array(self, items: list[Any]) -> xr.DataArray | Path:
        netcdf = items[0]
        info = items[-1]
        if netcdf:
            info["netcdf"] = netcdf
        return ArrayTransformer.try_create_dataarray(info)

    def layered_array(self, items: list[Any]) -> xr.DataArray | list[Path]:
        netcdf = items[0]
        infos = []
        for info in items[2:]:
            if info is None:
                continue
            if netcdf:
                info["netcdf"] = netcdf
            infos.append(ArrayTransformer.try_create_dataarray(info))
        return infos

    def array(self, items: list[Any]) -> dict[str, Any] | Path:
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

    def external(self, items: list[Any]) -> Path:
        return {"type": "external", "value": items[0]}

    def factor(self, items: list[Any]) -> dict[str, float]:
        return {"factor": items[0]}

    def iprn(self, items: list[Any]) -> dict[str, int]:
        return {"iprn": items[0]}

    def binary(self, items: list[Any]) -> dict[str, bool]:
        return {"binary": True}

    def filename(self, items: list[Any]) -> Path:
        return Path(items[0])

    def data(self, items: list[Any]) -> np.ndarray:
        return np.array(items)

    def netcdf(self, items: list[Any]) -> dict[str, bool]:
        return {"netcdf": True}

    def NUMBER(self, token: Token) -> int | float:
        return float(token)

    def SIGNED_NUMBER(self, token: Token) -> int | float:
        return self.NUMBER(token)

    def INT(self, token: Token) -> int:
        return int(token)

    def SIGNED_INT(self, token: Token) -> int:
        return int(token)

    def ESCAPED_STRING(self, token: Token) -> str:
        # Remove quotes from escaped string
        value = str(token)
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value

    @staticmethod
    def try_create_dataarray(array_info: dict) -> dict:
        """Create an xarray DataArray from MF6 array information."""
        control = array_info["control"]
        match control["type"]:
            case "constant":
                data = control["value"]
                array_info["data"] = xr.DataArray(data=data)
            case "internal":
                data = array_info["data"]
                factor = control.get("factor", 1.0)
                data = data * factor
                array_info["data"] = xr.DataArray(data=data)
            case "external":
                pass
        return array_info
