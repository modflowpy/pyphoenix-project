# The MF6 xarray representation

Status: **draft.** Only the first section is written. The rest is an outline,
to be filled in during `xarray-export-plan.md` phase 1. The design behind it
is in `xarray-package-plan.md` at the repo root.

The representation is the in-memory form of an MF6 simulation as xarray
objects: what flopy4's `to_xarray` produces, what `from_xarray` accepts, and
what the accessor, `dense()` and the encoders work on. Files come from
encodings of it, and none of those encodings is the representation itself.

## How it relates to netCDF, CF, UGRID and the MF6 NetCDF format

### The layers

These names are easy to mix up because they sit at different levels:

- **netCDF** is a data model and a file format: dimensions, variables,
  attributes and groups. It says nothing about what the data means.
- **CF** (Climate and Forecast) is a metadata convention on top of netCDF.
  It gives data meaning through `units`, `standard_name`, `axis`,
  `_FillValue`, `coordinates`, `bounds`, `grid_mapping` and time units.
- **UGRID** extends CF to unstructured meshes: mesh topology variables, and
  node, edge and face dimensions.
- **xarray** uses the netCDF data model in memory, but it isn't CF.
  - It applies CF rules when reading (`decode_cf`): it masks fill values,
    applies scale and offset, decodes times to `datetime64`, and promotes
    variables named in `coordinates` to coordinates. It reverses them when
    writing.
  - In memory it holds things netCDF and CF can't: indexes (pandas or
    custom), `datetime64` and bool dtypes, arbitrary Python objects in
    attrs, and lazy or dask-backed arrays.
- **The MF6 NetCDF format** ([wiki][mf6nc]) is CF plus UGRID plus
  MF6-specific attributes (`modflow_input`, `modflow_iaux`, `layer`). It's
  shaped around what MF6's input reader can load.
- **The representation** (this document) is the xarray data model plus MF6
  conventions: dims and coordinates for each grid type, a tree mirroring the
  simulation, period data as given, type tags. It's shaped around what
  Python users and tools need.

xarray already keeps the in-memory dataset apart from its CF-encoded file
form. The representation does the same one level up, for MF6.

### The picture

```
              object model (flopy4, attrs)
                         │  A: to_xarray / from_xarray
                         ▼
        representation (DataTree, xarray data model + MF6 conventions,
                        CF-friendly attrs, indexes, 0-based)
         ┌───────────────┼──────────────────┬──────────────────┐
         ▼               ▼                  ▼                  ▼
      native        MF6 NetCDF          UGRID (xugrid)     CF dataset
  (groups, full     project + flatten   per-model mesh     bounds,
  tree, Python)     + CF encode         UgridDataset       grid_mapping
                    (MF6 reads it,
                    plus text input)
```

CF appears twice, in two roles:

1. **Metadata inside the representation.** Where CF already has an answer
   (`units`, `standard_name`, `axis`, `grid_mapping`, fill-value
   semantics), the representation uses it rather than inventing its own.
2. **An encoding on the way to disk.** Fill values, time units, bounds,
   coordinate attributes, and so on.

Because of (1), the encoders don't each have to do CF from scratch. Most of
the CF dataset encoding is bounds plus `xr.conventions.encode_cf`, and the
MF6 NetCDF and native encodings build on the same metadata.

### The encodings

| | native | MF6 NetCDF | UGRID | CF |
|---|---|---|---|---|
| Read by | Python (flopy4, the accessor) | MF6, GIS and CF tools | xugrid, UGRID-aware tools (QGIS, MDAL) | CF tools (GDAL, Panoply, cf-python) |
| Scope | the whole simulation | one model's grid arrays | one model's grid arrays | one model's grid arrays |
| Hierarchy | netCDF/zarr groups mirroring the tree | flat; identity kept in names and `modflow_input` | flat | flat |
| Coverage | everything: options, dims, list data, arrays | GRIDDATA/PERIOD arrays; the rest stays in text input | arrays on DISV and layered DIS | arrays on structured grids |
| Lossless | yes | for what it covers | for what it covers | for what it covers |
| Indexing | 0-based | 1-based | 0-based (UGRID `start_index`) | n/a |

**Native** is the representation written as is: `DataTree.to_netcdf` or
`to_zarr`, with only the encoding netCDF needs (bools, None, fill values).
MF6 never reads it. It's for round trips, caching and sharing a simulation
between Python tools.

### MF6 NetCDF is a projection, not a serialization

The MF6 NetCDF format and the representation can't simply be the same
thing. The difference isn't mainly the flat layout: the file is a sidecar
holding one model's grid-shaped arrays, and the namefile and package text
files still carry everything else. So the encoder projects:

- **Project:** keep one model's GRIDDATA and PERIOD array fields.
- **Flatten:** turn package paths into variable names (`npf_k`) plus
  `modflow_input` (`<model>/<package>/<tag>`).
- **Renumber:** 0-based to 1-based.
- **Reshape:** split by layer where the layered mesh form needs it
  (`npf_k_l1`, …).
- **CF encode:** fill values, time units, `grid_mapping`, CRS.

The decoder reverses these steps. It parses the identity, rebuilds the
package nodes, and merges them into a tree whose other fields come from the
text input. This round trip is lossless for what the file covers, provided
the identity can be parsed reliably.

The flat layout is reasonable for a file MF6 reads:

- MF6's input data model loads one model at a time, keyed by
  model/package/tag.
- UGRID defines one mesh topology per dataset.
- GDAL/QGIS, CDO and older NCO handle netCDF groups poorly or not at all.

The flat file is a flattened tree, so we don't need groups there. What we
do need from the format is listed under "What the format could change".

### Where the representation and MF6 NetCDF differ

| | MF6 NetCDF format | Representation |
|---|---|---|
| Indexing | 1-based cell ids | 0-based; 1-based only in encodings and `sel_cell` |
| Layers (mesh) | one variable per layer (`npf_k_l1`, …) | a `layer` dim |
| List (stress period) data | not covered | a sparse table, plus `dense()` |
| DISU, DIS2D/DISV2D/DISV1D | not covered | covered |
| Scope | one model per file, flat | a `DataTree` of the whole simulation |
| Time | input `time` per period, output `time` per step, with no stated link | both, with the mapping |
| Indexes | none (files don't store them) | `CellIndex` and similar |
| Package identity | the `modflow_input` path string | a structured type tag |
| Fill values | vary (`9.97e36`, `3e30`, `1e30`, `-2147483647`) | one per dtype |

### What the format could change

Not groups, and not list data (that would be nice to have, but isn't
needed). These would make the projection well-defined and its inverse
reliable:

- **Structured identity:** separate model, package and tag attributes, or a
  documented grammar for `modflow_input`, so the decoder doesn't have to
  guess package names.
- **Consistent fill values** per dtype.
- **A documented layer convention:** when variables are split by layer, and
  how to reassemble them.
- **A time mapping** between period-sized input time and step-sized output
  time.

These come from reading the wiki and need checking against the MF6 source
before anything is proposed upstream.

## Grid dims and coordinates

To write. DIS from `rotated-grid-index-plan.md` "Coordinates on a DIS
array". A table for DISV and DISU still needs writing. DIS2D/DISV2D/DISV1D
are TBD.

## Tree, names and type tags

To write.

## Period data

To write. Period arrays along `<name>_period`, and list data as a sparse
table (see `period-lists-plan.md`).

## Time

To write. See `datetime-periods-plan.md`.

## Attributes and fill values

To write.

[mf6nc]: https://github.com/MODFLOW-ORG/modflow6/wiki/MODFLOW-NetCDF-Format
