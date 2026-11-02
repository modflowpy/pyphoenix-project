# xarray export plan

Follows up dead-code audit item 5 (`dead-code-audit.md`). Status: design
**decided** (2026-11-02), implementation not started. Nothing in `mixins.py`,
`protocols.py` or the reverse half of `attrs_xarray.py` gets deleted, and
no tests get dropped, except as the phases below say.

Scratch scripts used for the comparison (rerun them to see current
behavior):
`/private/tmp/claude-502/-Users-wbonelli-dev-pyphoenix-project/3ec4ddc6-e42e-49eb-bc12-ce39a377ee2c/scratchpad/compare.py` and
`/private/tmp/claude-502/-Users-wbonelli-dev-pyphoenix-project/3ec4ddc6-e42e-49eb-bc12-ce39a377ee2c/scratchpad/compare2.py`.
They build a 1x4x5 DIS GWF model (NPF, IC, CHD, WEL, RCHA, OC, IMS, TDIS)
and print `pkg.to_xarray()` next to `attrs_to_dataset(pkg)`, plus both
round trips.

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
   the docs must say which is which.
6. **Keep `protocols.py`; put the methods on `Package`/`Context` directly;
   delete `mixins.py`.** The protocols are cheap, the SDD describes them,
   and `isinstance(x, DataTreeConvertible)` is useful. The mixins are
   two-line forwarders that sit awkwardly in the hierarchy (`Context`
   subclasses `Component`). The reverse functions in `attrs_xarray.py`
   stay and get finished.

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

### Already fixed (uncommitted on `develop`)

`Package.to_dataarray` (and so the view) raised on structured DIS
(reshaping `delr`/`delc` onto the grid) and on any scalar griddata field
given before the package knew its grid (NPF's default `icelltype`,
`Ic(strt=10.0)` attached later). The fix fills constants to the field's
shape (a 0-d array if the shape is unknown). Arrays not on the cells get
one dim per shape name, via `_AXIS_DIMS` (`ncol` → `col`, `nrow` → `row`).
Tests: `test_to_xarray_constants_attached_later` and
`test_dis_to_xarray_axis_arrays` in `test/mf6/test_mf6_component.py`.
Should go in as its own small PR before phase 1.

## Phases

Each phase is roughly one PR. Per `CLAUDE.local.md`, verify with
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
  `to_xarray` example in `docs/dev/sdd.md`, and the tests in
  `test/mf6/test_mf6_period_lists.py` and `test/mf6/test_mf6_component.py`
  that use `to_xarray` options or expect the view's shape. Check
  `flopy4/mf6/adapters.py` (it calls `attrs_to_dataset` directly) still
  gets what it needs.

### Phase 3: wiring and cleanup

- `Context.from_xarray(tree)` classmethod (`datatree_to_attrs`), with
  parents and dims rebinding through the normal constructors.
- `Package` satisfies `DatasetConvertible`, and `Context` satisfies
  `DataTreeConvertible` (`flopy4/protocols.py`). Align the protocol
  method names with what's implemented (`from_xarray` vs
  `from_dataset`/`from_datatree`). Add `isinstance` checks to the tests.
- Delete `flopy4/mixins.py`, and move the `Leaf`/`Node` tests in
  `test/test_attrs_xarray.py` off the mixins onto the plain functions.
- Update `docs/dev/sdd.md` ("Xarray conversion") to describe the complete
  export, the accessor view, and how both differ from MF6 NetCDF input.
- Close audit item 5 in `dead-code-audit.md`, pointing here.

## Still open (decide during implementation)

- Bool encoding in netCDF attrs: int8 + a flag, or a convention.
- Type tag values: the DFN component name (`gwf-npf`) or the class path.
- Whether the old instance `from_xarray` survives in any form (phase 2).
- Whether `dense()` lives on DataArray too, or only on Dataset.
