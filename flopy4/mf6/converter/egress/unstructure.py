from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import attrs
import numpy as np
import xarray as xr
import xattree
from xattree import XatSpec

from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.context import Context
from flopy4.mf6.spec import FileInOut, block_sort_key, blocks_dict


def is_codegen_v2(cls: type) -> bool:
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
    else:
        # No structured grid decomposition available — keep nodes dim as-is.
        return value

    if "nper" in value.dims:
        shape.insert(0, value.sizes["nper"])
        dims.insert(0, "nper")
        coords = {"nper": value.coords["nper"], **coords}

    if "naux" in value.dims:
        naux = value.sizes["naux"]
        shape.append(naux)
        dims.append("naux")
        coords["naux"] = range(naux)

    return xr.DataArray(
        value.data.reshape(shape),
        dims=dims,
        coords=coords,
        name=value.name,
    )


_OC_SETTING_KEYWORDS = frozenset({"all", "first", "last", "steps", "frequency"})


def _is_emb_fill(val) -> bool:
    """Return True if val is a fill/absent value for embedded keystring rows."""
    if val is None:
        return True
    try:
        f = float(val)
        return f == FILL_DNODATA or np.isnan(f)
    except (TypeError, ValueError):
        return False


def _accumulate_embedded_keystring(
    field_value: xr.DataArray,
    field_meta: dict,
    period_data: dict,
) -> None:
    """Collect (ifno, keyword, value) rows per kper from a 2D embedded keystring field."""
    keyword = field_meta["keyword"]
    feature_dim = next((d for d in field_value.dims if d != "nper"), None)
    if feature_dim is None:
        return
    rows_by_kper: dict = period_data.setdefault("__embedded_rows__", {})
    for kper in range(field_value.sizes["nper"]):
        kper_slice = field_value.isel(nper=kper).values
        for ifeat, val in enumerate(kper_slice):
            if not _is_emb_fill(val):
                rows_by_kper.setdefault(kper, []).append((ifeat + 1, keyword, val))


def _unstructure_period_keystring(name: str, value: xr.DataArray) -> dict[str, dict[int, Any]]:
    """Unstructure a keystring period field (e.g. save_head, print_budget).

    The field name encodes the MF6 keyword: save_head → 'save head'.
    Values are ocsetting strings such as 'ALL', 'LAST', 'STEPS 1 3', 'FREQUENCY 2'.
    Empty strings act as a stop sentinel — they suppress fill-forward for that period.
    """
    fname = name.replace("_", " ")
    dat = {
        kper: value.values[kper]
        for kper in range(value.sizes["nper"])
        if (tokens := value.values[kper].lower().split()) and tokens[0] in _OC_SETTING_KEYWORDS
    }
    return {fname: dat}


def _unstructure_period_bool(name: str, value: xr.DataArray) -> dict[str, dict[int, Any]]:
    """Unstructure a boolean period field (e.g. STO steady_state, transient)."""
    fname = name.rstrip("_").replace("_", "-")  # type: ignore
    dat = {kper: "" for kper in range(value.sizes["nper"]) if value.values[kper]}
    return {fname: dat}


def _hack_period_non_numeric(name: str, value: xr.DataArray) -> dict[str, dict[int, Any]]:
    match value.dtype:
        case np.bool:
            return _unstructure_period_bool(name, value)
        case np.dtypes.StringDType():
            return _unstructure_period_keystring(name, value)
    return {}


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
        # Emit fixed syntax tokens (e.g. PRINT_FORMAT) before user fields.
        for tok in vars(cls).get("_extra_tokens", ()):
            tokens.append(tok)
        # Emit tagged (positional options) before untagged (required data)
        # so the MF6 token order matches the DFN regardless of attrs field order.
        all_fields = attrs.fields(cast(type[attrs.AttrsInstance], cls))
        tagged_fields = [a for a in all_fields if a.metadata.get("tagged", False)]
        untagged_fields = [a for a in all_fields if not a.metadata.get("tagged", False)]
        for a in tagged_fields + untagged_fields:
            val = getattr(raw_value, a.name)
            if val is None:
                continue
            if a.metadata.get("tagged", False):
                if isinstance(val, bool):
                    # keyword-type tagged field: emit name only, no value
                    if val:
                        tokens.append(a.name.upper())
                else:
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
                arr_spec = xatspec.arrays.get(field_name)
                _field_meta = (arr_spec.metadata or {}) if arr_spec is not None else {}
                if _field_meta.get("embedded_keystring"):
                    _accumulate_embedded_keystring(field_value, _field_meta, period_data)
                    return
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
                arr_spec = xatspec.arrays.get(field_name)
                field_meta = (arr_spec.metadata or {}) if arr_spec is not None else {}
                if "prefix" in field_meta or "row_keyword" in field_meta or "cellid" in field_meta:
                    field_value = field_value.copy()
                    if "prefix" in field_meta:
                        field_value.attrs["prefix"] = field_meta["prefix"]
                    if "row_keyword" in field_meta:
                        field_value.attrs["row_keyword"] = field_meta["row_keyword"]
                    if "cellid" in field_meta:
                        field_value.attrs["cellid"] = True
                blocks[block_name][field_name] = field_value
        case _:
            blocks[block_name][field_name] = field_value


def _recarray_to_rows(arr: np.recarray, schema: list[dict]) -> list[tuple]:
    """Convert a recarray to MF6 record tuples (cellids converted to 1-based).

    MF6 column order: required cols, aux cols, boundname.  Boundname is deferred
    past aux so that aux values land in the correct file positions.
    """
    rows = []
    schema_names = {col["name"] for col in schema}
    for i in range(len(arr)):
        row: list[Any] = []
        pending_boundname: Any = None
        for col in schema:
            role = col.get("role", "value")
            name = col["name"]
            if name not in (arr.dtype.names or ()):  # type: ignore[operator]
                continue
            val = arr[name][i]
            if role == "cellid":
                row.extend(int(c) + 1 for c in val)
            elif role == "feature_id":
                row.append(int(val) + 1)
            elif role == "boundname":
                # Deferred past aux so MF6 column order is: cols, aux, boundname.
                if val is not None and val != "":
                    pending_boundname = val
            elif role == "inline_keyword":
                # Trailing optional keyword token (e.g. MIXED in SSM fileinput).
                # Emit the column name uppercased only when value is truthy.
                if val:
                    row.append(name.upper())
            else:
                # Emit fixed prefix token(s) before the value when requested.
                prefix = col.get("prefix")
                if prefix:
                    row.extend(prefix.split())
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

    Dask arrays are computed eagerly so the writer can inspect values and
    choose CONSTANT vs INTERNAL without needing an external binary file.
    """
    if isinstance(value, xr.DataArray):
        return value
    if isinstance(value, np.ndarray):
        return xr.DataArray(value)
    # Compute dask arrays to numpy before wrapping — the text writer needs
    # concrete values to pick CONSTANT vs INTERNAL format.
    try:
        import dask.array as _da

        if isinstance(value, _da.Array):
            return xr.DataArray(value.compute())
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
            if meta.get("reader") == "readarray" and isinstance(field_value, np.ndarray):
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
                schema = getattr(cls, schema_name, []) if schema_name else []
                for kper, arr in field_value.items():
                    kper_int = _normalize_kper(kper)
                    if kper_int is None:
                        continue
                    rows = _recarray_to_rows(arr, schema) if isinstance(arr, np.recarray) else []
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
            schema = getattr(cls, schema_name, [])
            if isinstance(field_value, np.recarray) and len(field_value):
                rows = _recarray_to_rows(field_value, schema)
                blocks[block_name][f.name] = rows

        elif meta.get("shape") and not isinstance(field_value, bool):
            # griddata-style array (shape is a non-empty tuple)
            if meta["shape"]:
                blocks[block_name][f.name] = _wrap_array(field_value)

        elif f.name == "auxiliary" and isinstance(field_value, list):
            blocks[block_name][f.name] = ("AUXILIARY",) + tuple(field_value)

        elif attrs.has(type(field_value)) and "_keyword" in vars(type(field_value)):
            # Inner-class record (e.g. Oc.Headprint)
            inner_cls = type(field_value)
            keyword: str = vars(inner_cls)["_keyword"]
            tokens: list[Any] = [keyword.upper()] if keyword else []
            for tok in vars(inner_cls).get("_extra_tokens", ()):
                tokens.append(tok)
            all_inner = attrs.fields(inner_cls)
            tagged = [a for a in all_inner if a.metadata.get("tagged")]
            untagged = [a for a in all_inner if not a.metadata.get("tagged")]
            for a in tagged + untagged:
                v = getattr(field_value, a.name)
                if v is None:
                    continue
                if a.metadata.get("tagged"):
                    tokens.extend([a.name.upper(), v])
                elif isinstance(v, bool):
                    if v:
                        tokens.append(a.name.upper())
                else:
                    tokens.append(v)
            blocks[block_name][f.name] = tuple(tokens)

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
    if is_codegen_v2(type(value)):
        return _unstructure_codegen_v2(value)
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
                # G/A variant aux: split naux-dimensioned array into one readarray
                # block per auxiliary variable, named by value.auxiliary.
                if arr_name == "aux" and isinstance(val, xr.DataArray) and "naux" in val.dims:
                    _aux = getattr(value, "auxiliary", None)
                    if _aux is not None and hasattr(_aux, "values"):
                        aux_names = [str(n) for n in _aux.values.tolist()]
                    else:
                        aux_names = list(_aux or [])
                    for k in range(val.sizes["naux"]):
                        aux_slice = val.isel(naux=k)
                        if not np.all(aux_slice.values == FILL_DNODATA):
                            if key not in blocks:
                                blocks[key] = {}
                            name = aux_names[k] if k < len(aux_names) else f"aux{k}"
                            blocks[key][name] = aux_slice
                elif not np.all(val == FILL_DNODATA):
                    if key not in blocks:
                        blocks[key] = {}
                    blocks[key][arr_name] = val

    return {
        name: block
        for name, block in blocks.items()
        if name != "period" and not name.startswith("__")
    }


# Block names that MF6 rejects if present but empty.
# These blocks should only be written when they contain data.
_SKIP_IF_EMPTY = frozenset({"dimensions", "fileinput", "tables", "outlets", "tracktimes"})

# Block names whose fields are list columns (one array per column, same dim)
# rather than independent grid arrays.  Only these blocks are auto-combined
# into an xr.Dataset for row-per-record output.  griddata-style blocks must
# NOT be in this set — their fields are written individually with
# INTERNAL/CONSTANT/NETCDF format.
# Extend when adding a new recarray block; keep in sync with __block_col_maps__
# on generated Package classes.
# "sources" is the SSM sources block (pname/srctype/auxname per-row tabular input).
_LIST_BLOCK_NAMES = frozenset(
    {
        "packagedata",
        "packages",
        "partitions",
        "perioddata",
        "sources",
        "fileinput",
        "table",
        "outlets",
        "connectiondata",
        "tables",
    }
)


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
                if arr_name == "__embedded_rows__":
                    # Embedded keystring rows: list of (ifno, keyword, value) tuples.
                    # Accumulated from all embedded_keystring fields; write as a list
                    # so the Jinja 'list' macro renders each tuple as a record row.
                    if val:
                        if key not in blocks:
                            blocks[key] = {}
                        blocks[key]["lak_period"] = val
                elif np.any(val != FILL_DNODATA):
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
                # Expand any 2D DataArrays (e.g. aux with shape (nlakes, naux)) into
                # separate per-column 1D DataArrays so the Dataset stays uniformly 1D.
                expanded: dict[str, Any] = {}
                for name, v in current_block.items():
                    if isinstance(v, xr.DataArray) and v.ndim == 2:
                        for j in range(v.shape[1]):
                            expanded[f"{name}_{j}"] = v.isel({v.dims[1]: j})
                    else:
                        expanded[name] = v
                current_block = expanded

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
        if name != "period" and not name.startswith("__") and (block or name not in _SKIP_IF_EMPTY)
    }
