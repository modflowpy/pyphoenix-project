"""Writing arrays to files of their own, for OPEN/CLOSE control records,
text or binary."""

import os
import struct
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import attrs
import numpy as np
import xarray as xr

from flopy4.mf6.codec.writer.filters import array2chunks, array2string
from flopy4.mf6.write_context import WriteContext, array_hash

_session = threading.local()


class ArrayFileError(ValueError):
    """An array's file can't be written as given, with
    `WriteContext.strict` on. See `write_external_arrays`."""


@contextmanager
def write_session() -> Iterator[None]:
    """Track the files written for OPEN/CLOSE arrays across one `write()`
    call tree, so that arrays of different components naming one file are
    checked against each other. A nested session joins the outermost."""
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
    """One array, or one layer of a layered array, to write to a file."""

    block: str
    key: str
    layer: int | None
    label: str
    path: Path  # absolute, normalized
    values: xr.DataArray
    binary: bool
    hash: str | None = None  # the values' hash when loaded

    def unchanged(self) -> bool:
        """Whether the values are as loaded from the file."""
        return self.hash is not None and self.hash == array_hash(self.values)


@attrs.frozen
class _Written:
    label: str
    values: xr.DataArray
    binary: bool


def write_external_arrays(
    data: dict[str, Any], root: Path, filename: Path, label: str, context: WriteContext
) -> dict[str, Any]:
    """Write the arrays in `data` (an unstructured component, after
    `annotate_arrays`) that go to files of their own, and mark them so the
    writer writes OPEN/CLOSE records for them.

    An array goes to a file if it has an `ArrayIO.path` (in its `path`
    attr, or per layer in `layer_path`), or, without one, if
    `context.array_format` is "open/close", or if it's written binary
    (see `_is_binary`) and `array_format` isn't "internal": then a
    layered array gets a file per layer. Arrays the writer reads from
    NetCDF are left alone.

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

    With `context.strict`, either rule raises `ArrayFileError` instead,
    before any file of the component is written.
    """
    files: dict[Path, _Written] | None = getattr(_session, "files", None)
    moved: dict[Path, Path] | None = getattr(_session, "moved", None)
    if files is None or moved is None:
        files, moved = {}, {}
    root = Path(os.path.normpath(root.absolute()))
    targets: list[_Target] = []
    for block_name, block in data.items():
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if isinstance(value, xr.DataArray):
                targets.extend(_targets(block_name, key, value, root, filename, label, context))
    if not targets:
        return data

    def warn(message: str) -> None:
        if context.strict:
            raise ArrayFileError(message)
        warnings.warn(message, stacklevel=3)

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
                    "file, give the others another ArrayIO path."
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
        if t.binary:
            _write_binary_file(t.path, t.values, t.key, t.layer)
        else:
            _write_file(t.path, t.values, context)
        files[t.path] = _Written(t.label, t.values, t.binary)

    skip = {id(t) for t in inline}
    out = {name: dict(block) if isinstance(block, dict) else block for name, block in data.items()}
    for t in targets:
        if id(t) in skip:
            continue
        da = out[t.block][t.key]
        da = da.copy(deep=False)
        rel = _relative(t.path, root)
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
    layered = "nlay" in value.dims
    layer_binary = value.attrs.get("layer_binary", {})
    layer_hash = value.attrs.get("layer_hash", {})
    stem = filename.name.replace(".", "_") + f"_{key}"
    if kper is not None:
        stem += f"_p{kper + 1}"

    def target(path: Path | None, layer: int | None) -> _Target:
        values = value if layer is None else value.isel(nlay=layer)
        what = where if layer is None else f"{where} layer {layer + 1}"
        own = value.attrs.get("binary")
        if layer is not None:
            own = layer_binary.get(layer, own)
        binary = _is_binary(values, own, context)
        if path is None:
            name = stem + ("" if layer is None else f"_l{layer + 1}")
            path = filename.parent / f"{name}.{'bin' if binary else 'txt'}"
        loaded = value.attrs.get("hash") if layer is None else layer_hash.get(layer)
        return _Target(block_name, key, layer, what, _absolute(path, root), values, binary, loaded)

    if layered and (layer_path := value.attrs.get("layer_path")):
        return [target(p, layer) for layer, p in sorted(layer_path.items())]
    if (path := value.attrs.get("path")) is not None:
        return [target(path, None)]
    if context.array_format == "internal":
        return []
    if layered:
        targets = [target(None, layer) for layer in range(value.sizes["nlay"])]
    else:
        targets = [target(None, None)]
    if context.array_format == "open/close":
        return targets
    # otherwise only binary arrays go to files
    return [t for t in targets if t.binary]


def _is_binary(values: xr.DataArray, own: bool | None, context: WriteContext) -> bool:
    """Whether to write `values` to a binary file: its own `ArrayIO.binary`
    if set, else `context.use_binary`, if the values are bigger than
    `context.binary_threshold`, in bytes as written."""
    if own is not None:
        return own
    if not context.use_binary:
        return False
    if context.binary_threshold is None:
        return True
    return values.size * _binary_dtype(values).itemsize > context.binary_threshold


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


def _equal(a: xr.DataArray, b: xr.DataArray) -> bool:
    return a.shape == b.shape and bool(np.array_equal(np.asarray(a), np.asarray(b)))


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
# as many values as the array holds after it and checks the file is
# exactly that big.
_BINARY_HEADER = struct.Struct("<iidd16siii")


def _binary_dtype(values: xr.DataArray) -> np.dtype:
    """MF6 reads binary integer arrays as 4-byte, real ones as 8-byte."""
    return np.dtype("<i4" if np.issubdtype(values.dtype, np.integer) else "<f8")


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
        f.write(np.ascontiguousarray(values, dtype=_binary_dtype(values)).tobytes())
