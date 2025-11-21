from pathlib import Path
from typing import Any

import cattr
import xattree
from cattr import Converter
from cattrs.gen import make_hetero_tuple_unstructure_fn
from xattree import get_xatspec

from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter.egress.unstructure import (
    unstructure_component,
)
from flopy4.mf6.converter.ingress.dim_context import DimContext, _dim_context
from flopy4.mf6.converter.ingress.structure import structure_array, structure_keyword
from flopy4.mf6.dimensions import DimensionProvider
from flopy4.mf6.gwf.oc import Oc
from flopy4.mf6.spec import fields_dict as fields_dict

__all__ = [
    "structure",
    "unstructure",
    "structure_array",
    "unstructure_array",
    "structure_keyword",
    "COMPONENT_CONVERTER",
]


def _make_converter() -> Converter:
    converter = Converter(unstruct_strat=cattr.UnstructureStrategy.AS_TUPLE)
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    converter.register_unstructure_hook(
        Oc.PrintSaveSetting, make_hetero_tuple_unstructure_fn(Oc.PrintSaveSetting, converter)
    )
    converter.register_unstructure_hook(
        Oc.Steps, make_hetero_tuple_unstructure_fn(Oc.Steps, converter)
    )
    return converter


COMPONENT_CONVERTER = _make_converter()


def _map_block_names_to_attributes(data: dict, cls: type) -> dict:
    """
    Map block names in parsed data to attribute names using xattree metadata.

    Handles:
    - Exact block name matches (e.g., 'timing' -> 'tdis')
    - Recarray blocks (e.g., 'perioddata' -> split into ['perlen', 'nstp', 'tsmult'])
    - Numbered blocks (e.g., 'solutiongroup 1', 'solutiongroup 2' -> 'solutions')
    - Direct attribute names (passed through unchanged)

    Parameters
    ----------
    data : dict
        Parsed data with block names as keys
    cls : type
        Component class with xattree metadata

    Returns
    -------
    dict
        Data with attribute names as keys
    """
    import numpy as np

    # DEBUG
    # print(f"\n=== _map_block_names_to_attributes for {cls.__name__} ===")
    # print(f"Input keys: {list(data.keys())}")

    # Get xattree spec to find block name -> attribute name mappings
    spec = get_xatspec(cls)

    # Build mapping from xattree field metadata (supports multiple fields per block)
    block_to_attrs: dict[str, list[str]] = {}
    for field_name, field_spec in spec.flat.items():
        if (
            hasattr(field_spec, "metadata")
            and field_spec.metadata is not None
            and "block" in field_spec.metadata
        ):
            block_name = field_spec.metadata["block"]
            if block_name not in block_to_attrs:
                block_to_attrs[block_name] = []
            block_to_attrs[block_name].append(field_name)

    mapped = {}

    for key, value in data.items():
        # Try exact block name match
        if key in block_to_attrs:
            attr_names = block_to_attrs[key]

            if len(attr_names) == 1:
                # Single field for this block
                if isinstance(value, dict):
                    # For blocks like options/dimensions with nested dicts,
                    # extract the field value if it matches the attr name
                    if attr_names[0] in value:
                        mapped[attr_names[0]] = value[attr_names[0]]
                    else:
                        # Dict doesn't contain expected key - use whole dict
                        mapped[attr_names[0]] = value
                else:
                    # Direct mapping for non-dict values
                    mapped[attr_names[0]] = value
            else:
                # Multiple fields for this block
                # Check if all fields are array types - if so, pass through for array converter
                from xattree import Array

                all_arrays = all(isinstance(spec.flat.get(attr), Array) for attr in attr_names)
                if all_arrays:
                    # Block contains only array fields
                    if isinstance(value, dict):
                        # BasicTransformer returns dicts like
                        # {'top': xr.DataArray, 'botm': xr.DataArray}
                        # Pass through for array converter
                        mapped[key] = value
                    elif isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
                        # Tabular array data - split into columns
                        # Example: perioddata [[perlen, nstp, tsmult], ...]
                        try:
                            arr = np.array(value)
                            for i, attr_name in enumerate(attr_names):
                                if i < arr.shape[1]:
                                    mapped[attr_name] = arr[:, i].tolist()
                                else:
                                    # Not enough columns for this field
                                    mapped[attr_name] = None
                        except ValueError:
                            # Inhomogeneous array - can't convert to numpy array
                            # Fall back to assigning whole list to first field
                            mapped[attr_names[0]] = value
                    else:
                        # Fallback: value is not structured, assign to first field
                        mapped[attr_names[0]] = value
                elif isinstance(value, dict):
                    # Options/dimensions block with multiple fields - unpack dict
                    for attr_name in attr_names:
                        if attr_name in value:
                            mapped[attr_name] = value[attr_name]
                elif isinstance(value, list):
                    # Could be recarray format OR binding list format
                    # Check if this is a known binding block (by name)
                    is_binding_block = key in ("packages", "models", "exchanges", "solutiongroup")

                    if is_binding_block:
                        # Binding blocks: packages, models, exchanges, solutiongroup
                        if key == "packages" and value and isinstance(value[0], (list, tuple)):
                            # Packages block - route each binding to its field based on package name
                            # Binding format: [type, filename, package_name]
                            for binding in value:
                                if len(binding) >= 3:
                                    pkg_name = binding[2]  # Package name is 3rd element
                                    # Remove numeric suffix (e.g., "wel_0" -> "wel")
                                    base_pkg_name = (
                                        pkg_name.rsplit("_", 1)[0] if "_" in pkg_name else pkg_name
                                    )

                                    # Handle discretization package aliases: dis, disv, disu -> dis
                                    # only necessary because we put all the discretization packages
                                    # under a dis field in the model, instead of separate disv/disu
                                    if base_pkg_name in ("disv", "disu") and "dis" in attr_names:
                                        base_pkg_name = "dis"

                                    # Find matching field
                                    if base_pkg_name in attr_names:
                                        # Check if field expects a list (multiple pkgs of same type)
                                        if base_pkg_name not in mapped:
                                            # Initialize: check if field type is list
                                            # For now, just initialize as single binding
                                            mapped[base_pkg_name] = binding
                                        elif isinstance(
                                            mapped[base_pkg_name], list
                                        ) and not isinstance(mapped[base_pkg_name][0], str):
                                            # Already a list of bindings - append
                                            mapped[base_pkg_name].append(binding)
                                        else:
                                            # Convert single binding to list of bindings
                                            mapped[base_pkg_name] = [mapped[base_pkg_name], binding]
                        else:
                            # Other binding blocks (models, exchanges, solutiongroup)
                            # Pass through for binding resolution - assign to first field
                            mapped[attr_names[0]] = value
                    else:
                        # Recarray format: [[col0, col1, col2], ...]
                        # Split into columns, one per field
                        try:
                            arr = np.array(value)
                            for i, attr_name in enumerate(attr_names):
                                if i < arr.shape[1]:
                                    mapped[attr_name] = arr[:, i].tolist()
                                else:
                                    # Not enough columns for this field
                                    mapped[attr_name] = None
                        except ValueError:
                            # Inhomogeneous array - can't convert to numpy array
                            # Fall back to assigning whole list to first field
                            mapped[attr_names[0]] = value
                else:
                    # Can't split - assign same value to first field only
                    # (This shouldn't happen with proper recarray data)
                    mapped[attr_names[0]] = value
        else:
            # Try numbered block (e.g., "solutiongroup 1" -> "solutiongroup")
            parts = key.split(" ", 1)
            if len(parts) == 2 and parts[1].replace(".", "", 1).isdigit():
                base_name = parts[0]
                if base_name in block_to_attrs:
                    attr_names = block_to_attrs[base_name]
                    attr_name = attr_names[0]  # Use first field for numbered blocks
                    # Aggregate numbered blocks into a list
                    if attr_name not in mapped:
                        mapped[attr_name] = []
                    if isinstance(value, list):
                        mapped[attr_name].extend(value)
                    else:
                        mapped[attr_name].append(value)
                else:
                    # Base name not found - use key as-is
                    mapped[key] = value
            else:
                # Not a numbered block - use key as-is
                mapped[key] = value

    return mapped


def _extract_dimensions(data: dict, cls: type) -> dict[str, int]:
    """
    Extract dimension values from parsed data.

    Dimension fields are identified by having xattree metadata with
    kind='dim' (e.g., nper, nlay, nrow, ncol).

    Handles both:
    - Top-level dimension values: {'nper': 1}
    - Nested block values: {'dimensions': {'nper': 1}}
    - Block-mapped nested values: {'nper': {'nper': 1}}

    Parameters
    ----------
    data : dict
        Parsed data with attribute names as keys
    cls : type
        Component class with xattree metadata

    Returns
    -------
    dict[str, int]
        Dimension name to value mapping
    """

    dims: dict[str, int] = {}

    if not xattree.has(cls):
        return dims

    try:
        fields = fields_dict(cls)
    except (ValueError, AttributeError):
        return dims

    # Collect dimension field names (fields with xattree.kind == 'dim')
    dim_fields = set()
    for field_name, attr in fields.items():
        xatmeta = attr.metadata.get("xattree", {})
        if xatmeta.get("kind") == "dim":
            dim_fields.add(field_name)

    if not dim_fields:
        return dims

    # Helper to extract int value
    def try_extract_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        elif isinstance(value, dict):
            # Handle nested dicts like {'nper': 1} or {'nper': {'nper': 1}}
            for k, v in value.items():
                if k in dim_fields:
                    result = try_extract_int(v)
                    if result is not None:
                        return result
        return None

    # Search for dimension values in data
    for field_name in dim_fields:
        # Check direct field name
        if field_name in data:
            value = try_extract_int(data[field_name])
            if value is not None:
                dims[field_name] = value

    # Also check common block names that might contain dimensions
    for block_name in ("dimensions", "griddata"):
        if block_name in data and isinstance(data[block_name], dict):
            for field_name in dim_fields:
                if field_name in data[block_name]:
                    value = try_extract_int(data[block_name][field_name])
                    if value is not None:
                        dims[field_name] = value

    return dims


def _dict_to_binding_tuple(binding_dict: dict) -> list:
    """
    Convert binding dict format to tuple format.

    Handles:
    - Model bindings:
        {'mtype': 'gwf6', 'mfname': 'file.nam', 'mname': 'modelname'}
      → ['gwf6', 'file.nam', 'modelname']
    - Solution bindings:
        {'slntype': 'ims6', 'slnfname': 'file.ims', 'slnmnames': ['m1', 'm2']}
      → ['ims6', 'file.ims', 'm1', 'm2']
    - Exchange bindings:
        {'exgtype': 'gwf6-gwf6', 'exgfname': 'file.exg', 'exgmnamea': 'ma', 'exgmnameb': 'mb'}
      → ['gwf6-gwf6', 'file.exg', 'ma', 'mb']

    Parameters
    ----------
    binding_dict : dict
        Binding in dict format

    Returns
    -------
    list
        Binding in tuple format [type, fname, *terms]
    """
    # Detect binding type based on keys
    if "mtype" in binding_dict:
        # Model binding
        return [
            binding_dict["mtype"],
            binding_dict["mfname"],
            binding_dict.get("mname", ""),
        ]
    elif "slntype" in binding_dict:
        # Solution binding
        slnmnames = binding_dict.get("slnmnames", [])
        if isinstance(slnmnames, str):
            slnmnames = [slnmnames]
        return [binding_dict["slntype"], binding_dict["slnfname"], *slnmnames]
    elif "exgtype" in binding_dict:
        # Exchange binding
        return [
            binding_dict["exgtype"],
            binding_dict["exgfname"],
            binding_dict.get("exgmnamea", ""),
            binding_dict.get("exgmnameb", ""),
        ]
    else:
        # Unknown format - try to extract type and fname
        type_key = next((k for k in binding_dict if k.lower().endswith("type")), None)
        fname_key = next((k for k in binding_dict if "fname" in k.lower()), None)
        if type_key and fname_key:
            return [binding_dict[type_key], binding_dict[fname_key]]
        raise ValueError(f"Cannot convert binding dict to tuple: {binding_dict}")


def _update_dim_context_from_component(component: Component) -> None:
    """
    Update active DimContext if component provides dimensions.

    When a DimensionProvider component is loaded, extract its dimensions
    and add them to the active DimContext so subsequent sibling components
    can use them (e.g., DIS provides grid dims for IC package).

    Parameters
    ----------
    component : Component
        Loaded component to check for dimensions
    """
    if isinstance(component, DimensionProvider):
        component_dims = component.get_dims()
        if component_dims:
            # Merge with current context
            current = _dim_context.get().copy()
            current.update(component_dims)
            _dim_context.set(current)


def _resolve_bindings_in_dict(data: dict, workspace: Path, target_type: type) -> dict:
    """
    Resolve binding tuples in data dict to component instances.

    Detects:
    - Lists of binding tuples (e.g., [['gwf6', 'file.nam', 'name']])
    - Scalar bindings (e.g., {'tdis6': 'simulation.tdis'})

    Parameters
    ----------
    data : dict
        Data dict with potential binding tuples
    workspace : Path
        Workspace directory for loading child components
    target_type : type
        Target component type (e.g., Simulation)

    Returns
    -------
    dict
        Data with bindings resolved to component instances
    """
    resolved = dict(data)  # Copy

    # Get xattree spec to understand expected field types
    spec = get_xatspec(target_type)

    for field_name, field_spec in spec.flat.items():
        if field_name not in resolved:
            continue

        value = resolved[field_name]

        # Handle scalar bindings: {'tdis6': 'filename.tdis'}
        # These are dicts with a single key ending in '6'
        if isinstance(value, dict) and len(value) == 1:
            binding_key = next(iter(value.keys()))
            if isinstance(binding_key, str) and binding_key.lower().endswith("6"):
                binding_fname = value[binding_key]
                binding_tuple = [binding_key, binding_fname]
                component = Binding.to_component(binding_tuple, workspace)
                _update_dim_context_from_component(component)
                resolved[field_name] = component
                continue

        # Handle single binding tuples: ['TYPE6', 'filename', 'name']
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], str)
            and value[0].upper().endswith("6")
            and not isinstance(value[1], (list, tuple))  # Not a list of bindings
        ):
            # This is a single binding tuple - resolve it
            binding_tuple = list(value)
            component = Binding.to_component(binding_tuple, workspace)
            _update_dim_context_from_component(component)
            resolved[field_name] = component
            continue

        # Handle list bindings
        if not isinstance(value, list):
            continue

        # Handle empty lists - convert to empty dict if field expects a dict
        if not value:
            # Check if field expects a dict (child fields like models, solutions, exchanges)
            # These are known binding blocks that should be dicts
            if field_name in ("models", "solutions", "exchanges"):
                resolved[field_name] = {}
            continue

        # Check if this looks like a list of binding tuples or binding dicts
        # Binding tuples have:
        #   - First element is a list/tuple with 2+ elements
        #   - First element of that is a string ending with '6' (like 'gwf6', 'tdis6')
        # Binding dicts have:
        #   - First element is a dict with keys like mtype/slntype ending with '6'
        first_item = value[0]
        is_binding_tuples = (
            isinstance(first_item, (list, tuple))
            and len(first_item) >= 2
            and isinstance(first_item[0], str)
            and first_item[0].lower().endswith("6")
        )
        is_binding_dicts = isinstance(first_item, dict) and any(
            k.lower().endswith("type") and isinstance(v, str) and v.lower().endswith("6")
            for k, v in first_item.items()
        )

        if is_binding_tuples or is_binding_dicts:
            # This is a list of bindings - resolve each to a component instance
            resolved_components = {}
            for binding_data in value:
                # Convert dict format to tuple if needed
                if isinstance(binding_data, dict):
                    binding_tuple = _dict_to_binding_tuple(binding_data)
                else:
                    binding_tuple = binding_data

                component = Binding.to_component(binding_tuple, workspace)
                _update_dim_context_from_component(component)
                # Use component name as key (most bindings include name in terms)
                if hasattr(component, "name") and component.name:
                    resolved_components[component.name] = component
                else:
                    # Fallback: use filename as key
                    resolved_components[component.filename] = component

            resolved[field_name] = resolved_components

    return resolved


def structure(
    data: dict[str, Any], path: Path, component_type: type[Component] | None = None
) -> Component:
    """
    Structure parsed data into a Component instance.

    Parameters
    ----------
    data : dict
        Parsed component data
    path : Path
        Path to the component file (for setting workspace/filename)
    component_type : type[Component], optional
        Concrete component class to instantiate. If not provided, uses Component base class.

    Returns
    -------
    Component
        Structured component instance
    """
    # Use provided type or fall back to Component base class
    target_type = component_type if component_type is not None else Component

    # Map block names to attribute names if this is an xattree type
    if xattree.has(target_type):
        data = _map_block_names_to_attributes(data, target_type)

        # Get valid field names for this type
        spec = get_xatspec(target_type)
        valid_fields = set(spec.flat.keys())

        # Filter to only valid fields, excluding workspace (set after)
        data_for_structuring = {
            k: v for k, v in data.items() if k in valid_fields and k != "workspace"
        }

        # Resolve binding tuples to component instances (pre-construction)
        data_for_structuring = _resolve_bindings_in_dict(
            data_for_structuring, path.parent, target_type
        )

        # Convert field names to init parameter aliases
        # (attrs strips leading underscores: _list field -> list parameter)
        import attrs

        field_to_alias = {}
        if attrs.has(target_type):
            for field in attrs.fields(target_type):
                if field.alias != field.name:
                    field_to_alias[field.name] = field.alias

        if field_to_alias:
            data_for_structuring = {
                field_to_alias.get(k, k): v for k, v in data_for_structuring.items()
            }
    else:
        # Exclude workspace from structuring - will be set afterwards
        data_for_structuring = {k: v for k, v in data.items() if k != "workspace"}

    # Extract dimension values from parsed data and set in context.
    # This allows array converters to resolve dimensions during __init__
    # before the dimension fields are actually assigned to self.
    dims = _extract_dimensions(data_for_structuring, target_type)

    # Merge with parent context dimensions
    # (e.g., sibling packages inherit from parent model's context)
    parent_dims = DimContext.current()
    if parent_dims:
        # Parent dims have lower priority than component's own dims
        dims = parent_dims | dims

    # Also extract dimensions from child components that have already been loaded
    # (e.g., Dis grid dimensions for packages like IC that need them)

    for value in data_for_structuring.values():
        if isinstance(value, Component) and isinstance(value, DimensionProvider):
            child_dims = value.get_dims()
            dims.update(child_dims)

    # Compute derived dimensions (same logic as in structure.py _resolve_dimensions)
    # This must happen before xattree validation
    if "nodes" not in dims and "nlay" in dims and "nrow" in dims and "ncol" in dims:
        dims["nodes"] = dims["nlay"] * dims["nrow"] * dims["ncol"]
    if "nodes2d" not in dims and "nrow" in dims and "ncol" in dims:
        dims["nodes2d"] = dims["nrow"] * dims["ncol"]

    # Use context manager to provide dimensions during component construction
    # DimContext makes dimensions available to our custom converters (structure_array, etc.)
    with DimContext(dims):
        # Filter out fields with init=False before passing to constructor
        # These fields are computed in __attrs_post_init__ and cannot be passed to __init__
        if attrs.has(target_type):
            init_fields = {f.name for f in attrs.fields(target_type) if f.init}
            filtered_data = {
                k: v for k, v in data_for_structuring.items() if k in init_fields or k == "dims"
            }
        else:
            filtered_data = data_for_structuring

        # Structure the component
        if xattree.has(target_type):
            # Pass dims to xattree's dims parameter for validation
            # Note: dims that conflict with field names are handled by xattree
            component = target_type(**filtered_data, dims=dims)  # type: ignore
        else:
            component = COMPONENT_CONVERTER.structure(filtered_data, target_type)

    # Set workspace and filename after construction
    if isinstance(component, Context):
        component.workspace = path.parent
    component.filename = path.name
    return component


def unstructure(component: Component) -> dict[str, Any]:
    return COMPONENT_CONVERTER.unstructure(component)
