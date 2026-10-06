from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import xarray as xr

from flopy4.attrs_xarray import child_field_candidates
from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.block import block_list_type
from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.converter.binding import Binding
from flopy4.mf6.item import Item, item_list_type
from flopy4.mf6.package import Package
from flopy4.mf6.period_arrays import all_nodata, is_grid_package
from flopy4.mf6.record import Record
from flopy4.mf6.spec import FileDirection, block_sort_key, blocks_dict, to_field_type


def _path_to_tuple(field: attrs.Attribute, value: Path) -> tuple[str, ...]:
    """A block-level file record's ``KEYWORD FILEIN|FILEOUT <path>`` row. The
    keyword is the field's own ``_keyword`` metadata (see spec.path)."""
    keyword = field.metadata.get("_keyword")
    if not keyword:
        raise ValueError(f"file field {field.name!r} has no _keyword metadata")
    direction: FileDirection | None = field.metadata.get("direction")
    t = [keyword.upper()]
    if direction:
        t.append("FILEOUT" if direction == "out" else "FILEIN")
    t.append(value.as_posix())
    return tuple(t)


def _child_path(child: Component) -> Path:
    """A child's file as its parent's file record names it: relative to the
    simulation workspace, or just the name if it's absolute."""
    path = Path(child.filename or child.default_filename())
    return Path(path.name) if path.is_absolute() else path


def _put_child_file_records(block: dict, field: attrs.Attribute, value: Any) -> None:
    """File records naming children: NCF6 FILEIN <child's file>."""
    children = value if isinstance(value, list) else [value]
    rows = [_path_to_tuple(field, _child_path(c)) for c in children if c is not None]
    if rows and isinstance(value, list):
        block[field.name] = rows
    elif rows:
        block[rows[0][0].lower()] = rows[0]


def _make_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple[str, ...]]]]:
    if not isinstance(value, Context):
        return {}

    blocks = {}  # type: ignore

    for f in attrs.fields(type(value)):  # type: ignore[arg-type]
        # a child() field; a record option is a field like any other
        if not f.metadata.get("child") or child_field_candidates(f) is None:
            continue
        child_name = f.name
        if (child := getattr(value, child_name, None)) is None:
            continue
        block_name = f.metadata.get("block")
        if block_name is None:
            continue
        if block_name not in blocks:
            blocks[block_name] = {}
        if f.metadata.get("_keyword"):
            _put_child_file_records(blocks[block_name], f, child)
            continue
        match child:
            case Component():
                blocks[block_name][child_name] = [Binding.from_component(child).to_tuple()]
            case Mapping():
                bindings = [
                    Binding.from_component(c).to_tuple() for c in child.values() if c is not None
                ]
                if bindings:
                    blocks[block_name][child_name] = bindings
            case Iterable():
                bindings = [Binding.from_component(c).to_tuple() for c in child if c is not None]
                if bindings:
                    blocks[block_name][child_name] = bindings
            case _:
                raise ValueError(f"Unexpected child type: {type(child)}")

    return blocks


def _grid_dims(value: Package) -> tuple[int, tuple[int, ...]]:
    """(nlay, layer shape) for writing period arrays: a layer is (nrow, ncol)
    on a structured grid, else (ncpl,). Empty if the grid isn't known."""
    if not value._period_array_fields():
        return 1, ()
    d = (value.__dict__.get("dims") or {}) | value.resolve_dims(
        "nlay", "nrow", "ncol", "ncpl", "nodes"
    )
    nlay = d.get("nlay", 1)
    if "nrow" in d and "ncol" in d:
        return nlay, (d["nrow"], d["ncol"])
    ncpl = d.get("ncpl") or d.get("nodes", 0) // nlay
    return nlay, (ncpl,) if ncpl else ()


def _period_dataarray(
    name: str, value: Any, meta: Mapping, nlay: int, layer: tuple[int, ...]
) -> xr.DataArray | tuple:
    """One period's array, shaped like the grid so it's written a row per
    line. A layered one is written by layer, with an nlay dim. A time-array
    series' name is written as a reference to it."""
    if isinstance(value, TimeArraySeriesRef):
        return (name.upper(), "TIMEARRAYSERIES", value.name)
    if not hasattr(value, "shape"):
        value = np.asarray(value)
    if meta.get("index"):
        value = _to_file_index(value)
    ncpl = int(np.prod(layer)) if layer else 0
    if meta.get("layered", False) and nlay > 1 and ncpl and value.size == nlay * ncpl:
        dims = ("nlay", *(f"x{i}" for i in range(len(layer))))
        return xr.DataArray(value.reshape(nlay, *layer), dims=dims)
    if ncpl and value.size == ncpl and len(layer) > 1:
        return xr.DataArray(value.reshape(layer))
    return xr.DataArray(value)


def _rows_to_tuples(row_list: list) -> list[tuple]:
    """Convert a list of Item instances to MF6 record tuples via each
    Item's own to_tokens()."""
    return [row.to_tokens() for row in row_list]


def _wrap_array(value: Any) -> xr.DataArray:
    """Wrap a numpy array, scalar, or string default as an xr.DataArray.

    Dask arrays are preserved as-is so the codec writer can stream them
    chunk-by-chunk via array2chunks without materializing the full array.
    """
    if isinstance(value, xr.DataArray):
        return value
    if isinstance(value, np.ndarray):
        return xr.DataArray(value)
    # Preserve dask arrays — the writer streams them via array2chunks.
    try:
        import dask.array as _da

        if isinstance(value, _da.Array):
            return xr.DataArray(value)
    except ImportError:
        pass
    if isinstance(value, str):
        try:
            return xr.DataArray(float(value))
        except (ValueError, TypeError):
            return xr.DataArray(value)
    if isinstance(value, bool):
        return xr.DataArray(int(value))
    if isinstance(value, int):
        return xr.DataArray(value)
    if isinstance(value, float):
        return xr.DataArray(value)
    return xr.DataArray(value)


def _to_file_index(value: Any) -> Any:
    """0-based index values to 1-based. A dask array stays lazy."""
    return (value if hasattr(value, "shape") else np.asarray(value)) + 1


def _normalize_kper(kper: Any) -> int | None:
    """Normalize a period key to a 0-based int; '*' wildcard → 0; invalid → None."""
    if str(kper) == "*":
        return 0
    try:
        return int(kper)
    except (ValueError, TypeError):
        return None


def _unstructure_package(value: Package) -> dict[str, Any]:
    """Unstructure a package into a dict."""
    cls = type(value)
    blocks: dict[str, dict[str, Any]] = {}
    write_if_empty_set: set[str] = set()
    spd_period: dict[int, list[tuple]] = {}
    readarray_period: dict[int, dict[str, Any]] = {}
    # per period, the (non-aux) array fields given, and those all DNODATA
    stress_period: dict[int, set[str]] = {}
    nodata_period: dict[int, set[str]] = {}
    grid_dims = _grid_dims(value)
    grid = is_grid_package(cls)
    fill_forward_block: str | None = None

    for f in attrs.fields(cls):  # type: ignore[arg-type]
        meta = f.metadata
        block_name = meta.get("block")
        if not block_name:
            continue

        if meta.get("write_if_empty"):
            write_if_empty_set.add(block_name)
            blocks.setdefault(block_name, {})

        attr_name = f.alias if (f.alias and f.name.startswith("_")) else f.name
        field_value = getattr(value, attr_name, None)
        if field_value is None:
            continue

        dfn_type = to_field_type(f.type)

        # fill-forward block
        if meta.get("fill_forward"):
            fill_forward_block = block_name
            # dynamically named arrays (RCHA's aux): {kper: {name: array}}, each
            # written under its name
            if meta.get("fk"):
                for kper, arrays in field_value.items():
                    for name, arr in arrays.items():
                        readarray_period.setdefault(kper, {})[name] = _period_dataarray(
                            name, arr, meta, *grid_dims
                        )
                continue
            # arrays: {kper: array}
            if item_list_type(f.type) is None:
                for kper, arr in field_value.items():
                    readarray_period.setdefault(kper, {})[f.name] = _period_dataarray(
                        f.name, arr, meta, *grid_dims
                    )
                    if grid and all_nodata(arr):
                        nodata_period.setdefault(kper, set()).add(f.name)
                    stress_period.setdefault(kper, set()).add(f.name)
                continue
            # list: dict[int, list[Item]]
            if not isinstance(field_value, dict):
                continue
            for kper, row_list in field_value.items():
                kper_int = _normalize_kper(kper)
                if kper_int is None:
                    continue
                rows = (
                    _rows_to_tuples(row_list)
                    if isinstance(row_list, list) and row_list and isinstance(row_list[0], Item)
                    else []
                )
                spd_period.setdefault(kper_int, []).extend(rows)
            continue

        # blocks repeating under a record header (OBS's CONTINUOUS), one per
        # header: list[Block]
        if (block_cls := block_list_type(f.type)) is not None:
            _, list_name, _ = block_cls.parts()
            for block in field_value:
                key = " ".join([block_name, *map(str, block.header_tokens())])
                blocks[key] = {list_name: _rows_to_tuples(getattr(block, list_name))}
            continue

        if isinstance(field_value, dict):
            array_key = f.name if meta.get("tagged") else ""
            for tval, arr in field_value.items():
                blocks[f"{block_name} {tval}"] = {array_key: _wrap_array(arr)}
            continue

        # non-fill-forward block
        if block_name not in blocks:
            blocks[block_name] = {}

        if dfn_type == "keyword":
            if field_value:
                blocks[block_name][f.name] = field_value

        elif isinstance(field_value, list) and field_value and isinstance(field_value[0], Path):
            # A list of file records (DFN tagged list): one line each.
            blocks[block_name][f.name] = [_path_to_tuple(f, v) for v in field_value]

        elif meta.get("direction") and isinstance(field_value, Path):
            t = _path_to_tuple(f, field_value)
            blocks[block_name][t[0].lower()] = t

        elif meta.get("child") and meta.get("_keyword"):
            _put_child_file_records(blocks[block_name], f, field_value)

        elif isinstance(field_value, list) and field_value and isinstance(field_value[0], Item):
            blocks[block_name][f.name] = _rows_to_tuples(field_value)

        elif isinstance(field_value, list) and field_value and isinstance(field_value[0], tuple):
            blocks[block_name][f.name] = field_value

        elif meta.get("shape") and not isinstance(field_value, bool):
            if meta.get("index"):
                field_value = _to_file_index(field_value)
            if meta["shape"]:
                # reshape layered array to (nlay, ncpl) with named
                # dims to signal the writer to use layered format
                if (
                    meta.get("layered")
                    and hasattr(field_value, "reshape")
                    and not isinstance(field_value, xr.DataArray)
                ):
                    _get_dims = getattr(value, "get_dims", None)
                    _dims_d = _get_dims() if _get_dims else {}
                    _nlay = _dims_d.get("nlay", 0)
                    _ncpl = _dims_d.get("ncpl", 0)
                    if _nlay > 1 and _ncpl > 0 and field_value.size == _nlay * _ncpl:
                        blocks[block_name][f.name] = xr.DataArray(
                            field_value.reshape(_nlay, _ncpl),
                            dims=("nlay", "ncpl"),
                        )
                        continue
                blocks[block_name][f.name] = _wrap_array(field_value)

        elif isinstance(field_value, np.ndarray) and field_value.dtype.kind == "U":
            # An inline string array (AUXILIARY's names): one line.
            if field_value.size:
                blocks[block_name][f.name] = (f.name.upper(), *map(str, field_value))

        elif isinstance(field_value, Record):
            blocks[block_name][f.name] = field_value.to_tokens()

        elif dfn_type in ("integer", "double", "double precision"):
            blocks[block_name][f.name] = field_value

        elif dfn_type == "string" and field_value:
            blocks[block_name][f.name] = field_value

    # `maxbound` is a computed property on some classes, not a real field
    if isinstance(getattr(cls, "maxbound", None), property):
        maxbound = value.maxbound  # type: ignore[attr-defined]
        if maxbound:
            blocks.setdefault("dimensions", {})["maxbound"] = maxbound

    # sort filled blocks by label
    if fill_forward_block is not None:
        for kper in sorted(spd_period.keys()):
            key = f"{fill_forward_block} {kper + 1}"
            blocks[key] = {fill_forward_block: spd_period[kper]}

        # One block per period any array is given in. A grid package's
        # period whose stress arrays are all DNODATA clears every boundary:
        # an empty block.
        for kper in sorted(readarray_period.keys()):
            key = f"{fill_forward_block} {kper + 1}"
            if grid and stress_period.get(kper) and nodata_period.get(kper) == stress_period[kper]:
                blocks[key] = {}
                write_if_empty_set.add(key)
            else:
                blocks[key] = readarray_period[kper]

    return {
        name: block
        for name, block in sorted(blocks.items(), key=block_sort_key)
        if block or name in write_if_empty_set
    }


def unstructure_component(value: Component) -> dict[str, Any]:
    # TODO unify _unstructure_package/_unstructure_component into one path
    if isinstance(value, Package):
        return _unstructure_package(value)
    return _unstructure_component(value)


def _unstructure_component(value: Component) -> dict[str, Any]:
    """Unstructure an internal-node component (Gwf, Simulation, etc.) with
    attrs-typed child fields, including its child binding blocks."""
    blockspec = blocks_dict(type(value))
    blocks: dict[str, dict[str, Any]] = {}
    fields_by_name = {f.name: f for f in attrs.fields(type(value))}  # type: ignore[arg-type]

    # create child component binding blocks
    blocks.update(_make_binding_blocks(value))

    for block_name, block in blockspec.items():
        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            # Skip child components already processed as bindings
            field = fields_by_name.get(field_name)
            if (
                isinstance(value, Context)
                and field is not None
                and field.metadata.get("child")
                and child_field_candidates(field) is not None
                and field.metadata.get("block") == block_name
            ):
                continue

            raw_value = getattr(value, field_name, None)
            if raw_value is None:
                continue
            # a private field's file name is its alias (Gwf's _list: LIST), a
            # renamed keyword's is its name without the underscore (continue_)
            key = field.alias if field is not None and field_name.startswith("_") else field_name
            key = key.removesuffix("_")
            if isinstance(raw_value, Record):
                blocks[block_name][key] = raw_value.to_tokens()
                continue

            # Dispatch on field value type
            match field_value := raw_value:
                case None:
                    continue
                case bool():
                    if field_value:
                        blocks[block_name][key] = field_value
                case Path():
                    assert field is not None  # field_name comes from blocks_dict(type(value))
                    t = _path_to_tuple(field, field_value)
                    blocks[block_name][t[0]] = t
                case datetime():
                    blocks[block_name][key] = field_value.isoformat()
                case _:
                    blocks[block_name][key] = field_value

    blocks = dict(sorted(blocks.items(), key=block_sort_key))

    # total temporary hack! manually set solutiongroup 1.
    # TODO still need to support multiple..
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return {name: block for name, block in blocks.items()}
