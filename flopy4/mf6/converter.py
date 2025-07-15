from datetime import datetime
from pathlib import Path
from typing import Any

import xarray as xr
import xattree
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.spec import fields_dict, get_blocks


def _attach_field_metadata(
    dataset: xr.Dataset, component_type: type, field_names: list[str]
) -> None:
    field_metadata = {}
    component_fields = fields_dict(component_type)
    for field_name in field_names:
        if field_name in component_fields:
            field_metadata[field_name] = component_fields[field_name].metadata
    dataset.attrs["field_metadata"] = field_metadata


def _path_to_record(field_name: str, path_value: Path) -> tuple:
    if field_name.endswith("_file"):
        base_name = field_name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(path_value))
    return (field_name.upper(), "FILEOUT", str(path_value))


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blockspec = get_blocks(value.dfn)
    blocks: dict[str, dict[str, Any]] = {}
    for block_name, block in blockspec.items():
        blocks[block_name] = {}
        period_data = {}
        period_blocks = {}  # type: ignore
        for field_name in block.keys():
            field_value = data[field_name]
            # convert:
            #   - paths to records
            #   - datetime to ISO format
            #   - auxiliary fields to tuples
            #   - xarray DataArrays with 'nper' dimension to kper-sliced datasets
            #     (and split the period data into separate kper-indexed blocks)
            #   - other values to their original form
            if isinstance(field_value, Path) and field_value is not None:
                blocks[block_name][field_name] = _path_to_record(field_name, field_value)
            elif isinstance(field_value, datetime) and field_value is not None:
                blocks[block_name][field_name] = field_value.isoformat()
            elif (
                field_name == "auxiliary"
                and hasattr(field_value, "values")
                and field_value is not None
            ):
                blocks[block_name][field_name] = tuple(field_value.values.tolist())
            elif isinstance(field_value, xr.DataArray) and "nper" in field_value.dims:
                has_spatial_dims = any(
                    dim in field_value.dims for dim in ["nlay", "nrow", "ncol", "nnodes"]
                )
                if has_spatial_dims:
                    period_data[field_name] = {
                        kper: field_value.isel(nper=kper)
                        for kper in range(field_value.sizes["nper"])
                    }
                else:
                    if block_name not in period_data:
                        period_data[block_name] = {}
                    period_data[block_name][field_name] = field_value  # type: ignore
            else:
                if field_value is not None:
                    blocks[block_name][field_name] = field_value

        if block_name in period_data and isinstance(period_data[block_name], dict):
            dataset = xr.Dataset(period_data[block_name])
            _attach_field_metadata(dataset, type(value), list(period_data[block_name].keys()))  # type: ignore
            blocks[block_name] = {block_name: dataset}
            del period_data[block_name]

        for arr_name, periods in period_data.items():
            for kper, arr in periods.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr

        for kper, block in period_blocks.items():
            dataset = xr.Dataset(block)
            _attach_field_metadata(dataset, type(value), list(block.keys()))
            blocks[f"{block_name} {kper + 1}"] = {block_name: dataset}

    return {name: block for name, block in blocks.items() if block}


def _make_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = _make_converter()
