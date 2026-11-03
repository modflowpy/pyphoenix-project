# xarray export plan

Status: design **decided** (2026-11-02), implementation not started. The
spec it builds to is [`representation.md`](representation.md); the direction
and the higher-level open questions are in
[`package.md`](package.md).

This started from a dead-code audit question: is the test-only half of
the attrs/xarray layer (`mixins.py`, `protocols.py`, `dataset_to_attrs`,
`datatree_to_attrs`) the planned generic conversion layer, or leftover
from before xattree was dropped (#356)? The answer is to keep it and
finish it. Nothing in `mixins.py`, `protocols.py` or the reverse half of
`attrs_xarray.py` gets deleted, and no tests get dropped, except as the
phases below say.

The comparison behind "Where things stand" used a 1x4x5 DIS GWF model
(NPF, IC, CHD, WEL, RCHA, OC, IMS, TDIS), printing `pkg.to_xarray()` next
to `attrs_to_dataset(pkg)`, plus both round trips. Phase 1's tests
replace it.

## Decisions

1. **`to_xarray()` is the complete, lossless export** on every component.
   Packages give an `xr.Dataset` and contexts (models, the simulation) an
   `xr.DataTree`. `from_xarray(to_xarray(x)) == x`.
2. **The analysis view moves to the `grid` xarray accessor**
   (`flopy4/mf6/accessor.py`), computed from the complete export:
   `pkg.to_xarray().grid.dense(sparse=, duplicates=, grid=)`. It is no
   longer a second export path on the package.
3. **Grid dims and coordinates** in the complete export (`layer,row,col` /
   `layer,cell` / `node`, with x/y/z), falling back to DFN dims (`nodes`,
   `ncpl`, ...) when the grid doesn't resolve. A package looks the same
   whether you ask it or pull it out of a model's tree.
4. **Period arrays as given**, along `<name>_period`, as `attrs_xarray`
   does now. Filling forward is the accessor's job.
5. **The complete export is writable to netCDF.** It is distinct from
   MF6's NetCDF input format (`flopy4/mf6/netcdf.py`, `NetCDFModel`), and
   the docs must say which is which. [`representation.md`](representation.md)
   does: this is MF6 NetCDF (grouped), and `netcdf.py` writes MF6 NetCDF
   (ungrouped), a flattening of the same representation.
6. **Keep `protocols.py`; put the methods on `Package`/`Context` directly;
   delete `mixins.py`.** The protocols are cheap, the SDD describes them,
   and `isinstance(x, DataTreeConvertible)` is useful. The mixins are
   two-line forwarders that sit awkwardly in the hierarchy (`Context`
   subclasses `Component`). The reverse functions in `attrs_xarray.py`
   stay and get finished.
7. **Both cell layouts, flat and layered, through the accessor.** The
   export is layered (decision 3): `layer,row,col` on DIS, `layer,cell`
   on DISV. `grid.flatten()` gives the flat `node` view, as on DISU, and
   `grid.unflatten()` goes back. This is plain `stack`/`unstack`, not a
   custom index. The old "index mapping nodes to layer/row/col" (#207, see
   [`rotated-grid-index.md`](rotated-grid-index.md)) was dropped in #469 and stays dropped.

## Where things stand

### What calls what today

| Class | `to_xarray()` today |
|---|---|
| `Package` with griddata, period arrays or a period list | the view (`package.py`, `Package.to_xarray`), with `sparse`/`duplicates`/`grid` options |
| `Package` with none of these (IMS, ...) | `Component.to_xarray` (`component.py`) = `attrs_to_dataset` + a child-griddata merge that never fires |
| `Tdis` | its own `kper` dataset (`tdis_methods.py`) |
| `Context` (`Model`, `Simulation`) | `attrs_to_datatree` (`context.py`), already the generic layer |
| `Simulation` | the above + Tdis's `kper` vars merged into the root (`simulation_methods.py`) |

`Package.from_xarray(ds)` is an *instance* method that sets stress period
data only, via `period_lists.from_dataset`. It accepts the dense and the
sparse forms.

### Gaps in the generic layer (`attrs_to_dataset` / `attrs_to_datatree`)

- **List data** (CHD, WEL, OC, ...) isn't encoded. `_stress_period_data`
  goes into attrs as a live `PeriodRows` object. `dataset_to_attrs` then
  raises `TypeError: unexpected keyword argument '_stress_period_data'`.
- **Item tables** (`Tdis.perioddata` as `ItemTable`) go into attrs as objects too.
- **Attrs aren't netCDF-safe**: `PosixPath`, `bool`, `ChildList`,
  `PeriodRows`, `ItemTable`.
- **Empty child lists** (`api`, `drn`, ... `[]`) leak into a model's attrs.
- **Tree nodes are named by field and index** (`models0`,
  `solutiongroup0`, `chd0`), not by component name.
- **`datatree_to_attrs(Simulation, tree)` doesn't recover concrete
  types.** It rebuilds `models` as the abstract `Model`, with no packages.
  Fields annotated with a base class or a union are never resolved to a
  concrete class.
- **No coordinates**, and arrays sit on flat DFN dims.
- **Tdis appears twice** in `sim.to_xarray()`: as root vars, and as `/tdis`.

### Already fixed (branch `to-xarray-constants`)

`Package.to_dataarray` (and so the view) raised on structured DIS
(reshaping `delr`/`delc` onto the grid) and on any scalar griddata field
given before the package knew its grid (NPF's default `icelltype`,
`Ic(strt=10.0)` attached later). The fix fills constants to the field's
shape (a 0-d array if the shape is unknown). Arrays not on the cells get
one dim per shape name, via `_AXIS_DIMS` (`ncol` → `col`, `nrow` → `row`).
Tests: `test_to_xarray_constants_attached_later` and
`test_dis_to_xarray_axis_arrays` in `test/mf6/test_mf6_component.py`.
Committed on local branch `to-xarray-constants` (`07679ca0`, off
develop `000f63c3`). Should go in as its own small PR before phase 1.

## Phases

Each phase is roughly one PR. Verify with
`pixi run -e dev smoke` plus the test files touched; CI runs the rest.

### Phase 1: make the generic layer complete (`flopy4/attrs_xarray.py`)

Keep `Package.to_xarray` as it is in this phase. Work on
`attrs_to_dataset` / `attrs_to_datatree` and their inverses, and test
them directly.

- **List fields** encode as the sparse table from
  `period_lists.to_dataset(pkg, sparse=True)`: a variable per column
  along an entry dim, with `per` and the cellid as coordinates. Decode
  through `period_lists.from_dataset`. Map the private field name to its
  init name (`_stress_period_data` → `stress_period_data`) both ways.
- **Item tables and other row lists** (`Tdis.perioddata`, OC's rows,
  `packagedata`/`connectiondata` in SFR/LAK/MAW/UZF): the same sparse
  treatment, one variable per column along a `<field>_row` dim. Check
  whether `period_lists` already has a helper for non-period lists before
  writing one.
- **NetCDF-safe attrs**: paths as str, bools as int8 with a flag in the
  variable/attr metadata (or a documented convention, decide during
  implementation), references as names (already the case), None
  omitted, empty child lists omitted. The decoder reverses each.
- **Coordinates and grid dims**: reshape cell arrays to the grid dims and
  add the cell-center/elevation coordinates. Share the code with
  `Package.to_dataarray` / `_with_cell_centers` rather than duplicating
  it. Keep DFN dims when the grid doesn't resolve. Record the grid sizes
  (`nlay`, `nrow`, `ncol`, ...) and `nper` in attrs so the accessor and
  the decoder have them.
- **Options and constants as given** ([`layout-logical-decisions.md`](../dfn-spec/layout-logical-decisions.md),
  "Track C"). Logical options are data or attrs on the node, layout
  options an encoding record (`encoding` or prefixed attrs, decide here),
  output options off the package's data. Write the Options section of
  the spec. A griddata constant stays a constant in the complete export
  (0-d, marked), so `from_xarray` gives the constant back; only `dense()`
  expands it. The `to-xarray-constants` fix is for the view.
- **Tree nodes**: named by the component's name. Every node carries a
  type tag (e.g. `attrs["type"] = "gwf-npf"`, matching the namefile
  ftype convention if that's simpler) so the decoder can pick the concrete
  class for `list[Model]` and union fields. The tag replaces positional
  `f"{field}{i}"` lookup in `datatree_to_attrs`. Check how dict-kind child
  fields fit (the module docstring says they can't round-trip today).
- **Tests**: extend `test/test_attrs_xarray.py` with round trips on real
  components: a list package (CHD with boundnames and aux), OC, TDIS, a
  whole simulation (`datatree_to_attrs(Simulation, attrs_to_datatree(sim))
  == sim`, with concrete model and package types), and
  `to_netcdf` → `open_dataset`/`open_datatree` → rebuild. The existing
  synthetic `Leaf`/`Node` tests stay until phase 3, and the `Welg`/`Rcha`
  round trips in `test/mf6/test_mf6_period_arrays.py` stay.

### Phase 2: the `grid.dense()` accessor, and repoint `to_xarray`

- Add `dense(sparse=False, duplicates="raise", grid=False)` to the `grid`
  accessor (`flopy4/mf6/accessor.py`) on Dataset (and DataArray where it
  makes sense). It:
  - densifies list tables onto the grid with the `duplicates` policy
    (`period_lists`' existing logic),
  - fills period arrays forward over `nper`,
  - is a no-op on arrays already on the grid.

  With `sparse=True` it returns the list table as is (the current
  `to_xarray(sparse=True)`). It needs only what phase 1 puts in the
  dataset. If it needs the package or the grid object, phase 1 is
  missing something.
- Add the inverse, `grid.sparse()` (dense list variables back to a
  table), or have `from_xarray` accept the dense form. Pick the one that
  keeps `period_lists.from_dataset`'s current dense support working with
  the least code.
- `Package.to_xarray()` becomes the complete export (`attrs_to_dataset`);
  `Package.from_xarray` becomes a classmethod rebuilding the package
  (`dataset_to_attrs`). The old instance method's "set spd from a
  dataset" use moves to `Pkg.from_xarray(ds)` plus attaching, or to a
  small helper. Decide during implementation, and check the editing
  workflow in `docs/examples/period-data.py`.
- `Tdis.to_xarray`'s derived `kper` dataset (`perlen`/`nstp`/`tsmult`,
  Timestamp `start_date_time`): it goes, unless the accessor or the time
  API (`Simulation.time`) needs it. Then `Simulation.to_xarray`'s Tdis
  merge goes too.
- Delete `Component._collect_child_griddata_datasets` and the merge in
  `Component.to_xarray`.
- **Update callers**: `docs/examples/period-data.py` (+ the `.ipynb`), the
  `to_xarray` example in [`sdd.md`](../../sdd.md), and the tests in
  `test/mf6/test_mf6_period_lists.py` and `test/mf6/test_mf6_component.py`
  that use `to_xarray` options or expect the view's shape. Check
  `flopy4/mf6/adapters.py` (it calls `attrs_to_dataset` directly) still
  gets what it needs.

### Phase 2b: flat and layered cell layouts on the `grid` accessor

Decision 7. Both methods go on the `grid` accessor next to `dense()`,
work on Dataset and DataArray, and compose with it
(`ds.grid.dense().grid.flatten()`).

How this fits [`package.md`](package.md):

- `flatten()`/`unflatten()` are views, like `dense()`. They belong to the
  package side (grid and data semantics), use only what's in the
  dataset, and never change the representation. Writing a flat view to
  netCDF is a CF matter (compression by gathering, below), not a new
  format.
- `.grid` is the current accessor name. The package plan (step 2)
  renames it to something distinctive before more users depend on it, so
  rename these with it.
- A cf_xarray dependency (for `compress`, below) would be the package's,
  and optional.

- **`grid.flatten(dim="node")`**: `stack(node=("layer", "row", "col"))` on
  DIS, `stack(node=("layer", "cell"))` on DISV. Layer is slowest, so
  position `i` along `node` is MF6 user node `i + 1`, as in the flat DFN
  shape packages store internally (`Package.to_dataarray` reshapes from
  it). Variables without all the cell dims (DIS `delr`/`delc`, RCHA's
  one-layer arrays, list tables) are left as they are. A no-op on DISU
  and on arrays already flat.
- **`grid.unflatten(dim="node")`**: `unstack` when `node` carries the
  MultiIndex from `flatten()`. Without one (a flat array from somewhere
  else, or the export's DFN-dim fallback on `nodes`), reshape using the
  grid sizes phase 1 records in attrs (`nlay`, `nrow`, `ncol`/`ncpl`),
  and raise if they're missing or don't multiply out to the length.
- **Coordinates through the round trip**: per-cell coords (`z`,
  `z_top`, `z_bot`; `x`/`y` on DISV) stack along with the data. `x`/`y`
  on DIS are 1-D on `col`/`row` and carry a `CellIndex`. Find out what
  `stack` does with them. If they're dropped or lose the index, the flat
  view broadcasts them to `node` as plain coords, and `unflatten()`
  restores the 1-D form and re-runs `index_xy`. Containment `sel(x=, y=)`
  is a layered-view feature; on the flat view, use `.grid.sel` (see open
  questions).
- **netCDF**: xarray can't write a MultiIndex. The flat view is for
  analysis; the complete export (decision 5) stays layered. If a flat
  dataset needs writing, `flatten()` could take `index=False` to keep
  `layer`/`row`/`col` as plain coords on `node`, which `unflatten()` can
  still read. CF compression by gathering is the standard way to write
  it (see prior art below).
- **Not reduced nodes.** `node` here means user nodes (every cell).
  Budget output on reduced nodes (active cells only) is a different
  layout; leave it out of these methods, and don't name it `node`.
- **Tests**: `flatten().unflatten()` is the identity on a DIS and a DISV
  package export, on a period array (with `per`), and on a dense list
  variable. Flat values match the package's internal flat arrays.
  `unflatten()` from attrs alone. `CellIndex` comes back after the round
  trip. DISU is a no-op.

#### Prior art: xugrid, uxarray, CF

We checked what the established libraries do, so that where we differ
we do it on purpose. Sources: xugrid 0.15.3 (installed in the pixi env,
read from source), uxarray `main` (read from source on GitHub), and the
CF conventions.

| | xugrid | uxarray | Phase 2b |
|---|---|---|---|
| Entry point | `UgridDataArray.from_structured2d(da)` | `UxDataset.from_structured(ds)` | `.grid.flatten()` |
| Dims flattened | `(y, x)` only | `(lat, lon)` only | `(layer, row, col)` / `(layer, cell)` |
| Layer / vertical | kept as its own dim | kept as its own dim | folded into `node` |
| How | `da.stack({face_dim: (y, x)}, create_index=False)`, no MultiIndex | `ds.stack(n_face=[lat, lon])`, MultiIndex | `stack`, MultiIndex by default (open) |
| Order | row-major (y slowest) | row-major (lat slowest) | layer slowest, then row-major (MF6 order) |
| Way back | none by index; `rasterize`/`rasterize_like` regrid geometrically (lossy) | none | `unflatten()`, exact |
| Flat dim name | mesh-prefixed, e.g. `mesh2d_nFaces` | `n_face` | `node` |

Where we match:

- **Cell order.** Row-major within a layer, as in both libraries.
- **DISV layered view.** `(layer, cell)` is the UGRID layered-mesh shape:
  a 2-D mesh with a separate layer dim. Both libraries use it, and so
  does MF6's own netCDF mesh export (`head_l1`, `head_l2`, … on
  `nmesh_face`).

Where we depart, and what to do about it:

1. **Folding layer into `node`.** Neither library does this. It's still
   right for MF6, which numbers nodes in 3-D, and DISU uses that
   numbering. Keep it, and say so in the docstring. Also consider a
   horizontal-only flatten (`flatten(layers=False)` or similar):
   `(layer, row, col)` → `(layer, cell)`. That is xugrid's convention
   exactly, and it puts DIS data in the same shape as DISV. Both writers
   need this step for layered DIS anyway, so write it once and
   use it in both places (the UGRID adapter and the ungrouped mesh
   layout).
2. **MultiIndex by default.** The libraries disagree. xugrid skips it,
   which keeps the result netCDF-writable; uxarray keeps it. This leans
   toward no MultiIndex by default (`index=False`), or at least making
   the no-index form fully supported, including by `unflatten()`.
3. **Inverse.** Neither library has an exact index-based inverse.
   `unflatten()` is our addition. That's fine, but don't confuse it with
   xugrid's `rasterize`, which resamples.
4. **Dim naming inside flopy4.** The output readers
   (`flopy4/mf6/utils/heads_reader.py`, `cbc_reader.py`) already return
   DISV heads and budgets as xugrid objects on
   `(time, layer, nmesh_face)`, while the export uses `(layer, cell)`.
   That mismatch is within flopy4, independent of the libraries. The
   package plan settles it: readers produce the representation directly
   and xugrid objects only come from the UGRID adapter (`to_ugrid()`).
   So the readers move to `cell`, and `nmesh_face` is a UGRID adapter
   detail.

**netCDF for the flat view: CF "compression by gathering"** (CF §8.2).
This is the established encoding for a stacked dim. The flat dim is
written as an integer coordinate holding each cell's flattened index,
with a `compress = "layer row col"` attribute naming the dims it was
gathered from. cf_xarray implements both directions
(`cf_xarray.encode_multi_index_as_compress` and
`decode_compress_to_multi_index`), and its docs show a netCDF round
trip. That answers the netCDF bullet above: a flat dataset can be
written in a standard form, not only as plain coords. It also fits
reduced (active-only) budget nodes, since dropping always-missing cells
is what the convention was designed for. If reduced nodes are handled
later, use this encoding there too. cf_xarray isn't in the env.
Depend on it, or write the encoding ourselves (it's small: compute
`np.ravel_multi_index` on the way out, `np.unravel_index` on the way
back).

References:

- xugrid: `xugrid/core/wrap.py` (`from_structured2d`),
  `xugrid/core/dataarray_accessor.py` (`rasterize`, `rasterize_like`)
- uxarray: [`_map_dims_to_ugrid`](https://github.com/UXARRAY/uxarray/blob/main/uxarray/io/utils.py),
  [`Grid` API](https://uxarray.readthedocs.io/en/stable/generated/uxarray.Grid.html)
- CF: [§8.2 Compression by gathering](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.2/build/ch08s02.html)
- cf_xarray: [`encode_multi_index_as_compress`](https://cf-xarray.readthedocs.io/en/latest/generated/cf_xarray.encode_multi_index_as_compress.html),
  [`decode_compress_to_multi_index`](https://cf-xarray.readthedocs.io/en/latest/generated/cf_xarray.decode_compress_to_multi_index.html)

### Phase 3: wiring and cleanup

- `Context.from_xarray(tree)` classmethod (`datatree_to_attrs`), with
  parents and dims rebinding through the normal constructors.
- `Package` satisfies `DatasetConvertible`, and `Context` satisfies
  `DataTreeConvertible` (`flopy4/protocols.py`). Align the protocol
  method names with what's implemented (`from_xarray` vs
  `from_dataset`/`from_datatree`). Add `isinstance` checks to the tests.
- Delete `flopy4/mixins.py`, and move the `Leaf`/`Node` tests in
  `test/test_attrs_xarray.py` off the mixins onto the plain functions.
- Update [`sdd.md`](../../sdd.md) ("Xarray conversion") to describe the complete
  export, the accessor view, and how both differ from MF6 NetCDF input.
- Close the dead-code audit question (above): the layer was kept and finished.

## Still open (decide during implementation)

- Bool encoding in netCDF attrs: int8 + a flag, or a convention.
- Type tag values: the DFN component name (`gwf-npf`) or the class path.
- Whether the old instance `from_xarray` survives in any form (phase 2).
- Whether `dense()` lives on DataArray too, or only on Dataset.
- Names (`flatten()`/`unflatten()`, `node` vs `nodes`) are decided with
  the accessor name; see [`package.md`](package.md) "Open".
- Whether `.grid.sel(layer=, row=, col=)` and `.grid.sel(x=, y=)` should
  work on the flat view (map to `node` positions), or require
  `unflatten()` first.
- Whether `flatten()` keeps the MultiIndex by default (`sel(layer=0)`
  works on the flat view) or leaves plain coords (netCDF-safe). Prior
  art leans toward plain coords (xugrid's choice).
- Whether to add a horizontal-only flatten (`(layer, row, col)` →
  `(layer, cell)`), matching xugrid/UGRID layered meshes.
- netCDF for flat data: CF `compress` encoding via cf_xarray (new
  dependency) or our own small implementation.
- Cell dim name across export and output readers: leaning `cell` for
  both, with `nmesh_face` only in the UGRID adapter (departure 4).
