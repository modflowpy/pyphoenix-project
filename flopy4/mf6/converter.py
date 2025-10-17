from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sparse
import xarray as xr
import xattree
from cattrs import Converter
from modflow_devtools.dfn import block_sort_key
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA, PERIOD
from flopy4.mf6.context import Context
from flopy4.mf6.spec import fields_dict


def path_to_tuple(name: str, value: Path) -> tuple[str, str, str]:
    if name.endswith("_file"):
        base_name = name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(value))
    return (name.upper(), "FILEOUT", str(value))


def get_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple[str, ...]]]]:
    if not isinstance(value, Context):
        return {}

    blocks = {}
    xatspec = xattree.get_xatspec(type(value))

    for child_name, child_spec in xatspec.children.items():
        if (child := getattr(value, child_name, None)) is None:
            continue
        if (block_name := child_spec.metadata["block"]) not in blocks:
            blocks[block_name] = {}
        match child:
            case Component():
                blocks[block_name][child_name] = [Binding.from_component(child).to_tuple()]
            case Mapping():
                blocks[block_name][child_name] = [
                    Binding.from_component(comp).to_tuple()
                    for comp in child.values()
                    if comp is not None
                ]
            case Iterable():
                blocks[block_name][child_name] = [
                    Binding.from_component(comp).to_tuple() for comp in child if comp is not None
                ]
            case _:
                raise ValueError(f"Unexpected child type: {type(child)}")

    return blocks


def has_structured_grid_dims(value: xr.DataArray) -> bool:
    """
    Check if the DataArray has structured grid dimensions: 'nlay', 'nrow', and 'ncol'.
    """
    return all(dim in value.dims for dim in ["nlay", "nrow", "ncol"])


def has_grid_dims(value: xr.DataArray) -> bool:
    """
    Check if the DataArray has spatial dimensions: 'nodes' and/or 'nlay', 'nrow', and 'ncol'.
    """
    return "nodes" in value.dims or has_structured_grid_dims(value)


def has_tdis_dims(value: xr.DataArray) -> bool:
    """
    Check if the DataArray has a time dimensions 'nper'.
    """
    return "nper" in value.dims


def _hack_grid_dims(value, field_value):
    # terrible hack to convert flat nodes dimension to 3d structured dims.
    # long term solution for this is to use a custom xarray index. filters
    # should then have access to all dimensions needed.
    dims_ = set(field_value.dims).copy()
    parent = value.parent  # type: ignore
    if parent is None:
        # TODO for standalone packages
        return field_value

    if "nper" in dims_:
        dims_.remove("nper")
        shape = (
            field_value.sizes["nper"],
            parent.dims["nlay"],
            parent.dims["nrow"],
            parent.dims["ncol"],
        )
        dims = ("nper", "nlay", "nrow", "ncol")
        coords = {
            "nper": field_value.coords["nper"],
            "nlay": range(parent.dims["nlay"]),
            "nrow": range(parent.dims["nrow"]),
            "ncol": range(parent.dims["ncol"]),
        }
    else:
        shape = (
            parent.dims["nlay"],
            parent.dims["nrow"],
            parent.dims["ncol"],
        )
        dims = ("nlay", "nrow", "ncol")
        coords = {
            "nlay": range(parent.dims["nlay"]),
            "nrow": range(parent.dims["nrow"]),
            "ncol": range(parent.dims["ncol"]),
        }

    if dims_ == {"nodes"}:
        field_value = xr.DataArray(
            field_value.data.reshape(shape),
            dims=dims,
            coords=coords,
        )

    return field_value


def unstructure_field(name: str, value: Any) -> tuple[str, Any]:
    """
    Convert:

      - bools to keywords (since they should only be written if true)
      - paths to records with 'FILEIN/OUT' keywords etc
      - datetimes to ISO format
      - 'auxiliary' arrays to tuples since they are written inline
      - period block arrays to dictionaries of kper-sliced arrays

    All other values are left as is.

    Parameters
    ----------
    name : str
        The name of the field
    value : Any
        The value of the field

    Returns
    -------
        A tuple of (name, value) since the name might be
        modified (e.g. '_file' suffix removed for paths)
    """

    match value:
        case None:
            return name, None
        case bool():
            return name, (value if value else None)
        case Path():
            rec = path_to_tuple(name, value)
            name = rec[0]  # '_file' suffix may have been dropped
            return name, rec
        case datetime():
            return name, value.isoformat()
        case xr.DataArray():
            if name == "auxiliary":
                value = tuple(value.values.tolist())
            if has_grid_dims(value):
                value = _hack_grid_dims(value, value)
            if has_tdis_dims(value):
                value = {kper: value.isel(nper=kper) for kper in range(value.sizes["nper"])}
            return name, value
        case _:
            return name, value


def unstructure_block(block: dict[str, Any]) -> dict[str, Any]:
    """Unstructure a block of data, converting fields to a suitable format."""
    return dict([unstructure_field(block.get(field_name, None)) for field_name in block.keys()])


def _hack_field_metadata(
    dataset: xr.Dataset, component_type: type, field_names: Iterable[str]
) -> None:
    # TODO: attach metadata to array attrs instead of dataset attrs
    field_metadata = {}
    component_fields = fields_dict(component_type)
    for field_name in field_names:
        if field_name in component_fields:
            field_metadata[field_name] = component_fields[field_name].metadata
    dataset.attrs["field_metadata"] = field_metadata


def segment_period_data(block: dict[str, Any], cls: type[Component]) -> dict[str, dict[str, Any]]:
    """Partition period data by stress period"""
    arrays = {}
    blocks = {}
    period = PERIOD.upper()

    for arr_name, periods in block.items():
        for kper, arr in periods.items():
            if kper not in arrays:
                arrays[kper] = {}
            arrays[kper][arr_name] = arr

    for kper, arrs in arrays.items():
        dataset = xr.Dataset(arrs)
        _hack_field_metadata(dataset, cls, arrs.keys())
        blocks[f"{period} {kper + 1}"] = {period: dataset}

    return blocks


def unstructure_component(value: Component) -> dict[str, Any]:
    """Unstructure a Component."""
    dfn = value.dfn
    cls = type(value)
    data = value.to_dict(blocks=True)
    blocks: dict[str, dict[str, Any]] = {}
    blocks.update(binding_blocks := get_binding_blocks(value))
    blocks.update(
        {
            block_name: unstructure_block(data[block_name])
            for block_name in dfn.blocks.keys()
            if block_name not in binding_blocks
        }
    )
    if period_block := blocks.pop(PERIOD, None):
        blocks.update(segment_period_data(period_block, cls))

    # total temporary hack! manually set solutiongroup 1.
    # TODO support multiple solution groups
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return dict(sorted(blocks.items(), key=block_sort_key))


def make_component_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = make_component_converter()


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
