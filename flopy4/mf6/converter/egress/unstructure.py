from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import xarray as xr
import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.converter.binding import Binding
from flopy4.mf6.item import Item
from flopy4.mf6.package import Package
from flopy4.mf6.record import Record
from flopy4.mf6.spec import FileDirection, block_sort_key, blocks_dict, to_field_type


def _path_to_tuple(name: str, value: Path, direction: FileDirection) -> tuple[str, ...]:
    for suffix in ("_input_file", "_filerecord", "_file"):
        if name.endswith(suffix):
            prefix = name[: -len(suffix)]
            break
    else:
        prefix = name
    t = [prefix.upper()]
    if direction:
        t.append("FILEOUT" if direction == "out" else "FILEIN")
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


def _normalize_kper(kper: Any) -> int | None:
    """Normalize a period key to a 0-based int; '*' wildcard → 0; invalid → None."""
    if str(kper) == "*":
        return 0
    try:
        return int(kper)
    except (ValueError, TypeError):
        return None


def _unstructure_package(value: Package) -> dict[str, Any]:
    """Unstructure a package (attrs-based, non-xattree)."""
    cls = type(value)
    blocks: dict[str, dict[str, Any]] = {}
    # Block names that must appear in output even when empty (e.g. SSM SOURCES).
    always_emit_set: set[str] = set()
    # Stress-period recarray fields: {kper: [(cellid, val, ...), ...]}
    spd_period: dict[int, list[tuple]] = {}
    # READARRAY period fields (G/A variants): {kper: {field_name: xr.DataArray}}
    readarray_period: dict[int, dict[str, Any]] = {}
    try:
        from dask.array import Array as _DaskArray
    except ImportError:
        _DaskArray = type(None)  # type: ignore[misc,assignment]

    for f in attrs.fields(cls):  # type: ignore[arg-type]
        meta = f.metadata
        block_name = meta.get("block")
        if not block_name:
            continue

        if meta.get("always_emit"):
            always_emit_set.add(block_name)
            blocks.setdefault(block_name, {})

        # Private alias fields (e.g. _stress_period_data) → access via public name
        attr_name = f.alias if (f.alias and f.name.startswith("_")) else f.name
        field_value = getattr(value, attr_name, None)
        if field_value is None:
            continue

        dfn_type = to_field_type(f.type)

        # ── PERIOD block ────────────────────────────────────────────────────────
        if block_name == "period":
            # READARRAY period field (G/A variants): ndarray shaped (nper, ...)
            is_readarray = meta.get("reader") == "readarray"
            if is_readarray and isinstance(field_value, (np.ndarray, _DaskArray)):
                is_layered = meta.get("layered", False)
                nper = field_value.shape[0]
                # Aux field: shape (nper, ncpl, naux) → emit one named block per
                # aux variable so MF6 reads e.g. "TRACER" not "AUX".
                if f.name == "aux" and field_value.ndim == 3:
                    aux_names: list[str] = list(getattr(value, "auxiliary", None) or [])
                    naux = field_value.shape[2]
                    for kper in range(nper):
                        for i in range(naux):
                            col = field_value[kper, :, i]
                            aux_key = aux_names[i] if i < len(aux_names) else f"aux{i}"
                            readarray_period.setdefault(kper, {})[aux_key] = xr.DataArray(col)
                    continue
                for kper in range(nper):
                    layer_slice = field_value[kper]
                    if is_layered and layer_slice.ndim >= 2:
                        extra_dims = tuple(f"x{i}" for i in range(layer_slice.ndim - 1))
                        da = xr.DataArray(layer_slice, dims=("nlay",) + extra_dims)
                    else:
                        da = xr.DataArray(layer_slice)
                    readarray_period.setdefault(kper, {})[f.name] = da
                continue
            if not isinstance(field_value, dict):
                continue
            # Stress-period Item list: dict[int, list[Item]]
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

        # ── Non-period blocks ───────────────────────────────────────────────────
        if block_name not in blocks:
            blocks[block_name] = {}

        if dfn_type == "keyword":
            if field_value:
                blocks[block_name][f.name] = field_value

        elif meta.get("direction") and isinstance(field_value, Path):
            t = _path_to_tuple(f.name, field_value, meta.get("direction", "out"))
            blocks[block_name][t[0].lower()] = t

        elif isinstance(field_value, list) and field_value and isinstance(field_value[0], Item):
            # packagedata / connectiondata / etc. -- list[ItemClass] block
            blocks[block_name][f.name] = _rows_to_tuples(field_value)

        elif isinstance(field_value, list) and field_value and isinstance(field_value[0], tuple):
            # Pre-formatted list of row tuples (e.g. cell2d).
            blocks[block_name][f.name] = field_value

        elif meta.get("shape") and not isinstance(field_value, bool):
            # griddata-style array (shape is a non-empty tuple)
            if meta["shape"]:
                # For layered arrays, reshape to (nlay, ncpl) with named dims
                # so the writer can detect and emit LAYERED format.
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

        elif f.name == "auxiliary" and isinstance(field_value, list):
            blocks[block_name][f.name] = ("AUXILIARY",) + tuple(field_value)

        elif isinstance(field_value, Record):
            # Inner-class record (e.g. Oc.Headprint)
            blocks[block_name][f.name] = field_value.to_tokens()

        elif dfn_type in ("integer", "double", "double precision"):
            if field_value == 0 and meta.get("auto_from"):
                continue
            blocks[block_name][f.name] = field_value

        elif dfn_type == "string" and field_value:
            blocks[block_name][f.name] = field_value

    # Assemble period blocks (stress-period Item rows), in kper order.
    for kper in sorted(spd_period.keys()):
        key = f"period {kper + 1}"
        blocks[key] = {"period": spd_period[kper]}

    # READARRAY period blocks (G/A variants): each kper gets its own period block.
    # Fields where every value is FILL_DNODATA are skipped; if no fields remain
    # for a period, the block is omitted entirely so MF6 fill-forwards from the
    # previous period instead of treating 3e30 as a real array value.
    for kper in sorted(readarray_period.keys()):
        key = f"period {kper + 1}"
        ra_block = blocks.get(key, {})
        for field_name, da in readarray_period[kper].items():
            if not np.all(da.values == FILL_DNODATA):
                ra_block[field_name] = da
        if ra_block:
            blocks[key] = ra_block

    return {
        name: block
        for name, block in sorted(blocks.items(), key=block_sort_key)
        if block or name in always_emit_set
    }


def unstructure_component(value: Component) -> dict[str, Any]:
    # temporary; TODO unify once xattree is fully gone
    if isinstance(value, Package):
        return _unstructure_package(value)
    return _unstructure_component(value)


def _unstructure_component(value: Component) -> dict[str, Any]:
    """Unstructure a xattree component (Gwf, Simulation, etc.)."""
    blockspec = blocks_dict(type(value))
    blocks: dict[str, dict[str, Any]] = {}
    xatspec = xattree.get_xatspec(type(value))
    data = xattree.asdict(value)

    # create child component binding blocks
    blocks.update(_make_binding_blocks(value))

    for block_name, block in blockspec.items():
        if block_name not in blocks:
            blocks[block_name] = {}

        for field_name in block.keys():
            # Skip child components already processed as bindings
            if isinstance(value, Context) and field_name in xatspec.children:
                child_spec = xatspec.children[field_name]
                if hasattr(child_spec, "metadata") and "block" in child_spec.metadata:  # type: ignore
                    if child_spec.metadata["block"] == block_name:  # type: ignore
                        continue

            raw_value = getattr(value, field_name, None)
            if raw_value is None:
                continue
            if isinstance(raw_value, Record):
                blocks[block_name][field_name] = raw_value.to_tokens()
                continue

            # Dispatch on field value type
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
                        field_name, field_value, direction=field_meta.get("direction", "out")
                    )
                    blocks[block_name][t[0]] = t
                case datetime():
                    blocks[block_name][field_name] = field_value.isoformat()
                case _:
                    blocks[block_name][field_name] = field_value

    blocks = dict(sorted(blocks.items(), key=block_sort_key))

    # total temporary hack! manually set solutiongroup 1.
    # TODO still need to support multiple..
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return {name: block for name, block in blocks.items()}
