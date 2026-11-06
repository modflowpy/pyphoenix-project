# The MF6 xarray representation

The spec the export work builds to. Sections say what exists today and
what is planned. The design behind it, and the open questions, are in
[`overview.md`](overview.md); the implementation steps in
[`export.md`](export.md).

The representation is the in-memory form of an MF6 simulation as xarray
objects: what flopy4's `to_xarray` produces, what `from_xarray` accepts, and
what the accessor, `dense()`, the file writers and the adapters work on.
Files are written from it, and no file format is the representation itself.

**"Layout" in this doc** means one of two things, always qualified: the
two MF6 NetCDF *layouts* (grouped and ungrouped), and the two *cell
layouts* (flat `node` and layered). Neither is the MF6 *file* layout of
[`layout-logical-decisions.md`](../dfn-spec/layout-logical-decisions.md) (blocks, `CONSTANT`, `READASARRAYS`), which
here is the encoding of options and arrays.

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
| Coverage goal | everything | everything, to confirm with the MF6 developers |
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
  documented grammar for `modflow_input`. Today the reader has to parse
  `<model>/<package>/<tag>` strings, and the package name depends on the
  namefile (or the name FloPy generated). The format sets no naming rules
  beyond CF, so this attribute is the only reliable identity.
- **Coverage:** list data, options and scalars, simulation-level
  components, DISU and DIS2D/DISV2D/DISV1D.
- **CF/UGRID validity as a stated goal:** a `layer` dim rather than split
  variables (`npf_k_l1`, `z_l<n>`, each with a `layer` attr), or a
  documented reason for splitting; 2-D auxiliary coordinates for rotated
  grids, which without a CRS lose `axis`/`standard_name` today; and
  bounds, `grid_mapping` and standard names throughout.
- **Consistent fill values** per dtype.
- **A time mapping** between period-sized input time and step-sized output
  time.
- **Groups**, eventually, if MF6 is to read the grouped layout.

These come from the wiki, not the MF6 source, and need checking (and the
coverage goal confirming with the MF6 developers) before anything goes
upstream.

## Grid dims and coordinates

### Dims

| Grid | Cell dims | Flat view |
|---|---|---|
| DIS | `(layer, row, col)` | `node` |
| DISV | `(layer, cell)` | `node` |
| DISU | `(node,)` | (already flat) |
| DIS2D, DISV2D, DISV1D (OLF, CHF) | not yet defined | |

- **Dims are named for the grid's axes**, not the DFN sizes (`nlay`,
  `nrow`, `ncol`, `ncpl`, `nodes`), since they're typed in selections all
  the time and xarray has no dim aliases. The DFN names appear only as
  sizes in attrs, and as fallback dims for an array whose grid doesn't
  resolve. The mapping is `flopy4.mf6.constants.GRID_DIMS`.
- **`cell`, not `node`, on DISV**, because in UGRID a node is a vertex.
  `node` means an MF6 user node: a cell numbered in 3-D, as on DISU.
- **No index coordinates on `layer`/`row`/`col`/`cell`.** Positions are
  the indices, 0-based (`isel`). Selecting by MF6's 1-based numbers is a
  separate accessor method (`sel_cell`, planned).
- **Arrays not on the cells** get one dim per shape name: DIS `delr` on
  `col`, `delc` on `row`. Arrays with one layer's worth of values (DIS/DISV
  `top`, RCHA `recharge`) keep a size-1 `layer` dim.
- **The flat view** (`flatten()`/`unflatten()`, export plan phase 2b)
  stacks the cell dims into `node`, layer slowest, so position `i` is user
  node `i + 1`. It's a view, not stored.

### Coordinates on a DIS array

Design and alternatives in [`rotated-grid-index.md`](rotated-grid-index.md).

| Coord | Dims | Index | Rotated grid | Unrotated grid |
|---|---|---|---|---|
| `x` | `col` | `CellIndex` | local, zero-based | world |
| `y` | `row` | `CellIndex` | local, zero-based | world |
| `dx`/`dy` | scalar if uniform, else `col`/`row` | none | cell sizes (`dy` negative) | same |
| `projection` | scalar | none | grid mapping | grid mapping |
| `x_world`/`y_world` | `(row, col)` | none | world centres | omitted (same as `x`/`y`) |
| `z` | `(layer, row, col)` | none | cell-centre elevation | same |
| `z_top`/`z_bot` | `(layer, row, col)` | none | cell top and bottom | same |

- **`x`/`y` are in the grid's CRS.** Unrotated, that's the base CRS, so
  they're world coordinates. Rotated, it's a derived CRS (an EPSG:9624
  affine wrapping the base), so they're local. Rotation lives in the CRS,
  not in the coordinate values. This is CF's `rotated_latitude_longitude`
  pattern, and what MF6's own netCDF writer does.
- **`projection`** has the value `1`, and attrs `xorigin`/`yorigin`/
  `angrot` always, plus `crs_wkt` and `grid_mapping_name` when there's a
  CRS. Gridded variables name it in their `grid_mapping` attr.
  `xorigin`/`yorigin`/`angrot` aren't CF, but without a CRS they're the
  only record of where the grid is.
- **`CellIndex`** is a `PandasIndex` that also keeps each cell's edges.
  `sel` without a `method` gives the cell containing the point. A point on
  an edge goes to the lower-numbered cell (west, north), as in flopy3. A
  point outside raises `KeyError`.
- **z coordinates** come from `top`/`botm` (`vertical.z_coords`), with
  `z_top[0] = top`, `z_top[k] = botm[k-1]` and `z_bot = botm`. They're on
  every array on the grid's layers. `top` gets layer 0's. RCHA/EVTA arrays
  don't get them unless the model has one layer, since the layer their
  values go to depends on `irch`/`ievt` ([`rch-evt-layer.md`](rch-evt-layer.md)).

### DISV and DISU

- **DISV:** `x`/`y` on `cell`, world coordinates from `cell2d` (rotated by
  `angrot` about the origin), unindexed. `z`/`z_top`/`z_bot` on
  `(layer, cell)`. No containment index yet; whether DISV input gets an
  `NDPointIndex`, its own index, or goes through `to_ugrid()` is open
  ([`rotated-grid-index.md`](rotated-grid-index.md) Next 1).
- **DISU:** `x`/`y` on `node` from `cell2d`. Per-node z coordinates, from
  DISU's own `top`/`bot`, are open.

### What isn't stored

Indexes aren't written to files. An array read back from netCDF has its
coordinates but needs `index_xy` (or an accessor method, planned) to get
its `CellIndex` back. Cell bounds (`x_bnds`/`y_bnds`/`z_bnds`, CF
`bounds`) are planned for the writers, so a file can be indexed without
the GRB.

## Tree, names and type tags

Planned, in export plan phase 1. Today `attrs_to_datatree` names nodes by
field and position (`models0`, `chd0`) and can't recover concrete types.

- **Packages give an `xr.Dataset`, contexts an `xr.DataTree`.** The
  simulation is the root. Models, exchanges, solutions and TDIS are its
  children, and packages are children of their model. A package looks the
  same whether exported alone or pulled out of its model's tree: it carries
  its own grid coordinates.
- **Nodes are named by the component's name** (`gwf_1/npf`), not by field
  and position.
- **Every node has a type tag**, `attrs["type"]`, so a reader can pick the
  concrete class for `list[Model]` and union fields. Probably the DFN
  component name (`gwf-npf`), since it doesn't depend on Python, rather
  than the class path.
- **Grid metadata in attrs:** the grid type and sizes (`nlay`, `nrow`,
  `ncol`, `ncpl`, `nodes`) and `nper`, so `dense()`, `unflatten()` and the
  writers never need the DIS object.
- **References** between components (a solution's models, an exchange's
  models) are stored by name.
- **Empty child lists** are omitted.

## Period data

Data given per stress period is stored **as given**: only the periods the
user set, never filled forward. Filling forward is a view (`dense()`).

### How periods persist

What a new block means depends on the input form
(`doc/mf6io/gwf/bcoptions.tex`, `mvr.tex`):

| Input form | A new block | Not given in the block | Empty block |
|---|---|---|---|
| list (CHD, WEL, ...; also MVR) | replaces all entries | removed | clears all |
| layer array (RCHA, EVTA) | replaces the arrays it names | retained | no effect; turn off with a zero rate |
| grid array (CHDG, WELG, ...) | replaces the arrays it names | retained, by position | clears all |
| advanced (SFR, LAK, MAW, UZF) | changes only what it names | retained | no effect implied; deactivate through settings |

- A list block is a snapshot, a layer or grid array is a per-array snapshot,
  and only an advanced block is a true delta.
- MVR is grouped with the advanced packages by name, but behaves like a list.
- A grid array is stored by position among the active cells of the block that
  gave it, and each block's first array sets those cells again. So a retained
  array needs the same active cells (`check_grid_periods`). The DFNs make
  stress arrays required in each block and only aux optional, but flopy4
  follows MF6's loader, which retains both.
- Retaining aux is deliberate. 6.4.3 reset it to zero each period, which zeroed
  the `AUXMULTNAME` multiplier when it wasn't given again, and 6.8.0 reverted
  that for layer arrays, to match grid arrays.

**Proposed, not decided:** make layer and grid stress arrays replace as list
blocks do in MF6, leaving advanced packages as the only update regime. This
table describes MF6 as it is until that changes. The change would have to
decide what happens to aux and to `IRCH`/`IEVT`: an omitted `IRCH` means layer
1, so input that gives it once could move its recharge.

### Period arrays

RCHA's `recharge`, WELG's `q` and the like (built, in `attrs_xarray`):

- stacked along a `<name>_kper` dim, labelled by the periods given;
- a value from a time-array series is NaN, with the series' name in a
  `<name>_tas` coordinate along `<name>_kper` (`None` where a period has
  no series).

**Why each array has its own dim (decided 2026-11-05, open to revisiting).** The
logical data is a step function over every period, so one `kper` dim from TDIS
looks most correct, and it's what the [dense view](#the-dense-view) gives. But a
full `kper` dim is the dense form, and this export aims to hold input as given.
A period list's sparse form has a `kper` value on each row. An array has no rows,
so its sparse form needs a dim listing the periods given.

The alternatives, for `recharge` given in periods 0 and 3 and `irch` in 1, 2 and 3
(tested on xarray 2025.12.0, except fill forward):

| Alternative | What happens | Cost |
|---|---|---|
| shared `kper`, filled forward | every period has a value | can't tell a repeated block from no block, so `from_xarray` can't rebuild `{0: a, 3: b}` exactly; size grows with the periods; needs TDIS |
| shared `kper`, NaN where not given | xarray merges the labels to 0-3 and fills the gaps | also needs TDIS for the full dim; `irch` goes from `int64` to `float64`; NaN already means a time-array series value, and "not given" has to stay distinct from DNODATA |
| shared `kper`, no labels | `ValueError`: conflicting sizes | not an option |
| shared `kper` over the periods any array gave | the merge above, on fewer periods | the same costs as NaN, and it isn't TDIS's `kper` |
| one tree node per array, each with its own `kper` | siblings can differ | xarray rejects a child whose `kper` disagrees with a parent's, as a `kper` from TDIS on the simulation's root would |
| `kper` only when a package's arrays share periods | works for those packages | the shape depends on the data |

The size difference is what makes a shared dim expensive. At 1,000 periods and 1M
cells per layer, a `recharge` given twice takes about 16 MB here, and about 8 GB as
plain 8-byte arrays over the full dim. Lazy arrays might reduce that, but that's
untested.

**What would change this:** if most use turns out to be dense and models stay
small, the export could use the full `kper` dim, filled forward, with a
`<name>_given(kper)` mask to stay lossless. A package with no TDIS would label only
the periods given, so its shape would change on attach, which breaks "a package
looks the same whether exported alone or pulled out". It would also undo the
"as given, `dense()` is a view" decision.

### Period lists

CHD's, WEL's, SFR's stress period data (the sparse form is built, as
`to_xarray(sparse=True)`; export phase 1 makes it the stored form):

- a sparse table along an `entry` dim, one entry per row;
- a `kper` coordinate, 0-based;
- one coordinate per cellid component: `cellid_layer`, `cellid_row`,
  `cellid_col` on DIS;
- a `setting` coordinate for keystring packages (SFR, LAK, MAW);
- a variable per value column and per aux name. An array column (EVT's
  `pxdp`) gets a dim sized from its `shape`;
- a `<column>_ts` coordinate naming the time series where a value comes
  from one (the value is NaN), and a `boundname` coordinate.

Unset values are `FILL_DNODATA` (floats), `FILL_INT64` (ints) or `None`.

**Why `entry`, not `period_data_row` (decided 2026-11-05).** `entry` is mf6io's
word for a boundary row. A package has at most one period list, so the name isn't
ambiguous within a package, and `period_data_row` wouldn't separate packages either,
since every package would use the same name. `row` is also a grid axis here, so
`cellid_row` along `period_data_row` would give one suffix two meanings.

**Other row lists** (TDIS `perioddata`, `packagedata`, `connectiondata`)
get the same treatment (planned). A package can have several, of different lengths,
so each needs its own dim. The name is open: `<field>_row` has the same clash with
`cellid_row`.

### The dense view

`dense()` (planned, on the accessor; today it's `to_xarray()`'s default)
places each period's rows by their key and fills forward:

| Row key | Dense dims | Examples |
|---|---|---|
| one `cellid` | the grid | CHD, WEL, DRN |
| a foreign key to another table | that table's dim (`nreaches`), or the grid with `grid=True` | SFR, LAK, MAW, UZF |
| the package's own index | a dim named for it (`bndno`) | SPC |
| anything else (two cellids, no key) | no dense form; the table as is | HFB, MVR, OC |

- Periods fill forward by their [regime](#how-periods-persist).
- A row key holds within its period. A list entry has no identity across
  periods, and SPC's `bndno` is a position in the flow package's block for
  that period.
- Two rows in one cell raise, unless `duplicates="sum" | "first" | "last"`
  merges them (lossy).
- All of this is decided from field metadata (`cellid`, `fk`, `pk`,
  `union`, `shape`), with no per-package code, once the regime is there too.
  `fill_forward` is only a boolean today (see
  [`dfn-gaps.md`](../dfn-spec/dfn-gaps.md#rules-in-fortran-that-need-new-dfn-syntax)).

## Time

- **`kper`** is the 0-based stress period index, in list tables and in
  `<name>_kper` labels.
- **Datetime period keys** ([`datetime-periods.md`](datetime-periods.md), #518): packages
  may be keyed by datetimes. Keys stay as given and are resolved to `kper`
  against TDIS when needed, so TDIS stays the one source of truth for what
  period *n* means.
- **Time coordinates:** period start times come from TDIS
  (`start_date_time` plus the cumulative `perlen` in `time_units`); output
  is per time step. The representation should carry both and the mapping
  between them (the period of each step). Not built.
- **Time-array series** stay NaN plus a name in the representation.
  Evaluating them (MF6 averages over each step, STEPWISE or LINEAR only) is
  a view; see [`tas-interpolation.md`](tas-interpolation.md).

## Laziness

Planned; [`out-of-core.md`](out-of-core.md) has the design and today's gaps.

Any variable in the representation may be lazy, such as a dask array or a
deferred read of a file. Producing the representation never computes one. Each
consumer does one of three things, and says which:

| What it does | Consumers |
|---|---|
| **Preserves:** returns lazy data without computing | `to_xarray`, `from_xarray`, `dense()`, `flatten()`, the accessor's selections, the adapters where the target library allows it |
| **Computes once, a chunk at a time:** one ordered pass, with peak memory set by chunk size | the text, binary and NetCDF writers, and the checks and constant detection they do along the way |
| **Computes on request:** only when the user asks | explicit checks of values, `.compute()`, `.values` |

A consumer not listed computes nothing. The same values give the same files'
content and the same results whatever the array type or chunking, except for
what can't be known without computing, like a lazy array that's constant.

## Attributes and fill values

- **netCDF-safe attrs**, so the grouped layout is just `to_netcdf`: paths
  as strings, references as names, `None` omitted, empty child lists
  omitted. Bools are open: int8 with a flag, or a documented convention.
- **Variable metadata** (`long_name`, `units` where known) is put on by
  flopy from the DFNs. The package side doesn't read DFNs.
- **Fill values:** one per dtype. Today the code uses `FILL_DNODATA`
  (`3e30`, MF6's DNODATA) for unset floats in list data, `FILL_INT64`
  (`-2147483647`, netCDF's int default) for ints, and `FILL_FLOAT64`
  (`9.97e36`, netCDF's double default) when writing MF6 NetCDF. Which float
  value the representation uses for "not set", and how it maps to
  `_FillValue` on write, is open.

[mf6nc]: https://github.com/MODFLOW-ORG/modflow6/wiki/MODFLOW-NetCDF-Format
