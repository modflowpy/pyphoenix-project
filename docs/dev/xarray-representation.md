# The MF6 xarray representation

Status: **draft.** Only the first section is written. The rest is an outline,
to be filled in during `xarray-export-plan.md` phase 1. The design behind it
is in `xarray-package-plan.md` at the repo root.

The representation is the in-memory form of an MF6 simulation as xarray
objects: what flopy4's `to_xarray` produces, what `from_xarray` accepts, and
what the accessor, `dense()`, the file writers and the adapters work on.
Files are written from it, and no file format is the representation itself.

## How it relates to netCDF, CF, UGRID and the MF6 NetCDF format

### The layers

These names are easy to mix up because they sit at different levels:

- **netCDF** is a data model and a file format: dimensions, variables,
  attributes and groups. It says nothing about what the data means.
- **CF** (Climate and Forecast) is a metadata convention on top of netCDF.
  It gives data meaning through `units`, `standard_name`, `axis`,
  `_FillValue`, `coordinates`, `bounds`, `grid_mapping` and time units.
- **UGRID** is an extension of CF for unstructured meshes: mesh topology
  variables, and node, edge and face dimensions.
- **xarray** uses the netCDF data model in memory, but it isn't CF.
  - It applies CF rules when reading (`decode_cf`): it masks fill values,
    applies scale and offset, decodes times to `datetime64`, and promotes
    variables named in `coordinates` to coordinates. It reverses them when
    writing.
  - In memory it holds things netCDF and CF can't: indexes (pandas or
    custom), `datetime64` and bool dtypes, arbitrary Python objects in
    attrs, and lazy or dask-backed arrays.
- **The MF6 NetCDF format** ([wiki][mf6nc]) is a domain convention on top
  of CF and UGRID. It adds MF6 attributes (`modflow_input`, `modflow_iaux`,
  `layer`) and comes in a structured form and a layered-mesh form.
- **The representation** (this document) is the xarray data model plus MF6
  conventions: dims and coordinates for each grid type, a tree mirroring the
  simulation, period data as given, type tags. It's shaped around what
  Python users and tools need.

xarray already keeps the in-memory dataset apart from its CF-encoded file
form. The representation does the same one level up, for MF6.

### Conventions stack

CF, UGRID and MF6 NetCDF aren't alternatives. They are meant to be layered:
CF is the base, UGRID extends it for meshes, and domain conventions such as
MF6 NetCDF (or ACDD, SGRID) add their own attributes on top. A file lists
all of them in one attribute, e.g. `Conventions = "CF-1.11 UGRID-1.0"`.

This works because attributes add up. A CF tool reads the CF attributes and
ignores `modflow_input`; a UGRID tool reads the mesh topology and ignores
the rest. So one file can be valid CF, valid UGRID and valid MF6 NetCDF at
the same time.

Layering breaks on structure, not on attributes. When a format makes a
structural choice the base conventions don't expect, generic tools stop
understanding the data even though the file is technically valid. Examples
in the MF6 NetCDF format today:

- **Splitting variables by layer** (`npf_k_l1`, `npf_k_l2`, …). CF and
  UGRID allow a `layer` dim on face data; a generic tool sees N unrelated
  variables instead of one 3-D field.
- **Rotation only through a wrapped WKT2 `PROJCRS`.** CF's usual answer is
  2-D auxiliary coordinates (`x_world`/`y_world`, named in `coordinates`),
  which the representation already has.
- **Groups.** CF has allowed groups since 1.8, but most UGRID and GIS tools
  still read only the root group.

### The design: one format in two layouts, plus adapters

```
              object model (flopy4, attrs)
                         │  A: to_xarray / from_xarray
                         ▼
        representation (DataTree, xarray data model + MF6 conventions,
                        CF-friendly attrs, indexes, 0-based)
              ┌──────────┴────────────────┐
              ▼ files: MF6 NetCDF         ▼ adapters (in memory)
       ┌──────┴───────┐                   to_ugrid()     → UgridDataset
       ▼              ▼                   to_rioxarray() → rio-ready DataArray
    grouped       ungrouped               to_cf()        → CF-ready Dataset
    full tree,    flattened;              to_modelgrid() → flopy3 modelgrid
    lossless,     CF + UGRID valid;
    CF 1.8        MF6 reads it            each library writes its own
    groups        ├─ structured           files (UGRID netCDF, GeoTIFF)
                  └─ layered mesh
```

**Files** are MF6 NetCDF, in two layouts of one spec:

- **MF6 NetCDF (grouped)** is the representation encoded as is. Groups
  mirror the tree (simulation → models → packages), and it covers
  everything: options, dims, list data, arrays. It's valid CF 1.8+ with
  groups, but generic tools aren't expected to use it. MF6 doesn't read it
  yet. Today it's for round trips, caching, archiving and sharing a whole
  simulation from Python (netCDF, or zarr for cloud storage).
- **MF6 NetCDF (ungrouped)** is the same content flattened by a fixed rule.
  Group paths become name prefixes and `modflow_input`. This is the
  layout MF6 reads, and the interoperability layout: it aims to be fully
  valid CF and UGRID, so QGIS, GDAL, Panoply and xugrid open it directly.
  The MF6 attributes go along with the data, and other tools ignore them.
  It has a structured form (DIS) and a layered-mesh form (DISV, layered
  DIS).

**Adapters** hand the representation to another library's object model in
memory. They are not file formats. The library then reads, analyses,
plots and writes in its own way, e.g. UGRID netCDF through xugrid, GeoTIFF
through `rio.to_raster`.

| Adapter | Gives | For |
|---|---|---|
| `to_ugrid()` / `from_ugrid()` | xugrid `UgridDataset` | regridding, mesh plotting, mesh operations on DISV and layered DIS |
| `to_rioxarray()` | DataArray with CRS and transform written (`.rio`) | rasters, GeoTIFF, reprojection, clipping (structured grids) |
| `to_cf()` | Dataset with CF attributes, bounds and `grid_mapping` | cf_xarray and other CF-aware Python tools |
| `to_modelgrid()` | flopy3 `StructuredGrid`/`VertexGrid` | flopy3 plotting and utilities, while still needed |

The adapter names are placeholders. Writing an adapter's output with plain
`to_netcdf` should give something close to the ungrouped layout, not a
third format. If it doesn't, either the adapter or the ungrouped layout is
off, and that's worth fixing.

**CF plays two roles.** It's metadata inside the representation: where CF
already has an answer (`units`, `standard_name`, `axis`, `grid_mapping`,
fill-value semantics), the representation uses it rather than inventing
its own. It's also part of writing files: fill values, time units, bounds.
Because of the first role, the writers and adapters don't each have to do
CF from scratch.

### The two layouts compared

| | grouped | ungrouped |
|---|---|---|
| Read by | Python (flopy4, the accessor); MF6 not yet | MF6, GIS and CF/UGRID tools, xarray/xugrid |
| Hierarchy | groups mirroring the tree | flat; identity in name prefixes and `modflow_input` |
| Coverage today | everything | one model's GRIDDATA/PERIOD arrays; the rest in text input |
| Coverage goal | everything | everything (to confirm with the MF6 developers) |
| Conventions | CF 1.8+ with groups, MF6 | CF, UGRID (mesh form), MF6 |
| Indexing | 1-based on disk, 0-based in memory | 1-based (UGRID `start_index = 1`) |

### Ungrouped is a flattening

The ungrouped layout is meant to cover the whole simulation eventually; it
has been developed in steps. So the lasting difference between the layouts
is only groups vs flattening, and the cleanest spec defines the ungrouped
layout as a mechanical flattening of the grouped one. Then there's one spec,
not two.

Writing the ungrouped layout means:

- **Flatten:** turn package paths into variable names (`npf_k`) plus
  `modflow_input` (`<model>/<package>/<tag>`).
- **Renumber:** 0-based to 1-based.
- **Lay out layers:** a `layer` dim, or one variable per layer where the
  layered mesh form needs it (`npf_k_l1`, …). Prefer the dim (it's what
  CF/UGRID tools expect). If MF6 or a tool needs the split form, make it
  an option on the writer, not a separate format.
- **Write CF:** fill values, time units, `grid_mapping`, CRS.

Reading reverses these steps: parse the identity, rebuild the tree, and
(while coverage is partial) merge in the fields that come from text input.

**Dimension names are the hard part of flattening a whole simulation.**
One model per file avoids it, but a whole simulation in one flat file means
two GWF models each with their own `nlay`/`ncpl`, a GWT model on the same
grid as its GWF model, exchanges between models, and list data needing
per-package entry dims. Without groups, every dim needs a prefix
(`gwf1_nlay`) or a rule for when dims are shared. That's the problem groups
solve, and the flattening rule has to answer it either way. A shared-grid
rule (GWF and GWT on one grid share dims) would keep the file usable in GIS
tools.

**Today** the ungrouped layout covers only part of the model, so reading it
yields a partial tree, and the text input fills in the rest. That's a
projection of the representation, and it's lossless for what it covers if
the identity can be parsed reliably.

### Where the representation and today's MF6 NetCDF differ

| | MF6 NetCDF format (today) | Representation |
|---|---|---|
| Indexing | 1-based cell ids | 0-based; 1-based only on disk and in `sel_cell` |
| Layers (mesh) | one variable per layer (`npf_k_l1`, …) | a `layer` dim |
| List (stress period) data | not covered | a sparse table, plus `dense()` |
| Options, scalars, simulation components | not covered | covered |
| DISU, DIS2D/DISV2D/DISV1D | not covered | covered |
| Scope | one model per file, flat | a `DataTree` of the whole simulation |
| Time | input `time` per period, output `time` per step, with no stated link | both, with the mapping |
| Indexes | none (files don't store them) | `CellIndex` and similar |
| Package identity | the `modflow_input` path string | a structured type tag |
| Rotation | wrapped WKT2 `PROJCRS` only | `projection` coordinate, `x_world`/`y_world` |
| Fill values | vary (`9.97e36`, `3e30`, `1e30`, `-2147483647`) | one per dtype |

### What the format could change

To make the ungrouped layout a full, conventions-clean flattening of the
grouped one:

- **A flattening rule for the whole simulation**, including how dims are
  named or shared across models.
- **Structured identity:** separate model, package and tag attributes, or a
  documented grammar for `modflow_input`, so the reader doesn't have to
  guess package names.
- **Coverage:** list data, options and scalars, simulation-level
  components, DISU and DIS2D/DISV2D/DISV1D.
- **CF/UGRID validity as a stated goal:** a `layer` dim rather than split
  variables (or a documented reason for splitting), and 2-D auxiliary
  coordinates for rotated grids.
- **Consistent fill values** per dtype.
- **A time mapping** between period-sized input time and step-sized output
  time.
- **Groups**, eventually, if MF6 is to read the grouped layout.

These come from reading the wiki and need checking against the MF6 source,
and the coverage goal needs confirming with the MF6 developers, before
anything is proposed upstream.

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
