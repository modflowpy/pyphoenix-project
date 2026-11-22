# Vector export beyond shapefiles

Not started. Prompted by MODFLOW-ORG/gridgen#190 (evaluate GeoPackage and
FlatGeobuf output for gridgen grids and intersections). Written against
pyphoenix `develop` (`33b0f670`) and flopy `develop` (`a320dd0c`).

## Summary

- **flopy 3's export is built around shapefiles.** Every `export(f)`
  branches on `.nc` or `.shp`, writes shapefiles with pyshp, and
  shortens attribute names to fit dBASE's 10-character limit. The same
  `shorten_attr` flag has carried over into flopy4's adapters.
- **gridgen#190 has to choose one format; flopy doesn't.** Gridgen is
  static C++ without GDAL, so it must vendor a writer (SQLite for
  GeoPackage, header-only flatbuffers for FlatGeobuf). Flopy already has
  geopandas/pyogrio as an optional dependency, which writes GeoPackage,
  FlatGeobuf, GeoParquet and shapefile, chosen by file extension.
- **Proposal:** make the `GeoDataFrame` the hand-off point. Every
  exporter builds one (most already can, through `to_geodataframe`), and
  `export(path)` writes it with `gdf.to_file` / `gdf.to_parquet`,
  choosing the format from the extension. GeoPackage becomes the
  default, FlatGeobuf and GeoParquet are supported, and shapefile is
  kept as a legacy output.
- **Gridded data stays in xarray.** Vector formats are for handing data
  to GIS tools. Model data over time belongs in xarray/xugrid
  (UGRID netCDF, Zarr), as in [`../xarray/export.md`](../xarray/export.md),
  which takes over flopy 3's `.nc` branch.

## Where flopy is tied to shapefiles today

### flopy 3 (`flopy/export/`, shared code in 4.x)

- `flopy/export/utils.py`: `model_export`, `package_export`,
  `array2d_export`, `mflist_export` etc. each branch on
  `Path(f).suffix.lower() == ".shp"` (and `.nc`). There is no general
  path for other vector formats.
- `flopy/export/shapefile_utils.py`: `write_grid_shapefile`,
  `model_attributes_to_shapefile`, `recarray2shp`, `shp2recarray`,
  `write_prj` (pyshp), and the name shortening (`shape_attr_name`,
  `enforce_10ch_limit`).
- `to_geodataframe` already exists on grids
  (`structuredgrid.py:800`, `vertexgrid.py:330`,
  `unstructuredgrid.py:646`), models (`mbase.py:771`), packages
  (`pakbase.py:677`, `mf6/mfpackage.py:2137`), arrays and lists
  (`util_array.py`, `util_list.py`) and output files (`binaryfile`,
  `modpathfile.py`, `particletrackfile.py`). The shapefile exporters
  don't go through it; they build pyshp records separately.
- `pyproject.toml` optional dependencies include both `pyshp` and
  `geopandas >=1.0`.

### flopy4

- `flopy4/mf6/adapters.py`: `Flopy3Model.to_geodataframe` (`:186`),
  `Flopy3Package.to_geodataframe` (`:339`), and the array (`:457`) and
  list (`:650`) versions call flopy 3's `shape_attr_name` when
  `shorten_attr=True`. `pkg.export()` goes through `Flopy3Model` to
  flopy 3's exporters ([`replacing-flopy-mf6.md`](replacing-flopy-mf6.md)).
- geopandas is in flopy4's `optional` extra (`pyproject.toml:59`).

### The gridgen wrapper (`flopy/utils/gridgen.py`)

- **Input:** flopy writes features to temporary shapefiles for gridgen
  to read (`features_to_shapefile`, `ad{n}.shp`, `rf{n}.shp`,
  `intersect_feature.shp`) with pyshp.
- **Output:** the `GRID_TO_SHAPEFILE` blocks flopy writes (`:1930`)
  produce `qtgrid.shp` and `qtgrid_pt.shp`. `build()` reads
  `qtgrid.shp` with `gpd.read_file` (`:519`), and `_mkvertdict` reads it
  again with pyshp (`read_qtgrid_shp`, `:2030`). Both readers infer
  field types from the dBASE widths, which is the problem in
  gridgen#188.
- `intersect()` reads gridgen's `intersection.ifo` text file, not the
  `OUTPUT_SHAPEFILE`, so gridgen#190's intersection output doesn't
  affect flopy as things stand. The `shp2recarray` import at `:11` is
  unused.

## Formats and where each fits

| Format | Fits | Limits |
|---|---|---|
| GeoPackage (`.gpkg`) | Default. One file, several layers (grid, one per package or period) plus plain attribute tables. Full names, int32/int64/float/string, CRS stored. QGIS and ArcGIS Pro read it natively. | SQLite: one writer at a time; slower than FlatGeobuf for very large single layers. |
| FlatGeobuf (`.fgb`) | Large DISV/DISU grids, streaming, web maps (HTTP range reads). | One layer per file. Append-only. With a spatial index, features come back in spatial order, not node order (see below). |
| GeoParquet (`.parquet`) | Wide tables (per-layer, per-period columns), dataframe and DuckDB workflows. No GDAL needed (`gdf.to_parquet`). Gridgen#190 ruled it out for C++ dependencies, which don't apply here. | Less convenient for GIS-only users. |
| Shapefile (`.shp`) | Legacy, for users and tools that require it. | 10-character names, numeric types inferred from width, no int64, 2 GB, four or more files. |

## Design

1. **One writer.** `export(path, layer=None, **kwargs)` builds the
   component's `GeoDataFrame` and writes it:
   - `.gpkg`, `.fgb`, `.shp`, `.geojson`: `gdf.to_file(path,
     layer=layer, engine="pyogrio")`, driver from the extension.
   - `.parquet`: `gdf.to_parquet(path)`.
   - `.nc`: unchanged for now; moves to the xarray export later.
   The suffix branches in `flopy/export/utils.py` collapse into one
   dispatch. The pyshp writers in `shapefile_utils.py` go, and pyshp
   leaves the optional dependencies once the gridgen wrapper no longer
   needs it.
2. **Exporters build a `GeoDataFrame`, nothing format-specific.** Any
   exporter that builds pyshp records instead moves to
   `to_geodataframe`. This is where most of the work is.
3. **Name shortening is a shapefile concern.** Shorten only when the
   target is `.shp`, warn, and write the mapping from full to short
   names next to the file (e.g. a `.names.csv`). `shorten_attr` is
   deprecated in 3.x and removed in 4.x, including from flopy4's
   adapters.
4. **Multi-layer model export for GeoPackage.** `model.export("m.gpkg")`
   writes the grid as one layer and each package as its own layer (with
   one layer per period for transient lists, or a period column; to be
   decided), rather than one very wide table. Formats with one layer
   per file write the current single wide table.
5. **Keep types.** Node numbers and cell ids are int32 (int64 where the
   grid needs it), not floats or text. Column names are the full
   flopy4/DFN names.
6. **Never rely on row order.** Every exported table carries an explicit
   node or cellid column, and anything flopy reads back is indexed or
   joined on it. This makes FlatGeobuf with a spatial index safe to
   read.
7. **CRS from the grid.** The grid's CRS goes on the `GeoDataFrame`, so
   GeoPackage and GeoParquet store it. `write_prj` is only needed for
   shapefiles, and pyogrio writes the `.prj` itself.

## Gridgen

- **Reading output:** replace the pyshp reader (`read_qtgrid_shp`,
  `_mkvertdict`) and `gpd.read_file` with one `pyogrio.read_dataframe`
  that accepts any of the formats, and index by the node-number column.
  If gridgen#190 adds GeoPackage or FlatGeobuf, the wrapper asks for it
  in the `GRID_TO_SHAPEFILE` block (by extension or the new record) and
  gets correctly typed node numbers.
- **Feature input:** gridgen#190 covers output only, so flopy keeps
  writing temporary shapefiles for gridgen to read. That stays an
  internal detail. Ask on #190 whether input formats are in scope.
- **Which format for gridgen:** for flopy users, GeoPackage is better
  (multiple layers, ArcGIS, one file). FlatGeobuf is easier for gridgen
  to vendor. Since flopy reads either through pyogrio, flopy's needs
  shouldn't decide it; gridgen's build constraints should. Say so on
  #190 if asked.

## Steps

1. 3.x: add GeoPackage/FlatGeobuf/GeoParquet to the export dispatch
   through `to_geodataframe`, without removing the shapefile path.
   Deprecate `shorten_attr`.
2. 3.x: gridgen wrapper reads `qtgrid` through pyogrio, indexed by node
   number; drop the unused `shp2recarray` import.
3. 4.x: GeoPackage default in docs and examples; multi-layer model
   export; remove the pyshp writers and `shorten_attr`; shapefile
   output goes through pyogrio.
4. 4.x: once gridgen#190 lands, use its new format in the wrapper.
5. Later: `.nc` export moves to the xarray path
   ([`../xarray/export.md`](../xarray/export.md)).

## Open questions

- Transient data in a GeoPackage: one layer per period, or one layer
  per package with a period column (long format)? Long format suits
  joins and GeoParquet; wide suits shapefile-era users.
- Output files (heads, budgets, pathlines): same dispatch, or only
  through xarray?
- Does anything downstream (pyemu, modflow-setup) depend on the
  shapefile exporters' exact column names?
