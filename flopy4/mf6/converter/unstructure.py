from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
import xattree
from modflow_devtools.dfn.schema.block import block_sort_key

from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.spec import FileInOut


def _path_to_tuple(name: str, value: Path, inout: FileInOut) -> tuple[str, ...]:
    t = [name.upper()]
    if name.endswith("_file"):
        t[0] = name.replace("_file", "").upper()
    if inout:
        t.append(inout.upper())
    t.append(str(value))
    return tuple(t)


def _make_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple[str, ...]]]]:
    if not isinstance(value, Context):
        return {}

    blocks = {}  # type: ignore
    xatspec = xattree.get_xatspec(type(value))

    for child_name, child_spec in xatspec.children.items():
        if (child := getattr(value, child_name, None)) is None:
            continue
        if (block_name := child_spec.metadata["block"]) not in blocks:  # type: ignore
            blocks[block_name] = {}
        match child:
            case Component():
                blocks[block_name][child_name] = [Binding.from_component(child).to_tuple()]
            case Mapping():
                blocks[block_name][child_name] = [
                    Binding.from_component(c).to_tuple() for c in child.values() if c is not None
                ]
            case Iterable():
                blocks[block_name][child_name] = [
                    Binding.from_component(c).to_tuple() for c in child if c is not None
                ]
            case _:
                raise ValueError(f"Unexpected child type: {type(child)}")

    return blocks


def _hack_structured_grid_dims(
    value: xr.DataArray, structured_grid_dims: Mapping[str, int]
) -> xr.DataArray:
    """
    Temporary hack to convert flat nodes dimension to 3d structured dims.
    long term solution for this is to use a custom xarray index. filters
    should then have access to all dimensions needed.
    """

    if "nodes" not in value.dims:
        return value

    shape = [
        structured_grid_dims["nlay"],
        structured_grid_dims["nrow"],
        structured_grid_dims["ncol"],
    ]
    dims = ["nlay", "nrow", "ncol"]
    coords = {
        "nlay": range(structured_grid_dims["nlay"]),
        "nrow": range(structured_grid_dims["nrow"]),
        "ncol": range(structured_grid_dims["ncol"]),
    }

    if "nper" in value.dims:
        shape.insert(0, value.sizes["nper"])
        dims.insert(0, "nper")
        coords = {"nper": value.coords["nper"], **coords}

    return xr.DataArray(
        value.data.reshape(shape),
        dims=dims,
        coords=coords,
        name=value.name,
    )


def _hack_period_non_numeric(name: str, value: xr.DataArray) -> dict[str, dict[int, Any]]:
    from flopy4.mf6.gwf import Oc

    def oc_setting_data(rec, action):
        dat = {}
        if rec.steps.first:
            dat = {kper: "first" for kper in range(value.sizes["nper"])}
            key = f"{action} {rec.rtype}"
            data[key] = dat
        elif rec.steps.last:
            dat = {kper: "last" for kper in range(value.sizes["nper"])}
            key = f"{action} {rec.rtype}"
            data[key] = dat
        elif rec.steps.steps:
            steps = " ".join(str(x - 1) for x in rec.steps.steps)
            dat = {kper: f"steps {steps}" for kper in range(value.sizes["nper"])}
            key = f"{action} {rec.rtype}"
            data[key] = dat
        elif rec.steps.all:
            # check last as this defaults to True
            dat = {kper: "all" for kper in range(value.sizes["nper"])}
            key = f"{action} {rec.rtype}"
            data[key] = dat
        return dat

    data = {}
    match value.dtype:
        case np.bool:
            dat = {kper: "" for kper in range(value.sizes["nper"]) if value.values[kper]}  # type: ignore
            data[name] = dat
        case np.dtypes.StringDType():
            fname = name.replace("_", " ")
            dat = {kper: value.values[kper] for kper in range(value.sizes["nper"])}
            data[fname] = dat
        case object():
            if isinstance(value.values[0], Oc.PrintSaveSetting):
                if hasattr(value.values[0], "printrecord") and isinstance(
                    value.values[0].printrecord, list
                ):
                    action = "PRINT"
                    for rec in value.values[0].printrecord:
                        key = f"{action} {rec.rtype}"
                        data[key] = oc_setting_data(rec, action)
                if hasattr(value.values[0], "saverecord") and isinstance(
                    value.values[0].saverecord, list
                ):
                    action = "SAVE"
                    for rec in value.values[0].saverecord:  # type: ignore
                        key = f"{action} {rec.rtype}"
                        data[key] = oc_setting_data(rec, action)

    return data


def unstructure_component(value: Component) -> dict[str, Any]:
    blockspec = dict(sorted(value.dfn.blocks.items(), key=block_sort_key))  # type: ignore
    blocks: dict[str, dict[str, Any]] = {}
    xatspec = xattree.get_xatspec(type(value))
    data = xattree.asdict(value)

    # create child component binding blocks
    blocks.update(_make_binding_blocks(value))

    # process blocks in order, unstructuring fields as needed,
    # then slice period data into separate kper-indexed blocks
    # each of which contains a dataset indexed for that period.
    for block_name, block in blockspec.items():
        period_data = {}  # type: ignore
        period_blocks = {}  # type: ignore
        period_block_name = None

        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            # Skip child components that have been processed as bindings
            if isinstance(value, Context) and field_name in xatspec.children:
                child_spec = xatspec.children[field_name]
                if hasattr(child_spec, "metadata") and "block" in child_spec.metadata:  # type: ignore
                    if child_spec.metadata["block"] == block_name:  # type: ignore
                        continue

            # filter out empty values and false keywords, and convert:
            #   - paths to records
            #   - datetimes to ISO format
            #   - filter out false keywords
            #   - 'auxiliary' fields to tuples
            #   - xarray DataArrays with 'nper' dim to dict of kper-sliced datasets
            #   - other values to their original form
            # TODO: use cattrs converters for field unstructuring?
            match field_value := data[field_name]:
                case None:
                    continue
                case bool():
                    if field_value:
                        blocks[block_name][field_name] = field_value
                case Path():
                    field_spec = xatspec.attrs[field_name]
                    field_meta = getattr(field_spec, "metadata", {})
                    t = _path_to_tuple(
                        field_name, field_value, inout=field_meta.get("inout", "fileout")
                    )
                    # name may have changed e.g dropping '_file' suffix
                    blocks[block_name][t[0]] = t
                case datetime():
                    blocks[block_name][field_name] = field_value.isoformat()
                case t if (
                    field_name == "auxiliary"
                    and hasattr(field_value, "values")
                    and field_value is not None
                ):
                    blocks[block_name][field_name] = tuple(field_value.values.tolist())
                case xr.DataArray() if "nper" in field_value.dims:
                    has_spatial_dims = any(
                        dim in field_value.dims for dim in ["nlay", "nrow", "ncol", "nodes"]
                    )
                    if has_spatial_dims:
                        field_value = _hack_structured_grid_dims(
                            field_value,
                            structured_grid_dims=value.parent.data.dims,  # type: ignore
                        )
                    if block_name == "period":
                        if not np.issubdtype(field_value.dtype, np.number):
                            dat = _hack_period_non_numeric(field_name, field_value)
                            for n, v in dat.items():
                                period_data[n] = v
                        else:
                            period_data[field_name] = {
                                kper: field_value.isel(nper=kper)  # type: ignore
                                for kper in range(field_value.sizes["nper"])
                            }
                    else:
                        blocks[block_name][field_name] = field_value

                case _:
                    blocks[block_name][field_name] = field_value

        # invert key order, (arr_name, kper) -> (kper, arr_name)
        for arr_name, periods in period_data.items():
            for kper, arr in periods.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr

        # sort kper order
        period_blocks = dict(sorted(period_blocks.items()))

        # setup indexed period blocks, combine arrays into datasets
        for kper, block in period_blocks.items():
            blocks[f"period {kper + 1}"] = {}
            for arr_name, val in block.items():
                match block[arr_name]:
                    case str():
                        blocks[f"period {kper + 1}"][arr_name] = val
                    case xr.DataArray():
                        blocks[f"period {kper + 1}"]["period"] = xr.Dataset(
                            block, coords=block[arr_name].coords
                        )

        # combine "perioddata" block arrays (tdis, ats) into datasets
        # so they render as lists. temp hack TODO do this generically
        if perioddata := blocks.get("perioddata", None):
            blocks["perioddata"] = {"perioddata": xr.Dataset(perioddata)}

    # total temporary hack! manually set solutiongroup 1.
    # TODO still need to support multiple..
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return {name: block for name, block in blocks.items() if name != "period"}
