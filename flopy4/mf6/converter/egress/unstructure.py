from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import xarray as xr
import xattree

from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.spec import FileInOut, block_sort_key, blocks_dict


def has_dfn_metadata(cls: type) -> bool:
    """True if cls is a codegen v2 package (has attrs fields with 'dfn_block' metadata).

    Old xattree-based packages use 'block' as the metadata key; codegen v2 uses 'dfn_block'.
    This distinguishes Ic/Chd/Npf (codegen v2) from Dis/Gwf/Package (xattree).
    """
    if not attrs.has(cls):
        return False
    return any("dfn_block" in f.metadata for f in attrs.fields(cls))


def _path_to_tuple(name: str, value: Path, inout: FileInOut) -> tuple[str, ...]:
    for suffix in ("_input_file", "_filerecord", "_file"):
        if name.endswith(suffix):
            prefix = name[: -len(suffix)]
            break
    else:
        prefix = name
    t = [prefix.upper()]
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


def _recarray_to_rows(arr: np.recarray, schema: "type[Schema]") -> list[tuple]:  # type: ignore[name-defined]
    """Convert a recarray to MF6 record tuples (cellids converted to 1-based).

    MF6 column order: required cols, aux cols, boundname.  Boundname is deferred
    past aux so that aux values land in the correct file positions.
    """
    cols = schema.columns()
    schema_names = {col.name for col in cols}
    rows = []
    for i in range(len(arr)):
        row: list[Any] = []
        pending_boundname: Any = None
        for col in cols:
            name = col.name
            if name not in (arr.dtype.names or ()):  # type: ignore[operator]
                continue
            val = arr[name][i]
            if col.role == "cellid":
                row.extend(int(c) + 1 for c in val)
            elif col.role == "feature_id":
                row.append(int(val) + 1)
            elif col.role == "boundname":
                # Deferred past aux so MF6 column order is: cols, aux, boundname.
                if val is not None and val != "":
                    pending_boundname = val
            elif col.role == "inline_keyword":
                # Trailing optional keyword token (e.g. MIXED in SSM fileinput).
                # Emit the column name uppercased only when value is truthy.
                if val:
                    row.append(name.upper())
            else:
                # Emit fixed prefix token(s) before the value when requested.
                if col.prefix:
                    row.extend(col.prefix.split())
                row.append(val)
        # aux columns not in schema (named aux0, aux1, ...) come after required cols
        for name in arr.dtype.names or ():  # type: ignore[union-attr]
            if name not in schema_names:
                row.append(arr[name][i])
        # boundname is always last per MF6 convention
        if pending_boundname is not None:
            row.append(pending_boundname)
        rows.append(tuple(row))
    return rows


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


def _unstructure_codegen_v2(value: Any) -> dict[str, Any]:
    """Unstructure a codegen v2 (attrs-based, non-xattree) Package."""
    cls = type(value)
    blocks: dict[str, dict[str, Any]] = {}
    # Block names that must appear in output even when empty (e.g. SSM SOURCES).
    always_emit_set: set[str] = set()
    # OC-style period fields: {field_key: {kper: setting}} (including "" stop sentinels)
    oc_per_field: dict[str, dict[int, str]] = {}
    # Stress-period recarray fields: {kper: [(cellid, val, ...), ...]}
    spd_period: dict[int, list[tuple]] = {}
    # READARRAY period fields (G/A variants): {kper: {field_name: xr.DataArray}}
    readarray_period: dict[int, dict[str, Any]] = {}
    try:
        from dask.array import Array as _DaskArray
    except ImportError:
        _DaskArray = type(None)  # type: ignore[misc,assignment]

    for f in attrs.fields(cls):
        meta = f.metadata
        block_name = meta.get("dfn_block")
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

        dfn_type = meta.get("dfn_type", "")

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
            if isinstance(field_value, (list, tuple)) and meta.get("oc_action"):
                field_value = {0: field_value}
            if not isinstance(field_value, dict):
                continue
            if meta.get("oc_action"):
                # OC-style: collect per-field settings (including "" stop sentinels).
                # Processing is deferred to after all fields are collected so that
                # fill-forward state can be computed correctly when stop sentinels
                # cancel one field but other fields should continue.
                action = meta["oc_action"].lower()
                rtype = meta["oc_rtype"].lower()
                field_key = f"{action} {rtype}"
                for kper_raw, setting in field_value.items():
                    kper_int = _normalize_kper(kper_raw)
                    if kper_int is None:
                        continue
                    if isinstance(setting, (list, tuple)):
                        setting = " ".join(str(s) for s in setting)
                    oc_per_field.setdefault(field_key, {})[kper_int] = setting
            else:
                # Stress-period recarray: dict[int, recarray]
                schema_name = meta.get("schema")
                schema = getattr(cls, schema_name, None) if schema_name else None
                for kper, arr in field_value.items():
                    kper_int = _normalize_kper(kper)
                    if kper_int is None:
                        continue
                    rows = (
                        _recarray_to_rows(arr, schema)
                        if isinstance(arr, np.recarray) and schema is not None
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

        elif dfn_type == "record" and isinstance(field_value, Path):
            t = _path_to_tuple(f.name, field_value, meta.get("inout", "fileout"))
            blocks[block_name][t[0].lower()] = t

        elif meta.get("schema"):
            # packagedata / connectiondata / perioddata recarray block
            schema_name = meta["schema"]
            schema = getattr(cls, schema_name, None)
            if schema is not None and isinstance(field_value, np.recarray) and len(field_value):
                rows = _recarray_to_rows(field_value, schema)
                blocks[block_name][f.name] = rows

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

        elif attrs.has(type(field_value)) and "_keyword" in vars(type(field_value)):
            # Inner-class record (e.g. Oc.Headprint)
            blocks[block_name][f.name] = field_value.to_tokens()

        elif dfn_type in ("integer", "double", "double precision"):
            if field_value == 0 and meta.get("auto_from"):
                continue
            blocks[block_name][f.name] = field_value

        elif dfn_type == "string" and field_value:
            blocks[block_name][f.name] = field_value

    # All kpers where any OC field has an explicit setting (including "" stop sentinels).
    oc_explicit_kpers: set[int] = set()
    for fk_settings in oc_per_field.values():
        oc_explicit_kpers.update(fk_settings.keys())

    # Build oc_period: for each explicit kper include fields with an explicit
    # non-empty setting. "" is a stop sentinel that cancels that field's
    # fill-forward. When a kper has any stop sentinel we must emit a PERIOD
    # block; include fill-forward values for still-active non-stopped fields so
    # the emitted block doesn't silently reset them in MF6.
    oc_period: dict[int, dict[str, str]] = {}
    oc_is_stop: set[int] = set()  # kpers that have at least one stop sentinel
    ff_state: dict[str, str] = {}  # currently active fill-forward values
    for kper in sorted(oc_explicit_kpers):
        block_oc: dict[str, str] = {}
        stopped_fields: set[str] = set()
        for field_key, fk_settings in oc_per_field.items():
            if kper not in fk_settings:
                continue
            v = fk_settings[kper]
            if not v:
                oc_is_stop.add(kper)
                stopped_fields.add(field_key)
            else:
                block_oc[field_key] = v
                ff_state[field_key] = v
        if kper in oc_is_stop:
            # Include fill-forward values for fields that are still active so
            # the required PERIOD block doesn't reset them in MF6.
            for field_key, ff_val in list(ff_state.items()):
                if field_key not in stopped_fields and field_key not in block_oc:
                    block_oc[field_key] = ff_val
            for field_key in stopped_fields:
                ff_state.pop(field_key, None)
        oc_period[kper] = block_oc

    # Assemble period blocks: OC scalar fields + recarray rows, in kper order
    all_kpers = set(oc_period.keys()) | set(spd_period.keys())
    for kper in sorted(all_kpers):
        key = f"period {kper + 1}"
        block: dict[str, Any] = {}
        if kper in oc_period:
            block.update(oc_period[kper])
        if kper in spd_period:
            block["period"] = spd_period[kper]
        if block or kper in oc_is_stop:
            blocks[key] = block
            if kper in oc_is_stop and not block:
                always_emit_set.add(key)

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
    if has_dfn_metadata(type(value)):
        return _unstructure_codegen_v2(value)
    return _unstructure_component(value)


def _unstructure_component(value: Component) -> dict[str, Any]:
    """Unstructure a model-level xattree component (Gwf, Simulation, etc.).

    Model-level classes only have options blocks (bools, paths, inner records,
    strings) and child bindings. They have no griddata, period, or list blocks.
    """
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
            cls = type(raw_value)
            if attrs.has(cls) and "_keyword" in vars(cls):
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
                        field_name, field_value, inout=field_meta.get("inout", "fileout")
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
