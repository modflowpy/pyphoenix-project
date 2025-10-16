from collections.abc import Iterable, MutableMapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sparse
import xarray as xr
import xattree
from attrs import define
from cattrs import Converter
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import fields_dict


@define
class _Binding:
    """
    An MF6 component binding: a record representation of the
    component for writing to a parent component's name file.
    """

    type: str
    fname: str
    terms: tuple[str, ...] | None = None

    def to_tuple(self):
        if self.terms and any(self.terms):
            return (self.type, self.fname, *self.terms)
        else:
            return (self.type, self.fname)

    @classmethod
    def from_component(cls, component: Component) -> "_Binding":
        def _get_binding_type(component: Component) -> str:
            cls_name = component.__class__.__name__
            if isinstance(component, Exchange):
                return f"{'-'.join([cls_name[:2], cls_name[3:]]).upper()}6"
            elif isinstance(component, Solution):
                return f"{component.slntype}6"
            else:
                return f"{cls_name.upper()}6"

        def _get_binding_terms(component: Component) -> tuple[str, ...] | None:
            if isinstance(component, Exchange):
                return (component.exgmnamea, component.exgmnameb)  # type: ignore
            elif isinstance(component, Solution):
                return tuple(component.models)
            elif isinstance(component, (Model, Package)):
                return (component.name,)  # type: ignore
            return None

        return cls(
            type=_get_binding_type(component),
            fname=component.filename or component.default_filename(),
            terms=_get_binding_terms(component),
        )


def _attach_field_metadata(
    dataset: xr.Dataset, component_type: type, field_names: list[str]
) -> None:
    # TODO: attach metadata to array attrs instead of dataset attrs
    field_metadata = {}
    component_fields = fields_dict(component_type)
    for field_name in field_names:
        if field_name in component_fields:
            field_metadata[field_name] = component_fields[field_name].metadata
    dataset.attrs["field_metadata"] = field_metadata


def _path_to_tuple(field_name: str, path_value: Path) -> tuple:
    if field_name.endswith("_file"):
        base_name = field_name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(path_value))
    return (field_name.upper(), "FILEOUT", str(path_value))


def _hack_spatial_dims(value, field_value):
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


def _get_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple]]]:
    if not isinstance(value, Context):
        return {}

    blocks = {}
    for name, spec in xattree.get_xatspec(type(value)).children.items():
        block_name = spec.metadata["block"]
        match child := getattr(value, name):
            case None:
                continue
            case Component():
                if block_name not in blocks:
                    blocks[block_name] = {}
                blocks[block_name][name] = [_Binding.from_component(child).to_tuple()]
            case MutableMapping():
                if block_name not in blocks:
                    blocks[block_name] = {}
                blocks[block_name][name] = [
                    _Binding.from_component(comp).to_tuple()
                    for comp in child.values()
                    if comp is not None
                ]
            case Iterable():
                if block_name not in blocks:
                    blocks[block_name] = {}
                blocks[block_name][name] = [
                    _Binding.from_component(comp).to_tuple() for comp in child if comp is not None
                ]
            case _:
                raise ValueError(f"Unexpected child type: {type(child)}")

    return blocks


def _has_spatial_dims(value: xr.DataArray) -> bool:
    return any(dim in value.dims for dim in ["nlay", "nrow", "ncol", "nodes"])


def unstructure_component(value: Component) -> dict[str, Any]:
    dfnspec = value.dfn
    xatspec = xattree.get_xatspec(type(value))
    blocks: dict[str, dict[str, Any]] = _get_binding_blocks(value)
    data = xattree.asdict(value)

    for block_name, block in dfnspec.blocks.items():
        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            # Skip child components that have been processed as bindings
            if (
                isinstance(value, Context)
                and (child_spec := xatspec.children.get(field_name, None))
                and child_spec.metadata["block"] == block_name
            ):
                continue

            # convert:
            #   - bools to keywords
            #   - paths to records
            #   - datetime to ISO format
            #   - auxiliary fields to tuples
            #   - xarray DataArrays with 'nper' dimension to kper-sliced datasets
            #     (and split the period data into separate kper-indexed blocks)
            #   - other values to their original form
            match field_value := data[field_name]:
                case None:
                    pass
                case bool():
                    if field_value:  # only write if true
                        blocks[block_name][field_name] = field_value
                case Path():
                    rec = _path_to_tuple(field_name, field_value)
                    field_name = rec[0]  # '_file' suffix dropped
                    blocks[block_name][field_name] = rec
                case datetime():
                    blocks[block_name][field_name] = field_value.isoformat()
                case xr.DataArray():
                    if field_name == "auxiliary":
                        blocks[block_name][field_name] = tuple(field_value.values.tolist())
                    elif "nper" not in field_value.dims:
                        blocks[block_name][field_name] = _hack_spatial_dims(value, field_value)
                    else:
                        period_data = {}
                        period_blocks = {}
                        if _has_spatial_dims(field_value):
                            field_value = _hack_spatial_dims(value, field_value)
                            period_data[field_name] = {
                                kper: field_value.isel(nper=kper)
                                for kper in range(field_value.sizes["nper"])
                            }
                        else:
                            if np.issubdtype(field_value.dtype, np.str_):
                                period_data[field_name] = {
                                    kper: field_value[kper]
                                    for kper in range(field_value.sizes["nper"])
                                    if field_value[kper] is not None
                                }
                            else:
                                if block_name not in period_data:
                                    period_data[block_name] = {}
                                period_data[block_name][field_name] = field_value  # type: ignore

                        dataset = xr.Dataset(period_data[block_name])
                        _attach_field_metadata(
                            dataset, type(value), list(period_data[block_name].keys())
                        )  # type: ignore
                        blocks[block_name] = {block_name: dataset}
                        del period_data[block_name]

                        for arr_name, periods in period_data.items():
                            for kper, arr in periods.items():
                                if isinstance(arr, xr.DataArray):
                                    max = arr.max()
                                    if max == arr.min() and max == FILL_DNODATA:
                                        # don't write empty period blocks unless
                                        # to intentionally reset data
                                        pass
                                    else:
                                        if kper not in period_blocks:
                                            period_blocks[kper] = {}
                                        period_blocks[kper][arr_name] = arr
                                else:
                                    if kper not in period_blocks:
                                        period_blocks[kper] = {}
                                    period_blocks[kper][arr_name] = arr.upper()

                        for kper, block in period_blocks.items():
                            dataset = xr.Dataset(block)
                            _attach_field_metadata(dataset, type(value), list(block.keys()))
                            blocks[f"{block_name} {kper + 1}"] = {block_name: dataset}
                case _:
                    blocks[block_name][field_name] = field_value

    # make sure options block always comes first
    # TODO: blocks should already be sorted here
    if "options" in blocks:
        options_block = blocks.pop("options")
        blocks = {"options": options_block, **blocks}

    # total temporary hack! manually set solutiongroup 1.
    # TODO support multiple solution groups
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    # remove period block
    blocks.pop("period", None)

    return blocks


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
