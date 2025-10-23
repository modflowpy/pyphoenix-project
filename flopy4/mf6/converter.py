from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sparse
import xarray as xr
import xattree
from cattrs import Converter
from modflow_devtools.dfn.schema.block import block_sort_key
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.spec import FileInOut


def path_to_tuple(name: str, value: Path, inout: FileInOut) -> tuple[str, ...]:
    t = [name.upper()]
    if name.endswith("_file"):
        t[0] = name.replace("_file", "").upper()
    if inout:
        t.append(inout.upper())
    t.append(str(value))
    return tuple(t)


def get_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple[str, ...]]]]:
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


def unstructure_component(value: Component) -> dict[str, Any]:
    blockspec = dict(sorted(value.dfn.blocks.items(), key=block_sort_key))  # type: ignore
    blocks: dict[str, dict[str, Any]] = {}
    xatspec = xattree.get_xatspec(type(value))
    data = xattree.asdict(value)

    blocks.update(binding_blocks := get_binding_blocks(value))

    for block_name, block in blockspec.items():
        if block_name not in blocks:
            blocks[block_name] = {}
        period_data = {}
        period_blocks = {}  # type: ignore

        for field_name in block.keys():
            # Skip child components that have been processed as bindings
            if isinstance(value, Context) and field_name in xatspec.children:
                child_spec = xatspec.children[field_name]
                if hasattr(child_spec, "metadata") and "block" in child_spec.metadata:  # type: ignore
                    if child_spec.metadata["block"] == block_name:  # type: ignore
                        continue

            field_value = data[field_name]
            # convert:
            #   - paths to records
            #   - datetime to ISO format
            #   - auxiliary fields to tuples
            #   - xarray DataArrays with 'nper' dimension to kper-sliced datasets
            #     (and split the period data into separate kper-indexed blocks)
            #   - other values to their original form
            if isinstance(field_value, Path):
                field_spec = xatspec.attrs[field_name]
                field_meta = getattr(field_spec, "metadata", {})
                t = path_to_tuple(field_name, field_value, inout=field_meta.get("inout", "fileout"))
                # name may have changed e.g dropping '_file' suffix
                blocks[block_name][t[0]] = t
            elif isinstance(field_value, datetime):
                blocks[block_name][field_name] = field_value.isoformat()
            elif (
                field_name == "auxiliary"
                and hasattr(field_value, "values")
                and field_value is not None
            ):
                blocks[block_name][field_name] = tuple(field_value.values.tolist())
            elif isinstance(field_value, xr.DataArray) and "nper" in field_value.dims:
                has_spatial_dims = any(
                    dim in field_value.dims for dim in ["nlay", "nrow", "ncol", "nodes"]
                )
                if has_spatial_dims:
                    field_value = _hack_structured_grid_dims(
                        field_value,
                        structured_grid_dims=value.parent.data.dims,  # type: ignore
                    )

                    period_data[field_name] = {
                        kper: field_value.isel(nper=kper)
                        for kper in range(field_value.sizes["nper"])
                    }
                else:
                    # TODO why not putting in block here but doing below? how does this even work
                    if np.issubdtype(field_value.dtype, np.str_):
                        period_data[field_name] = {
                            kper: field_value[kper] for kper in range(field_value.sizes["nper"])
                        }
                    else:
                        if block_name not in period_data:
                            period_data[block_name] = {}
                        period_data[block_name][field_name] = field_value  # type: ignore
            else:
                if field_value is not None:
                    if isinstance(field_value, bool):
                        if field_value:
                            blocks[block_name][field_name] = field_value
                    else:
                        blocks[block_name][field_name] = field_value

        if block_name in period_data and isinstance(period_data[block_name], dict):
            dataset = xr.Dataset(period_data[block_name])
            blocks[block_name] = {block_name: dataset}
            del period_data[block_name]

        for arr_name, periods in period_data.items():
            for kper, arr in periods.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr

        for kper, block in period_blocks.items():
            dataset = xr.Dataset(block)
            blocks[f"{block_name} {kper + 1}"] = {block_name: dataset}

    # total temporary hack! manually set solutiongroup 1. still need to support multiple..
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return {name: block for name, block in blocks.items() if name != "period"}


def _make_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = _make_converter()


def dict_to_array(value, self_, field) -> NDArray:
    """
    Convert a sparse dictionary representation of an array to a
    dense numpy array or a sparse COO array.

    TODO: generalize this not only to dictionaries but to any
    form that can be converted to an array (e.g. nested list)
    """

    if not isinstance(value, dict):
        # if not a dict, assume it's a numpy array
        # and let xarray deal with it if it isn't
        return value

    spec = get_xatspec(type(self_)).flat
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # resolve dims
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = dict(self_.parent.data.dims) if self_.parent else {}
    dims = inherited_dims | explicit_dims
    shape = [dims.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    if np.prod(shape) > SPARSE_THRESHOLD:
        a: dict[tuple[Any, ...], Any] = dict()

        def set_(arr, val, *ind):
            arr[tuple(ind)] = val

        def final(arr):
            coords = np.array(list(map(list, zip(*arr.keys()))))
            return sparse.COO(
                coords,
                list(arr.values()),
                shape=shape,
                fill_value=field.default or FILL_DNODATA,
            )
    else:
        a = np.full(shape, FILL_DNODATA, dtype=field.dtype)  # type: ignore

        def set_(arr, val, *ind):
            arr[ind] = val

        def final(arr):
            arr[arr == FILL_DNODATA] = field.default or FILL_DNODATA
            return arr

    if "nper" in dims:
        for kper, period in value.items():
            if kper == "*":
                kper = 0
            match len(shape):
                case 1:
                    set_(a, period, kper)
                case _:
                    for cellid, v in period.items():
                        nn = get_nn(cellid, **dims)
                        set_(a, v, kper, nn)
            if kper == "*":
                break
    else:
        for cellid, v in value.items():
            nn = get_nn(cellid, **dims)
            set_(a, v, nn)

    return final(a)


def structure(data: dict[str, Any], path: Path) -> Component:
    component = COMPONENT_CONVERTER.structure(data, Component)
    if isinstance(component, Context):
        component.workspace = path.parent
    component.filename = path.name
    return component


def unstructure(component: Component) -> dict[str, Any]:
    return COMPONENT_CONVERTER.unstructure(component)
