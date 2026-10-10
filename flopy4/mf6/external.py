"""Writing arrays to files of their own, for OPEN/CLOSE control records."""

import os
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
from flopy4.mf6.write_context import WriteContext

_session = threading.local()


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


@attrs.define
class _Target:
    """One array, or one layer of a layered array, to write to a file."""

    block: str
    key: str
    layer: int | None
    label: str
    path: Path  # absolute, normalized
    values: xr.DataArray


@attrs.frozen
class _Written:
    label: str
    values: xr.DataArray


def write_external_arrays(
    data: dict[str, Any], root: Path, filename: Path, label: str, context: WriteContext
) -> dict[str, Any]:
    """Write the arrays in `data` (an unstructured component, after
    `annotate_arrays`) that go to files of their own, and mark them so the
    writer writes OPEN/CLOSE records for them.

    An array goes to a file if it has an `ArrayIO.path` (in its `path`
    attr, or per layer in `layer_path`), or, without one, if
    `context.array_format` is "open/close": then a layered array gets a
    file per layer. Arrays the writer reads from NetCDF are left alone.

    `root` is the simulation directory, which every path is relative to,
    `filename` the component's file, relative to it, and `label` names the
    component in warnings. Two rules keep a write from losing data:

    - A file outside `root` (and the component file's directory) is never
      written to. The array is written beside the component's file
      instead, under the same name (with a suffix if another file of the
      write claims it), with a warning.
    - Arrays naming one file must hold the same values. If they don't,
      the writer can't tell which is the edited one: within a component,
      every array of the file is written inline; an array disagreeing with
      a file another component already wrote is written inline. Either
      way, with a warning.
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
            new = moved[t.path] = _unique(home / t.path.name, claimed)
            claimed.add(new)
            warnings.warn(
                f"{t.label}: {t.path} is outside the simulation directory {root}; "
                f"writing it to {new} instead",
                stacklevel=2,
            )
        t.path = new

    groups: dict[Path, list[_Target]] = {}
    for t in targets:
        groups.setdefault(t.path, []).append(t)

    inline: list[_Target] = []
    for path, group in groups.items():
        first = group[0].values
        if not all(_equal(first, t.values) for t in group[1:]):
            warnings.warn(
                f"{path}: {', '.join(t.label for t in group)} use this file but "
                "hold different values; writing them inline. To write one of them "
                "to the file, give the others another ArrayIO path.",
                stacklevel=2,
            )
            inline.extend(group)
            continue
        if (written := files.get(path)) is not None:
            if not _equal(written.values, first):
                warnings.warn(
                    f"{path}: {', '.join(t.label for t in group)} use this file, "
                    f"which {written.label} wrote with different values; writing "
                    "them inline.",
                    stacklevel=2,
                )
                inline.extend(group)
            continue
        _write_file(path, first, context)
        files[path] = _Written(group[0].label, first)

    skip = {id(t) for t in inline}
    out = {name: dict(block) if isinstance(block, dict) else block for name, block in data.items()}
    for t in targets:
        if id(t) in skip:
            continue
        da = out[t.block][t.key]
        da = da.copy(deep=False)
        rel = _relative(t.path, root)
        if t.layer is None:
            da.attrs = {**da.attrs, "open_close": rel}
        else:
            layers = {**da.attrs.get("layer_open_close", {}), t.layer: rel}
            da.attrs = {**da.attrs, "layer_open_close": layers}
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

    def target(path: Path, layer: int | None) -> _Target:
        values = value if layer is None else value.isel(nlay=layer)
        what = where if layer is None else f"{where} layer {layer + 1}"
        return _Target(block_name, key, layer, what, _absolute(path, root), values)

    if layered and (layer_path := value.attrs.get("layer_path")):
        return [target(p, layer) for layer, p in sorted(layer_path.items())]
    if (path := value.attrs.get("path")) is not None:
        return [target(path, None)]
    if context.array_format != "open/close":
        return []
    stem = filename.name.replace(".", "_") + f"_{key}"
    if kper is not None:
        stem += f"_p{kper + 1}"
    parent = filename.parent
    if layered:
        return [
            target(parent / f"{stem}_l{layer + 1}.txt", layer)
            for layer in range(value.sizes["nlay"])
        ]
    return [target(parent / f"{stem}.txt", None)]


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
