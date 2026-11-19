# An MF6 xarray package

Where to draw the boundary inside flopy4 so that a separate MF6 xarray
package can be pulled out later as a packaging step, not a redesign.
Everything stays in flopy4 for now.

## Direction

- **A separate package, eventually** (working name `mf6xr`). It implements
  MF6's discretization, data semantics and file formats on xarray, roughly
  what xugrid is to UGRID. flopy4 depends on it; it never imports flopy4
  or flopy.
- **Our own representation first, encodings second.** The in-memory form
  is plain `xr.Dataset`/`xr.DataTree` with custom indexes, close to MF6's
  concepts and lossless for every grid type. Files and other libraries'
  objects are explicit conversions to and from it:
  - **Files are [MF6 NetCDF][mf6nc], in two layouts of one spec.**
    *Grouped* is the whole tree, lossless. *Ungrouped* is the same content
    flattened; MF6 reads it, and it aims to be valid CF and UGRID so GIS
    tools open it directly.
  - **Adapters** (`to_ugrid`, `to_rioxarray`, `to_cf`, `to_modelgrid`)
    hand the representation to xugrid, rioxarray, cf_xarray or flopy3 in
    memory. Those libraries write their own files.
- **The boundary is a data contract, not an API.** The export schema
  ([`export.md`](export.md) phase 1) is the interface. flopy4 produces it;
  the package (accessor, `dense()`, writers, adapters) consumes it using
  only what's in the dataset.
- **The generic attrs ↔ xarray layer could become xattree v2**, a second
  library beside the package, not under it. xattree knows nothing about
  MF6, and the package knows nothing about attrs.

[mf6nc]: https://github.com/MODFLOW-ORG/modflow6/wiki/MODFLOW-NetCDF-Format
[x36]: https://github.com/wpbonelli/xattree/issues/36

## Related docs

- [`representation.md`](representation.md): the spec, and how it relates
  to netCDF, CF, UGRID and MF6 NetCDF.
- [`export.md`](export.md): `to_xarray`/`from_xarray`, `dense()`,
  `flatten()`. Phase 1 fills in the spec; it needs branch
  `to-xarray-constants` first.
- [`rotated-grid-index.md`](rotated-grid-index.md): DIS coordinates,
  rotation, `CellIndex`, z selection, the accessor (#469-#490). DISV
  selection (its Next 1) should follow the xugrid notes below.
- [`rch-evt-layer.md`](rch-evt-layer.md): z coordinates for RCHA/EVTA.
- [`combined-index.md`](combined-index.md): a combined `GridIndex`;
  revisit if DISV needs its own index anyway.
- [`datetime-periods.md`](datetime-periods.md): datetime period keys,
  `create_tdis` (#518, #226).
- [`tas-interpolation.md`](tas-interpolation.md): time-array series in
  the dense view. Its step view is opt-in and never read back by
  `from_xarray`.
- [`layout-logical-decisions.md`](../dfn-spec/layout-logical-decisions.md):
  how options appear in the export (logical as data, layout as encoding).
- Period lists (#476): the spec's "Period data" records the result.
- [`out-of-core.md`](out-of-core.md): larger-than-memory models (FUNC-8). Lazy
  `dense()` belongs to job C and chunk-aware encoders to job D.
- [`sdd.md`](../../sdd.md) "Xarray conversion" and "NetCDF": to update
  (step 7).
- [xattree #36][x36] and #367 (attrs vs. pydantic): see "xattree".

## The layers

Four jobs, all in flopy4 today. Job A splits into a generic half and an
MF6 half.

| Job | What | Today | Layer |
|---|---|---|---|
| A1. attrs ↔ xarray, generic | attrs instance ↔ `Dataset`/`DataTree` from field metadata (dims, `shape`), child fields as tree nodes, protocols | most of `attrs_xarray.py`, `protocols.py`, part of `dimensions.py` | xattree v2 |
| A2. Object model ↔ xarray, MF6 | hooks for period arrays, TAS refs, fill values, aux names, references; type tags; which DFN field goes on which dims | the MF6 parts of `attrs_xarray.py`, `Package/Context.to_xarray`, `adapters.py` | flopy |
| B. Discretization → coordinates and indexes | dims and coordinates per grid type, cell centres, z bounds, rotation and CRS, `CellIndex`, `sel`/`sel_world`/`sel_z`/`mask_z` | `utils/grid.py`, `utils/vertical.py`, `utils/crs.py`, `accessor.py` | package |
| C. MF6 data semantics | sparse ↔ dense, period fill-forward, cellid ↔ node, the `duplicates` policy, TAS evaluation | `period_lists.py` (densify half), `period_arrays.py`, the planned `dense()` | package |
| D. Encodings and files | MF6 NetCDF input/output, CF, UGRID, GRB/HDS/CBC readers | `netcdf.py`, `utils/netcdf_postprocess.py`, `utils/heads_reader.py`, `utils/cbc_reader.py`, `dims_from_grb` | package |

Dependencies: flopy4 → package → xarray, and flopy4 → xattree → attrs,
xarray. xugrid (and flopy3, while needed) are optional. The package and
xattree don't depend on each other. Jobs B-D have users who never touch
flopy's object model (output post-processing, xmipy/BMI, other model
builders); that's what makes a separate package worth having.

### Coupling to remove (as of `000f63c3`)

| Module | Imports that cross the boundary | What to do |
|---|---|---|
| `utils/grid.py` | subclasses flopy3 `StructuredGrid`/`VertexGrid`; imports `xugrid` at module level; `flopy4.adapters.read_binary_grid_file` (lazy) | Compute geometry from arrays (composition, not inheritance); build a flopy3 `modelgrid` from it where needed. Make xugrid lazy. Move the GRB reader to D. |
| `utils/heads_reader.py`, `utils/cbc_reader.py` | `flopy.discretization`, `flopy4.adapters`, `xugrid` | Take geometry from the GRB or a dataset, not a flopy grid. |
| `utils/time.py` | `flopy.discretization.modeltime` | A small time-coordinate builder from perlen/nstp/tsmult (+ start date). |
| `period_lists.py` | `item`, `item_table`, `flopy4.spec` | Split: the encoder (`ItemTable` → sparse table) stays in flopy; densify/sparsify moves to C. |
| `period_arrays.py` | `_types` (`TimeArraySeriesRef`), `constants` | Constants move with it. TAS refs are already coordinates (`<name>_tas`, #489). |
| `netcdf.py` | `Model`, `Package`, `spec`, pydantic `NetCDFModel` | Split: walking the model stays in flopy; writing a representation dataset as MF6 NetCDF moves to D. |
| `vertical.py`, `crs.py`, `accessor.py` | none | Already clean. |
| `attrs_xarray.py` (A1) | lazy `TimeArraySeriesRef`, `FILL_DNODATA`; `flopy4.spec` references; `fill_forward`/`fk` metadata | Move into hooks registered from `flopy4.mf6` (see "xattree"). |
| `dimensions.py` (A1) | `modflow_devtools.dfns.dim_value`; `flopy4.spec.is_reference` | `DerivedDim` and DFN expressions stay in flopy; the generic part is a small resolver. |

## Files and adapters

Each is a pair of functions (representation ↔ file or object) plus
accessor methods. None changes the representation.

- **MF6 NetCDF, grouped:** the representation as is, through
  `DataTree.to_netcdf`/`to_zarr`, with only the encoding netCDF needs.
  Lossless. MF6 doesn't read it yet.
- **MF6 NetCDF, ungrouped** (structured and layered mesh): what
  `netcdf.py` writes today, restated as a fixed flattening of the grouped
  layout. Readers reverse it and, while coverage is partial, merge in
  fields from text input. CF bounds come with it (rotated-grid-index
  Next 3).
- **Adapters:** `to_ugrid()`/`from_ugrid()` (DISV, layered DIS),
  `to_rioxarray()` (structured; rioxarray takes a rotated affine but its
  1-D x/y assume no rotation, so check), `to_cf()`, `to_modelgrid()`
  (flopy3, replacing the inheritance in `utils/grid.py`).
- **Binary output** (GRB/HDS/CBC): readers that produce the representation
  directly.

The format is ours to change too; the spec's "What the format could
change" lists candidates. First to settle is the flattening rule for a
whole simulation, chiefly how dims are prefixed or shared across models.

## xugrid

- Optional, behind the UGRID adapter and DISV selection, not in the core
  representation. A `UgridDataset` is a wrapper, not an `xr.Dataset`: it
  doesn't nest in a `DataTree`, and our accessors don't reach it.
- The `xugrid` branch (May 2026, `b00d7a05`) returns xugrid objects from
  `to_xarray`. Don't merge it as is; its useful parts (dropping
  hand-written UGRID attrs, keeping CF bounds) go into the UGRID adapter
  and the ungrouped mesh writer.
- DISV selection: output readers return `UgridDataArray` today. For the
  representation, prefer a plain dataset with an index (`NDPointIndex` for
  nearest, or our own containment index, maybe the combined-index design),
  and `to_ugrid()` for regridding and plotting.
- xugrid #35 / PR #373 (custom indexes instead of wrapper types) would let
  DISV be a plain dataset plus xugrid's index.
- The `xugrid==0.15.3` pin needs a range before flopy4 goes into flopy.
  Making it optional comes after `grid.py` stops importing it at module
  level.

## xattree

[xattree #36][x36] proposes rewriting xattree as a functional layer:
explicit `to_datatree()`/`from_datatree()`, protocols instead of
inheritance, pure translation functions. It keeps the spec system, the
field factories and dimension inheritance, and drops the imposter
containers, `bind_tree()` and `init_tree()`.

flopy4 has mostly built this since dropping xattree (#356, #359):

| #36 asks for | flopy4 today |
|---|---|
| pure `to_datatree`/`from_datatree` | `attrs_to_dataset`, `dataset_to_attrs`, `attrs_to_datatree`, `datatree_to_attrs` in `attrs_xarray.py` |
| a `DataTreeConvertible` protocol | `protocols.py`, same name |
| dimension inheritance | `dimensions.py`: `DimensionProvider`/`DimensionResolver`, `DerivedDim` |
| dims tagged on fields | `shape` metadata from `flopy4.mf6.spec.array()` |
| no imposter containers | gone |

So xattree v2 would start from `attrs_xarray.py` and the generic part of
`dimensions.py`. What isn't generic yet: period-array stacking along
`<name>_kper` (keyed off `fill_forward`), the `<name>_name` aux dim,
`TimeArraySeriesRef` and `FILL_DNODATA`, references stored by name, the
reserved names `dims`, `parent` and `_parent`, and DFN dimension
expressions.

The design is a converter with hooks, like cattrs:

- hooks keyed by a predicate on the field, each a pair (value →
  `DataArray`, `DataArray` → value);
- a policy for which fields are children (tree nodes) and which leaves;
- a policy for excluded fields, instead of hard-coded reserved names;
- a fallback dim name (`<name>_dim<i>`) when a field has no `shape`.

flopy4 registers the MF6 hooks. Naming conventions come from the
representation spec, through flopy's field metadata and hooks. Pipeline:
object → xattree (with flopy's hooks) → a raw `DataTree` following the
spec → the package (indexes, `dense()`, encodings).

`DataTree` inherits coordinates from parent nodes, which covers dims once a
tree exists. Resolving dims before conversion (shape checks, scalar
expansion) still needs something at the object level, but maybe only a
small `resolve_dims(obj, ancestors)` rather than the provider/resolver
protocols.

The code is about 400 lines, so extracting it won't shrink flopy much. The
payoff is the boundary: a generic core makes the MF6 parts explicit as
hooks. An attrs-only xattree locks in attrs; a thin field-introspection
layer could keep #367 open, but settling #367 first is simpler. Before
flopy depends on xattree, it should probably move to MODFLOW-ORG.

## Steps inside flopy4

Roughly in order; none needs a new repo.

1. Finish the representation spec as part of export phase 1 (bool
   encoding, type tags, the float fill value).
2. Rename the accessor from `.grid` to something distinctive (e.g.
   `.mf6`) before more users depend on it; xugrid uses `.ugrid`, uxarray
   `.uxgrid`. Do it with export phase 2, which adds `dense()` to it.
3. One subpackage for jobs B-D, e.g. `flopy4/mf6/xr/` or `flopy4/xr/`.
   Move modules as they're touched. Add an import-linter contract
   forbidding imports from
   `flopy4.mf6.{component,package,context,model,simulation,item,item_table}`
   and `flopy4.spec`.
4. Drop the flopy3 grid inheritance in `utils/grid.py`, and replace
   `utils/time.py`'s use of `ModelTime`. The biggest piece. Moving flopy4
   into flopy doesn't need it, since these become internal imports
   ([`replacing-flopy-mf6.md`](../integration/replacing-flopy-mf6.md)
   "Layout in 4.x"). Extraction does: see "When to extract".
5. Split `netcdf.py` and `period_lists.py` along the encode/densify line.
6. Make xugrid lazy throughout the subpackage, then decide whether it's an
   optional dependency.
7. Update [`sdd.md`](../../sdd.md) ("Xarray conversion", "NetCDF") for the
   representation, the two layouts, the adapters and the boundary. Its
   "NetCDF" section is close, except that xugrid is one adapter, not the
   writer.
8. Make `attrs_xarray.py` generic as part of export phase 1, with an
   import-linter contract so `attrs_xarray`, `protocols` and the generic
   part of `dimensions` can't import `flopy4.mf6`. Then move period, TAS,
   fill-value and reference handling into hooks. Worth doing even if
   xattree v2 never happens.

## When to extract

When all of these hold:

- the spec has been stable for a release or two;
- the import-linter contract is green and the subpackage imports neither
  flopy3 nor flopy4's object model;
- someone outside flopy wants it (an output-only user, imod, xmipy, a GUI);
- flopy4 is in flopy, so a third repo doesn't add to the devtools release
  coordination already blocking that.

Until then, a subpackage with an enforced boundary gets most of the
benefit. xattree v2 has its own criteria: the A1 contract is green, the
hook API has been stable for a while, and #367 is settled.

## Coordination

- **imod-python** already builds MF6 on xarray/xugrid and reads
  GRB/HDS/CBC into xarray. Before creating a package, ask Deltares whether
  the grid, encoding and output layer could be shared, or at least whether
  we can agree on the representation.
- **MF6 NetCDF**: raise the spec's format notes on modflow6 once checked
  against the source. First confirm the intent: is the ungrouped layout
  meant to cover a whole simulation, and would MF6 ever read a grouped one?
- **xugrid**: follow #35 / #373; report DISV edge-tie behaviour if it
  differs from DIS.
- **xattree**: note in #36 that `attrs_xarray.py` is the prototype, once
  there's something to point at.

## Open questions

- The flattening rule for a whole simulation in the ungrouped layout.
- Default layout per writer: ungrouped for model input and tool-facing
  output, grouped for saving a whole simulation from flopy?
- Which adapters, and their names.
- Package name, and `flopy4/xr/` vs. `flopy4/mf6/xr/`.
- Accessor name, decided together with export phase 2b's names
  (`flatten()`/`unflatten()`; flat dim `node`, as DISU, or `nodes`, the
  DFN fallback).
- Whether the time code (TDIS → time coordinate, TAS evaluation) belongs
  in the package. Probably, since output readers need it too.
- Whether the package knows DFNs. Preferably not: writers take metadata
  from attrs flopy puts on the representation.
- The representation for DIS2D/DISV2D/DISV1D (OLF/CHF).
- Whether xattree v2 is attrs-only (#367), keeps the field factories, and
  lives under MODFLOW-ORG.
