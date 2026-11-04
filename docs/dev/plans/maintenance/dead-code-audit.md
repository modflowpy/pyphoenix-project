# Dead code audit (develop @ 5ac2af7a)

Audit of `flopy4/` on `develop` after #505. Generated component modules
(`gwf/`, `gwt/`, `gwe/`, `prt/`, `olf/`, `chf/`, `exg/`, `utl/`) were left out.
Line numbers are as of `5ac2af7a`; re-check before editing.

Status re-checked at `febcfd51`: sections 1, 3 and 4 are done (section 1
finished in #528). Section 2's deletions are merged (#530); the rest of it,
and the gaps found along the way, are in #531 (open). Section 5 is
untouched.

Method: a reference scan (every function/class in `flopy4/` with no reference
elsewhere in `flopy4/`, counting `.lark` grammars and `.jinja` templates,
ignoring self-references, comments and `__all__` entries) plus ruff
`F401,F811,F841,ERA001,B018`. Every hit was checked by hand.

Each item below is meant to be one session / one small PR. Per
`CLAUDE.local.md`, verify with `pixi run -e dev smoke` plus the test files
touched.

## 1. Remove unused modules and functions

- [x] **`flopy4/mf6/indexes.py`** (done in #510): delete the whole module (`alias`,
  `MetaIndex`, `grid_index`, `time_index`). Nothing imports it, tests
  included. Last touched in #291.
- [x] **`flopy4/dimensions.py:263-343`**: delete `validate_dimension_resolution`.
  It only calls itself; no callers in source, tests, docs or benchmarks.
  (Resolved differently in #528: fixed, not deleted.
  It read `metadata["dims"]`, which nothing sets (arrays record `shape`), so
  it always returned `[]`, and it recursed through `_parent`. It now checks
  that each array field's shape resolves, and `Simulation.write` runs it
  first. List shapes are left out: their counts are the package's own
  dimension fields.)
- [x] **`flopy4/dimensions.py:69`**: delete the `DimensionResolver` protocol.
  It's only mentioned in the docstring of `validate_dimension_resolution`.
  (`DimensionProvider` and `DimensionResolverMixin` are used; keep them.)
  (Resolved differently in #528: kept as the consumer-side contract next
  to `DimensionProvider`. The mixin's `hasattr(parent, "resolve_dims")`
  checks became `isinstance(parent, DimensionResolver)`.)
- [x] **`flopy4/adapters.py:268`**: delete `get_nn` and its `__all__` entry.
  Nothing calls it. (Resolved differently in #510: moved to
  `flopy4/mf6/utils/grid.py`, vectorized with numpy, and tested. Kept.)
- [x] **`flopy4/mf6/codec/reader/transformer/typed.py:227`** (done in #509): delete
  `TypedTransformer.simple_string`. No grammar rule (hand-written or
  generated) has that name, so Lark never calls it.

## 2. flopy3 adapter cleanup (`flopy4/mf6/adapters.py`)

- [x] **`:420-431`**: delete `Flopy3ListData`. (Resolved differently in
  #531: implemented, not deleted. It was the
  placeholder for a real gap: flopy3's plotting and export read boundary
  conditions through `DataListInterface`, and the adapter never gave them
  any. It now wraps stress period data, and `Flopy3Model.version` is
  "mf6" so `plot_bc` works. The plan's 3.x item 2, a neutral protocol in
  flopy3, may make it unnecessary after the merge.)
- [x] **`:77-91`** (`Flopy3Model.__init__`): unused `lenuni`/`xoff`/`yoff`/
  `angrot`. Deleted in #530: every `to_grid()`
  already passes the origin, rotation, length units and crs. `_to_numpy`,
  used only there, went too.
- [x] **`:337-345`**: the commented-out `DataType` enum. Deleted in #530.

Keep the `Flopy3Model` properties that look unused (`model_ws`, `exe_name`,
`hdry`, `hnoflo`, `get_package`, ...). They exist for flopy3's
export and plot code, which duck-types these objects.

Found along the way:
- [x] Fixed in #531:
  - `crs=` was ignored.
  - Only `dis` models got a grid. GWF's `dis` already covers Disv/Disu;
    OLF/CHF (`dis2d`/`disv2d`/`disv1d`) got none, and a model with `dis`
    unset failed.
  - Models and packages had no `to_geodataframe`.
  - `get_package` never matched.
  - `name` was a string, not a list.
  - An unset `boundname` column was exported as NaN.
- [ ] Lists besides stress period data (`packagedata`, `connectiondata`)
  aren't wrapped, which flopy3's SFR/LAK/MAW/UZF `plot_bc` reads. Left for
  later, or for the plan's neutral protocol (3.x item 2); #531's
  description says why.
- [x] Array fields holding a scalar (a constant, e.g. `Ic(strt=5.0)`, or a
  default like Npf's `k`) were skipped by `Flopy3Package`. Now filled to
  their shape, also in #531.

## 3. Unused constants and config, plus a test that never runs

- [x] **`flopy4/mf6/constants.py`** (done in #509): delete `FILL_DEFAULT`, `FILL_INT32`,
  `LENBOUNDNAME`. Never referenced.
- [x] **`flopy4/mf6/config.py`** (done in #509): `SPARSE_THRESHOLD` isn't read by any
  library code. The only reader is
  `TestSparseArrays.test_sparse_array_creation`
  (`test/test_converter_structure.py:205`), whose body is gated on
  `nper * nodes (1e6) > SPARSE_THRESHOLD (1e7)` and so never runs. The test
  passes without testing anything. Delete the test class and `config.py`
  (the module holds only this constant and a TODO).

## 4. Small leftovers

- [x] **`flopy4/mf6/codec/writer/__init__.py:22`** (done in #509): drop the
  `_JINJA_ENV.filters["is_constant"]` registration. No template uses it.
  Keep the function; `layer_is_constant` in `writer/filters.py` calls it.
- [x] **`flopy4/mf6/utils/grid.py:180`, `:933`** (done in #509): unused local `nlay`
  (ruff F841) in the scalar-`botm` broadcasting branches.

## 5. Decision needed: test-only attrs/xarray layer

Only `test/test_attrs_xarray.py` uses these; nothing in `flopy4/mf6` does:

- `flopy4/mixins.py` (`DatasetConvertibleMixin`, `DataTreeConvertibleMixin`)
- `flopy4/protocols.py` (`DatasetConvertible`, `DataTreeConvertible`)
- the dataset→object half of `flopy4/attrs_xarray.py`: `dataset_to_attrs`
  (`:266`), `datatree_to_attrs` (`:370`), `_leaf_kwargs_from_dataset`
  (`:251`), `_init_field_names` (`:244`), `_period_value` (`:181`)

The object→dataset half (`attrs_to_dataset`, `attrs_to_datatree`,
`child_field_candidates`, `_child_field_spec`) **is** used by `mf6` and
codegen; keep it.

Correction: `test/mf6/test_mf6_period_arrays.py` also round-trips real
`Welg`/`Rcha` through `dataset_to_attrs`. Comparison and design options are
in [`export.md`](../xarray/export.md); nothing gets deleted until those decisions are made.

- [ ] Decide whether this is the planned generic conversion layer (keep it,
  maybe wire `mf6` to it) or leftover from before xattree was dropped (#356)
  (delete it along with the matching tests).

## Not dead (for reference, so later sessions don't re-flag them)

- **Lark callbacks:** `BasicTransformer.TOKEN`/`CNAME`/`INT`/`QUOTED_WORD`/
  `NUMBERS`/`RECORDS`, `TypedTransformer.block_kw_word`/`single_array`/
  `layered_array`, `_BufferLexerThread.from_custom_input` (called by
  Lark's `LexerThread` machinery).
- **pydantic `field_validator`s** in `flopy4/mf6/netcdf.py`.
- **xarray hooks:** `CellIndex.roll`/`concat`/`isel` in `utils/grid.py`, and
  the `grid` accessors in `accessor.py` (registered when `flopy4.mf6`
  imports it).
- **Import hook:** `_StagedFinder.find_spec` in `_sync.py`.
- **Overrides and public API:** `StructuredGridWrapper.from_binary_grid_file`
  (overrides flopy's), `IODescriptor.list_formats` (public, but no tests;
  maybe add one).
- **Public, tested only by tests:** `component.get_fnames`,
  `utils.grid.dims_from_grb`, `Package.from_xarray`, `NetCDFModel.from_model`.
- **Side effect on purpose:** `self._children` alone on a line at
  `simulation_methods.py:56` names any unnamed models.
- **Generated aliases** like `TdisPerioddata` and `WelStressPeriodData`: public
  API from codegen.
- **ruff ERA001 false positives** in `converter/egress/unstructure.py:305,316,329`:
  comments describing types.
