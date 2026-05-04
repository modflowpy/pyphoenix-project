from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import attrs
import numpy as np
import xarray as xr
import xattree
from modflow_devtools.dfns.schema.block import block_sort_key
from xattree import XatSpec

from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.spec import FileInOut, blocks_dict


def _path_to_tuple(name: str, value: Path, inout: FileInOut) -> tuple[str, ...]:
    t = [name.upper()]
    if name.endswith("_filerecord"):
        t[0] = name.replace("_filerecord", "").upper()
    elif name.endswith("_file"):
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

    if (
        "ncol" in structured_grid_dims
        and "nrow" in structured_grid_dims
        and structured_grid_dims["ncol"] > 0
        and structured_grid_dims["nrow"] > 0
    ):
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
    elif (
        "nlay" in structured_grid_dims
        and "ncpl" in structured_grid_dims
        and structured_grid_dims["ncpl"] > 0
    ):
        shape = [
            structured_grid_dims["nlay"],
            structured_grid_dims["ncpl"],
        ]
        dims = ["nlay", "ncpl"]
        coords = {
            "nlay": range(structured_grid_dims["nlay"]),
            "ncpl": range(structured_grid_dims["ncpl"]),
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

    def oc_setting_data(rec, dat, iper):
        if rec.steps.first:
            dat[iper] = "first"
        elif rec.steps.last:
            dat[iper] = "last"
        elif rec.steps.steps:
            steps = " ".join(str(x + 1) for x in rec.steps.steps)
            dat[iper] = f"steps {steps}"
        elif rec.steps.all:
            # check last as this defaults to True
            dat[iper] = "all"

    data = {}
    match value.dtype:
        case np.bool:
            # supports boolean dataarrays, e.g. STO steady_state and transient
            # e.g. steady_state to steady-state, why is't this the dfn name?
            fname = name.replace("_", "-")  # type: ignore
            dat = {kper: "" for kper in range(value.sizes["nper"]) if value.values[kper]}
            data[fname] = dat
        case np.dtypes.StringDType():
            # supports string dataarrays, e.g. OC save_budget, save_head
            fname = name.replace("_", " ")
            dat = {
                kper: value.values[kper]
                for kper in range(value.sizes["nper"])
                if value.values[kper].lower() in ["first", "last", "steps", "all"]
            }
            data[fname] = dat
        case object():
            # supports object dataararys, e.g. OC PrintSaveSetting
            for i, setting in enumerate(value.values):
                if isinstance(value.values[i], Oc.PrintSaveSetting):
                    if hasattr(value.values[i], "printrecord") and isinstance(
                        value.values[i].printrecord, list
                    ):
                        for rec in value.values[i].printrecord:
                            key = f"{rec.print} {rec.rtype}"
                            if key not in data:
                                data[key] = {}
                            oc_setting_data(rec, data[key], i)
                    if hasattr(value.values[i], "saverecord") and isinstance(
                        value.values[i].saverecord, list
                    ):
                        for rec in value.values[i].saverecord:  # type: ignore
                            key = f"{rec.save} {rec.rtype}"  # type: ignore
                            if key not in data:
                                data[key] = {}
                            oc_setting_data(rec, data[key], i)

    return data


def _unstructure_block_param(
    block_name: str,
    field_name: str,
    xatspec: XatSpec,
    value: Component,
    data: dict[str, Any],
    blocks: dict,
    period_data: dict,
) -> None:
    # Skip child components that have been processed as bindings
    if isinstance(value, Context) and field_name in xatspec.children:
        child_spec = xatspec.children[field_name]
        if hasattr(child_spec, "metadata") and "block" in child_spec.metadata:  # type: ignore
            if child_spec.metadata["block"] == block_name:  # type: ignore
                return

    # xattree.asdict converts inner-class attrs instances (like Rclose) to
    # plain dicts before this function sees them. Check the raw component attribute
    # first so the attrs match case can fire on the real object.
    raw_value = getattr(value, field_name, None)
    cls = type(raw_value)
    if attrs.has(cls) and "_keyword" in vars(cls):
        # Generated inner class record: convert to keyword-prefixed tuple.
        # _keyword is "" for records with no leading trigger token (e.g. rcloserecord).
        keyword: str = vars(cls)["_keyword"]
        tokens: list[Any] = [keyword.upper()] if keyword else []
        for a in attrs.fields(cast(type[attrs.AttrsInstance], cls)):
            val = getattr(raw_value, a.name)
            if val is None:
                continue
            if a.metadata.get("tagged", False):
                tokens.append(a.name.upper())
                tokens.append(val)
            elif isinstance(val, bool):
                if val:
                    tokens.append(a.name.upper())
            else:
                tokens.append(val)
        blocks[block_name][field_name] = tuple(tokens)
        return

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
            return
        case bool():
            if field_value:
                blocks[block_name][field_name] = field_value
        case Path():
            field_spec = xatspec.attrs[field_name]
            field_meta = getattr(field_spec, "metadata", {})
            t = _path_to_tuple(field_name, field_value, inout=field_meta.get("inout", "fileout"))
            # name may have changed e.g dropping '_file' suffix
            blocks[block_name][t[0]] = t
        case datetime():
            blocks[block_name][field_name] = field_value.isoformat()
        case t if (
            field_name == "auxiliary" and hasattr(field_value, "values") and field_value is not None
        ):
            # MF6 OPTIONS format requires the keyword "AUXILIARY" before the variable names.
            blocks[block_name][field_name] = ("AUXILIARY",) + tuple(field_value.values.tolist())
        case xr.DataArray():
            has_spatial_dims = any(
                dim in field_value.dims for dim in ["nlay", "nrow", "ncol", "ncpl", "nodes"]
            )
            if has_spatial_dims:
                field_value = _hack_structured_grid_dims(
                    field_value,
                    structured_grid_dims=value.data.dims,  # type: ignore
                )
            if "nper" in field_value.dims and block_name == "period":
                is_tabular = (
                    np.issubdtype(field_value.dtype, np.number)
                    or np.issubdtype(field_value.dtype, np.str_)
                    or (
                        field_value.dtype == object
                        and field_value.size > 0
                        and isinstance(field_value.values.flat[0], str)
                    )
                )
                if is_tabular:
                    period_data[field_name] = {
                        kper: field_value.isel(nper=kper)  # type: ignore
                        for kper in range(field_value.sizes["nper"])
                    }
                else:
                    dat = _hack_period_non_numeric(field_name, field_value)
                    for n, v in dat.items():
                        period_data[n] = v
            else:
                blocks[block_name][field_name] = field_value
        case _:
            blocks[block_name][field_name] = field_value


def unstructure_component(value: Component) -> dict[str, Any]:
    xatspec = xattree.get_xatspec(type(value))
    if "readarraygrid" in xatspec.attrs or "readasarrays" in xatspec.attrs:
        return _unstructure_array_component(value)
    else:
        return _unstructure_component(value)


def _unstructure_array_component(value: Component) -> dict[str, Any]:
    blockspec = blocks_dict(type(value))
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

        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            _unstructure_block_param(
                block_name, field_name, xatspec, value, data, blocks, period_data
            )

        # invert key order, (arr_name, kper) -> (kper, arr_name)
        for arr_name, periods in period_data.items():
            for kper, arr in periods.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr

        # setup indexed period blocks, combine arrays into datasets
        for kper, block in period_blocks.items():
            key = f"period {kper + 1}"
            for arr_name, val in block.items():
                if not np.all(val == FILL_DNODATA):
                    if key not in blocks:
                        blocks[key] = {}
                    blocks[key][arr_name] = val

    return {name: block for name, block in blocks.items() if name != "period"}


# Block names that MF6 rejects if present but empty.
# These blocks should only be written when they contain data.
_SKIP_IF_EMPTY = frozenset({"dimensions", "tracktimes"})

# Block names whose fields are list columns (one array per column, same dim)
# rather than independent grid arrays.  Only these blocks are auto-combined
# into an xr.Dataset for row-per-record output.  griddata-style blocks must
# NOT be in this set — their fields are written individually with
# INTERNAL/CONSTANT/NETCDF format.
_LIST_BLOCK_NAMES = frozenset({"packagedata", "packages", "perioddata", "table"})


def _unstructure_component(value: Component) -> dict[str, Any]:
    blockspec = blocks_dict(type(value))
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

        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            _unstructure_block_param(
                block_name, field_name, xatspec, value, data, blocks, period_data
            )

        # invert key order, (arr_name, kper) -> (kper, arr_name)
        for arr_name, periods in period_data.items():
            for kper, arr in periods.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr

        # sort kper order
        # needed because some package period parameters have their
        # own kper dicts and these may be out of order for the package,
        # e.g. STO transient and steady_state
        period_blocks = dict(sorted(period_blocks.items()))

        # setup indexed period blocks, combine arrays into datasets
        for kper, block in period_blocks.items():
            key = f"period {kper + 1}"
            for arr_name, val in block.items():
                if np.any(val != FILL_DNODATA):
                    # don't create the block (so it isn't written)
                    # unless there is data to write
                    if key not in blocks:
                        blocks[key] = {}
                    match block[arr_name]:
                        case str():
                            # non data period parameters have their period
                            # write key set in the _hack_period_non_numeric
                            # routine
                            blocks[f"period {kper + 1}"][arr_name] = val
                        case xr.DataArray():
                            blocks[f"period {kper + 1}"]["period"] = xr.Dataset(
                                block, coords=block[arr_name].coords
                            )

        if vertices := blocks.get("vertices", None):
            # TODO comes twice once with "vertices" key and once with dataarrays
            if "vertices" in vertices:
                continue
            if "iv" in vertices:
                vertices["iv"] = vertices["iv"] + 1
            blocks["vertices"] = {"vertices": xr.Dataset(vertices)}

        # Combine list-style blocks into a Dataset for row-per-record output.
        # Only applies to known list block names — griddata-style blocks (each
        # field a separate array) must NOT be combined.
        if block_name in _LIST_BLOCK_NAMES:
            current_block = blocks.get(block_name, {})
            if current_block:
                das = [v for v in current_block.values() if isinstance(v, xr.DataArray)]
                if das and len(das) == len(current_block):
                    first_dim = das[0].dims[0] if das[0].dims else None
                    if first_dim and all(da.dims and da.dims[0] == first_dim for da in das):
                        blocks[block_name] = {block_name: xr.Dataset(current_block)}

    blocks = dict(sorted(blocks.items(), key=block_sort_key))

    # total temporary hack! manually set solutiongroup 1.
    # TODO still need to support multiple..
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return {
        name: block
        for name, block in blocks.items()
        if name != "period" and (block or name not in _SKIP_IF_EMPTY)
    }
