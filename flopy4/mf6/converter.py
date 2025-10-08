from collections.abc import MutableMapping
from datetime import datetime
from pathlib import Path
from typing import Any

import xarray as xr
import xattree
from attrs import define
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import fields_dict, get_blocks


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
    blockspec = get_blocks(value.dfn)
    blocks: dict[str, dict[str, Any]] = {}
    xatspec = xattree.get_xatspec(type(value))

    # Handle child component bindings before converting to dict
    if isinstance(value, Context):
        for field_name, child_spec in xatspec.children.items():
            if hasattr(child_spec, "metadata") and "block" in child_spec.metadata:  # type: ignore
                block_name = child_spec.metadata["block"]  # type: ignore
                field_value = getattr(value, field_name, None)

                if block_name not in blocks:
                    blocks[block_name] = {}

                if isinstance(field_value, Component):
                    components = [_Binding.from_component(field_value).to_tuple()]
                elif isinstance(field_value, MutableMapping):
                    components = [
                        _Binding.from_component(comp).to_tuple()
                        for comp in field_value.values()
                        if comp is not None
                    ]
                elif isinstance(field_value, (list, tuple)):
                    components = [
                        _Binding.from_component(comp).to_tuple()
                        for comp in field_value
                        if comp is not None
                    ]
                else:
                    continue

                if components:
                    blocks[block_name][field_name] = components

    data = xattree.asdict(value)

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
                    # terrible hack to convert flat nodes dimension to 3d structured dims.
                    # long term solution for this is to use a custom xarray index. filters
                    # should then have access to all dimensions needed.
                    dims_ = set(field_value.dims).copy()
                    dims_.remove("nper")
                    if dims_ == {"nnodes"}:
                        parent = value.parent
                        field_value = xr.DataArray(
                            field_value.data.reshape(
                                (
                                    field_value.sizes["nper"],
                                    parent.dims["nlay"],
                                    parent.dims["ncol"],
                                    parent.dims["nrow"],
                                )
                            ),
                            dims=("nper", "nlay", "ncol", "nrow"),
                            coords={
                                "nper": field_value.coords["nper"],
                                "nlay": range(parent.dims["nlay"]),
                                "ncol": range(parent.dims["ncol"]),
                                "nrow": range(parent.dims["nrow"]),
                            },
                            name=field_value.name,
                        )

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

    # make sure options block always comes first
    if "options" in blocks:
        options_block = blocks.pop("options")
        blocks = {"options": options_block, **blocks}

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
