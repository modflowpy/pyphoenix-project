import struct
from abc import ABC
from pathlib import Path
from typing import Any, get_args

import attrs
import numpy as np
import xattree

from flopy4.dimensions import DimensionProvider
from flopy4.mf6.component import Component, get_ftype
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.item import Item, infer_ncelldim, item_list_type, parse_union_items
from flopy4.mf6.package import Package
from flopy4.mf6.spec import to_field_type


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


def _parse_rows(
    rows: list,
    item_cls: "type[Item] | tuple[type[Item], ...]",
    *,
    naux: int = 0,
    boundnames: bool = False,
    dims: "dict | None" = None,
) -> list | None:
    """Parse raw token rows into a list of Item instances.

    item_cls is either a single Item class or a tuple of arm classes for a
    keystring union field, dispatched per-row by keyword token (see
    item.parse_union_items). ncelldim (a variable-width cellid's element
    count) is inferred once from the first row -- not applicable to unions
    (arms with a cellid field aren't a case seen in the corpus). Prefers
    `dims` (unambiguous: 3/2/1 for DIS/DISV/DISU) over counting row tokens
    when available -- see `item.infer_ncelldim`.
    """
    if not rows:
        return None
    if isinstance(item_cls, tuple):
        return parse_union_items(rows, item_cls, naux=naux, boundnames=boundnames)
    ncelldim = infer_ncelldim(rows, item_cls, naux=naux, dims=dims)
    result = [
        item_cls.from_tokens(row, ncelldim=ncelldim, naux=naux, boundnames=boundnames)
        for row in rows
        if row
    ]
    return result or None


# One MF6 binary-array record: KSTP, KPER (int4 each), PERTIM, TOTIM
# (float8 each), TEXT (16-byte label), NCOL, NROW, ILAY (int4 each) -- 52
# bytes total. Same layout flopy4's own binary head-output reader
# (`utils/heads_reader.py::read_hds_timestep`, "f.seek(52, 1)  # skip
# kstp, kper, pertime") already decodes; MF6 has used one binary
# 2D-array record format for both real and integer arrays since
# MODFLOW-2005 (u2drel/u2dint), for output and OPEN/CLOSE (BINARY) input
# alike -- the data portion follows immediately, NROW*NCOL values, real
# arrays double-precision (matching MF6's own double-precision solver and
# head-output convention) and integer arrays 4-byte.
_BINARY_ARRAY_HEADER = struct.Struct("<iidd16siii")


def _read_binary_array_values(path: Path, dtype) -> np.ndarray:
    """Read one MF6 binary-array record (header + NROW*NCOL values) from
    an OPEN/CLOSE (BINARY)-referenced file. See `_BINARY_ARRAY_HEADER`.
    """
    with path.open("rb") as fh:
        header = fh.read(_BINARY_ARRAY_HEADER.size)
        if len(header) < _BINARY_ARRAY_HEADER.size:
            raise ValueError(f"{path}: too short for an MF6 binary-array header")
        *_, ncol, nrow, _ilay = _BINARY_ARRAY_HEADER.unpack(header)
        file_dtype = np.int32 if dtype == np.int64 else np.float64
        values = np.fromfile(fh, dtype=file_dtype, count=nrow * ncol)
    if values.size != nrow * ncol:
        raise ValueError(
            f"{path}: expected {nrow * ncol} values (NROW={nrow}, NCOL={ncol}), got {values.size}"
        )
    return values.astype(dtype)


def _strip_quotes(fname: str) -> str:
    """MF6 (and flopy3's own writer, confirmed against its
    `test_gwf_utl01_binaryinput.py`: writes ``OPEN/CLOSE 'top.bin' ...``)
    allows an OPEN/CLOSE filename to be single- or double-quoted; `word`'s
    tokenizer keeps the quote characters as part of the token since they're
    valid filename characters on their own. Strip one matching pair from
    the ends, if present."""
    if len(fname) >= 2 and fname[0] == fname[-1] and fname[0] in ("'", '"'):
        return fname[1:-1]
    return fname


def _read_open_close_values(vrow: list, workspace: "Path | None", dtype) -> np.ndarray:
    """Read an ``OPEN/CLOSE <fname> [(BINARY)] [FACTOR <f>] [IPRN <i>]``
    griddata control record's referenced file.

    Not seen in the corpus (0/242 models use OPEN/CLOSE ... (BINARY) for
    an input array) so this path is unverified against a real fixture --
    based on the binary-array record format flopy4's own head-output
    reader already relies on, per `_BINARY_ARRAY_HEADER`. Otherwise the
    referenced file is a plain numeric array, whitespace- or (seen in one
    fixture family) comma-separated with no spaces at all, optionally
    scaled by FACTOR.
    """
    tokens = [str(t) for t in vrow[1:]]
    if not tokens:
        raise ValueError("OPEN/CLOSE control record missing a filename")
    fname = _strip_quotes(tokens[0])
    if workspace is None:
        raise ValueError(f"OPEN/CLOSE {fname}: no workspace to resolve the referenced file")
    path = workspace / fname

    if any(t.upper() in ("BINARY", "(BINARY)") for t in tokens[1:]):
        values = _read_binary_array_values(path, dtype)
    else:
        text = path.read_text().replace(",", " ")
        values = np.array(text.split(), dtype=dtype)

    for j, tok in enumerate(tokens[1:], start=1):
        if tok.upper() == "FACTOR" and j + 1 < len(tokens):
            factor = tokens[j + 1]
            values = values * (int(factor) if dtype == np.int64 else float(factor))
            break
    return values


def _resolve_open_close_rows(rows: list, workspace: "Path | None") -> list:
    """A period/list block's row data can itself be OPEN/CLOSE-redirected
    to an external file instead of written inline -- MF6 syntax:
    ``BEGIN PERIOD 1 / OPEN/CLOSE <fname> / END PERIOD 1``. Same keyword as
    griddata's OPEN/CLOSE control record, but a different mechanism: the
    referenced file holds list rows, not a flat numeric array, so it's
    parsed the same way an inline block's own content would be (wrapped in
    a synthetic block and run back through the block/token grammar) rather
    than through `_read_open_close_values`.

    Detects that shape -- a block whose *only* content is one OPEN/CLOSE
    row -- and returns the referenced file's rows in its place; otherwise
    returns `rows` unchanged.
    """
    if len(rows) != 1 or not rows[0] or str(rows[0][0]).upper() != "OPEN/CLOSE":
        return rows
    row = rows[0]
    if len(row) < 2:
        raise ValueError("OPEN/CLOSE control record missing a filename")
    fname = _strip_quotes(str(row[1]))
    if workspace is None:
        raise ValueError(f"OPEN/CLOSE {fname}: no workspace to resolve the referenced file")

    from flopy4.mf6.codec.reader import loads as _codec_loads

    text = (workspace / fname).read_text()
    wrapped = _codec_loads(f"BEGIN DATA\n{text}\nEND DATA\n")
    return wrapped.get("DATA", [])


def _numeric_prefix(row: list) -> list:
    """Tokens from the start of `row` up to (not including) the first
    non-numeric one. Real INTERNAL/bare-data-row array data is purely
    numeric; a trailing inline annotation -- e.g. a "row 1" remark seen
    on some fixtures, one per data line, as many lines as the array has
    -- always starts with a non-numeric word, so stopping there drops
    the annotation without needing to know each line's real data width
    up front (unlike a single trailing annotation on the array's last
    line only, `_read_control_record`'s final `values[:length]` slice
    already handles that case)."""
    out = []
    for tok in row:
        if not isinstance(tok, (int, float)):
            try:
                float(tok)
            except (TypeError, ValueError):
                break
        out.append(tok)
    return out


def _read_control_record(
    rows: list, i: int, workspace: "Path | None", dtype, length: int
) -> "tuple[np.ndarray, int]":
    """Read one CONSTANT/INTERNAL/OPEN-CLOSE array control record starting
    at ``rows[i]``, shared by griddata (`_parse_griddata_block`) and
    READARRAY period (`_parse_readarray_period_block`) array ingress.

    Always returns a full ``length``-element ``ndarray`` (CONSTANT
    broadcasts here rather than leaving that to the caller) plus the next
    row index to resume from. INTERNAL's (and a bare, keyword-less data
    row's) values commonly wrap across multiple physical lines for a large
    array -- each is one row here -- so both keep consuming rows until
    ``length`` values are collected, rather than assuming exactly one row.
    """
    vrow = rows[i]
    kind = str(vrow[0]).upper() if vrow else ""
    if kind == "CONSTANT":
        v = int(vrow[1]) if dtype == np.int64 else float(vrow[1])
        return np.full(length, v, dtype=dtype), i + 1
    if kind == "OPEN/CLOSE":
        return _read_open_close_values(vrow, workspace, dtype), i + 1
    j = i + 1 if kind == "INTERNAL" else i
    values: list = []
    while len(values) < length and j < len(rows):
        values.extend(_numeric_prefix(rows[j]))
        j += 1
    return np.array(values[:length], dtype=dtype), j


def _griddata_flat_length(f, dims: dict, default: int) -> int:
    """Target length for a non-layered griddata field's flat array --
    e.g. DIS's `delr`/`delc` are `(ncol,)`/`(nrow,)`, not `(nodes,)`. Falls
    back to `default` (the grid's total node count) when the field's
    declared shape dimension isn't resolvable from `dims`.
    """
    shape_meta = f.metadata.get("shape")
    if shape_meta:
        dim_name = shape_meta[-1] if isinstance(shape_meta, (tuple, list)) else shape_meta
        if dim_name in dims:
            return dims[dim_name]
    return default


def _parse_griddata_block(
    rows: list, fields_by_name: dict, dims: dict, workspace: "Path | None" = None
) -> dict:
    """Parse GRIDDATA token rows into {field_name: np.ndarray}.

    Token rows alternate: [field_name, ?LAYERED] then one control record
    per layer (LAYERED) or a single one otherwise -- CONSTANT/INTERNAL/
    OPEN-CLOSE, per `_read_control_record`.
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

        dtype = np.int64 if to_field_type(f.type) == "integer" else np.float64
        layered = any(str(t).upper() == "LAYERED" for t in row[1:])
        i += 1

        if layered:
            # Read as many per-layer control records as are actually there,
            # rather than assuming exactly `nlay` -- some real-world files
            # (mf5to15-converted ones observed so far) tag a field LAYERED
            # with fewer rows than nlay (e.g. a single-row TOP); trusting
            # nlay blindly would consume the next field's name row as if
            # it were layer data. Stops at the first row that isn't a
            # recognized control record -- i.e. the next field's row.
            #
            # Per-record length is min(ncpl, target): correct for a truly
            # per-layer field (botm/idomain, shape=(nodes,), target > ncpl)
            # *and* for a field tagged LAYERED despite not truly being one
            # (delr/delc/top, shape=(ncol,)/(nrow,)/(ncpl,), target <=
            # ncpl) -- using ncpl unconditionally there would read far more
            # values than the field's one real record has, consuming
            # however many subsequent lines (including the next field's
            # own name row) it takes to reach ncpl values.
            target = _griddata_flat_length(f, dims, nodes)
            record_len = min(ncpl, target) if target else ncpl
            layers = []
            while i < len(rows):
                vrow = rows[i]
                if not vrow or str(vrow[0]).upper() not in ("CONSTANT", "INTERNAL", "OPEN/CLOSE"):
                    break
                value, i = _read_control_record(rows, i, workspace, dtype, record_len)
                layers.append(value)
            if layers:
                # A single-record LAYERED field (see above) is really a
                # plain target-shaped array duplicated across nlay --
                # broadcast to it rather than leaving it short
                # (concatenating fewer than nlay records would).
                stacked = np.concatenate(layers).astype(dtype)
                if stacked.size < target and stacked.size and target % stacked.size == 0:
                    stacked = np.tile(stacked, target // stacked.size)
                result[f.name] = stacked
        else:
            if i >= len(rows):
                break
            length = _griddata_flat_length(f, dims, nodes)
            value, i = _read_control_record(rows, i, workspace, dtype, length)
            result[f.name] = value

    return result


def _self_dims_from_kwargs(kwargs: dict) -> dict:
    """Derive grid dimensions from a component's own just-parsed DIMENSIONS
    block (already in `kwargs` from Pass 1) -- needed when structuring a
    `DimensionProvider` itself (Dis/Disv/...): its GRIDDATA block has to be
    parsed before an instance -- and thus `get_dims()` -- exists, and
    before it's registered as a sibling dims source for anyone else. A
    no-op ({}) for any other class, which simply has none of these fields.
    """
    keys = ("nlay", "nrow", "ncol", "ncpl", "nvert", "nodes")
    local = {k: kwargs[k] for k in keys if isinstance(kwargs.get(k), int)}
    if "ncpl" not in local and "nrow" in local and "ncol" in local:
        local["ncpl"] = local["nrow"] * local["ncol"]
    if "nodes" not in local and "nlay" in local and "ncpl" in local:
        local["nodes"] = local["nlay"] * local["ncpl"]
    return local


def _parse_readarray_period_block(
    rows: list, ra_fields: dict, dims: dict, workspace: "Path | None" = None
) -> "dict[str, np.ndarray]":
    """Parse one READARRAY period block (rows from a BEGIN PERIOD N block).

    Returns {field_name: ndarray} shaped (ncpl,) for non-layered fields
    or (nlay, ncpl) for layered fields. Control records (CONSTANT/
    INTERNAL/OPEN-CLOSE) are the same vocabulary as griddata blocks -- see
    `_read_control_record`, shared with `_parse_griddata_block`.
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
        i += 1

        # A field can be sourced from a named time-array-series instead of
        # literal data -- "RECHARGE TIMEARRAYSERIES <name>" -- rather than
        # a CONSTANT/INTERNAL/OPEN-CLOSE control record following on its
        # own row. Not resolved to real values yet (would need reading and
        # time-interpolating the referenced .tas file); just consume this
        # one row and move on, rather than misreading the *next* row as
        # this field's data.
        if any(str(t).upper() in ("TIMEARRAYSERIES", "TAS6") for t in row[1:]):
            continue

        if f is None:
            # Unrecognized field name -- e.g. a per-period AUXILIARY-named
            # array (RCHA/EVTA-style: `AUXILIARY <name>` in OPTIONS lets
            # `<name>` appear as its own array field in the period block,
            # keyed dynamically, so it's not one of `ra_fields`'s declared
            # class fields). Still consume its control-record data so it
            # doesn't get mistaken for the *next* real field's row; just
            # don't store it (not resolved to a real array yet either).
            is_layered_unknown = any(str(t).upper() == "LAYERED" for t in row[1:])
            if is_layered_unknown:
                while i < len(rows):
                    vrow = rows[i]
                    if not vrow or str(vrow[0]).upper() not in (
                        "CONSTANT",
                        "INTERNAL",
                        "OPEN/CLOSE",
                    ):
                        break
                    _, i = _read_control_record(rows, i, workspace, np.float64, ncpl)
            elif i < len(rows):
                _, i = _read_control_record(rows, i, workspace, np.float64, ncpl)
            continue

        is_int = to_field_type(f.type) == "integer"
        is_layered = f.metadata.get("layered", False) or any(
            str(t).upper() == "LAYERED" for t in row[1:]
        )
        dtype = np.int64 if is_int else np.float64

        if is_layered:
            # Same "read what's actually there, don't assume exactly nlay
            # rows" lookahead as _parse_griddata_block's LAYERED branch.
            layers = []
            while i < len(rows):
                vrow = rows[i]
                if not vrow or str(vrow[0]).upper() not in ("CONSTANT", "INTERNAL", "OPEN/CLOSE"):
                    break
                value, i = _read_control_record(rows, i, workspace, dtype, ncpl)
                layers.append(value)
            if layers:
                if len(layers) < nlay:
                    layers = (layers * nlay)[:nlay]
                result[f.name] = np.stack(layers)  # (nlay, ncpl)
        else:
            if i >= len(rows):
                break
            value, i = _read_control_record(rows, i, workspace, dtype, ncpl)
            result[f.name] = value

    return result


def _binding_target_classes(child_type: type) -> "tuple[type[Component], ...]":
    """The concrete `Component` subclass(es) a xattree `Child.type` accepts.

    `xattree.get_xatspec()` already unwraps `Optional`/`list`/`dict` down to
    the child's element type -- only a bare `Union[A, B]` (e.g. a G/A-variant
    package pair like `Union[Chd, Chdg]`) needs unwrapping here.
    """
    args = get_args(child_type)
    return args if args else (child_type,)


def _apply_binding_terms(child: Any, terms: list) -> None:
    """Ingress mirror of `converter/binding.py`'s `Binding.from_component`'s
    `_get_binding_terms`: for `Exchange`/`Solution` targets, a binding
    row's trailing terms carry real semantic data (the two model names an
    exchange couples, or the model name(s) a solution applies to) that
    isn't recoverable from the referenced file's own content -- write it
    back onto the loaded child. A `Model`/`Package` target's trailing term
    is just its pname, handled by the caller (`_resolve_bindings`) via
    `Component.pname`, not state to set here.
    """
    from flopy4.mf6.exchange import Exchange
    from flopy4.mf6.solution import Solution

    if not terms:
        return
    if isinstance(child, Exchange):
        if len(terms) > 0:
            child.exgmnamea = str(terms[0])
        if len(terms) > 1:
            child.exgmnameb = str(terms[1])
    elif isinstance(child, Solution):
        child.models = [str(t) for t in terms]


def _disambiguate_ga_variant(candidates: "list[type[Component]]", path: Path) -> "type[Component]":
    """Pick between a base package class and its G/A-variant sibling (e.g.
    Chd vs Chdg) when both share one namefile ftype (see
    `component_ftype()`'s docstring) -- real MF6 decides this from a
    READASARRAYS/READARRAYGRID option keyword inside the file itself, not
    the namefile row, so peek the file's own text for either marker rather
    than requiring a per-package-family keyword table (both markers are
    used consistently, one across RCH/EVT, the other across CHD/DRN/GHB/
    RIV/WEL).
    """
    text = path.read_text().upper()
    is_variant = "READASARRAYS" in text or "READARRAYGRID" in text
    for c in candidates:
        suffixed = len(c.__name__) == 4 and c.__name__[-1] in ("g", "a")
        if suffixed == is_variant:
            return c
    return candidates[0]


def _resolve_bindings(cls: type, raw_lower: dict, workspace: Path) -> dict[str, Any]:
    """Resolve packages/models/exchanges/solutiongroup-style binding rows
    into loaded child component instances, keyed by field name -- merged
    into `structure_component`'s kwargs so children are attached the same
    way manual construction already attaches them (`Gwf(dis=Dis(...))`).

    Child-Component fields are found via `xattree.get_xatspec(cls).children`
    (mirroring `unstructure.py`'s `_make_binding_blocks`, the egress side of
    this same job), grouped by block name since several fields can share one
    block (every `Gwf` package field shares `"packages"`). Within a block,
    `DimensionProvider` targets (`dis`/`disv`/`disu`) are resolved first so
    their dims can be threaded into that block's other `Package.load(...,
    dims=dims)` calls -- `dimensions.py`'s object-graph walk only helps once
    a child is already attached, not while its siblings are still loading.
    """
    from flopy4.mf6.converter.binding import component_ftype
    from flopy4.mf6.exchange import Exchange
    from flopy4.mf6.model import Model
    from flopy4.mf6.solution import Solution

    xatspec = xattree.get_xatspec(cls)
    if not xatspec.children:
        return {}

    # Model scope to prefer when resolving this class's own binding rows'
    # ftype tokens via get_ftype() below -- e.g. structuring a Gwf's
    # "packages" block should resolve "DIS6" to gwf's own Dis, not gwt's/
    # gwe's/prt's.
    # A Model class's __module__ is "flopy4.mf6.<model>" (defined directly
    # in that subpackage's __init__.py), not "...<model>.<name>" like its
    # child packages, so this can't reuse component.py's _model_prefix --
    # a Model's own class name *is* its model prefix by convention.
    model_prefix = cls.__name__.lower() if issubclass(cls, Model) else None

    fields_by_block: dict[str, list] = {}
    for child_name, child_spec in xatspec.children.items():
        fields_by_block.setdefault((child_spec.metadata or {})["block"], []).append(
            (child_name, child_spec)
        )

    kwargs: dict[str, Any] = {}
    for block_name, field_specs in fields_by_block.items():
        # Some binding blocks are numbered (e.g. "SOLUTIONGROUP 1", like
        # "PERIOD 1" elsewhere) -- gather every raw block whose name matches
        # or starts with "{block_name} ".
        rows = [
            row
            for raw_name, raw_rows in raw_lower.items()
            if raw_name == block_name or raw_name.startswith(f"{block_name} ")
            for row in raw_rows
        ]
        if not rows:
            continue

        # Resolve each row's target class + owning field up front, so rows
        # can be reordered (dims providers first) without re-parsing.
        resolved = []
        for row in rows:
            if not row:
                continue
            token = str(row[0]).lower()
            for child_name, child_spec in field_specs:
                accepted = _binding_target_classes(child_spec.type)

                # Concrete candidates first: compare each accepted class's
                # own ftype directly to the row's token. G/A-variant pairs
                # (Chd/Chdg, Rch/Rcha, ...) share one namefile ftype (real
                # MF6 has no separate 'CHDG6' case, only 'CHD6' -- see
                # component_ftype()'s docstring), so more than one concrete
                # candidate can match; disambiguate from the file content.
                concrete = [c for c in accepted if ABC not in c.__bases__]
                matches = [c for c in concrete if component_ftype(c).lower() == token]
                if len(matches) > 1:
                    target_cls = _disambiguate_ga_variant(matches, workspace / str(row[1]))
                elif matches:
                    target_cls = matches[0]
                else:
                    # Fall back to the ftype registry for abstract-typed
                    # fields (Model/Exchange/Solution/DisBase), where the
                    # field's declared type can't be compared to a token
                    # directly.
                    resolved_cls = get_ftype(token, prefix=model_prefix)
                    if resolved_cls is None or not any(
                        issubclass(resolved_cls, t) for t in accepted
                    ):
                        continue
                    target_cls = resolved_cls

                resolved.append((row, target_cls, child_name, child_spec.kind))
                break

        resolved.sort(key=lambda r: 0 if issubclass(r[1], DimensionProvider) else 1)

        dims: dict = {}
        collectors: dict[str, Any] = {}
        for row, target_cls, child_name, kind in resolved:
            fname = str(row[1])
            # A row's third+ terms mean different things by target kind (see
            # _apply_binding_terms): for a plain Model/Package they're the
            # pname; for Exchange/Solution they're real semantic data
            # (coupled model names / applicable models), not a name to
            # assign the loaded child itself.
            #
            # name= (xattree's own attribute) only actually takes effect
            # for "dict"-kind children below (Simulation.models/exchanges/
            # solutions) -- xattree reconciles a "list"-kind child's name
            # to f"{field}{index}" and an "only"-kind child's to the field
            # name regardless of what's passed (confirmed both at load
            # time here and at write time: Chd(name="custom")/
            # Ic(name="custom") get renamed "chd0"/"ic" the same way on
            # construction already, before this code ever runs). Passed
            # through anyway for the dict case and because it's harmless
            # (silently ignored) otherwise. The real pname for "list"/
            # "only"-kind children is instead preserved via the plain,
            # xattree-unmanaged Component.pname field, set below.
            pname = (
                str(row[2])
                if len(row) > 2 and not issubclass(target_cls, (Exchange, Solution))
                else None
            )
            child = (
                target_cls.load(workspace / fname, dims=dims, name=pname)
                if issubclass(target_cls, Package)
                else target_cls.load(workspace / fname, name=pname)
            )
            child.filename = fname
            if pname:
                # Plain, xattree-unmanaged field (see Component.pname) --
                # preserves the row's real pname for "list"/"only"-kind
                # children even though xattree itself reconciles .name to
                # a field-derived value regardless of what's passed above.
                child.pname = pname
            _apply_binding_terms(child, row[2:])
            if isinstance(child, DimensionProvider):
                dims = {**dims, **child.get_dims()}

            if kind == "only":
                collectors[child_name] = child
            elif kind == "list":
                collectors.setdefault(child_name, []).append(child)
            elif kind == "dict":
                # pname when there is one (matches the child's own real
                # name, e.g. Simulation.models); row fname as a fallback
                # for rows with no pname (e.g. solutiongroup, whose row[2:]
                # are applicable model names, not a pname -- see pname
                # above). This key is NOT cosmetic: xattree reconciles a
                # dict-kind child's attached .name to match the key it's
                # placed under, overriding whatever name= was passed to
                # load() above.
                collectors.setdefault(child_name, {})[pname or fname] = child

        kwargs.update(collectors)

    return kwargs


def structure_component(
    raw: dict,
    cls: type,
    *,
    dims: dict | None = None,
    workspace: Path | None = None,
    name: str | None = None,
) -> Any:
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
    workspace : Path, optional
        Directory binding-shaped fields' (packages/models/exchanges/
        solutiongroup) relative filenames are resolved against, and each
        loaded child recursively loaded from. Required only for classes
        that actually have such fields (see `_resolve_bindings`); unused
        for leaf `Package` classes, which have none.
    name : str, optional
        Explicit component name (e.g. a namefile binding row's pname),
        overriding xattree's default auto-assigned name. Not derivable
        from the file's own content -- passed down by a parent's
        `_resolve_bindings` call when loading this component as a child.

    Returns
    -------
    Component instance.
    """

    raw_lower = {k.lower(): v for k, v in raw.items()}
    binding_kwargs = _resolve_bindings(cls, raw_lower, workspace) if workspace else {}

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

    # Identify Item-list fields (packagedata, connectiondata, partitions …) --
    # the field's own type annotation (Optional[list[ItemClass]] or
    # Optional[dict[int, list[ItemClass]]]) is the schema.
    block_item_fields: dict[str, tuple] = {}  # block_name → (field, item_cls)
    period_field = None  # field for the period Item-list
    period_item_cls: "type[Item] | tuple[type[Item], ...] | None" = None

    for f in attrs.fields(cls):
        block = f.metadata.get("block", "")
        item_cls = item_list_type(f.type)
        if item_cls is None:
            continue
        if block == "period":
            period_field = f
            period_item_cls = item_cls
        else:
            block_item_fields[block] = (f, item_cls)

    # ── Pass 1: scalar blocks (options, dimensions, etc.) ────────────────────
    kwargs: dict[str, Any] = {}
    for block_name, rows in raw_lower.items():
        if not rows:
            continue
        if (
            block_name in block_item_fields
            or block_name.startswith("period")
            or block_name == "griddata"
        ):
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

    # Prefer grid dims (unambiguous) over row-width guessing for a
    # variable-width cellid's element count -- see item.infer_ncelldim.
    # Same "self dims, since a DimensionProvider has none threaded to it
    # yet" fallback as Pass 4's griddata parsing.
    effective_dims = dims or _self_dims_from_kwargs(kwargs)

    # ── Pass 2: block Item-list fields (packagedata, partitions …) ──────────
    for block_name, (f, item_cls) in block_item_fields.items():
        rows = raw_lower.get(block_name, [])
        if not rows:
            continue
        rows = _resolve_open_close_rows(rows, workspace)
        row_list = _parse_rows(
            rows, item_cls, naux=naux, boundnames=boundnames, dims=effective_dims
        )
        if row_list is not None:
            init_key = f.alias if (f.alias and not f.alias.startswith("_")) else f.name
            kwargs[init_key] = row_list

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
        if period_field is not None:
            assert period_item_cls is not None  # set together with period_field above
            spd: dict[int, list] = {}
            for kper, rows in sorted(kper_rows.items()):
                if not rows:
                    continue
                rows = _resolve_open_close_rows(rows, workspace)
                row_list = _parse_rows(
                    rows, period_item_cls, naux=naux, boundnames=boundnames, dims=effective_dims
                )
                if row_list is not None:
                    spd[kper] = row_list
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
                    parsed = _parse_readarray_period_block(rows, ra_fields, dims, workspace)
                    for fname, arr in parsed.items():
                        accum[fname][kper] = arr
                kwargs.update(accum)

    # ── Pass 4: griddata block ────────────────────────────────────────────────
    griddata_rows = raw_lower.get("griddata", [])
    if griddata_rows:
        # A DimensionProvider (Dis/Disv/...) has no external `dims` the
        # first time it's loaded -- it *is* the dims source. Its own
        # GRIDDATA block still needs shapes, derived from the DIMENSIONS
        # block Pass 1 already parsed into kwargs above. A no-op ({}) for
        # any other class, which just falls through to the `dims` param
        # threaded from an already-loaded sibling (unchanged behavior).
        effective_dims = dims or _self_dims_from_kwargs(kwargs)
        if effective_dims:
            gd_fields = {
                f.name: f
                for f in attrs.fields(cls)
                if f.metadata.get("block") == "griddata" and f.init is not False
            }
            parsed = _parse_griddata_block(griddata_rows, gd_fields, effective_dims, workspace)
            kwargs.update(parsed)

    kwargs.update(binding_kwargs)
    if name is not None:
        kwargs["name"] = name

    return cls(**kwargs)
