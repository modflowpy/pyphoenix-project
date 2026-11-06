from collections.abc import Mapping
from functools import cached_property, partial
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import xarray as xr
from modflow_devtools.dfns import dim_value

from flopy4._imports import isinstance_of
from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.block import block_list_type
from flopy4.mf6.component import Component, WorkspaceComponent
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.converter.binding import write_row
from flopy4.mf6.converter.ingress.structure import _init_key, _per_header
from flopy4.mf6.dims_provider_methods import DimsProviderMethods
from flopy4.mf6.item import Item, conditional_fields, dim_lookup, item_list_type, sized_by
from flopy4.mf6.item_table import ItemTable, Rows
from flopy4.mf6.package import Package
from flopy4.mf6.period_arrays import is_cleared, is_grid_package
from flopy4.mf6.record import Record, record_type
from flopy4.mf6.spec import (
    FileDirection,
    binding_fields,
    block_keys,
    field_key,
    file_blocks,
    is_tagged,
)
from flopy4.mf6.write_context import WriteContext
from flopy4.spec import is_array


def _path_to_tuple(field: attrs.Attribute, value: Path) -> tuple[str, ...]:
    """A block-level file record's ``KEYWORD FILEIN|FILEOUT <path>`` row. The
    keyword is the field's own ``_keyword`` metadata (see spec.file)."""
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
    path = child.filename
    return Path(path.name) if path.is_absolute() else path


def _grid_dims(value: Package) -> tuple[int, tuple[int, ...]]:
    """(nlay, layer shape) of the package's grid: a layer is (nrow, ncol) on
    a structured grid, else (ncpl,). Empty if the grid isn't known. A grid
    package's are its own."""
    own = value.get_dims() if isinstance(value, DimsProviderMethods) else {}
    d = own | value.dims | value.resolve_dims("nlay", "nrow", "ncol", "ncpl", "nodes")
    nlay = d.get("nlay", 1)
    if "nrow" in d and "ncol" in d:
        return nlay, (d["nrow"], d["ncol"])
    ncpl = d.get("ncpl") or d.get("nodes", 0) // nlay
    return nlay, (ncpl,) if ncpl else ()


def _mark_netcdf(da: xr.DataArray, meta: Mapping) -> xr.DataArray:
    """Mark an array of a field MF6 reads from NetCDF (dfn `netcdf` flag), so
    a NetCDF write writes `NETCDF` for it; unmarked arrays keep their data."""
    if not meta.get("netcdf"):
        return da
    da = da.copy(deep=False)
    da.attrs = {**da.attrs, "netcdf": True}
    return da


def _grid_shaped(value: Any, meta: Mapping, nlay: int, layer: tuple[int, ...]) -> xr.DataArray:
    """A per-cell array shaped like the grid (see `_grid_dims`), since MF6
    reads a structured grid's layer a row per line: each layer (nrow, ncol).
    A layered one (dfn `layered`) the size of the grid is shaped by layer,
    with an nlay dim to signal the writer to use layered format. An array
    of another size, or one already an xr.DataArray, is kept as it is."""
    if isinstance(value, xr.DataArray) or not hasattr(value, "reshape"):
        return _wrap_array(value)
    ncpl = int(np.prod(layer)) if layer else 0
    layer_dims = ("nrow", "ncol") if len(layer) > 1 else ("ncpl",)
    if meta.get("layered", False) and nlay > 1 and ncpl and value.size == nlay * ncpl:
        return xr.DataArray(value.reshape(nlay, *layer), dims=("nlay", *layer_dims))
    if len(layer) > 1 and value.size == ncpl:
        return xr.DataArray(value.reshape(layer), dims=layer_dims)
    return _wrap_array(value)


def _period_dataarray(
    name: str, value: Any, meta: Mapping, nlay: int, layer: tuple[int, ...]
) -> xr.DataArray | tuple:
    """One period's array, shaped like the grid (see `_grid_shaped`). A
    time-array series' name is written as a reference to it."""
    if isinstance(value, TimeArraySeriesRef):
        return (name.upper(), "TIMEARRAYSERIES", value.name)
    if not hasattr(value, "shape"):
        value = np.asarray(value)
    if meta.get("index"):
        value = _to_file_index(value)
    return _mark_netcdf(_grid_shaped(value, meta, nlay, layer), meta)


def materialize(data: Any) -> Any:
    """``data`` with its `Rows` made lists, for a writer that walks the
    containers itself (JSON, TOML)."""
    if isinstance(data, Rows):
        return list(data)
    if isinstance(data, dict):
        return {k: materialize(v) for k, v in data.items()}
    return data


def _rows(row_list: "list | ItemTable", ncelldim: int | None, **kwargs: Any) -> Rows:
    rows = Rows(ncelldim, **kwargs)
    rows.append(row_list)
    return rows


def _list_layout(value: Package, item_cls: "type[Item]") -> tuple[dict[str, int], frozenset[str]]:
    """The sizes of `item_cls`'s package-sized columns (aux, by
    AUXILIARY) and the options on that put its conditional ones in its
    rows (BOUNDNAMES), as `value` sets them."""
    values: dict[str, Any] = {}
    for f in attrs.fields(type(value)):  # type: ignore[arg-type]
        v = getattr(value, f.alias if (f.alias and f.name.startswith("_")) else f.name, None)
        values[f.name] = v
        if f.alias:
            values[f.alias] = v
    sizes = {}
    for shape in sized_by(item_cls):
        if (n := dim_value(shape, lookup=lambda name: dim_lookup(values, name))) is not None:
            sizes[shape] = n
    enabled = frozenset(o for o in conditional_fields(item_cls).values() if values.get(o))
    return sizes, enabled


def _list_kwargs(value: Package, name: str, f: attrs.Attribute) -> dict[str, Any]:
    """A list field's `Rows` arguments, for writing it to a file."""
    item_cls = item_list_type(f.type)
    layout = None
    if isinstance(item_cls, type):
        layout = partial(_list_layout, value, item_cls)
    return {"field": name, "item_cls": item_cls, "layout": layout}


def _ncelldim(value: Package) -> int | None:
    """The package's grid's ncelldim, or None if the grid isn't known."""
    try:
        return value.resolve_dims("ncelldim").get("ncelldim")
    except ValueError:
        return None


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
    if isinstance_of(value, "dask.array.core", "Array"):
        return xr.DataArray(value)
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


def annotate_arrays(
    data: dict[str, Any], cls: type[Component], context: WriteContext
) -> dict[str, Any]:
    """Copy each array's settings from `context.arrays` (see `ArrayKey`) onto
    the DataArray `data` holds for it, as attrs the writer reads: `iprn`,
    and `layer_iprn` for layers of a layered array whose IPRN differs from
    the whole array's; `path`, `format`, `hash` and `layered`, and
    `layer_path`, `layer_format` and `layer_hash` for layers given their
    own (see `write_external_arrays` and `array_how`). A block whose
    header is an index (a period's IPER, see `cls.headers`) has its
    arrays keyed by it, 0-based."""
    if not context.arrays:
        return data
    out: dict[str, Any] = {}
    for block_name, block in data.items():
        name, _, header = block_name.partition(" ")
        kind = cls.headers.get(name)
        kper = int(header) - 1 if kind is not None and kind.index and header.isdigit() else None
        if not isinstance(block, dict):
            out[block_name] = block
            continue
        out[block_name] = block = dict(block)
        for key, value in block.items():
            if not isinstance(value, xr.DataArray):
                continue
            base = (key,) if kper is None else (key, kper)
            io = context.array_io(*base)
            attrs_: dict[str, Any] = {
                name: getattr(io, name)
                for name in ("iprn", "path", "format", "hash", "layered")
                if getattr(io, name) is not None
            }
            if "nlay" in value.dims:
                layers: dict[str, dict[int, Any]] = {}
                for layer in range(value.sizes["nlay"]):
                    layer_iprn = context.array_io(*base, layer).iprn
                    if layer_iprn is not None and layer_iprn != io.iprn:
                        layers.setdefault("layer_iprn", {})[layer] = layer_iprn
                    # only a layer's own settings, not the whole array's
                    own = context.arrays.get((*base, layer))
                    for name in ("path", "format", "hash") if own is not None else ():
                        if getattr(own, name) is not None:
                            layers.setdefault(f"layer_{name}", {})[layer] = getattr(own, name)
                attrs_.update(layers)
            if attrs_:
                value = value.copy(deep=False)
                value.attrs = {**value.attrs, **attrs_}
                block[key] = value
    return out


def _not_a_record(component: Component, name: str, rec: type[Record], value: Any) -> TypeError:
    """A record field holding something else, which the writer can't write
    (the field's converter makes one, see `Record.convert`)."""
    return TypeError(
        f"{type(component).__name__}.{name} must be a {rec.__qualname__}, "
        f"not {type(value).__name__}: {value!r}"
    )


def unstructure_component(value: Component) -> dict[str, Any]:
    """A component as the writer takes it, ``{block: {field: value}}``
    (see `_Unstructure`)."""
    return _Unstructure(value).blocks()


class _Unstructure:
    """One component's blocks for the writer, the inverse of the loader's
    `_Load`: its class's blocks, in file order (see `file_blocks`), each
    field keyed by its name in the file (see `field_key`), from its
    attribute or from a property computing it (a list package's MAXBOUND).
    A repeating block is written once per header (see `occurrences`), and the rows
    naming children (a model's packages, the simulation's models and
    solutions) are made from them (see `bindings`). A block with nothing
    to write is left out, unless codegen marked it `write_if_empty` or
    it's a name file's."""

    def __init__(self, value: Component) -> None:
        self.value = value
        self.cls = type(value)
        self._fields = attrs.fields_dict(self.cls)  # type: ignore[arg-type]
        self.grid = is_grid_package(self.cls)
        # blocks whose rows name children
        self.binding_blocks = binding_fields(self.cls)

    @cached_property
    def ncelldim(self) -> int | None:
        return _ncelldim(self.value) if isinstance(self.value, Package) else None

    @cached_property
    def grid_dims(self) -> tuple[int, tuple[int, ...]]:
        return _grid_dims(self.value)  # type: ignore[arg-type]

    def blocks(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        keep: set[str] = set()
        for name in file_blocks(self.cls):
            if isinstance(self.value, WorkspaceComponent) or any(
                f.metadata.get("write_if_empty")
                for f in self._fields.values()
                if f.metadata.get("block") == name
            ):
                keep.add(name)
            if name not in self.cls.headers:
                out[name] = self.body(name)
            else:
                for header, (body, empty) in self.occurrences(name).items():
                    out[f"{name} {header}"] = body
                    if empty:
                        keep.add(f"{name} {header}")
        return {name: body for name, body in out.items() if body or name in keep}

    def entries(self, name: str) -> "dict[str, attrs.Attribute | None]":
        """The block `name`'s fields, in file order, by their keys for the
        writer: a computed field first, with no attribute; a binding block's
        children as one entry, its rows, keyed and placed where the first
        of them is, likewise with no attribute."""
        out: "dict[str, attrs.Attribute | None]" = dict.fromkeys(
            block_keys(self.cls, name).computed
        )
        for a in file_blocks(self.cls)[name]:
            if a.metadata.get("row"):
                out[name] = None
            else:
                out[field_key(a)] = a
        return out

    def body(self, name: str) -> dict[str, Any]:
        """A block that doesn't repeat, by field."""
        values = {key: self.value_of(name, key, a) for key, a in self.entries(name).items()}
        return {k: v for k, v in values.items() if v is not None}

    def value_of(self, name: str, key: str, a: "attrs.Attribute | None") -> Any:
        """The field's value as the writer takes it, or None to leave it
        out. With no attribute, it's a binding block's rows or a computed
        field; a MAXBOUND of 0 (no rows) isn't written."""
        if a is None:
            return self.bindings(name) if key == name else getattr(self.value, key) or None
        value = getattr(self.value, _init_key(a), None)
        return None if value is None else self.field(key, a, value)

    def field(self, key: str, a: attrs.Attribute, value: Any) -> Any:
        """The field `a`'s value as the writer takes it, by its type, or
        None to leave it out."""
        meta = a.metadata
        if meta.get("child"):
            # a child's file record: OBS6 FILEIN <the child's file>
            if isinstance(value, list):
                return [_path_to_tuple(a, _child_path(c)) for c in value if c is not None] or None
            return _path_to_tuple(a, _child_path(value))
        match meta.get("type"):
            case "keyword":
                return value or None
            case "integer" | "double":
                return value
            case "string":
                return value or None
            case "file" if isinstance(value, list):
                # a tagged list of file records: one line each
                return [_path_to_tuple(a, v) for v in value] or None
            case "file":
                return _path_to_tuple(a, value)
            case "record":
                if not isinstance(value, Record):
                    raise _not_a_record(self.value, a.name, record_type(a.type) or Record, value)
                return value.to_tokens()
            case "array" if meta.get("shape"):
                # a grid array; a grid package's are shaped like its grid,
                # others' (NPF's K) stay as given, non-layered, which MF6
                # reads in one go
                if meta.get("index"):
                    value = _to_file_index(value)
                dims = self.grid_dims if isinstance(self.value, DimsProviderMethods) else (1, ())
                return _mark_netcdf(_grid_shaped(value, meta, *dims), meta)
            case "array":
                # inline (AUXILIARY's names): one line
                return (key.upper(), *map(str, value)) if len(value) else None
            case "list" if not value:
                return None
            case "list" if isinstance(value[0], tuple):
                return value
            case "list":
                return _rows(value, self.ncelldim, **self.list_kwargs(a))
        return None

    def bindings(self, name: str) -> list[tuple[str, ...]] | None:
        """The rows naming the children of the block `name` (``GWF6
        <file> <name>``), in field order: the inverse of
        `_resolve_bindings`."""
        rows = []
        for f, *_ in self.binding_blocks.get(name, ()):
            child = getattr(self.value, f.name, None)
            children = child if isinstance(child, list) else [child]
            rows += [write_row(c, f.metadata["row"]) for c in children if c is not None]
        return rows or None

    def list_kwargs(self, a: attrs.Attribute) -> dict[str, Any]:
        """A list field's `Rows` arguments, for writing it to a file."""
        return _list_kwargs(self.value, _init_key(a), a)  # type: ignore[arg-type]

    def occurrences(self, name: str) -> dict[str, tuple[dict[str, Any], bool]]:
        """A repeating block's occurrences by header as written (a period's
        1-based number), each its fields and whether it's written even if
        empty (a grid package's period clearing every boundary). A field
        holding one value, not one per header (the simulation's MXITER),
        is the first occurrence's (``SOLUTIONGROUP 1``). A period's
        cleared grid array (None) is written as DNODATA."""
        header = self.cls.headers[name]
        numbered = header.kind != "record"
        found: dict[Any, dict[str, Any]] = {}
        # per period, the (non-aux) arrays given, and those all DNODATA
        given: dict[Any, set[str]] = {}
        cleared: dict[Any, set[str]] = {}
        for key, a in self.entries(name).items():
            if a is None or not _per_header(a):
                if (value := self.value_of(name, key, a)) is not None:
                    found.setdefault(1, {})[key] = value
                continue
            if (value := getattr(self.value, _init_key(a), None)) is None:
                continue
            meta = a.metadata
            if (blocks := block_list_type(a.type)) is not None:
                # OBS's CONTINUOUS FILEOUT <name>: list[Block]
                _, list_name, _ = blocks.parts()
                for b in value:
                    header_tokens = " ".join(map(str, b.header_tokens()))
                    found.setdefault(header_tokens, {})[key] = _rows(
                        getattr(b, list_name), self.ncelldim
                    )
            elif meta.get("fk"):
                # dynamically named arrays (RCHA's aux): {kper: {name: array}},
                # each written under its name
                for kper, arrays in value.items():
                    for aux, arr in arrays.items():
                        found.setdefault(kper, {})[aux] = _period_dataarray(
                            aux, arr, meta, *self.grid_dims
                        )
            elif is_array(a) and meta.get("fill_forward"):
                for kper, arr in value.items():
                    found.setdefault(kper, {})[key] = (
                        None if arr is None else _period_dataarray(key, arr, meta, *self.grid_dims)
                    )
                    if self.grid and is_cleared(arr):
                        cleared.setdefault(kper, set()).add(key)
                    given.setdefault(kper, set()).add(key)
            elif is_array(a):
                # TAS times: {time: array}, a layer each
                tag = key if is_tagged(a) else ""
                for time, arr in value.items():
                    arr = arr if hasattr(arr, "shape") or isinstance(arr, str) else np.asarray(arr)
                    found.setdefault(time, {})[tag] = _grid_shaped(arr, meta, *self.grid_dims)
            elif meta.get("type") == "string":
                # a word per period (STO's steady-state or transient), untagged,
                # written uppercase as keywords are
                for kper, word in value.items():
                    found.setdefault(kper, {})[""] = word.upper()
            else:
                # a list per period: {kper: list[Item]}
                list_kwargs = self.list_kwargs(a)
                for kper, row_list in value.items():
                    if (kper := _normalize_kper(kper)) is None:
                        continue
                    rows = found.setdefault(kper, {}).setdefault(
                        key, Rows(self.ncelldim, **list_kwargs)
                    )
                    if isinstance(row_list, (list, ItemTable)):
                        rows.append(row_list)

        out: dict[str, tuple[dict[str, Any], bool]] = {}
        for h in sorted(found) if numbered else found:
            body = found[h]
            label = h + 1 if header.index else h
            if self.grid and given.get(h) and cleared.get(h) == given[h]:
                # every stress array DNODATA clears every boundary: an empty block
                out[str(label)] = ({}, True)
                continue
            if any(v is None for v in body.values()):
                like = next(v for v in body.values() if v is not None)
                body = {
                    k: xr.full_like(like, FILL_DNODATA, dtype=np.float64) if v is None else v
                    for k, v in body.items()
                }
            out[str(label)] = (body, False)
        return out
