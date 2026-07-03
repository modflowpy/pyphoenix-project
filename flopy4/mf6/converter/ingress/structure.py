from typing import Any, get_args

import attrs
import numpy as np

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.package import Package
from flopy4.mf6.schema import Schema


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


_DTYPE_MAP = Package._DTYPE_MAP


def _parse_rows_to_recarray(
    rows: list,
    schema: "type[Schema]",  # type: ignore[name-defined]
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

    cols = schema.columns()
    cellid_col = next((c for c in cols if c.role == "cellid"), None)
    feature_id_cols = [c for c in cols if c.role == "feature_id"]
    value_cols = [c for c in cols if c.role == "value"]
    boundname_col = next((c for c in cols if c.role == "boundname"), None)
    keystring_cols = [c for c in cols if c.role in ("keystring", "keystring_value")]
    inline_kw_cols = [c for c in cols if c.role == "inline_keyword"]
    # Count only value columns that are actually emitted in each row for ncelldim
    # inference.  Columns that are optional AND not time_series are excluded from
    # the recarray dtype by __attrs_post_init__ and therefore absent from emitted
    # rows; counting them inflates n_fixed and under-counts ncelldim.
    required_value_cols = [c for c in value_cols if not c.optional or c.time_series]
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
    for col in cols:
        if col.role == "cellid":
            dtype_fields.append(("cellid", np.int64, (ncelldim,)))
        elif col.role == "feature_id":
            dtype_fields.append((col.name, np.int64))
        elif col.role == "value":
            if col.dtype:
                dt = _DTYPE_MAP.get(col.dtype, np.object_)
            elif col.time_series:
                dt = np.object_
            else:
                dt = _DTYPE_MAP.get(col.dfn_type, np.float64)
            dtype_fields.append((col.name, dt))
        elif col.role in ("keystring", "keystring_value"):
            dtype_fields.append((col.name, np.object_))
        elif col.role == "inline_keyword":
            dtype_fields.append((col.name, np.object_))
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

        for col in cols:
            if col.role == "cellid":
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
            elif col.role == "feature_id":
                record.append(int(float(str(row[tok_idx]))) - 1)
                tok_idx += 1
            elif col.role == "value":
                if tok_idx >= len(row):
                    record.append(None)
                    continue
                if col.prefix:
                    tok_idx += len(col.prefix.split())
                if tok_idx >= len(row):
                    record.append(None)
                    continue
                tok = row[tok_idx]
                if col.dtype or col.time_series:
                    try:
                        record.append(float(tok))
                    except (ValueError, TypeError):
                        record.append(str(tok))
                else:
                    col_dtype = _DTYPE_MAP.get(col.dfn_type, np.float64)
                    record.append(_coerce_token(tok, col_dtype))
                tok_idx += 1
            elif col.role in ("keystring", "keystring_value"):
                if tok_idx >= len(row):
                    record.append(None)
                else:
                    record.append(str(row[tok_idx]))
                    tok_idx += 1
            elif col.role == "inline_keyword":
                kw = col.name.upper()
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
        if f is None or f.metadata.get("block") != "griddata":
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
                    if vrow and str(vrow[0]).upper() == "INTERNAL":
                        if i >= len(rows):
                            break
                        vrow = rows[i]
                        i += 1
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
                if vrow and str(vrow[0]).upper() == "INTERNAL":
                    if i >= len(rows):
                        break
                    vrow = rows[i]
                    i += 1
                result[f.name] = np.array(vrow, dtype=np.int64 if is_int else np.float64)

    return result


def _parse_readarray_period_block(
    rows: list, ra_fields: dict, dims: dict
) -> "dict[str, np.ndarray]":
    """Parse one READARRAY period block (rows from a BEGIN PERIOD N block).

    Returns {field_name: ndarray} shaped (ncpl,) for non-layered fields
    or (nlay, ncpl) for layered fields.
    """
    nlay = dims.get("nlay", 1)
    nodes = dims.get("nodes", 1)
    ncpl = nodes // nlay if nlay > 1 else nodes

    result: dict[str, np.ndarray] = {}
    i = 0
    while i < len(rows):
        row = rows[i]
        if not row:
            i += 1
            continue
        key = str(row[0]).lower()
        f = ra_fields.get(key)
        if f is None:
            i += 1
            continue
        is_int = f.metadata.get("dfn_type") in ("integer",)
        is_layered = f.metadata.get("layered", False) or any(
            str(t).upper() == "LAYERED" for t in row[1:]
        )
        i += 1
        dtype = np.int64 if is_int else np.float64

        if is_layered:
            layers = []
            for _ in range(nlay):
                if i >= len(rows):
                    break
                vrow = rows[i]
                i += 1
                if vrow and str(vrow[0]).upper() == "CONSTANT":
                    v = int(vrow[1]) if is_int else float(vrow[1])
                    layers.append(np.full(ncpl, v, dtype=dtype))
                else:
                    if vrow and str(vrow[0]).upper() == "INTERNAL":
                        if i >= len(rows):
                            break
                        vrow = rows[i]
                        i += 1
                    layers.append(np.array(vrow, dtype=dtype))
            result[f.name] = np.stack(layers)  # (nlay, ncpl)
        else:
            if i >= len(rows):
                break
            vrow = rows[i]
            i += 1
            if vrow and str(vrow[0]).upper() == "CONSTANT":
                v = int(vrow[1]) if is_int else float(vrow[1])
                result[f.name] = np.full(ncpl, v, dtype=dtype)
            else:
                if vrow and str(vrow[0]).upper() == "INTERNAL":
                    if i >= len(rows):
                        break
                    vrow = rows[i]
                    i += 1
                result[f.name] = np.array(vrow, dtype=dtype)

    return result


def structure_component(raw: dict, cls: type, *, dims: dict | None = None) -> Any:
    """Reconstruct a component instance from a raw parsed MF6 input dict.

    Parameters
    ----------
    raw : dict
        Output of ``loads()`` — {BLOCK_NAME_UPPER: list_of_token_rows}.
    cls : type
        The component class to instantiate. Fields are read via ``block``/
        ``schema``/``oc_action`` metadata (see ``flopy4.mf6.spec.field``).
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
        block = f.metadata.get("block", "")
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

        else:
            # ── Pass 3b: READARRAY period fields (G/A variants) ─────────────
            # Packages like Rcha/Chdg store full-grid arrays per stress period.
            # Each field has block="period" + reader="readarray".
            ra_fields = {
                f.name: f
                for f in attrs.fields(cls)
                if f.metadata.get("block") == "period"
                and f.metadata.get("reader") == "readarray"
                and f.init is not False
            }
            if ra_fields and dims:
                nper = max(kper_rows.keys()) + 1
                nlay = dims.get("nlay", 1)
                nodes = dims.get("nodes", 1)
                ncpl = nodes // nlay if nlay > 1 else nodes
                # Pre-fill with FILL_DNODATA; periods absent from file use MF6
                # fill-forward semantics (egress skips all-FILL_DNODATA periods).
                accum: dict[str, np.ndarray] = {}
                for fname, f in ra_fields.items():
                    shape = (nper, nlay, ncpl) if f.metadata.get("layered", False) else (nper, ncpl)
                    accum[fname] = np.full(shape, FILL_DNODATA)
                for kper, rows in sorted(kper_rows.items()):
                    if not rows:
                        continue
                    parsed = _parse_readarray_period_block(rows, ra_fields, dims)
                    for fname, arr in parsed.items():
                        accum[fname][kper] = arr
                kwargs.update(accum)

    # ── Pass 4: griddata block ────────────────────────────────────────────────
    if dims:
        griddata_rows = raw_lower.get("griddata", [])
        if griddata_rows:
            gd_fields = {
                f.name: f
                for f in attrs.fields(cls)
                if f.metadata.get("block") == "griddata" and f.init is not False
            }
            parsed = _parse_griddata_block(griddata_rows, gd_fields, dims)
            kwargs.update(parsed)

    return cls(**kwargs)
