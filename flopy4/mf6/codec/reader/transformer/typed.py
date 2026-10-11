from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from lark import Token, Transformer

from flopy4.mf6.codec.reader.grammar.names import parse_rule_name
from flopy4.utils import parse_number


class _Element(tuple):
    """A (name, value) for one element of a list, which collects them."""


def _header_key(block_name: str, parts: list) -> str:
    """A block's key from its record header, as written (OBS's
    "continuous FILEOUT obs.csv BINARY"): keywords in upper case."""
    tokens = [block_name]
    for part in parts:
        if part is None:
            continue
        if isinstance(part, Token):
            tokens.append(str(part).upper())
        elif isinstance(part, tuple):  # an optional keyword, given
            tokens.append(part[0].upper())
        else:
            tokens.append(str(part))
    return " ".join(tokens)


class TypedTransformer(Transformer):
    """Type-aware transformer for MF6 input files.

    Reads each generated rule by its name, which says what the rule is (see
    ``grammar/names.py``), so one transformer reads every component's
    grammar and needs no DFN.
    """

    def __init__(self, visit_tokens=False):
        super().__init__(visit_tokens)

    def __getattr__(self, name):
        """Handle typed__ prefixed methods by delegating to the unprefixed version."""
        if name.startswith("typed__"):
            unprefixed = name[7:]  # Remove "typed__" prefix
            if hasattr(self, unprefixed):
                return getattr(self, unprefixed)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

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
                elif isinstance(block_data, dict) and all(
                    isinstance(k, float) for k in block_data.keys()
                ):
                    merged[block_name].update(block_data)
                else:
                    # This shouldn't happen for well-formed input
                    pass
        return merged

    def block(self, items: list[Any]) -> dict:
        return items[0]

    def array(self, items: list[Any]) -> dict:
        arrs = items[0]
        if isinstance(arrs, list):
            # A LAYERED array can mix CONSTANT/INTERNAL layers (real
            # DataArrays, already resolved by try_create_dataarray) with an
            # OPEN/CLOSE layer (left as a bare Path -- resolving it needs
            # workspace access, out of this pass's parse-level-parity scope).
            # xr.concat can't mix DataArray and Path, so only concat what's
            # actually concatenable; each layer's raw value (DataArray or
            # Path) is preserved in "layers" rather than crashing the parse.
            dataarrays = [arr["data"] for arr in arrs if isinstance(arr.get("data"), xr.DataArray)]
            data = xr.concat(dataarrays, dim="layer") if dataarrays else None
            return {
                "control": [arr["control"] for arr in arrs if "control" in arr],
                "data": data,
                "layers": [arr.get("data") for arr in arrs],
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
        result = {"type": "constant", "value": items[0]}
        for item in items[1:]:
            if item is not None:
                result.update(item)
        return result

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

    def timearrayseries(self, items: list[Any]) -> dict[str, Any]:
        return {"type": "timearrayseries", "value": items[0]}

    def factor(self, items: list[Any]) -> dict[str, float]:
        return {"factor": items[0]}

    def iprn(self, items: list[Any]) -> dict[str, int]:
        return {"iprn": items[0]}

    def binary(self, _) -> dict[str, bool]:
        return {"binary": True}

    def filename(self, items: list[Any]) -> Path:
        return Path(items[0].strip("\"'"))

    def string(self, items: list[Any]) -> str:
        # String can be either a token or a tree (word)
        value = items[0]
        if hasattr(value, "strip"):
            return value.strip("\"'")
        else:
            # It's a tree, extract the token value
            return str(value["children"][0]) if hasattr(value, "children") else str(value)

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
        return parse_number(str(items[0]))

    def data(self, items: list[Any]) -> np.ndarray:
        return np.array(items)

    def netcdf(self, _) -> dict[str, bool]:
        return {"netcdf": True}

    def block_index(self, items: list[Any]) -> int | float:
        """Extract block index (e.g., period number, or utl-tas's time)."""
        return parse_number(str(items[0]))

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
                    values.append(token_child["children"][0])
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

    def double_index(self, items: list[Any]) -> float:
        """A block index that's a time (utl-tas's TIME block)."""
        return float(items[0])

    def _block(self, block_name: str, children: list[Any]) -> dict | None:
        """A block: [fields], or [index, fields, closing index], or [header,
        fields, closing header]. The closing index or header is optional in
        the grammar (most real files write a bare "END <name>") -- Lark
        fills the omitted slot with None rather than dropping it."""
        if len(children) == 3 and isinstance(children[0], tuple):
            # A record header (OBS's "CONTINUOUS FILEOUT <file> [BINARY]"),
            # keyed like the basic transformer's.
            _, parts = children[0]
            return {_header_key(block_name, parts): children[1]}
        if (
            len(children) == 3
            and isinstance(children[0], (int, float))
            and (children[2] is None or isinstance(children[2], (int, float)))
        ):
            return {block_name: {children[0]: children[1]}}
        if len(children) == 1:
            return {block_name: children[0]}
        return None

    @staticmethod
    def _fields(children: list[Any]) -> dict:
        """A block's contents, by field name. A list's elements are always a
        list, anything else one value."""
        if children and not isinstance(children[0], tuple):
            # list data (e.g. stress_period_data records), not named fields
            if len(children) == 1 and isinstance(children[0], list):
                return {"stress_period_data": children[0]}
            return {"stress_period_data": children}
        fields: dict = {}
        for item in children:
            if isinstance(item, _Element):
                fields.setdefault(item[0].lower(), []).append(item[1])
            elif isinstance(item, tuple):
                fields[item[0].lower()] = item[1]
        return fields

    def __default__(self, data, children, meta):
        name, tags = parse_rule_name(str(data))
        if "block" in tags:
            if (block := self._block(name, children)) is not None:
                return block
            return super().__default__(data, children, meta)
        if "fields" in tags:
            return self._fields(children)
        if "hdr" in tags:
            return name, children  # its parts as written, see _header_key
        value: Any
        if "kw" in tags:
            # A keyword union arm keeps its token: the arm, as spelled in
            # the DFN (AMT-LMK, not amt_lmk).
            if children and isinstance(children[0], Token):
                name = str(children[0]).lower()
            value = True
        elif "arr" in tags:
            value = list(children)
        elif "rec" in tags:
            # Each part is its own rule, read as (name, value); an optional
            # part that's absent is None.
            value = {c[0]: c[1] for c in children if isinstance(c, tuple)}
        elif "union" in tags:
            arm, value = children[0]
            if value is True:  # only a keyword reads as True
                value = arm
        elif "val" in tags:
            value = children[0] if len(children) == 1 else children
        else:
            return super().__default__(data, children, meta)
        return _Element((name, value)) if "elem" in tags else (name, value)


_TYPED_TRANSFORMER = TypedTransformer()


def get_typed_transformer() -> TypedTransformer:
    """The typed transformer, which reads any component's typed grammar."""
    return _TYPED_TRANSFORMER
