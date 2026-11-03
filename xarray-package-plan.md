# An MF6 xarray package: layering now, extraction later

Written 2026-11-03, against develop `000f63c3`. Status: **direction agreed,
nothing scheduled.** Everything stays in flopy4 for now. This plan is about
where to draw the boundary inside flopy4 so that pulling out a separate
package later is a packaging decision rather than a redesign.

## Decisions

1. **Eventually, a separate package** (working name `mf6xr`; the name is
   open) implements MF6's discretization, data semantics and file formats on
   xarray. It's to MF6 roughly what xugrid is to UGRID. flopy4 depends on it;
   it never imports flopy4 or flopy.
2. **Our own representation first, encodings second.** The in-memory form
   is plain `xr.Dataset`/`xr.DataTree` with custom indexes, close to MF6's
   own concepts and lossless for every grid type. Files and other
   libraries' objects are explicit conversions to and from it, and none of
   them is the core:
   - **Files are [MF6 NetCDF][mf6nc] in two layouts of one spec.**
     *Grouped* is the whole tree, lossless. *Ungrouped* is the same content
     flattened. MF6 reads it, and it aims to be valid CF and UGRID, so GIS
     tools open it directly. CF and UGRID are conventions MF6 NetCDF builds
     on, not separate formats.
   - **Adapters** (`to_ugrid`, `to_rioxarray`, `to_cf`, `to_modelgrid`)
     hand the representation to xugrid, rioxarray, cf_xarray or flopy3 in
     memory. Those libraries write their own files.

   `docs/dev/xarray-representation.md` explains how netCDF, CF, UGRID, the
   MF6 NetCDF format and the representation relate.
3. **The boundary is a data contract, not an API.** The export schema from
   `xarray-export-plan.md` phase 1 is the interface. flopy4 produces it;
   the package (the accessor, `dense()`, the writers and adapters)
   consumes it, using
   only what's in the dataset. The export plan already states the rule:
   *"If it needs the package or the grid object, phase 1 is missing
   something."*
4. **Not yet.** Extract only when the criteria in "When to extract" hold.
5. **The generic attrs ↔ xarray layer could become xattree v2** (see
   "xattree"). It would be a second library beside the package, not under
   it: xattree knows nothing about MF6, and the package knows nothing about
   attrs. Same approach: make it generic inside flopy4 first, extract later.

[mf6nc]: https://github.com/MODFLOW-ORG/modflow6/wiki/MODFLOW-NetCDF-Format
[x36]: https://github.com/wpbonelli/xattree/issues/36

## How this relates to the other xarray docs

This is the umbrella doc for direction: decisions, the boundary, when to
extract, coordination, and all open questions. The other docs keep their
scope:

- **`docs/dev/xarray-representation.md`** is the spec: what the
  representation is, how it relates to netCDF, CF, UGRID and MF6 NetCDF,
  and the notes on the MF6 NetCDF format.
- **`xarray-export-plan.md`** is the implementation checklist for the
  export, the accessor and the cell layouts.
- The plans below are where specific pieces were designed. The spec now
  summarizes what they decided.

| Doc | Scope | Layer | Status |
|---|---|---|---|
| `xarray-export-plan.md` | lossless `to_xarray`/`from_xarray`, `dense()`, `flatten()` | flopy (export) + package (accessor) | Decided, not started. Phase 1 fills in the spec. Needs branch `to-xarray-constants` merged first. |
| `rotated-grid-index-plan.md` | DIS coords, rotation, `CellIndex`, z selection, `.grid` accessor | package (grid) | Mostly done (#469–#490). Its Next list is still live; Next 1 (DISV) should follow the xugrid stance below. |
| `rch-evt-layer-plan.md` | z coordinates for RCHA/EVTA arrays | package (grid) | Not started. |
| `combined-index-notes.md` | a combined `GridIndex` on `CellIndex` | package (grid) | Deferred. Revisit if DISV needs its own index anyway (see xugrid). |
| `datetime-periods-plan.md` | datetime period keys, `create_tdis` | flopy + package (time) | In progress (#518, #226). |
| `tas-interpolation-plan.md` | time-array series in the dense view | package (time) | Ready, not started. |
| period lists (#476) | period lists in xarray, dense/sparse | flopy (encode) + package (densify) | Done. The spec's "Period data" records the result; the dense view becomes `dense()`. |
| `docs/dev/spatial-index-design.md` on `origin/xarray-index` (#278) | original spatial index design | — | Superseded by `rotated-grid-index-plan.md`, whose Next 9 covers the housekeeping. |
| `docs/dev/sdd.md` "Xarray conversion", "NetCDF" | SDD description | both | Update after export phase 1 (representation) and once the writers and adapters exist (NetCDF); see step 7. |
| [xattree #36][x36] | functional rewrite of xattree | generic (A1) | Open. flopy4's `attrs_xarray.py` is the working prototype; see "xattree". |
| #367 | attrs vs pydantic dataclasses | flopy (object model) | Stale. Its outcome decides whether xattree v2 is attrs-only. |

## The layers

Four jobs, today all in flopy4. Job A splits into a generic half and an MF6
half:

| Job | What | Today | Layer |
|---|---|---|---|
| A1. attrs ↔ xarray, generic | attrs instance ↔ `Dataset`/`DataTree` from field metadata (dims, `shape`), child fields as tree nodes, protocols | `attrs_xarray.py` (most of it), `protocols.py`, part of `dimensions.py` | **xattree v2** (eventually) |
| A2. Object model ↔ xarray, MF6 | hooks for period arrays, TAS refs, fill values, aux names, references; type tags; which DFN field goes on which dims | the MF6 parts of `attrs_xarray.py`, `Package/Context.to_xarray`, `adapters.py` | **flopy** |
| B. Discretization → coordinates and indexes | dims and coordinates per grid type, cell centres, z bounds, rotation and CRS, `CellIndex`, `sel`/`sel_world`/`sel_z`/`mask_z` | `utils/grid.py`, `utils/vertical.py`, `utils/crs.py`, `accessor.py` | **package** |
| C. MF6 data semantics | sparse table ↔ dense, period fill-forward, cellid ↔ node, the `duplicates` policy, TAS evaluation | `period_lists.py` (densify half), `period_arrays.py`, the planned `dense()` | **package** |
| D. Encodings and files | MF6 NetCDF input/output, CF, UGRID, GRB/HDS/CBC readers | `netcdf.py`, `utils/netcdf_postprocess.py`, `utils/heads_reader.py`, `utils/cbc_reader.py`, `dims_from_grb` | **package** |

Dependencies: **flopy4 → package → xarray** and **flopy4 → xattree →
attrs, xarray**, with xugrid (and flopy3, while it's still needed)
optional. The package and xattree don't depend on each other. Jobs B–D have users who never touch
flopy's object model: people post-processing MF6 output, xmipy/BMI users,
other model builders. That's what makes a separate package worth having
at all.

### Coupling to remove (as of `000f63c3`)

| Module | Imports that cross the boundary | What to do |
|---|---|---|
| `utils/grid.py` | subclasses flopy3 `StructuredGrid`/`VertexGrid`; imports `xugrid` at module level; `flopy4.adapters.read_binary_grid_file` (lazy) | Compute geometry from arrays (composition, not inheritance). Build a flopy3 `modelgrid` *from* it where flopy needs one. Make xugrid lazy. Move the GRB reader to D. |
| `utils/heads_reader.py`, `utils/cbc_reader.py` | `flopy.discretization`, `flopy4.adapters`, `xugrid` | Take grid geometry from the GRB (or a dataset), not a flopy grid. |
| `utils/time.py` | `flopy.discretization.modeltime` | Replace with a small time-coordinate builder from perlen/nstp/tsmult (+ start date). |
| `period_lists.py` | `item`, `item_table`, `flopy4.spec` | Split: the encoder (`ItemTable` → sparse table) stays in flopy, and densify/sparsify on tables moves to C. |
| `period_arrays.py` | `_types` (`TimeArraySeriesRef`), `constants` | Constants move with it. TAS refs are already coordinates (`<name>_tas`, #489), so dense code shouldn't need the type. |
| `netcdf.py` | `Model`, `Package`, `spec`, pydantic `NetCDFModel` | Split: "walk the model and pick fields" stays in flopy, and "write a representation dataset in MF6 NetCDF form" moves to D. |
| `vertical.py`, `crs.py`, `accessor.py` | none | Already clean. |
| `attrs_xarray.py` (A1) | lazy `flopy4.mf6._types.TimeArraySeriesRef`, `flopy4.mf6.constants.FILL_DNODATA`; `flopy4.spec` references; `fill_forward`/`fk` metadata | Move these into hooks registered from `flopy4.mf6` (see "xattree"). |
| `dimensions.py` (A1) | `modflow_devtools.dfns.dim_value`; `flopy4.spec.is_reference` | Keep `DerivedDim` and DFN expressions in flopy; the generic part is a small resolver. |

## The representation

The contract from decision 3, specified in
`docs/dev/xarray-representation.md`: grid dims and coordinates, the tree
and type tags, period data as given (dense and flat are views), time, and
attributes and fill values. Export plan phase 1 makes `to_xarray` produce
it and settles the spec's open points as it goes.

## Files and adapters

Each is a pair of functions (representation ↔ file or object) plus
accessor methods. None changes the representation. The spec's first
section has the full picture; in short:

- **MF6 NetCDF (grouped):** the representation as is, through
  `DataTree.to_netcdf`/`to_zarr`, with only the encoding netCDF needs.
  Lossless. MF6 doesn't read it yet.
- **MF6 NetCDF (ungrouped), structured and layered mesh:** what
  `netcdf.py` writes today, restated as a fixed flattening of the grouped
  layout, aiming to be valid CF and UGRID. Readers reverse it and, while
  coverage is partial, merge in the fields that come from text input. CF
  bounds come with it (`rotated-grid-index-plan.md` Next 3).
- **Adapters:** `to_ugrid()`/`from_ugrid()` (xugrid, DISV and layered
  DIS), `to_rioxarray()` (structured grids; rioxarray takes a rotated
  affine transform but its 1-D x/y assume no rotation, so check this),
  `to_cf()` (cf_xarray), `to_modelgrid()` (flopy3, replacing the
  inheritance in `utils/grid.py`, step 4). Names are placeholders.
- **Binary output** (GRB/HDS/CBC): readers that produce the
  representation directly.

The format is ours to change too. The spec's "What the format could
change" lists candidates. The first thing to settle is the flattening
rule for a whole simulation, chiefly how dims are prefixed or shared
across models.

## xugrid

- **Optional, behind the UGRID adapter and DISV selection**, not in the core
  representation. A `UgridDataset` is a wrapper type, not an `xr.Dataset`:
  it doesn't nest in a `DataTree`, and our registered accessors don't reach
  it. That conflicts with the export plan's "packages give a Dataset,
  contexts a DataTree".
- **The `xugrid` branch** (May 2026, `b00d7a05`, merge-base `52daeeb0`)
  returns xugrid objects from `to_xarray`. Don't merge it as is. Its useful
  parts (dropping hand-written UGRID attrs, keeping CF bounds) go into the
  UGRID adapter and the ungrouped mesh writer instead.
- **DISV selection** (`rotated-grid-index-plan.md` Next 1): output readers
  return `UgridDataArray` today. For the representation, prefer a plain
  dataset with an index (an `NDPointIndex` for nearest, or our own
  containment index, maybe the `combined-index-notes.md` design). Use
  `to_ugrid()` for anything xugrid does better (regridding, plotting).
- **Watch xugrid #35 / PR #373** (custom indexes instead of wrapper types).
  If it lands, DISV could be "plain dataset plus xugrid's index", and the
  wrapper concern goes away.
- **The pin** (`xugrid==0.15.3` in `pyproject.toml`) needs a range anyway
  before flopy4 can go into flopy. Making it optional is a bigger
  step; do it once grid.py no longer imports it at module level.

## xattree

[xattree #36][x36] proposes rewriting xattree as a functional conversion
layer: explicit `to_datatree()`/`from_datatree()`, protocols instead of
inheritance, a normal object lifecycle, pure translation functions. It
would keep the spec system, the field factories (`dim`, `coord`, `array`)
and dimension inheritance, and drop the imposter dict/list classes,
`bind_tree()` and `init_tree()`.

**flopy4 has mostly built this already** since dropping xattree (#356,
#359):

| #36 asks for | flopy4 today |
|---|---|
| pure `to_datatree`/`from_datatree` | `attrs_to_dataset`, `dataset_to_attrs`, `attrs_to_datatree`, `datatree_to_attrs` in `flopy4/attrs_xarray.py` |
| a `DataTreeConvertible` protocol | `flopy4/protocols.py`, same name |
| dimension inheritance | `flopy4/dimensions.py`: `DimensionProvider`/`DimensionResolver` protocols, `DerivedDim` |
| dims tagged on fields | `shape` metadata from `flopy4.mf6.spec.array()` |
| no imposter containers, no `__dict__` swapping | gone |

So xattree v2 would start from `attrs_xarray.py` and the generic part of
`dimensions.py`. Little of the current xattree code carries over beyond
the field factory names.

**What isn't generic yet** (see "Coupling to remove"): period-array
stacking along `<name>_period` (keyed off `fill_forward`), the
`<name>_name` aux dim (`fk` + `fill_forward`), `TimeArraySeriesRef` and
`FILL_DNODATA`, references stored by name, the reserved names `dims`,
`parent` and `_parent`, and DFN dimension expressions.

**Design: a converter with hooks**, like cattrs (which flopy already uses
in `converter/`):

- hooks keyed by a predicate on the field, each a pair (value →
  `DataArray`, `DataArray` → value);
- a policy for which fields are children (tree nodes) and which are leaves;
- a policy for excluded fields (instead of hard-coded reserved names);
- a fallback dim naming (`<name>_dim<i>`) when a field has no `shape`.

flopy4 registers the MF6 hooks (period arrays, TAS refs, fill values,
references). xattree doesn't set naming conventions. The representation
spec does that, through flopy's field metadata and hooks.

**Pipeline:** object → xattree (with flopy's hooks) → a raw `DataTree` that
follows the representation spec → the package (indexes, `dense()`,
encodings).

**Dimension inheritance may be partly native now.** `DataTree` inherits
coordinates from parent nodes, which xattree used to do by hand. That
covers dims once a tree exists. Resolving dims before conversion (shape
checks, scalar expansion) still needs something at the object level. xattree
v2 may only need a small pure `resolve_dims(obj, ancestors)`, not the
provider/resolver protocols. Check this before extracting.

**Payoff and risks:**

- The code is about 400 lines, so extraction won't shrink flopy much. The
  main payoff is the boundary: a generic core makes the MF6 parts explicit
  as hooks, and that's the same discipline the package needs. Reuse outside
  flopy is secondary.
- **attrs vs pydantic.** #367 is stale but open. An attrs-only xattree
  locks in attrs. attrs, dataclasses and pydantic dataclasses all expose
  fields with metadata, so a thin field-introspection layer could keep the
  choice open. Better still, settle #367 first.
- **Repo home.** flopy would depend on a personal repo. Before flopy
  depends on xattree, consider moving it to MODFLOW-ORG, as with the package.

## Steps inside flopy4

Roughly in order. Each is small and fits the existing plans. None needs a
new repo.

1. **Finish the representation spec** (`docs/dev/xarray-representation.md`,
   drafted) as part of export plan phase 1, settling its open points (bool
   encoding, type tags, the float fill value).
2. **Rename the accessor** from `.grid` to something distinctive (e.g.
   `.mf6`) before more users depend on it. `.grid` is generic enough to
   collide (xugrid uses `.ugrid`, uxarray `.uxgrid`). Do it with export plan
   phase 2, which adds `dense()` to it anyway.
3. **One subpackage for jobs B–D**, e.g. `flopy4/mf6/xr/` (or top-level
   `flopy4/xr/`). Move the modules as they're touched rather than in one
   sweep. Add an import-linter contract forbidding imports from
   `flopy4.mf6.{component,package,context,model,simulation,item,item_table}`
   and `flopy4.spec`, so the boundary holds while it's one repo.
4. **Drop the flopy3 grid inheritance** (`utils/grid.py`), and replace
   `utils/time.py`'s use of flopy3's `ModelTime`. This is the biggest piece.
   It's also needed for moving flopy4 into flopy, which shouldn't depend
   on flopy3's discretization classes.
5. **Split `netcdf.py` and `period_lists.py`** along the encode/densify line
   above.
6. **Lazy xugrid** everywhere in the subpackage, then decide whether it's
   an optional dependency.
7. **Update `docs/dev/sdd.md`** ("Xarray conversion", "NetCDF") to describe
   the representation, the two MF6 NetCDF layouts, the adapters, and the
   boundary. The current "NetCDF" section ("adopt xugrid ... `.to_netcdf()`
   through the appropriate accessor") is close to right, except that xugrid
   is one adapter, not the writer.
8. **Make `attrs_xarray.py` generic** as part of export plan phase 1, which
   already says to "make the generic layer complete". Add an import-linter
   contract so `flopy4.attrs_xarray`, `flopy4.protocols` and the generic
   part of `dimensions` can't import `flopy4.mf6`. Then move the period,
   TAS, fill-value and reference handling into hooks registered from
   `flopy4.mf6`. Worth doing even if xattree v2 never happens.

## When to extract

All of:

- the spec has been stable for a release or two (no schema changes in
  export or period-list work),
- the import-linter contract is green and the subpackage imports neither
  flopy3 nor flopy4's object model,
- someone outside flopy wants it: an output-only user, imod, xmipy, a GUI,
- flopy4 is in flopy, so the third repo isn't
  on top of the devtools release coordination already blocking that.

Until then, a subpackage with an enforced boundary gets most of the benefit.

**xattree v2** is a separate decision with its own criteria: the A1
linter contract is green, the hook API has gone unchanged for a while,
and #367 is settled. Then rewrite xattree around the module, close #36
with it, and have flopy depend on it. This is independent of the package's
timing.

## Coordination

- **imod-python** already builds MF6 on xarray/xugrid and reads GRB/HDS/CBC
  into xarray. Before creating a package, ask Deltares whether the grid,
  encoding and output layer could be shared, or at least whether we can
  agree on the representation so datasets move between the tools. Don't
  contact anyone without asking.
- **MF6 NetCDF format**: the spec's format notes, as an issue or discussion on
  modflow6, once checked against the source. First confirm the intent:
  is the ungrouped layout meant to cover the whole simulation, and would
  MF6 ever read a grouped one? Don't post without asking.
- **xugrid**: follow #35 / #373. Report DISV edge-tie behaviour if it
  differs from DIS (`rotated-grid-index-plan.md` Next 1).
- **xattree**: ours, so no outside coordination, apart from where it lives
  (personal repo vs MODFLOW-ORG). Note in #36 that flopy4's `attrs_xarray.py`
  is the prototype, when there's something to point at. Don't post without
  asking.

## Open

- The flattening rule for a whole simulation in the ungrouped layout:
  how dims are prefixed or shared across models (see the format notes).
- Default layout per writer: ungrouped for model input and tool-facing
  output, grouped when saving a whole simulation from flopy? Users should
  only ever have to pick the layout.
- Adapter names and which ones to have (`to_ugrid`, `to_rioxarray`,
  `to_cf`, `to_modelgrid`). The format names are settled: MF6 NetCDF
  (grouped) and MF6 NetCDF (ungrouped).
- Package name, and whether the subpackage is `flopy4/xr/` or `flopy4/mf6/xr/`.
- Accessor name, and with it the names in export plan phase 2b, decided
  together: `flatten()`/`unflatten()` or something else, and whether the
  flat dim is `node` (DISU's) or `nodes` (the DFN fallback, which should
  then use the same name).
- Whether the time code (TDIS → time coordinate, TAS evaluation) is part of
  the package or stays in flopy. Leaning package, since output readers need
  it too.
- Does the package know DFNs (for variable metadata, long names, units)?
  Prefer not: the writers take the metadata from attrs that flopy puts on
  the representation, and devtools stays a flopy dependency only.
- Representation for DIS2D/DISV2D/DISV1D (OLF/CHF).
- When to get this branch's docs onto develop: now, as plans, or with
  export phase 1.
- attrs vs pydantic (#367): whether xattree v2 is attrs-only or works with
  any dataclass-like.
- Whether xattree v2 keeps the field factories (`dim`, `coord`, `array`)
  or just reads metadata that flopy's own `spec` functions set.
- Where xattree lives: personal repo or MODFLOW-ORG.
