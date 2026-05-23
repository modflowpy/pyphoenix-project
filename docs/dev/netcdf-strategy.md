# NetCDF Strategy — flopy4 MF6 Input and Output Files

This document describes the design decisions behind the NetCDF files that
flopy4 generates for MODFLOW 6 and the post-processing utility that brings
MF6 output files into compliance.  It covers three distinct file types and
evaluates each against four considerations: convention compliance, external
tooling support, risk minimization, and internal consistency (including
xarray integration).

---

## Context

MODFLOW 6 supports two NetCDF output modes and one NetCDF input mode:

| Mode | MF6 keyword | Format |
|---|---|---|
| Structured output | `NETCDF_STRUCTURED` | CF-1.11 raster (x/y dimension coordinates) |
| Mesh/UGRID output | `NETCDF_MESH2D` | CF-1.11 + UGRID-1.0 (face-indexed variables) |
| NetCDF input | `NETCDF` | Same format as the matching output type |

flopy4 generates the **input** files.  MF6 generates the **output** files.
The two are written to the same conventions so that input and output files
are interchangeable in downstream tooling.

---

## File Type 1: Structured NetCDF Input (`NetCDFFormat.STRUCTURED`)

### What is written

**Dimension coordinates** — `x`, `y`, `layer`, `time`

- `x` and `y` are 1-D projected cell-centre coordinates (easting/northing).
  Each carries `axis`, `standard_name = "projection_x/y_coordinate"`, `units`,
  `bounds`, and `grid_mapping = "projection"`.
  `encoding["_FillValue"] = None` prevents xarray adding a spurious fill value.
- `layer` carries `axis = "Z"`, `positive = "down"`, `units = "1"`.
  `encoding["_FillValue"] = None`.
- `time` carries `calendar`, `units` (CF datetime offset), `axis = "T"`,
  `standard_name = "time"`.  `encoding["_FillValue"] = None`.
- `x_bnds` and `y_bnds` are cell boundary arrays referenced by the `bounds`
  attribute on `x` and `y`.  `encoding["_FillValue"] = None`.

**Projection variable** — `projection` (scalar integer)

- `crs_wkt` — WKT2 (ISO 19162:2019).  CF-1.11 authoritative form.
- `wkt` — WKT1 (OGC 01-009).  Legacy alias for GDAL < 3 and older tools.
- `grid_mapping_name` — CF-1.11 required string (e.g. `"transverse_mercator"`).
  Derived via pyproj `crs.to_cf()`.
- `GeoTransform` — GDAL affine transform string derived from actual grid bounds
  (`x_bnds`/`y_bnds`), not from cell-centre spacing.  Uses the effective
  pixel size over the full grid extent so variable-spacing grids (e.g.
  Frenchman Flat) produce the correct bounding box.
- `spatial_ref` — WKT1 copy for GDAL's companion attribute to `GeoTransform`.

**Data variables** — `{package}_{param}`

- `grid_mapping = "projection"`.
- No `coordinates` attribute.  `x` and `y` are dimension coordinates; CF
  tools find them by dimension name.  Writing a redundant `coordinates` attr
  requires exploiting xarray encoding internals and adds no information.

### Convention compliance (CF-1.11)

Fully compliant.  All required coordinate attrs (`axis`, `standard_name`,
`units`, `bounds`) are present.  `crs_wkt` is WKT2 as specified.  `wkt` is
present for backwards compatibility.  `grid_mapping_name` is set.
`GeoTransform` and `spatial_ref` are GDAL extensions, not CF — they are
included because GDAL-based tools cannot build a geotransform from projected
1-D dimension coordinates alone.

### External tooling

| Tool | Mechanism | Status |
|---|---|---|
| QGIS | `GeoTransform` + `crs_wkt` on `projection` variable | Correct placement |
| ArcGIS Pro | `crs_wkt` + `x`/`y` `standard_name` → Make NetCDF Raster Layer | Works |
| GDAL | `GeoTransform` + `spatial_ref` on grid-mapping variable | Reads correctly |
| xarray | `x`/`y`/`layer` dimension coords → `sel()`, `isel()`, plotting | Native |
| rioxarray | `grid_mapping = "projection"` + `crs_wkt` → CRS-aware operations | Works |
| ncview | Dimension coordinates → basic slice display | Works |

Note: ArcGIS Pro uses **Make NetCDF Raster Layer** for uniform grids and
**Make Multidimensional Raster Layer** for variable `delr`/`delc` grids.

### xarray integration

The structured format is the most natural for xarray.  `x`, `y`, and `layer`
are dimension coordinates so `ds.sel(layer=1)`, `ds.sel(x=300_000,
method="nearest")`, and label-based plotting all work without any
intermediate steps.  rioxarray CRS operations are available via
`grid_mapping`.  No xarray internals are exploited — encoding is used only
for `_FillValue` suppression on coordinate arrays.

### Risk minimization

`GeoTransform` is the only non-CF attribute and the one with the most
arithmetic.  It is derived from `x_bnds`/`y_bnds` (the same arrays used for
CF `bounds`) which are already in memory at write time.  No external library
is required for derivation.  The postprocess utility independently derives
`GeoTransform` for MF6 output using the same algorithm.

---

## File Type 2: Mesh/UGRID NetCDF Input (`NetCDFFormat.LAYERED_MESH`)

Applies to both `StructuredGrid` (DIS-based) and `VertexGrid` (DISV-based)
sources.  The output format is identical; only the topology arrays differ.

### What is written

**Dimension coordinates** — `layer`, `time`

Same conventions as structured.  `x` and `y` do NOT appear as dimension
coordinates here — the mesh face dimension `nmesh_face` is the spatial index.

**Mesh topology variable** — `mesh` (scalar integer)

UGRID-1.0 container variable carrying:
- `cf_role = "mesh_topology"`
- `topology_dimension = 2`
- `face_dimension = "nmesh_face"`
- `node_coordinates = "mesh_node_x mesh_node_y"`
- `face_coordinates = "mesh_face_x mesh_face_y"`
- `face_node_connectivity = "mesh_face_nodes"`

**Geometry arrays**

- `mesh_node_x`, `mesh_node_y` — vertex coordinates.
  `standard_name`, `units`, `grid_mapping`.  `encoding["_FillValue"] = None`.
- `mesh_face_x`, `mesh_face_y` — face centroid coordinates.
  `standard_name`, `units`, `grid_mapping`, `bounds`.  `encoding["_FillValue"] = None`.
- `mesh_face_xbnds`, `mesh_face_ybnds` — per-face vertex coordinate arrays
  (shape `[nmesh_face, max_face_nodes]`).  Padding slots use `FILL_INT64`.
  `_FillValue` not suppressed since these arrays have real pad values.
- `mesh_face_nodes` — face-node connectivity (1-based, CCW).
  `cf_role = "face_node_connectivity"`, `start_index = 1`.
  `encoding["_FillValue"] = FILL_INT64` for padding.

**Projection variable** — same WKT2/WKT1 split as structured.  No
`GeoTransform` — GDAL cannot interpret unstructured grids as rasters.

**Data variables** — `{package}_{param}_l{layer}`

- `grid_mapping = "projection"`.
- `mesh = "mesh"`.
- `location = "face"` (UGRID-1.0 required).
- `coordinates = "mesh_face_x mesh_face_y"` — pointer to the geographic
  face centroid arrays.  Written via `attrs` (not `encoding`) because
  `mesh_face_x`/`mesh_face_y` are data variables, not xarray coordinate
  variables.  xarray passes the attr through to disk unchanged.

### Convention compliance (CF-1.11 + UGRID-1.0)

Fully compliant.  All required UGRID topology attrs are present on the mesh
variable.  Face data variables carry `mesh`, `location`, and `coordinates`.
Node and face coordinate arrays carry `standard_name`.  `crs_wkt` is WKT2,
`wkt` is WKT1.  `grid_mapping_name` is set.

### External tooling

| Tool | Mechanism | Status |
|---|---|---|
| QGIS Mesh Layer | UGRID topology via `cf_role = "mesh_topology"` | Correct |
| ArcGIS Pro | Multidimensional/Mesh Layer tools | Not supported — UGRID topology not recognized natively |
| xugrid | UGRID topology → `UgridDataset` with geographic selection | Native |
| xarray (raw) | `nmesh_face` abstract index — geographic ops not available | Limited |
| ncview | Does not understand UGRID | Not applicable |

### xarray integration

Raw xarray treats `nmesh_face` as an abstract 1-D index.  This is correct
and expected — xarray is not the right tool for geographic operations on
unstructured grids.  **xugrid** is the appropriate layer: it reads the UGRID
topology, wraps the dataset in `UgridDataset`, and provides face selection,
interpolation, and plotting with full geographic context.  The files are
written to be xugrid-compatible.

For layer/time operations that don't require geographic context (e.g.
extracting a parameter across all layers for a given time step), raw xarray
works fine via the `layer` and `time` dimension coordinates.

### Risk minimization

The main risk is UGRID topology correctness — specifically 1-based CCW
face-node ordering and proper padding.  Both are enforced in `_topology()`
and tested.  The `coordinates` attribute on data variables is passed through
xarray's write path naturally (not via encoding internals) because the
referenced variables are data vars, not xarray coords.

---

## File Type 3: MF6 Output NetCDF (post-processed)

MF6 writes output files (head, budget) using the same structured or mesh
format as the input files, but with some attributes missing.  The
`postprocess_mesh_nc` and `postprocess_structured_nc` functions in
`flopy4/mf6/utils/netcdf_postprocess.py` bridge the gap.

### What MF6 currently writes vs. what the postprocessor adds

| Attribute | Location | MF6 writes | After postprocess |
|---|---|---|---|
| `wkt` | `projection` | Mesh only (WKT1) | Structured: added (WKT1) |
| `crs_wkt` | `projection` | Structured only (WKT1) | Mesh: added (WKT2); Structured: overwritten (WKT2) |
| `grid_mapping_name` | `projection` | Neither | Both: added |
| `GeoTransform` | `projection` | Neither | Structured: added |
| `spatial_ref` | `projection` | Neither | Structured: added (WKT1) |

The postprocessor is idempotent — running it twice produces the same result.
`setdefault` is used for all additive attrs (mesh).  For structured, `crs_wkt`
is explicitly overwritten because MF6 already wrote it with WKT1.

### pyproj dependency

The postprocessor requires pyproj for WKT version conversion and
`grid_mapping_name` derivation.  Both functions guard with
`try/except ImportError` and return the dataset unmodified if pyproj is
absent.  The `GeoTransform` derivation uses only array arithmetic and does
not require pyproj.

---

## Internal Consistency

Across all three file types, the following conventions are held constant:

- Grid mapping variable is always named `projection`.
- `crs_wkt` is always WKT2; `wkt` is always WKT1.
- `grid_mapping_name` is always derived via `crs.to_cf()`.
- `layer` coordinate always carries `axis = "Z"`, `positive = "down"`.
- `time` coordinate always carries `calendar = "standard"`, CF datetime `units`.
- `_FillValue = None` on all fully-defined coordinate and geometry arrays.
- Data variable `_FillValue` is always `FILL_FLOAT64` / `FILL_INT64` from the
  spec encoding — never suppressed, never modified by the grid layer.

---

## xarray Encoding Conventions

One non-obvious aspect of the implementation: xarray distinguishes `attrs`
(semantic metadata written as NetCDF variable attributes) from `encoding`
(write-time instructions consumed by the encoder, not written as attributes).

Key decisions:

| Attribute | Placed in | Reason |
|---|---|---|
| `_FillValue = None` on coords | `encoding` | xarray honors encoding to suppress default fill |
| `_FillValue = FILL_INT64` on `mesh_face_nodes` | `encoding` | Ensures proper NetCDF fill value declaration |
| `coordinates` on mesh face vars | `attrs` | `mesh_face_x/y` are data vars, not xarray coords — xarray passes attrs through |
| `grid_mapping`, `mesh`, `location` | `attrs` | Semantic metadata, not write-time instructions |
| `GeoTransform`, `spatial_ref` | `attrs` | GDAL reads these as attributes, not encoding |

The `coordinates` attribute on structured data vars was considered and
explicitly rejected: `x` and `y` are dimension coordinates so `coordinates`
is redundant in CF, and writing it would require exploiting `encoding`
internals whose behavior is not part of xarray's public API.

---

## Forward-Looking Items

### Near-term (within flopy4)

- **GWE/GWT DISV support** — GWE and GWT currently have `dis.py` (DIS
  package) but not `disv.py`.  DISV support for mesh output from transport
  models is deferred to a separate PR.
- **Latlon option in `Ncf.from_grid()`** — a `latlon=True` parameter that
  writes 2-D geographic coordinate arrays for users who need them.  Mutually
  exclusive with `wkt`.  Separate PR.
- **ArcGIS Pro documentation** — distinguish Make NetCDF Raster Layer
  (uniform grids) from Make Multidimensional Raster Layer (variable spacing)
  in notebook and repo docs.

### MF6 Fortran — two-phase plan

**Phase 1 (low risk, additive only):**

- Mesh output: write `crs_wkt` (WKT2) alongside existing `wkt`.
- Structured output: write `wkt` (WKT1) alongside existing `crs_wkt`.
- Both: write `grid_mapping_name` derived from a WKT string scan + lookup table.
- NCF subpackage DFN: add optional `crs_wkt` field so users can supply WKT2
  directly.  When present, MF6 writes it without conversion.  When absent,
  MF6 writes WKT1 to `crs_wkt` as today and the postprocessor corrects it.

**Phase 2 (moderate risk, coordinate arithmetic):**

- Structured output: write `GeoTransform` and `spatial_ref` from cell
  coordinate arrays already in memory at write time.  Once MF6 writes these
  natively, the postprocessor becomes optional for structured output.

Once both phases are in MF6, flopy4's `Ncf.from_grid()` should populate both
`wkt` (WKT1) and `crs_wkt` (WKT2) fields so that MF6 output matches the
flopy4 input convention end-to-end without post-processing.
