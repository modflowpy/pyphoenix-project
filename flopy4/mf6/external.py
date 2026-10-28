"""Reading and writing arrays' and lists' own files, for OPEN/CLOSE
control records, text or binary."""

import os
import struct
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, cast

import attrs
import numpy as np
import numpy.typing as npt
import xarray as xr

from flopy4.mf6.codec.reader.transformer.rows import array_values
from flopy4.mf6.codec.writer.filters import array2chunks, array2string, data2lines
from flopy4.mf6.item_table import Rows
from flopy4.mf6.write_context import ArrayFormat, WriteContext, array_hash

_session = threading.local()


class ExternalFileError(ValueError):
    """An array's or list's file can't be written as given, with
    `WriteContext.strict` on. See `write_external_arrays` and
    `write_external_lists`."""


def in_write_session() -> bool:
    """Whether a `write_session` is open, i.e. this is a nested `write()`."""
    return getattr(_session, "files", None) is not None


@contextmanager
def write_session() -> Iterator[None]:
    """Track the files written for OPEN/CLOSE arrays and lists across one
    `write()` call tree, so that those of different components naming one
    file are checked against each other. A nested session joins the
    outermost."""
    if getattr(_session, "files", None) is not None:
        yield
        return
    _session.files = {}
    _session.moved = {}
    try:
        yield
    finally:
        _session.files = None
        _session.moved = None


@attrs.define(eq=False)
class _Target:
    """One array, one layer of a layered array, or one list, to write to
    a file."""

    block: str
    key: str
    layer: int | None
    label: str
    path: Path  # absolute, normalized
    values: "xr.DataArray | Rows"
    binary: bool
    hash: str | None = None  # the values' hash when loaded
    records: np.ndarray | None = None  # a list's rows, for a binary file

    def unchanged(self) -> bool:
        """Whether the values are as loaded from the file."""
        return self.hash is not None and self.hash == _hash(self.values)


@attrs.frozen
class _Written:
    label: str
    values: "xr.DataArray | Rows"
    binary: bool


def _warner(context: WriteContext):
    def warn(message: str) -> None:
        if context.strict:
            raise ExternalFileError(message)
        warnings.warn(message, stacklevel=4)

    return warn


def write_external_arrays(
    data: dict[str, Any], root: Path, filename: Path, label: str, context: WriteContext
) -> dict[str, Any]:
    """Write the arrays in `data` (an unstructured component, after
    `annotate_arrays`) that go to files of their own, and mark them so the
    writer writes OPEN/CLOSE records for them.

    An array goes to a file if its format (see `_file_format`) is
    "open/close" or "binary": its `ArrayIO.path` (in its `path` attr, or
    per layer in `layer_path`), or one named for the component and field.
    A layered array not marked `layered=False` gets a file per layer.
    Arrays the writer reads from NetCDF are left alone.

    `root` is the simulation directory, which every path is relative to,
    `filename` the component's file, relative to it, and `label` names the
    component in warnings. Two rules keep a write from losing data:

    - A file outside `root` (and the component file's directory) is never
      written to. The array is written beside the component's file
      instead, under the same name (with a suffix if another file of the
      write claims it), with a warning.
    - Arrays naming one file must hold the same values, and be written
      binary or not alike. If they don't, within a component, those still
      holding the values loaded from the file (see `ArrayIO.hash`) keep
      it, if they agree, and the others are written inline; failing that,
      the writer can't tell which is the edited one, and writes every
      array of the file inline. An array disagreeing with a file another
      component already wrote is written inline. Either way, with a
      warning.

    With `context.strict`, either rule raises `ExternalFileError` instead,
    before any file of the component is written.
    """
    targets: list[_Target] = []
    for block_name, block in data.items():
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if isinstance(value, xr.DataArray):
                targets.extend(_targets(block_name, key, value, root, filename, label, context))
    return _write_targets(data, targets, root, filename, context)


def write_external_lists(
    data: dict[str, Any], root: Path, filename: Path, label: str, context: WriteContext
) -> dict[str, Any]:
    """Write the lists in `data` (an unstructured component) that go to
    files of their own, and mark them so the writer writes OPEN/CLOSE
    records for them, as `write_external_arrays` does arrays, by the
    same rules, and in the same files a write's arrays are checked
    against.

    A list goes to a file if its `ListIO.format`, else the context's
    `list_format` (for "binary", only if its rows are bigger than
    `binary_threshold`, in bytes as written), is "open/close" or
    "binary", or else if it has a `ListIO.path`: that path, or one named
    for the component, field and period. Only a list alone in its block
    can, and not an empty one; another is written inline, with a warning
    if its own `ListIO` says otherwise.

    A list MF6 can't read from a binary file (see `binary_row_spec`), or
    whose rows hold words where it reads numbers (time series' names), is
    written to a text file instead, with a warning if its own `ListIO`
    says "binary". So is a list not in a period block, unless its own
    `ListIO` says "binary": MF6 reads a binary list only into a block it
    knows the length of beforehand, as it knows a period's (MAXBOUND) but
    not, say, TDIS's PERIODDATA's.
    """
    warn = _warner(context)
    targets: list[_Target] = []
    for block_name, block in data.items():
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if not isinstance(value, Rows) or value.field is None:
                continue
            alone = len(block) == 1
            t = _list_target(block_name, key, value, alone, root, filename, label, context, warn)
            if t is not None:
                targets.append(t)
    return _write_targets(data, targets, root, filename, context)


def _write_targets(
    data: dict[str, Any], targets: list[_Target], root: Path, filename: Path, context: WriteContext
) -> dict[str, Any]:
    """Write `targets`' files, but those the rules of `write_external_arrays`
    keep inline, and mark the others in a copy of `data`."""
    files: dict[Path, _Written] | None = getattr(_session, "files", None)
    moved: dict[Path, Path] | None = getattr(_session, "moved", None)
    if files is None or moved is None:
        files, moved = {}, {}
    if not targets:
        return data
    warn = _warner(context)
    # the component's own directory is being written to anyway, even if
    # outside the simulation's (a standalone component's file can be)
    home = _absolute(filename.parent, root)
    allowed = (root, home)
    claimed = set(files) | {t.path for t in targets if _inside(t.path, allowed)}
    for t in targets:
        if _inside(t.path, allowed):
            continue
        # arrays sharing an outside file share its copy
        if (new := moved.get(t.path)) is None:
            new = _unique(home / t.path.name, claimed)
            warn(
                f"{t.label}: {t.path} is outside the simulation directory {root}; "
                f"writing it to {new} instead"
            )
            moved[t.path] = new
            claimed.add(new)
        t.path = new

    groups: dict[Path, list[_Target]] = {}
    for t in targets:
        groups.setdefault(t.path, []).append(t)

    inline: list[_Target] = []
    writes: list[_Target] = []
    for path, group in groups.items():
        if (differ := _disagree(group)) is not None:
            unchanged = [t for t in group if t.unchanged()]
            changed = [t for t in group if not any(t is u for u in unchanged)]
            if unchanged and changed and _disagree(unchanged) is None:
                warn(
                    f"{path}: {', '.join(t.label for t in changed)} changed since "
                    "loaded from this file; writing them inline. "
                    f"{', '.join(t.label for t in unchanged)} still use it."
                )
                inline.extend(changed)
                group = unchanged
            else:
                warn(
                    f"{path}: {', '.join(t.label for t in group)} use this file but "
                    f"{differ}; writing them inline. To write one of them to the "
                    "file, give the others another path."
                )
                inline.extend(group)
                continue
        first = group[0]
        if (written := files.get(path)) is not None:
            differ = None
            if not _equal(written.values, first.values):
                differ = "with different values"
            elif written.binary != first.binary:
                differ = "binary" if written.binary else "as text"
            if differ:
                warn(
                    f"{path}: {', '.join(t.label for t in group)} use this file, "
                    f"which {written.label} wrote {differ}; writing them inline."
                )
                inline.extend(group)
            continue
        writes.append(first)

    for t in writes:
        if isinstance(t.values, Rows):
            if t.records is not None:
                _write_binary_list_file(t.path, t.records)
            else:
                _write_list_file(t.path, t.values)
        elif t.binary:
            _write_binary_file(t.path, t.values, t.key, t.layer)
        else:
            _write_file(t.path, t.values, context)
        files[t.path] = _Written(t.label, t.values, t.binary)

    skip = {id(t) for t in inline}
    out = {name: dict(block) if isinstance(block, dict) else block for name, block in data.items()}
    for t in targets:
        if id(t) in skip:
            continue
        rel = _relative(t.path, root)
        if isinstance(t.values, Rows):
            out[t.block][t.key] = t.values.marked(rel, t.binary)
            continue
        da = out[t.block][t.key]
        da = da.copy(deep=False)
        if t.layer is None:
            da.attrs = {**da.attrs, "open_close": rel, "open_close_binary": t.binary}
        else:
            layers = {**da.attrs.get("layer_open_close", {}), t.layer: rel}
            binaries = {**da.attrs.get("layer_open_close_binary", {}), t.layer: t.binary}
            da.attrs = {
                **da.attrs,
                "layer_open_close": layers,
                "layer_open_close_binary": binaries,
            }
        out[t.block][t.key] = da
    return out


def _targets(
    block_name: str,
    key: str,
    value: xr.DataArray,
    root: Path,
    filename: Path,
    label: str,
    context: WriteContext,
) -> list[_Target]:
    if value.ndim == 0 or not np.issubdtype(value.dtype, np.number):
        return []
    if context.use_netcdf and value.attrs.get("netcdf", False):
        return []
    name, _, header = block_name.partition(" ")
    kper = int(header) - 1 if name == "period" and header.isdigit() else None
    where = f"{label}.{key}" + (f" period {kper + 1}" if kper is not None else "")
    layer_format = value.attrs.get("layer_format", {})
    layer_path = value.attrs.get("layer_path", {})
    layer_hash = value.attrs.get("layer_hash", {})
    stem = filename.name.replace(".", "_") + f"_{key}"
    if kper is not None:
        stem += f"_p{kper + 1}"

    def target(layer: int | None) -> _Target | None:
        values = value if layer is None else value.isel(nlay=layer)
        if layer is None:
            own, path, loaded = (value.attrs.get(a) for a in ("format", "path", "hash"))
        else:
            own = layer_format.get(layer, value.attrs.get("format"))
            path, loaded = layer_path.get(layer), layer_hash.get(layer)
        fmt = _file_format(values, own, path is not None, context)
        if fmt is None:
            return None
        binary = fmt == "binary"
        if path is None:
            name = stem + ("" if layer is None else f"_l{layer + 1}")
            path = filename.parent / f"{name}.{'bin' if binary else 'txt'}"
        what = where if layer is None else f"{where} layer {layer + 1}"
        return _Target(block_name, key, layer, what, _absolute(path, root), values, binary, loaded)

    by_layer = "nlay" in value.dims and (
        bool(layer_path)
        or (value.attrs.get("path") is None and value.attrs.get("layered") is not False)
    )
    if by_layer:
        targets = [target(layer) for layer in range(value.sizes["nlay"])]
    else:
        targets = [target(None)]
    return [t for t in targets if t is not None]


def _file_format(
    values: xr.DataArray, own: ArrayFormat | None, has_path: bool, context: WriteContext
) -> ArrayFormat | None:
    """The file format to write `values` in, "open/close" or "binary", or
    None to write them inline: their own `ArrayIO.format` if set, else the
    context's `array_format` if a file format (for "binary", only if the
    values are bigger than `binary_threshold`, in bytes as written), else
    "open/close" if they have a path. A path beats an inline
    `array_format`: one of a lower context would have been dropped
    (`WriteContext.over`), so it's of the same context or a higher."""
    fmt = own
    if fmt is None and context.array_format in _FILE_FORMATS:
        fmt = context.array_format
        threshold = context.binary_threshold
        if fmt == "binary" and threshold is not None:
            if values.size * _binary_dtype(values.dtype).itemsize <= threshold:
                fmt = None
    if fmt is None and has_path:
        fmt = "open/close"
    return fmt if fmt in _FILE_FORMATS else None


_FILE_FORMATS = ("open/close", "binary")


def _list_target(
    block_name: str,
    key: str,
    rows: Rows,
    alone: bool,
    root: Path,
    filename: Path,
    label: str,
    context: WriteContext,
    warn,
) -> _Target | None:
    name, _, header = block_name.partition(" ")
    kper = int(header) - 1 if name == "period" and header.isdigit() else None
    field = cast(str, rows.field)
    io = context.list_io(field) if kper is None else context.list_io(field, kper)
    where = f"{label}.{field}" + (f" period {kper + 1}" if kper is not None else "")
    fmt = io.format
    if fmt is None and context.list_format in _FILE_FORMATS:
        fmt = context.list_format
    if fmt is None and io.path is not None:
        fmt = "open/close"
    if fmt not in _FILE_FORMATS or not len(rows):
        return None
    if not alone:
        if io.format in _FILE_FORMATS or io.path is not None:
            warn(f"{where}: only a list alone in its block can go to a file; writing it inline")
        return None
    if fmt == "binary" and io.format is None and kper is None:
        # MF6 reads a binary list only into a block it knows the length
        # of beforehand: a period's (MAXBOUND), not every other's (TDIS's
        # PERIODDATA), so only its own ListIO makes another one binary
        fmt = "open/close"
    records = None
    if fmt == "binary":
        spec = rows.binary_spec()
        records = None if spec is None else _binary_records(rows, spec)
        if records is None:
            if io.format == "binary":
                warn(f"{where}: MF6 can't read these rows from a binary file; writing them as text")
            fmt = "open/close"
        elif io.format is None and (threshold := context.binary_threshold) is not None:
            if records.nbytes <= threshold:
                if io.path is None:
                    return None
                fmt, records = "open/close", None
    binary = fmt == "binary"
    path = io.path
    if path is None:
        stem = filename.name.replace(".", "_") + f"_{field}"
        if kper is not None:
            stem += f"_p{kper + 1}"
        path = filename.parent / f"{stem}.{'bin' if binary else 'txt'}"
    return _Target(
        block_name, key, None, where, _absolute(path, root), rows, binary, io.hash, records
    )


def _absolute(path: Path, root: Path) -> Path:
    return Path(os.path.normpath(root / path))


def _inside(path: Path, dirs: tuple[Path, ...]) -> bool:
    return any(path.is_relative_to(d) for d in dirs)


def _relative(path: Path, root: Path) -> PurePosixPath:
    """`path` as written in the file: relative to `root`, else absolute."""
    if path.is_relative_to(root):
        return PurePosixPath(path.relative_to(root).as_posix())
    return PurePosixPath(path.as_posix())


def _unique(path: Path, claimed: set[Path]) -> Path:
    """`path`, or with a ``_1``, ``_2``, ... suffix if it's claimed."""
    candidate, n = path, 0
    while candidate in claimed:
        n += 1
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
    return candidate


def _disagree(group: list[_Target]) -> str | None:
    """How the arrays of `group`, sharing a file, disagree, or None."""
    first = group[0]
    if not all(_equal(first.values, t.values) for t in group[1:]):
        return "hold different values"
    if not all(t.binary == first.binary for t in group[1:]):
        return "aren't all binary or all text"
    return None


def _equal(a: "xr.DataArray | Rows", b: "xr.DataArray | Rows") -> bool:
    if isinstance(a, Rows) or isinstance(b, Rows):
        return isinstance(a, Rows) and isinstance(b, Rows) and a.hash() == b.hash()
    return a.shape == b.shape and bool(np.array_equal(np.asarray(a), np.asarray(b)))


def _hash(values: "xr.DataArray | Rows") -> str:
    return values.hash() if isinstance(values, Rows) else array_hash(values)


def _write_file(path: Path, values: xr.DataArray, context: WriteContext) -> None:
    """Write `values` as MF6 reads an OPEN/CLOSE text file: a layer at a
    time, a structured grid's layer a row per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    layers = (
        [values.isel({values.dims[0]: i}) for i in range(values.shape[0])]
        if values.ndim > 2
        else [values]
    )
    with path.open("w") as f:
        for layer in layers:
            for chunk in array2chunks(layer):
                f.write(array2string(chunk, context.float_precision) + "\n")


# MF6's binary array header: KSTP, KPER, PERTIM, TOTIM, TEXT, and three
# sizes MF6 only logs (`ArrayReaders.f90::read_binary_header`); it reads
# as many values as the array holds after it.
_BINARY_HEADER = struct.Struct("<iidd16siii")


def _binary_dtype(dtype: npt.DTypeLike) -> np.dtype:
    """MF6 reads binary integer arrays as 4-byte, real ones as 8-byte."""
    return np.dtype("<i4" if np.issubdtype(dtype, np.integer) else "<f8")


def _write_binary_file(path: Path, values: xr.DataArray, key: str, layer: int | None) -> None:
    """Write `values` as MF6 reads an OPEN/CLOSE (BINARY) file: one header,
    then every value, C order (a layer's rows, then the next layer's)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    shape = (1, 1, *values.shape)[-3:]
    ilay = shape[0] if layer is None else layer + 1
    text = key.upper().encode("ascii", "replace")[:16].rjust(16)
    header = _BINARY_HEADER.pack(1, 1, 1.0, 1.0, text, shape[2], shape[1], ilay)
    with path.open("wb") as f:
        f.write(header)
        f.write(np.ascontiguousarray(values, dtype=_binary_dtype(values.dtype)).tobytes())


def _write_list_file(path: Path, rows: Rows) -> None:
    """Write `rows` as MF6 reads an OPEN/CLOSE list file: a row per line,
    as in the block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(data2lines(rows, inset="") + "\n")


def _binary_list_dtype(spec: "list[tuple[str, int]]") -> np.dtype:
    """A binary list row's record type: a field per `spec` piece."""
    return np.dtype([(f"f{i}", piece, (n,)) for i, (piece, n) in enumerate(spec)])


def _binary_records(rows: Rows, spec: "list[tuple[str, int]]") -> np.ndarray | None:
    """`rows` as a binary list file's records, laid out by `spec`, or None
    if they don't fit it: a word where a number goes (a time series'
    name), a fraction where an integer does, or another count of values."""
    try:
        table = np.array(list(rows), dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if table.ndim != 2 or table.shape[1] != sum(n for _, n in spec):
        return None
    records = np.empty(len(table), dtype=_binary_list_dtype(spec))
    start = 0
    for i, (piece, n) in enumerate(spec):
        values = table[:, start : start + n]
        start += n
        if np.dtype(piece).kind == "i":
            info = np.iinfo(piece)
            if not np.all(np.isfinite(values)) or not np.array_equal(values, np.trunc(values)):
                return None
            if values.size and (values.min() < info.min or values.max() > info.max):
                return None
        records[f"f{i}"] = values
    return records


def _write_binary_list_file(path: Path, records: np.ndarray) -> None:
    """Write `records` as MF6 reads an OPEN/CLOSE (BINARY) list file: each
    row's values back to back, with no header (see `read_binary_list_file`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(records.tobytes())


# --- reading ---------------------------------------------------------------


def read_array_file(
    path: Path, dtype: npt.DTypeLike, count: int, binary: bool = False
) -> np.ndarray:
    """An OPEN/CLOSE array file's first ``count`` values."""
    if not binary:
        return array_values(path.read_text(), dtype, count, source=path)
    with path.open("rb") as fh:
        header = fh.read(_BINARY_HEADER.size)
        if len(header) < _BINARY_HEADER.size:
            raise ValueError(f"{path}: too short for an MF6 binary-array header")
        values = np.fromfile(fh, dtype=_binary_dtype(dtype))
    if len(values) < count:
        raise ValueError(f"{path}: expected {count} values, got {len(values)}")
    return values[:count].astype(dtype)


def read_list_file(path: Path) -> list:
    """An OPEN/CLOSE list file's rows."""
    from flopy4.mf6.codec.reader import loads

    return loads(f"BEGIN DATA\n{path.read_text()}\nEND DATA\n").get("DATA", [])


def read_binary_list_file(path: Path, spec: "list[tuple[str, int]]") -> list[list]:
    """A binary OPEN/CLOSE list file's rows: each `spec`'s pieces back to
    back, until EOF, with no header. A partial last row is dropped, as
    IDM's ``StructArray%read_from_binary`` drops it."""
    dtype = _binary_list_dtype(spec)
    data = path.read_bytes()
    records = np.frombuffer(data, dtype=dtype, count=len(data) // dtype.itemsize)
    columns = [records[name].tolist() for name in dtype.names or ()]
    return [[v for piece in pieces for v in piece] for pieces in zip(*columns)]
