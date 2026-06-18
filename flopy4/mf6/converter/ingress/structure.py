from typing import Any, get_args

import attrs
import numpy as np
import pandas as pd
import sparse
import xarray as xr
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.dimensions import DimensionResolver


def structure_keyword(value, field) -> str | None:
    return field.name if value else None


def _inner_class_type(field_type) -> type | None:
    """If field_type is Optional[C] where C is an attrs inner-record class, return C."""
    args = get_args(field_type)
    if not args:
        return None
    for arg in args:
        if arg is type(None):
            continue
        if attrs.has(arg) and "_keyword" in vars(arg):
            return arg
    return None


def _list_block_col_info(col_map: dict, xatspec) -> dict[str, tuple[bool, bool, Any, tuple]]:
    """Return {col_name: (is_true_cellid, is_numeric_index, dtype, prefix)} for a col_map.

    is_true_cellid  — object-dtype field, expands to ncelldim tokens in the file
    is_numeric_index — int-dtype field, single 1-based token in the file
    dtype            — numpy dtype for type-compatibility checks when skipping
                       absent optional columns
    prefix           — tuple of fixed keyword tokens that precede the value in each row
                       (e.g. ("FILEIN",) for fname in FMI packagedata)
    """
    info = {}
    for col_name, attr_name in col_map.items():
        fspec = xatspec.flat.get(attr_name)
        if fspec is None:
            info[col_name] = (False, False, object, ())
            continue
        meta = getattr(fspec, "metadata", {}) or {}
        has_cellid_flag = bool(meta.get("cellid"))
        dtype = getattr(fspec, "dtype", object)
        is_object = dtype == object or dtype == np.object_  # noqa: E721
        prefix = tuple(meta.get("prefix", ()))
        info[col_name] = (
            has_cellid_flag and is_object,  # true cellid → multi-token tuple
            has_cellid_flag and not is_object,  # numeric index → 1-based single token
            dtype,
            prefix,
        )
    return info


def _token_fits(token: Any, dtype: Any) -> bool:
    """True if *token* is type-compatible with *dtype*.

    Numeric dtypes (float64, int64, …) require a numeric token (int or float).
    String tokens that look like numbers (e.g. '-0.4' from the grammar's word
    rule) are also accepted for numeric dtypes.
    Object dtype accepts any token.  Used to detect absent optional columns
    whose token slot would otherwise consume the next column's value.
    """
    if dtype == object or dtype == np.object_:  # noqa: E721
        return True
    if isinstance(token, (int, float)):
        return True
    if isinstance(token, str):
        try:
            float(token)
            return True
        except ValueError:
            return False
    return False


def _coerce_token(token: Any, dtype: Any) -> Any:
    """Coerce a string token to its numeric value for numeric dtypes."""
    if isinstance(token, str) and not (dtype == object or dtype == np.object_):  # noqa: E721
        try:
            if np.issubdtype(np.dtype(dtype), np.floating):
                return float(token)
            if np.issubdtype(np.dtype(dtype), np.integer):
                return int(float(token))
        except (ValueError, TypeError):
            pass
    return token


def _parse_list_block_rows(
    rows: list,
    col_map: dict,
    col_info: dict[str, tuple[bool, bool, Any, tuple]],
    naux: int = 0,
) -> dict[str, Any]:
    """Parse token rows into {col_name: numpy_array} using col_map.

    Token→value rules:
    - true cellid  (object dtype + cellid flag): consume ncelldim tokens, pack
      to a tuple, subtract 1 from each component.  ncelldim is inferred from
      row length minus the count of remaining single-token columns.
    - numeric index (int dtype + cellid flag): consume 1 token, subtract 1.
    - aux column (col_name == "aux"): consume exactly naux float tokens and
      return as a list; caller assembles into a 2D array (nlakes, naux).
    - regular column: consume 1 token, no transform.

    Absent optional columns are detected by type mismatch: if the current token
    is a string but the column dtype is numeric, the column is marked absent and
    the token is left for the next column.  All-absent columns are omitted from
    the returned dict.
    """
    col_names = list(col_map.keys())
    col_lists: dict[str, list] = {c: [] for c in col_names}

    for row in rows:
        tok_idx = 0
        for i, col_name in enumerate(col_names):
            is_true_cellid, is_numeric_index, dtype, prefix = col_info[col_name]

            if tok_idx >= len(row):
                col_lists[col_name].append(None)
                continue

            # Skip fixed prefix tokens (e.g. "FILEIN" before a filename column).
            tok_idx += len(prefix)
            if tok_idx >= len(row):
                col_lists[col_name].append(None)
                continue

            cur_tok = row[tok_idx]

            if is_true_cellid:
                # Infer ncelldim from remaining tokens: remaining = single-token cols after this
                remaining_single = sum(1 for cn in col_names[i + 1 :] if not col_info[cn][0])
                ncelldim = len(row) - tok_idx - remaining_single
                if ncelldim < 1:
                    ncelldim = 1
                cellid = tuple(int(row[tok_idx + j]) - 1 for j in range(ncelldim))
                col_lists[col_name].append(cellid)
                tok_idx += ncelldim
            elif is_numeric_index:
                if not _token_fits(cur_tok, np.int64):
                    col_lists[col_name].append(None)
                    continue
                col_lists[col_name].append(int(float(str(cur_tok))) - 1)
                tok_idx += 1
            elif col_name == "aux":
                # Aux: consume exactly naux float tokens
                if naux == 0:
                    col_lists[col_name].append(None)
                else:
                    aux_vals: list[float] = []
                    ok = True
                    for _ in range(naux):
                        if tok_idx < len(row) and _token_fits(row[tok_idx], np.float64):
                            aux_vals.append(float(str(row[tok_idx])))
                            tok_idx += 1
                        else:
                            ok = False
                            break
                    col_lists[col_name].append(aux_vals if ok else None)
            else:
                if not _token_fits(cur_tok, dtype):
                    col_lists[col_name].append(None)
                    continue
                col_lists[col_name].append(_coerce_token(cur_tok, dtype))
                tok_idx += 1

    result = {}
    for col_name, vals in col_lists.items():
        if any(v is None for v in vals):
            continue
        if vals and isinstance(vals[0], list):
            # Multi-aux: list of naux-element lists → 2D float array (nrows, naux)
            result[col_name] = np.array(vals, dtype=np.float64)
        elif vals and isinstance(vals[0], tuple):
            # True cellid: 2D int array (N, ncelldim); _set_block packs to tuples
            try:
                result[col_name] = np.array(vals, dtype=int)
            except (ValueError, TypeError):
                result[col_name] = np.array(vals, dtype=object)
        elif vals and isinstance(vals[0], int):
            result[col_name] = np.array(vals, dtype=np.int64)
        elif vals and isinstance(vals[0], float):
            result[col_name] = np.array(vals, dtype=np.float64)
        else:
            result[col_name] = np.array(vals, dtype=object)
    return result


def _parse_period_rows(
    rows: list,
    period_col_map: dict[str, str],
    naux: int = 0,
) -> dict[str, dict]:
    """Parse token rows from one PERIOD block into {col_name: {cellid_tuple: value}}.

    Handles cellid (variable-width tuple, 0-based after -1), value columns
    (each 1 token, float64), and optional boundname (final non-numeric string).
    Aux parsing is deferred — callers receive {"aux": {cellid: [v1, v2, ...]}}
    when naux > 0.

    Returns col_name → {cellid: value} for each column that has data.
    """
    n_value = len(period_col_map)
    value_col_names = list(period_col_map.keys())
    value_col_results: dict[str, dict] = {c: {} for c in value_col_names}
    aux_results: dict = {}
    bn_results: dict = {}

    for row in rows:
        if not row:
            continue
        last_tok = row[-1] if row else None
        has_bn = (
            last_tok is not None
            and isinstance(last_tok, str)
            and not _token_fits(last_tok, np.float64)
        )
        ncelldim = len(row) - n_value - naux - (1 if has_bn else 0)
        if ncelldim < 1:
            continue
        cellid = tuple(int(row[j]) - 1 for j in range(ncelldim))
        tok_idx = ncelldim
        for col_name in value_col_names:
            if tok_idx >= len(row):
                break
            value_col_results[col_name][cellid] = _coerce_token(row[tok_idx], np.float64)
            tok_idx += 1
        if naux > 0 and tok_idx + naux <= len(row):
            aux_results[cellid] = [float(str(row[tok_idx + k])) for k in range(naux)]
            tok_idx += naux
        if has_bn:
            bn_results[cellid] = str(last_tok)

    result: dict[str, dict] = {}
    for col_name, d in value_col_results.items():
        if d:
            result[col_name] = d
    if aux_results:
        result["aux"] = aux_results
    if bn_results:
        result["boundname"] = bn_results
    return result


_DTYPE_MAP = {
    "integer": np.int64,
    "double": np.float64,
    "double precision": np.float64,
    "string": np.object_,
    "keyword": np.object_,
    "object": np.object_,
}


def _parse_rows_to_recarray(
    rows: list,
    schema: list[dict],
    *,
    naux: int = 0,
    boundnames: bool = False,
) -> np.recarray | None:
    """Parse raw token rows into a np.recarray using a codegen v2 schema.

    Columns are parsed in schema order so that schemas with multiple feature_id
    columns (e.g. LAK connectiondata: ifno, iconn, cellid, ...) round-trip
    correctly.  Schema roles:
      - 'cellid'         → variable-width tuple of 1-based ints, converted to 0-based
      - 'feature_id'     → 1-based int, converted to 0-based (multiple allowed)
      - 'value'          → scalar numeric or object token
      - 'boundname'      → trailing non-numeric string (always parsed last)
    """
    if not rows:
        return None

    cellid_col = next((c for c in schema if c.get("role") == "cellid"), None)
    feature_id_cols = [c for c in schema if c.get("role") == "feature_id"]
    value_cols = [c for c in schema if c.get("role") == "value"]
    boundname_col = next((c for c in schema if c.get("role") == "boundname"), None)
    keystring_cols = [c for c in schema if c.get("role") in ("keystring", "keystring_value")]
    inline_kw_cols = [c for c in schema if c.get("role") == "inline_keyword"]
    # Count only value columns that are actually emitted in each row for ncelldim
    # inference.  Columns that are optional AND not time_series are excluded from
    # the recarray dtype by __attrs_post_init__ and therefore absent from emitted
    # rows; counting them inflates n_fixed and under-counts ncelldim.
    required_value_cols = [
        c for c in value_cols if not c.get("optional", False) or c.get("time_series")
    ]
    n_fixed = len(required_value_cols) + len(keystring_cols) + len(feature_id_cols)

    # Infer ncelldim from the first row that has tokens
    ncelldim = 0
    if cellid_col:
        first = next((r for r in rows if r), None)
        if first:
            last = first[-1]
            first_has_bn = isinstance(last, str) and not _token_fits(last, np.float64)
            ncelldim = max(1, len(first) - n_fixed - naux - (1 if first_has_bn else 0))

    # Build dtype in schema order so field names align with token parse order
    dtype_fields: list = []
    for col in schema:
        role = col.get("role")
        if role == "cellid":
            dtype_fields.append(("cellid", np.int64, (ncelldim,)))
        elif role == "feature_id":
            dtype_fields.append((col["name"], np.int64))
        elif role == "value":
            raw_dt = col.get("dtype")
            if raw_dt:
                dt = eval(raw_dt)  # e.g. "np.object_"
            elif col.get("time_series"):
                dt = np.object_
            else:
                dt = _DTYPE_MAP.get(col.get("dfn_type", "double"), np.float64)
            dtype_fields.append((col["name"], dt))
        elif role in ("keystring", "keystring_value"):
            dtype_fields.append((col["name"], np.object_))
        elif role == "inline_keyword":
            dtype_fields.append((col["name"], np.object_))
        # boundname role is appended after aux below
    for i in range(naux):
        dtype_fields.append((f"aux{i}", np.object_))
    has_bn_col = boundname_col is not None and boundnames
    if has_bn_col:
        dtype_fields.append(("boundname", np.object_))
    dtype = np.dtype(dtype_fields)

    # Parse each row in schema order
    records: list[tuple] = []
    for row in rows:
        if not row:
            continue
        tok_idx = 0
        record: list = []

        for col in schema:
            role = col.get("role")
            if role == "cellid":
                last = row[-1]
                row_has_bn = isinstance(last, str) and not _token_fits(last, np.float64)
                this_ncd = max(1, len(row) - n_fixed - naux - (1 if row_has_bn else 0))
                cellid = tuple(int(row[tok_idx + j]) - 1 for j in range(this_ncd))
                # Pad/truncate to consistent ncelldim
                if this_ncd < ncelldim:
                    cellid = cellid + (0,) * (ncelldim - this_ncd)
                elif this_ncd > ncelldim:
                    cellid = cellid[:ncelldim]
                record.append(cellid)
                tok_idx += this_ncd
            elif role == "feature_id":
                record.append(int(float(str(row[tok_idx]))) - 1)
                tok_idx += 1
            elif role == "value":
                if tok_idx >= len(row):
                    record.append(None)
                    continue
                prefix = col.get("prefix")
                if prefix:
                    tok_idx += len(prefix.split())
                if tok_idx >= len(row):
                    record.append(None)
                    continue
                tok = row[tok_idx]
                raw_dt = col.get("dtype")
                if raw_dt or col.get("time_series"):
                    try:
                        record.append(float(tok))
                    except (ValueError, TypeError):
                        record.append(str(tok))
                else:
                    col_dtype = _DTYPE_MAP.get(col.get("dfn_type", "double"), np.float64)
                    record.append(_coerce_token(tok, col_dtype))
                tok_idx += 1
            elif role in ("keystring", "keystring_value"):
                if tok_idx >= len(row):
                    record.append(None)
                else:
                    record.append(str(row[tok_idx]))
                    tok_idx += 1
            elif role == "inline_keyword":
                kw = col["name"].upper()
                if tok_idx < len(row) and str(row[tok_idx]).upper() == kw:
                    record.append(str(row[tok_idx]))
                    tok_idx += 1
                else:
                    record.append(None)
            # boundname role: handled after schema loop

        # Aux columns
        for i in range(naux):
            if tok_idx < len(row):
                try:
                    record.append(float(row[tok_idx]))
                except (ValueError, TypeError):
                    record.append(row[tok_idx])
                tok_idx += 1
            else:
                record.append(None)

        # Boundname (final non-numeric string if present)
        if has_bn_col:
            if tok_idx < len(row):
                last = row[tok_idx]
                if isinstance(last, str) and not _token_fits(last, np.float64):
                    record.append(str(last))
                else:
                    record.append(None)
            else:
                record.append(None)

        records.append(tuple(record))

    if not records:
        return None

    arr = np.zeros(len(records), dtype=dtype)
    for i, rec in enumerate(records):
        for j, name in enumerate(dtype.names or ()):  # type: ignore[arg-type]
            if j < len(rec) and rec[j] is not None:
                arr[name][i] = rec[j]
    return arr.view(np.recarray)


def _parse_griddata_block(rows: list, fields_by_name: dict, dims: dict) -> dict:
    """Parse GRIDDATA token rows into {field_name: np.ndarray}.

    Token rows alternate: [field_name, ?LAYERED] then value row(s).
    CONSTANT broadcasts to shape; LAYERED expects one value row per layer.
    """
    result: dict = {}
    nlay = dims.get("nlay", 1)
    nodes = dims.get("nodes", 0)
    if not nodes:
        return result
    ncpl = nodes // nlay if nlay else nodes

    i = 0
    while i < len(rows):
        row = rows[i]
        if not row:
            i += 1
            continue
        key = str(row[0]).lower()
        f = fields_by_name.get(key)
        if f is None or f.metadata.get("dfn_block") != "griddata":
            i += 1
            continue

        is_int = f.metadata.get("dfn_type") in ("integer",)
        layered = any(str(t).upper() == "LAYERED" for t in row[1:])
        i += 1

        if layered:
            layers = []
            for _ in range(nlay):
                if i >= len(rows):
                    break
                vrow = rows[i]
                i += 1
                if vrow and str(vrow[0]).upper() == "CONSTANT":
                    v = int(vrow[1]) if is_int else float(vrow[1])
                    layers.append(np.full(ncpl, v))
                else:
                    layers.append(np.array(vrow, dtype=np.int64 if is_int else np.float64))
            result[f.name] = np.concatenate(layers).astype(np.int64 if is_int else np.float64)
        else:
            if i >= len(rows):
                break
            vrow = rows[i]
            i += 1
            if vrow and str(vrow[0]).upper() == "CONSTANT":
                v = int(vrow[1]) if is_int else float(vrow[1])
                result[f.name] = np.full(nodes, v, dtype=np.int64 if is_int else np.float64)
            else:
                result[f.name] = np.array(vrow, dtype=np.int64 if is_int else np.float64)

    return result


def _structure_codegen_v2(raw: dict, cls: type, dims: dict | None = None) -> Any:
    """Reconstruct a codegen v2 (attrs-based) component from raw MF6 input.

    Parameters
    ----------
    raw : dict
        Output of ``loads()`` — {BLOCK_NAME_UPPER: list_of_token_rows}.
    cls : type
        A codegen v2 package class (has attrs fields with 'dfn_block' metadata).
    dims : dict, optional
        Grid dimensions (e.g. {"nlay": 3, "nodes": 675}) used to resolve
        GRIDDATA array shapes.  Required for packages with griddata fields.

    Returns
    -------
    Component instance.
    """

    raw_lower = {k.lower(): v for k, v in raw.items()}

    # Index all init-eligible fields by name and alias
    all_fields = {f.name: f for f in attrs.fields(cls) if f.init is not False}
    alias_map: dict[str, str] = {}  # alias → name
    for f in attrs.fields(cls):
        if f.alias and f.alias != f.name:
            alias_map[f.alias] = f.name

    # Index Optional[InnerClass] fields by the inner class's _keyword (lowercase).
    # Covers options-block compound records like Npf.Cvoptions, Ims.Rclose, etc.
    inner_class_fields: dict[str, tuple] = {}
    for f in attrs.fields(cls):
        if f.init is False:
            continue
        inner_cls = _inner_class_type(f.type)
        if inner_cls is None:
            continue
        kw = vars(inner_cls).get("_keyword", "")
        if kw:
            inner_class_fields[kw.lower()] = (f, inner_cls)

    # Identify block-schema fields (packagedata, connectiondata, partitions …)
    block_schema_fields: dict[str, tuple] = {}  # block_name → (field, schema)
    oc_fields: list = []  # fields with oc_action metadata
    period_field = None  # field for recarray stress_period_data

    for f in attrs.fields(cls):
        block = f.metadata.get("dfn_block", "")
        schema_ref = f.metadata.get("schema")
        oc_action = f.metadata.get("oc_action")

        if oc_action:
            oc_fields.append(f)
        elif block == "period" and schema_ref:
            period_field = f
        elif schema_ref and block not in ("period",):
            schema = getattr(cls, schema_ref, None)
            if schema is not None:
                block_schema_fields[block] = (f, schema)

    # ── Pass 1: scalar blocks (options, dimensions, etc.) ────────────────────
    kwargs: dict[str, Any] = {}
    for block_name, rows in raw_lower.items():
        if not rows:
            continue
        if block_name in block_schema_fields or block_name.startswith("period"):
            continue
        for row in rows:
            if not row:
                continue
            key = str(row[0]).lower()
            f = all_fields.get(key) or all_fields.get(alias_map.get(key, ""))
            if f is None or f.init is False:
                if key in inner_class_fields:
                    cand_f, inner_cls = inner_class_fields[key]
                    cand_init = cand_f.alias if cand_f.alias else cand_f.name
                    kwargs[cand_init] = inner_cls.from_tokens(row)
                continue
            init_key = f.alias if f.alias else f.name
            if len(row) == 1:
                kwargs[init_key] = True
            else:
                # List-valued options (auxiliary, etc.) have shape metadata;
                # always keep them as a list so __attrs_post_init__ can use len().
                is_list_opt = isinstance(f.metadata.get("shape"), tuple)
                if is_list_opt:
                    kwargs[init_key] = list(row[1:])
                else:
                    kwargs[init_key] = list(row[1:]) if len(row) > 2 else row[1]

    naux = 0
    if "auxiliary" in kwargs:
        aux_opt = kwargs["auxiliary"]
        naux = len(aux_opt) if isinstance(aux_opt, list) else 1
    boundnames = bool(kwargs.get("boundnames", False))

    # ── Pass 2: block-schema blocks (packagedata, partitions …) ─────────────
    for block_name, (f, schema) in block_schema_fields.items():
        rows = raw_lower.get(block_name, [])
        if not rows:
            continue
        recarray = _parse_rows_to_recarray(rows, schema, naux=naux, boundnames=boundnames)
        if recarray is not None:
            init_key = f.alias if (f.alias and not f.alias.startswith("_")) else f.name
            kwargs[init_key] = recarray

    # ── Pass 3: period blocks ────────────────────────────────────────────────
    kper_rows: dict[int, list] = {}
    for block_name, rows in raw_lower.items():
        if not block_name.startswith("period"):
            continue
        parts = block_name.split()
        if len(parts) < 2:
            continue
        try:
            kper = int(parts[1]) - 1
        except ValueError:
            continue
        kper_rows[kper] = rows

    if kper_rows:
        if oc_fields:
            # OC-style: rows like [ACTION, RTYPE, SETTING …]
            # Map (action, rtype) → field name
            oc_map: dict[tuple[str, str], str] = {}
            for f in oc_fields:
                action = f.metadata["oc_action"].lower()
                rtype = f.metadata["oc_rtype"].lower()
                oc_map[(action, rtype)] = f.alias if f.alias else f.name

            collected: dict[str, dict[int, str]] = {}
            for kper, rows in sorted(kper_rows.items()):
                for row in rows:
                    if len(row) < 2:
                        continue
                    action = str(row[0]).lower()
                    rtype = str(row[1]).lower()
                    field_key = oc_map.get((action, rtype))
                    if field_key:
                        setting = " ".join(str(t) for t in row[2:]) if len(row) > 2 else "all"
                        collected.setdefault(field_key, {})[kper] = setting
            kwargs.update(collected)

        elif period_field is not None:
            schema_ref = period_field.metadata.get("schema")
            period_schema = getattr(cls, schema_ref, None) if schema_ref else None
            if period_schema:
                spd: dict[int, np.recarray] = {}
                for kper, rows in sorted(kper_rows.items()):
                    if not rows:
                        continue
                    recarray = _parse_rows_to_recarray(
                        rows, period_schema, naux=naux, boundnames=boundnames
                    )
                    if recarray is not None:
                        spd[kper] = recarray
                if spd:
                    # Use the alias (stress_period_data) as the init kwarg
                    init_key = period_field.alias if period_field.alias else period_field.name
                    kwargs[init_key] = spd

    # ── Pass 4: griddata block ────────────────────────────────────────────────
    if dims:
        griddata_rows = raw_lower.get("griddata", [])
        if griddata_rows:
            gd_fields = {
                f.name: f
                for f in attrs.fields(cls)
                if f.metadata.get("dfn_block") == "griddata" and f.init is not False
            }
            parsed = _parse_griddata_block(griddata_rows, gd_fields, dims)
            kwargs.update(parsed)

    return cls(**kwargs)


def structure_component(raw: dict, cls: type, *, dims: dict | None = None) -> Any:
    """Reconstruct a component instance from a raw parsed MF6 input dict.

    Parameters
    ----------
    raw : dict
        Output of ``loads()`` — {block_name_upper: list_of_token_rows}.
    cls : type
        The component class to instantiate.

    Returns
    -------
    Component instance.
    """
    from flopy4.mf6.converter.egress.unstructure import is_codegen_v2

    if is_codegen_v2(cls):
        return _structure_codegen_v2(raw, cls, dims=dims)

    raw_lower = {k.lower(): v for k, v in raw.items()}
    xatspec = get_xatspec(cls)
    block_col_maps: dict[str, dict[str, str]] = getattr(cls, "__block_col_maps__", {})

    # Build (name → attrs.Attribute) for init-eligibility checks
    all_attrs = {f.name: f for f in attrs.fields(cls)}

    kwargs: dict[str, Any] = {}

    # Scalar block (options / dimensions) pass: collect kwargs first so that
    # auxiliary (and hence naux) is known when processing list blocks.
    for block_name, rows in raw_lower.items():
        if not rows or block_name in block_col_maps or block_name.startswith("period"):
            continue
        for row in rows:
            if not row:
                continue
            if len(row) == 1:
                key = str(row[0]).lower()
                af = all_attrs.get(key)
                if af is not None and af.init is not False:
                    kwargs[key] = True
            elif len(row) >= 2:
                key = str(row[0]).lower()
                af = all_attrs.get(key)
                if af is not None and af.init is not False:
                    # Collect all values for list-type options (e.g. auxiliary names)
                    kwargs[key] = list(row[1:]) if len(row) > 2 else row[1]

    # Derive naux from auxiliary option so list-block parsing can consume the
    # right number of aux tokens per row.
    naux = 0
    if "auxiliary" in kwargs:
        aux_opt = kwargs["auxiliary"]
        naux = len(aux_opt) if isinstance(aux_opt, list) else 1

    # Pass naux as constructor kwarg when the class declares a naux dim field.
    # This ensures structure_array can resolve the naux dimension during __init__.
    if naux > 0 and any(f.name == "naux" for f in attrs.fields(cls)):
        kwargs["naux"] = naux

    # List block pass
    for block_name, rows in raw_lower.items():
        if not rows or block_name.startswith("period"):
            continue
        if block_name in block_col_maps:
            col_map = block_col_maps[block_name]
            col_info = _list_block_col_info(col_map, xatspec)
            block_dict = _parse_list_block_rows(rows, col_map, col_info, naux=naux)
            if block_dict:
                kwargs[block_name] = block_dict

    # TODO: ingress for G/A variant period blocks is not yet supported.
    # G-variants (CHDG/WELG/DRNG/GHBG/RIVG) and A-variants (RCHA/EVTA) use
    # readarray-based period input, not the list-row format that
    # _parse_period_rows handles.  Period aux for these packages is also not
    # ingested; aux arrays are emitted as named readarray blocks per variable
    # on egress but are not reconstructed on ingress.

    # Period block pass: parse PERIOD N blocks using __period_col_maps__ ClassVar.
    period_col_map: dict[str, str] = getattr(cls, "__period_col_maps__", {})
    if period_col_map:
        # Group raw rows by 0-based kper
        kper_rows: dict[int, list] = {}
        for block_name, rows in raw_lower.items():
            if not block_name.startswith("period"):
                continue
            parts = block_name.split()
            if len(parts) < 2:
                continue
            try:
                kper = int(parts[1]) - 1
            except ValueError:
                continue
            kper_rows[kper] = rows

        if kper_rows:
            # {col_name: {kper: {cellid: value}}}
            col_period_dicts: dict[str, dict] = {}
            for kper, rows in sorted(kper_rows.items()):
                period_data = _parse_period_rows(rows, period_col_map, naux=naux)
                for col_name, cellid_dict in period_data.items():
                    if cellid_dict:
                        col_period_dicts.setdefault(col_name, {})[kper] = cellid_dict

            # aux and boundname share the same attr name as their col_name
            all_col_map = dict(period_col_map)
            all_col_map["aux"] = "aux"
            all_col_map["boundname"] = "boundname"
            cls_attr_names = {f.name for f in attrs.fields(cls)}
            for col_name, period_dict in col_period_dicts.items():
                attr_name = all_col_map.get(col_name, col_name)
                if attr_name in cls_attr_names:
                    kwargs[attr_name] = period_dict

    if dims:
        kwargs["dims"] = dims
    return cls(**kwargs)


def _resolve_dimensions(
    self_, field, *, dims: dict | None = None
) -> tuple[list[str], list[int], dict]:
    """
    Get expected dimensions, shape, and resolved dimension values.

    Parameters
    ----------
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default
    dims : dict, optional
        Explicit dimension sizes to use. If provided, takes precedence over
        dims from parent or self_.__dict__.

    Returns
    -------
    dims : list[str]
        Dimension names (e.g., ['nper', 'nodes'])
    shape : list[int]
        Resolved shape (e.g., [10, 1000])
    dim_dict : dict
        Dimension values (e.g., {'nper': 10, 'nodes': 1000})
    """
    spec = get_xatspec(type(self_)).flat
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # Resolve dims from model context
    # Priority: 1) explicit dims parameter, 2) self_.__dict__, 3) parent
    inherited_dims = {}
    if self_.parent and isinstance(self_.parent, DimensionResolver):
        inherited_dims = self_.parent.resolve_dims()

    explicit_dims = self_.__dict__.get("dims", {})
    dim_dict = inherited_dims | explicit_dims

    # Override with explicitly provided dims (highest priority)
    if dims is not None:
        dim_dict.update(dims)

    # Check object attributes directly for dimension values
    # These override inherited dims (important during initialization when dims are passed as kwargs)
    for dim_name in field.dims:
        if hasattr(self_, dim_name):
            dim_value = getattr(self_, dim_name)
            if isinstance(dim_value, int):
                # Override any inherited value with the object's attribute value
                dim_dict[dim_name] = dim_value

    # Build shape by resolving dimension values
    shape = [dim_dict.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    return list(field.dims), shape, dim_dict


def _detect_grid_reshape(
    value_shape: tuple, expected_dims: list[str], dim_dict: dict
) -> tuple[bool, tuple | None]:
    """
    Check if structured↔flat conversion needed.

    Parameters
    ----------
    value_shape : tuple
        Shape of input array
    expected_dims : list[str]
        Expected dimension names
    dim_dict : dict
        Resolved dimension values

    Returns
    -------
    needs_reshape : bool
        True if reshape required
    target_shape : tuple | None
        Target shape for reshape, or None
    """
    # Get expected shape
    expected_shape = tuple(dim_dict.get(d, d) for d in expected_dims)

    # Check if value has structured dimensions
    has_structured_3d = "nlay" in dim_dict and "nrow" in dim_dict and "ncol" in dim_dict
    has_structured_2d = "nrow" in dim_dict and "ncol" in dim_dict

    # Handle 'nodes' dimension (full 3D grid)
    if "nodes" in expected_dims and has_structured_3d:
        nlay = dim_dict["nlay"]
        nrow = dim_dict["nrow"]
        ncol = dim_dict["ncol"]
        nodes = dim_dict.get("nodes", nlay * nrow * ncol)

        # Case 1: (nlay, nrow, ncol) → (nodes,)
        if value_shape == (nlay, nrow, ncol) and expected_shape == (nodes,):
            return True, (nodes,)

        # Case 2: (nper, nlay, nrow, ncol) → (nper, nodes)
        if "nper" in expected_dims:
            nper = dim_dict["nper"]
            if value_shape == (nper, nlay, nrow, ncol) and expected_shape == (nper, nodes):
                return True, (nper, nodes)

    # Handle 'ncpl' dimension (cells per layer, 2D per-layer arrays)
    if "ncpl" in expected_dims and has_structured_2d:
        nrow = dim_dict["nrow"]
        ncol = dim_dict["ncol"]
        ncpl = dim_dict.get("ncpl", nrow * ncol)

        # Case 3: (nrow, ncol) → (ncpl,)
        if value_shape == (nrow, ncol) and expected_shape == (ncpl,):
            return True, (ncpl,)

        # Case 4: (nper, nrow, ncol) → (nper, ncpl)
        if "nper" in expected_dims:
            nper = dim_dict["nper"]
            if value_shape == (nper, nrow, ncol) and expected_shape == (nper, ncpl):
                return True, (nper, ncpl)

    return False, None


def _reshape_grid(
    data: np.ndarray | xr.DataArray,
    target_shape: tuple,
    source_dims: list[str] | None = None,
    target_dims: list[str] | None = None,
) -> np.ndarray | xr.DataArray:
    """
    Perform structured↔flat grid conversion.

    Parameters
    ----------
    data : np.ndarray | xr.DataArray
        Input array to reshape
    target_shape : tuple
        Target shape after reshape
    source_dims : list[str] | None
        Source dimension names (for xarray)
    target_dims : list[str] | None
        Target dimension names (for xarray)

    Returns
    -------
    np.ndarray | xr.DataArray
        Reshaped array, preserving xarray metadata if applicable
    """
    if isinstance(data, xr.DataArray):
        # Reshape xarray and update dims
        reshaped_data = data.values.reshape(target_shape)
        if target_dims:
            return xr.DataArray(reshaped_data, dims=target_dims, attrs=data.attrs)
        return xr.DataArray(reshaped_data, attrs=data.attrs)
    else:
        # Simple numpy reshape
        return data.reshape(target_shape)


def _validate_duck_array(
    value: xr.DataArray | np.ndarray,
    expected_dims: list[str],
    expected_shape: tuple,
    dim_dict: dict,
) -> xr.DataArray | np.ndarray:
    """
    Validate and optionally reshape duck arrays.

    Parameters
    ----------
    value : xr.DataArray | np.ndarray
        Input array to validate
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    dim_dict : dict
        Resolved dimension values

    Returns
    -------
    xr.DataArray | np.ndarray
        Validated and possibly reshaped array
    """
    if isinstance(value, xr.DataArray):
        # Check dimension names
        if set(value.dims) != set(expected_dims):
            # Check for structured→flat conversion
            needs_reshape, target_shape = _detect_grid_reshape(value.shape, expected_dims, dim_dict)
            if needs_reshape:
                assert (
                    target_shape is not None
                )  # target_shape is always set when needs_reshape is True
                return _reshape_grid(
                    value, target_shape, [str(d) for d in value.dims], expected_dims
                )
            raise ValueError(f"Dimension mismatch: {value.dims} vs {expected_dims}")
        return value

    elif isinstance(value, np.ndarray):
        # Check shape
        if value.shape != expected_shape:
            # Try structured→flat reshape
            needs_reshape, target_shape = _detect_grid_reshape(value.shape, expected_dims, dim_dict)
            if needs_reshape:
                assert (
                    target_shape is not None
                )  # target_shape is always set when needs_reshape is True
                return _reshape_grid(value, target_shape)
            # Allow 1D float input as a (n, 1) shorthand when the target has a trailing
            # dimension of size 1 (e.g. single-aux: (nlakes,) → (nlakes, naux=1)).
            if (
                value.ndim + 1 == len(expected_shape)
                and expected_shape[-1] == 1
                and np.issubdtype(value.dtype, np.floating)
            ):
                return value.reshape(*value.shape, 1)
            raise ValueError(f"Shape mismatch: {value.shape} vs {expected_shape}")
        return value


def _fill_forward_time(
    data: np.ndarray | xr.DataArray, dims: list[str], nper: int
) -> np.ndarray | xr.DataArray:
    """
    Add nper dimension if missing (broadcast to all periods).

    Parameters
    ----------
    data : np.ndarray | xr.DataArray
        Input array
    dims : list[str]
        Expected dimension names
    nper : int
        Number of stress periods

    Returns
    -------
    np.ndarray | xr.DataArray
        Array with nper dimension added if needed
    """
    if "nper" not in dims:
        return data

    if isinstance(data, xr.DataArray):
        if "nper" not in data.dims:
            # Broadcast to add nper dimension
            data_broadcast = np.broadcast_to(data.values, (nper, *data.shape))
            return xr.DataArray(data_broadcast, dims=["nper"] + list(data.dims), attrs=data.attrs)
        return data

    elif isinstance(data, np.ndarray):
        # Check if nper is in expected dims but not in data shape
        if len(data.shape) < len(dims):
            # Broadcast to add nper dimension
            data_broadcast = np.broadcast_to(data, (nper, *data.shape))
            return data_broadcast
        return data


def _parse_list_format(
    value: list, expected_dims: list[str], expected_shape: tuple, field
) -> np.ndarray:
    """
    Parse nested list formats to numpy array.

    Parameters
    ----------
    value : list
        Input list (possibly nested)
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    field : object
        Field specification

    Returns
    -------
    np.ndarray
        Parsed numpy array
    """
    # Convert to numpy array
    arr = np.array(value, dtype=field.dtype if hasattr(field, "dtype") else None)

    # Validate shape (convert both to tuples for comparison)
    expected_shape_tuple = tuple(expected_shape)
    if arr.shape != expected_shape_tuple:
        raise ValueError(f"List shape {arr.shape} doesn't match expected {expected_shape_tuple}")

    return arr


def _to_xarray(
    data: np.ndarray | sparse.COO,
    dims: list[str],
    coords: dict | None = None,
    attrs: dict | None = None,
) -> xr.DataArray:
    """
    Wrap array in xarray DataArray with metadata.

    Parameters
    ----------
    data : np.ndarray | sparse.COO
        Underlying array data
    dims : list[str]
        Dimension names
    coords : dict | None
        Coordinate arrays for each dimension
    attrs : dict | None
        Metadata attributes

    Returns
    -------
    xr.DataArray
        DataArray with proper metadata
    """
    return xr.DataArray(data=data, dims=dims, coords=coords or {}, attrs=attrs or {})


def _parse_dataframe(
    df: pd.DataFrame,
    field_name: str,
    dim_dict: dict,
) -> dict[int, dict]:
    """
    Parse pandas DataFrame to dict format compatible with stress period data.

    Expected DataFrame format (from stress_period_data property):
    - 'kper' column: stress period index
    - Spatial columns: either ('layer', 'row', 'col') or ('node',)
    - Field value column: named after the field (e.g., 'head', 'elev')

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with stress period data
    field_name : str
        Name of the field to extract values for
    dim_dict : dict
        Resolved dimension values (for coordinate conversion)

    Returns
    -------
    dict[int, dict]
        Dict mapping stress periods to cellid: value dicts
        Format: {kper: {cellid: value, ...}, ...}
    """
    if field_name not in df.columns:
        raise ValueError(
            f"Field '{field_name}' not found in DataFrame columns: {df.columns.tolist()}"
        )

    result: dict[int, dict] = {}

    # Determine coordinate format
    has_structured = all(col in df.columns for col in ["layer", "row", "col"])
    has_node = "node" in df.columns

    if not has_structured and not has_node:
        raise ValueError("DataFrame must have either (layer, row, col) or (node,) columns")

    # Group by stress period
    for kper in df["kper"].unique():
        period_data = df[df["kper"] == kper]
        cellid_dict = {}

        for _, row in period_data.iterrows():
            # Extract cellid based on coordinate format
            if has_structured:
                cellid = (int(row["layer"]), int(row["row"]), int(row["col"]))
            else:
                cellid = (int(row["node"]),)  # type: ignore

            # Extract field value
            value = row[field_name]
            cellid_dict[cellid] = value

        result[int(kper)] = cellid_dict

    return result


def _parse_dict_format(
    value: dict, expected_dims: list[str], expected_shape: tuple, dim_dict: dict, field, self_
) -> dict[int, Any]:
    """
    Parse dict format with fill-forward logic and mixed value types.

    Supports:
    - Stress period dicts: {0: data1, 5: data2} (fills forward)
    - Layer dicts: {0: data1, 1: data2}
    - Mixed value types: xarray, numpy, list, scalar
    - Metadata dicts: {0: {'data': ..., 'factor': 1.0}}
    - External file: {'filename': '...', 'data': [...]}

    Parameters
    ----------
    value : dict
        Input dictionary
    expected_dims : list[str]
        Expected dimension names
    expected_shape : tuple
        Expected shape
    dim_dict : dict
        Resolved dimension values
    field : object
        Field specification
    self_ : object
        Parent object for context

    Returns
    -------
    dict[int, Any]
        Parsed dict with integer keys and normalized values
    """
    # Check for external file format
    if "filename" in value:
        # External file format - for now, just extract data if present
        # TODO: implement actual file reading
        if "data" in value:
            return {0: value["data"]}
        return {0: value}

    wildcard_val = None
    parsed: dict[int, Any] = {}

    for key, val in value.items():
        if key == "*":
            wildcard_val = val
            continue
        elif isinstance(key, str):
            try:
                key = int(key)
            except ValueError:
                continue

        # Skip non-integer keys
        if not isinstance(key, int):
            continue

        # Handle metadata dict format: {0: {'data': ..., 'factor': 1.0}}
        if isinstance(val, dict) and "data" in val:
            # Extract data and metadata
            val = val["data"]
            # TODO: preserve metadata (factor, iprn, etc.) for later use

        # Process value based on type
        if isinstance(val, (xr.DataArray, np.ndarray)):
            # Duck array - validate and reshape if needed
            # For dict values, we need to handle them without the outer dimension
            # since the dict key provides that dimension
            if "nper" in expected_dims or "nlay" in expected_dims:
                # Remove the outer dimension from expected for validation
                inner_dims = expected_dims[1:] if expected_dims else expected_dims
                inner_shape = expected_shape[1:] if expected_shape else expected_shape
            else:
                inner_dims = expected_dims
                inner_shape = expected_shape

            parsed[key] = val

        elif isinstance(val, list):
            # List format
            if "nper" in expected_dims or "nlay" in expected_dims:
                inner_shape = expected_shape[1:] if expected_shape else expected_shape
            else:
                inner_shape = expected_shape

            # Check if it's a list of lists (structured data)
            if val and isinstance(val[0], (list, tuple)):
                # Structured boundary condition data
                parsed[key] = val
            else:
                # Simple list - convert to array
                parsed[key] = np.array(val)

        elif isinstance(val, (int, float)):
            # Scalar value
            parsed[key] = val

        else:
            # Unknown type, store as-is
            parsed[key] = val

    # Expand "*" to every period not already covered by an explicit key.
    if wildcard_val is not None:
        nper = dim_dict.get("nper")
        if nper is not None:
            for kper in range(nper):
                if kper not in parsed:
                    parsed[kper] = wildcard_val
        elif 0 not in parsed:
            parsed[0] = wildcard_val

    return parsed


def _infer_naux(value) -> int | None:
    """Infer the naux dimension from a period-aux value when self_.naux is not set.

    Peeks at the first leaf of a nested dict (kper → cellid → aux_list) or uses
    the last dimension of an array.  Returns None when naux cannot be determined.
    """
    if isinstance(value, np.ndarray):
        return int(value.shape[-1]) if value.ndim >= 3 else 1
    if isinstance(value, xr.DataArray):
        return int(value.shape[-1]) if value.ndim >= 3 else 1
    if isinstance(value, dict):
        v: object = value
        while isinstance(v, dict):
            if not v:
                return 0
            v = next(iter(v.values()))
        if isinstance(v, (list, tuple)):
            return len(v)
        if isinstance(v, (int, float)):
            return 1
    return None


def structure_array(
    value,
    self_,
    field,
    *,
    return_xarray: bool = False,
    sparse_threshold: int | None = None,
    dims: dict | None = None,
) -> xr.DataArray | NDArray | sparse.COO:
    """
    Convert various array representations to structured arrays.

    Supports:
    - Dict-based sparse formats (stress periods, layers) with fill-forward
    - List-based formats (nested lists)
    - Duck arrays (xarray, numpy) with validation/reshaping
    - Scalars (broadcast to full shape)
    - External file metadata dicts
    - Mixed value types within dicts

    Parameters
    ----------
    value : dict | list | xr.DataArray | np.ndarray | float | int
        Input data in any supported format
    self_ : object
        Parent object containing dimension context
    field : object
        Field specification with dims, dtype, default
    return_xarray : bool, default False
        If True, return xr.DataArray; otherwise return raw array (for backward compatibility)
    sparse_threshold : int | None
        Override default sparse threshold for COO vs dense
    dims : dict | None
        Explicit dimension sizes (e.g., {'nper': 10, 'nodes': 100}).
        If provided, takes precedence over dims from parent or self_.

    Returns
    -------
    xr.DataArray | np.ndarray | sparse.COO
        Structured array with proper shape and metadata
    """
    # When naux is in the field dims but self_ hasn't had it set yet (direct
    # construction without explicit naux kwarg), infer it from the value shape.
    # Also set self_.naux so xattree's dimension resolution can see it when it
    # processes the returned DataArray during __setattr__.
    if field.dims and "naux" in field.dims and not isinstance(getattr(self_, "naux", None), int):
        inferred = _infer_naux(value)
        if inferred is not None:
            try:
                self_.naux = inferred
            except Exception:
                pass
            dims = dict(dims or {})
            dims["naux"] = inferred

    # Resolve dimensions
    dims_names, shape, dim_dict = _resolve_dimensions(self_, field, dims=dims)
    threshold = sparse_threshold if sparse_threshold is not None else SPARSE_THRESHOLD

    # Handle different input types
    if isinstance(value, pd.DataFrame):
        # Parse DataFrame format (from stress_period_data property)
        # Convert to dict format for processing
        value = _parse_dataframe(value, field.name, dim_dict)
        # Continue processing as dict below

    if isinstance(value, dict):
        # Parse dict format with fill-forward logic
        parsed_dict = _parse_dict_format(value, dims_names, tuple(shape), dim_dict, field, self_)

        # Build array using sparse or dense approach
        if np.prod(shape) > threshold:
            # Sparse approach
            coords_dict: dict[tuple[Any, ...], Any] = {}

            for key, val in parsed_dict.items():
                if isinstance(val, (int, float, str)):
                    # Scalar value (number or string) - set for entire period/layer
                    if "nper" in dim_dict:
                        coords_dict[(key,)] = val
                    else:
                        # Fill entire spatial extent with scalar
                        if len(shape) == 1:
                            coords_dict[(key,)] = val
                        else:
                            # For now, store scalar - will be expanded later
                            coords_dict[(key,)] = val
                elif isinstance(val, list) and val and isinstance(val[0], (list, tuple)):
                    # Structured boundary condition data: [[cellid, ...], ...]
                    for row in val:
                        cellid = (
                            row[0] if isinstance(row[0], tuple) else tuple(row[: len(shape) - 1])
                        )
                        value_data = row[-1]
                        nn = get_nn(cellid, **dim_dict)
                        if "nper" in dims_names:
                            coords_dict[(key, nn)] = value_data
                        else:
                            coords_dict[(nn,)] = value_data
                elif isinstance(val, dict):
                    # Nested dict: {cellid: value}
                    for cellid, v in val.items():
                        nn = get_nn(cellid, **dim_dict)
                        if "nper" in dims_names:
                            coords_dict[(key, nn)] = v
                        else:
                            coords_dict[(nn,)] = v
                else:
                    # Other types (including custom objects) - store as scalar for this period/layer
                    if "nper" in dim_dict or "nlay" in dim_dict:
                        coords_dict[(key,)] = val
                    else:
                        if len(shape) == 1:
                            coords_dict[(key,)] = val
                        else:
                            coords_dict[(key,)] = val

            # Convert to sparse COO
            if coords_dict:
                coords = np.array(list(map(list, zip(*coords_dict.keys()))))
                result = sparse.COO(
                    coords,
                    list(coords_dict.values()),
                    shape=shape,
                    fill_value=FILL_DNODATA,
                )
            else:
                # Empty dict - return empty sparse array
                result = sparse.COO(
                    np.empty((len(shape), 0), dtype=int),
                    [],
                    shape=shape,
                    fill_value=FILL_DNODATA,
                )
        else:
            # Dense approach
            result = np.full(shape, FILL_DNODATA, dtype=field.dtype)

            # Keystring (OC) fields use no fill-forward: each key covers only
            # that period.  Stress-package dicts fill forward from each key to
            # the next specified key so boundary conditions persist by default.
            is_keystring = getattr(field, "metadata", {}).get("keystring", False)

            sorted_keys = sorted(parsed_dict.keys())
            for idx, key in enumerate(sorted_keys):
                val = parsed_dict[key]

                # Determine fill range
                if "nper" in dims_names and not is_keystring:
                    next_key = (
                        sorted_keys[idx + 1]
                        if idx + 1 < len(sorted_keys)
                        else dim_dict.get("nper", key + 1)
                    )
                    kper_range = range(key, next_key)
                else:
                    kper_range = range(key, key + 1)

                for kper in kper_range:
                    if isinstance(val, (int, float, str)):
                        # Scalar value (number or string)
                        if len(shape) == 1:
                            result[kper] = val
                        else:
                            result[kper] = np.full(shape[1:], val, dtype=field.dtype)
                    elif isinstance(val, list) and val and isinstance(val[0], (list, tuple)):
                        # Structured boundary condition data
                        for row in val:
                            cellid = (
                                row[0]
                                if isinstance(row[0], tuple)
                                else tuple(row[: len(shape) - 1])
                            )
                            value_data = row[-1]
                            nn = get_nn(cellid, **dim_dict)
                            if "nper" in dims_names:
                                result[kper, nn] = value_data
                            else:
                                result[nn] = value_data
                    elif isinstance(val, dict):
                        # Nested dict: {cellid: value}
                        for cellid, v in val.items():
                            nn = get_nn(cellid, **dim_dict)
                            if "nper" in dims_names:
                                result[kper, nn] = v
                            else:
                                result[nn] = v
                    elif isinstance(val, np.ndarray):
                        # Array value
                        if "nper" in dims_names:
                            result[kper] = val
                        else:
                            result = val
                    elif isinstance(val, xr.DataArray):
                        # xarray value
                        if "nper" in dims_names:
                            result[kper] = val.values
                        else:
                            result = val.values
                    else:
                        # Other types (including custom objects) - store as-is
                        if len(shape) == 1:
                            result[kper] = val
                        else:
                            # For multi-dimensional arrays with object dtype, store the object
                            result[kper] = val

    elif isinstance(value, list):
        # List format
        result = _parse_list_format(value, dims_names, tuple(shape), field)

    elif isinstance(value, (xr.DataArray, np.ndarray)):
        # For cellid=True fields: convert 2D (N, ncelldim) integer array to 1D object array
        # of tuples so the writer can emit each component individually with +1 conversion.
        if (
            isinstance(value, np.ndarray)
            and value.ndim == 2
            and len(shape) == 1
            and value.shape[0] == shape[0]
            and getattr(field, "metadata", {}).get("cellid")
        ):
            obj = np.empty(value.shape[0], dtype=object)
            for _ci in range(value.shape[0]):
                obj[_ci] = tuple(int(x) for x in value[_ci])
            value = obj

        # Duck array - validate and reshape if needed
        result = _validate_duck_array(value, dims_names, tuple(shape), dim_dict)

        # Handle time fill-forward
        if "nper" in dims_names and "nper" in dim_dict:
            result = _fill_forward_time(result, dims_names, dim_dict["nper"])

    elif isinstance(value, (int, float)):
        # Scalar - broadcast to full shape
        result = np.full(shape, value, dtype=field.dtype)

    else:
        # Unknown type - return as-is for backward compatibility
        return value

    # Wrap in xarray if requested
    if return_xarray and not isinstance(result, xr.DataArray):
        # Build coordinates
        xr_coords: dict[str, Any] = {}
        for dim in dims:  # type: ignore
            if dim in dim_dict:
                xr_coords[dim] = np.arange(dim_dict[dim])

        result = _to_xarray(result, dims, xr_coords)  # type: ignore

    return result
