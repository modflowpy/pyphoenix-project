# dask1 branch: scope and status

**Branch:** `dask1`
**Base:** `develop`
**Preceded by:** `docs/dev/storage_strategy.md`, `docs/dev/implementation_plan.md`

---

## 1. Why this branch exists

The flopy4 codegen was producing `@xattree(kw_only=True)` decorated package classes. xattree intercepts every `__setattr__` to immediately wrap arrays in `xr.DataArray`. That design has three structural consequences that block large-scale simulation support:

1. **Dask arrays cannot be held at rest.** The setattr hook consumes them on assignment.
2. **List fields lose their row structure.** A DFN `recarray` field (`cellid elev cond`) was expanded into parallel per-column NDArray attrs fields; a `__period_col_maps__` ClassVar was needed to reassemble rows downstream.
3. **Packages cannot be constructed outside a model tree.** xattree resolves shape expressions (`nlay`, `nodes`) by walking the parent tree at setattr time.

The goal of dask1 is to replace `@xattree` with `@attrs.define` in the codegen output — making generated package classes numpy/recarray-first, constructable in isolation, and capable of holding dask-backed arrays without interception. xarray, xugrid, and pandas become explicit on-demand views (`to_dataarray()`, `to_xarray()`, `to_dataframe()`) rather than implicit primary storage.

This is the prerequisite for chunked out-of-core loading of large MODFLOW 6 simulations.

---

## 2. What was planned (from implementation_plan.md)

The original plan had four phases:

| Phase | Planned deliverable | What was actually done |
|---|---|---|
| 1 | Codegen template + filters: emit `@attrs.define` + recarray/ndarray fields | Complete; all 64 packages migrated at once rather than incrementally |
| 2 | `_PackageLean` mixin: `to_dataarray(field, grid)`, `to_xarray(grid)`, `to_ugrid(grid)` | Methods on `Package` base class instead (no mixin); `grid` arg replaced by `resolve_dims()`; `to_ugrid()` not implemented |
| 3 | Codec alignment: ingress reads into `dict[int, np.recarray]`; egress iterates recarray rows | Complete for packages covered by tests |
| 4 | Chunked loading: `load(chunks=)` classmethod on NPF and similar griddata packages | Complete for all griddata packages via `Package.load(path, dims, chunks)`; G/A period packages deferred |

The plan targeted IC, NPF, and DRN as initial validation packages, with all others migrated incrementally using a `use_new_codegen` flag. In practice, all 64 packages were migrated in a single pass.

---

## 3. What was actually done

### 3.1 Scope expanded to all packages

Rather than incrementally migrating three packages, all 64 generated package files were migrated to codegen v2 simultaneously. `use_new_codegen=True` is now the default for all packages that are not in the explicit skip set (`gwf-dis`, `gwf-disv`, `gwf-tdis`, hand-managed files).

### 3.2 Generated class interface (Phase 1 — complete)

Every generated package file now:

- Uses `@attrs.define(kw_only=True, slots=False)` instead of `@xattree(kw_only=True)`
- Stores all field metadata in passive `attrs.field(metadata={"dfn_block": ..., "dfn_type": ..., ...})` dicts, readable by the codec without calling into xattree
- Stores stress period data as `_stress_period_data: Optional[dict[int, np.recarray]]` (a single field, not per-column expansion)
- Stores non-period list blocks (packagedata, connectiondata, etc.) as `Optional[np.recarray]`
- Declares `__period_schema__` and per-block `__xxx_schema__` ClassVars that describe column names, roles, and types
- Emits no `__period_col_maps__` or per-column period fields

### 3.3 Post-init and view methods (Phase 2 — complete, diverged from plan)

The plan proposed a `_PackageLean` mixin (with `to_dataarray(field, grid)` and a `utils/array_views.py` helper) that migrated packages would inherit alongside `Package`. The actual implementation diverged in three ways:

- Methods went on `Package` itself (no mixin, no `utils/array_views.py`), making them available to all subclasses without inheritance changes in the template.
- The `grid` argument was dropped; `self.resolve_dims("nlay", "nrow", "ncol", "ncpl", "nodes")` replaces it, working via the parent chain or a pre-populated `_dimension_cache`.
- `to_ugrid()` (listed in the plan) was not implemented; `xugrid` integration is deferred.

The template emits (for packages with period or block schemas):

- `__attrs_post_init__`: builds `period_dtype` and per-block dtypes from schema ClassVars; coerces user-supplied list/dict input to recarrays; auto-fills `maxbound` from SPD; detects vertex grids for `ncelldim`
- `stress_period_data` property + setter: thin wrapper over `_stress_period_data`
- `to_dataframe()`: converts `_stress_period_data` to a tidy pandas DataFrame on demand

`to_dataarray(field_name)` and `to_xarray()` live on the `Package` base class (see §3.10).

The `_DTYPE_MAP` ClassVar (string type name → numpy dtype) is also emitted per-class and is identical across all generated files (candidate for base class, discussed in §9).

`Package` (the base class in `flopy4/mf6/package.py`) also defines a `__attrs_post_init__` that handles griddata field broadcasting — expanding scalar defaults like `icelltype=0` to `np.full((N,), 0)` when `dims` is supplied. Simple packages with no schemas (IC, NPF, OC) inherit this without generating their own override. Packages with schemas generate their own `__attrs_post_init__` (for dtype construction) and end it with `super().__attrs_post_init__()` to chain up.

### 3.4 Runtime fixes applied during branch work

Several issues were found and fixed while running the full test suite for the first time:

- **xattree name registration** (`flopy4/mf6/package.py`): xattree's `_init_tree` defaults the `name` field to `cls.__name__.lower()`, which for `Package` is `'package'`. Codegen v2 subclasses inherited this default, so children registered under `'package'` in the parent DataTree instead of `'ic'`/`'npf'`/etc. Fixed in `Package.__attrs_post_init__`: if `self.__dict__["name"] == "package"`, override with `type(self).__name__.lower()` before xattree pops it.

- **`_compute_ncelldim()`** (`flopy4/mf6/package.py`): List packages need `ncelldim` (2 for DISV vertex, 3 for structured) to build cellid dtypes. The original inline logic (`"ncpl" in dims and "nrow" not in dims`) defaulted to 3 when `dims={}`, even for packages attached to a DISV parent. Fixed by adding `Package._compute_ncelldim()`, which checks `dims` first, then walks `parent.dis` type if needed. All 25+ generated list packages and the Jinja template were updated to call `self._compute_ncelldim()`.

- **`_dimension_cache` lazy property** (`flopy4/mf6/dimensions.py`): `DimensionResolverMixin.__attrs_post_init__` initialised `_dimension_cache` as an instance attribute, but `Package.__attrs_post_init__` did not chain `super()` at that point, so the attribute was never set. Converted to a lazy `@property` that initialises from `__dict__` on first access, bypassing the call-chain dependency.

- **OC stop-sentinel + fill-forward interaction** (`flopy4/mf6/converter/egress/unstructure.py`): When `save_budget={1: ""}` (stop sentinel) forced an empty `BEGIN PERIOD 2` block to be emitted, MF6 reset *all* OC settings for that period — including `save_head` set via `"*"` wildcard that should persist. Fixed by tracking `ff_state` (fill-forward active values per field) while building `oc_period`; when a stop-sentinel kper is emitted, non-stopped fields are re-stated explicitly so the period block does not silently reset them.

- **`adapters.py` codegen v2 compatibility** (`flopy4/mf6/adapters.py`): `Flopy3Model.laytyp` was accessing `self._model.data["npf"].icelltype` (DataTree node, not the Package object). Fixed to `getattr(self._model, "npf", None).icelltype`. `Flopy3Package.has_stress_period_data` only checked `"nper" in self._data.dims` (xarray dims, always empty for codegen v2 packages). Fixed by storing `self._package` and checking `_stress_period_data` and attrs period-block fields directly.

### 3.5 Codec alignment (Phase 3 — complete for packages covered by tests)

**Ingress** (`flopy4/mf6/converter/ingress/structure.py`):
- `_structure_codegen_v2` identifies new-codegen packages by `dfn_block` metadata presence
- Reads all option/dimension/griddata fields by name from the structured parse tree
- Reads period blocks into `dict[int, list[tuple]]` keyed by 0-based kper
- Handles OC-style per-field period dicts
- Inner-class option records (e.g. `Cvoptions`, `Rewet`, `Xt3doptions`) are resolved via a `_inner_class_type()` lookup that maps `_keyword` to the correct field, then calls `Record.from_tokens()` on the row

**Egress** (`flopy4/mf6/converter/egress/unstructure.py`):
- `_unstructure_codegen_v2` dispatches on `dfn_block` metadata per field
- OC-style period dicts: emitted per explicit kper with no fill-forward (each field only emitted for periods where it is explicitly set)
- Recarray period data: rows emitted in MF6 list format per period block
- READARRAY period data (G/A variants: Chdg, Drng, Welg, Rcha): emitted as layered or flat `CONSTANT`/`INTERNAL` arrays per period; periods where every cell is `FILL_DNODATA` (3e30) are omitted so MF6 fill-forwards the previous period rather than reading 3e30 as real data
- Path fields: resolved to `(KEYWORD FILEOUT|FILEIN path)` tuples
- Inner-class records: `to_tokens()` via attrs introspection
- Integer griddata fields (e.g. `icelltype=0`) are correctly written as `CONSTANT 0` (not `CONSTANT 0.00000000e+00`) because `_wrap_array` preserves Python `int` dtype when wrapping scalar defaults

### 3.6 Record base class for inner classes

Inner-class record types (e.g. `Ims.Rclose`, `Npf.Cvoptions`, `Gwf_oc.Headprint`) all inherit from `Record` (`flopy4/mf6/record.py`), which provides a two-pass `from_tokens()` classmethod. This eliminated ~680 lines of inlined `from_tokens()` duplicated across generated files and the Jinja template.

### 3.7 Ruff and mypy compliance

All hand-written files pass ruff with 0 errors. 9 E501 errors remain in generated files — all `attrs.field()` definitions where a long type annotation (e.g. `Optional[InterpolationMethod]`) combined with the field name pushes the declaration line past 100 chars. Fixing these requires either threading a `prefix_len` hint through `_ml_field()` (so it can decide to wrap even single-kwarg calls) or adding a `ruff format` post-processing step to codegen. Both are deferred.

All 64 generated files have no `# ruff: noqa: E501`. `attrs.field()` calls are multi-line with hardcoded class-body indentation; schema ClassVars are multi-line; the template body has no long lines. The `field_call()` function in `filters.py` and `_ml_field()` helper in `make.py` produce correctly indented multi-line strings that render verbatim through Jinja's `trim_blocks=True` environment.

Both `flopy4` and `test` pass mypy with 0 errors. Key suppressions applied: `# type: ignore[override]` on `Package.load()` (incompatible signature with `Component.load()`), `# type: ignore[arg-type]` on `attrs.fields(type(self))` calls (mypy does not infer `Package` as `AttrsInstance`), `# type: ignore[name-defined]` on `to_dataframe()` return annotations (pandas not imported at module level), and bare lambdas replacing `attrs.Converter(lambda …)` wrappers in the template (mypy-attrs does not support the `Converter` class).

### 3.8 Profiling infrastructure extended

`docs/profile/_timer.py` was extended with:
- `profile_memory(fn, label)`: single-run `tracemalloc` peak-heap measurement (Python-managed allocations; native-heap requires memray)
- `sweep_chunks(fn_factory, chunk_sizes, ...)`: benchmarks a callable across a list of dask chunk sizes
- `time_reads` alias of `time_writes` for semantic clarity in read scripts

`docs/profile/run_all.py` now includes `ff_read.py` in its script list and accepts `--memory` to pass through to sub-scripts.

`docs/profile/ff_read.py` is a new read-time profiling script covering lazy open, first-timestep compute, full compute, and chunk-size sweep variants for both HDS and CBC outputs from the frenchman-flat model.

### 3.9 Chunked loading (Phase 4 — complete for griddata packages)

`Package.load(path, dims, chunks)` is implemented as a classmethod on `Package` and inherited by all codegen v2 subclasses:

- `dims`: optional dict of grid dimensions (required for griddata packages; omitted for list-input packages)
- `chunks=None`: eager numpy arrays
- `chunks="auto"`: one dask chunk per layer (griddata fields only)
- `chunks=int`: approximate chunk size in elements

`dims_from_grb(grb_path)` in `utils/grid.py` resolves a dims dict from a binary grid file, enabling any package to load from a model workspace without manually constructing the dims dict:

```python
dims = dims_from_grb(grb_path)
npf = Npf.load(npf_path, dims=dims, chunks="auto")
ic  = Ic.load(ic_path, dims=dims)
```

Returns `{"nlay", "nrow", "ncol", "nodes"}` for DIS grids and `{"nlay", "ncpl", "nodes"}` for DISV grids.

`_wrap_array` in `converter/egress/unstructure.py` computes dask arrays at serialization time, enabling text-format round-trips without a pre-existing binary file.

`Package.load()` also pre-populates `_pkg._dimension_cache` with the supplied dims so that `to_xarray()` / `to_dataarray()` work correctly on standalone packages (not attached to a parent model).

17 tests in `test/test_chunked.py` cover eager load, chunked load, laziness, and text round-trip write.

### 3.10 to_xarray / to_dataarray — moved to Package base class

`to_xarray()` and `to_dataarray(field_name)` are implemented on `Package` and inherited by all codegen v2 subclasses. They are no longer template-generated.

- `npf.to_dataarray("k")` → `xr.DataArray` for a single griddata field, shaped by `resolve_dims()`.
- `npf.to_xarray()` → `xr.Dataset` of all set griddata (or period-array) fields; tries `"griddata"` block first, then `"period"` (for G/A packages), then falls through to `super().to_xarray()`.

The `super()` fall-through means the base-class implementation is safe for all Package subclasses, including `Tdis` and other non-griddata packages that route through `Component.to_xarray()`.

Works in two modes:
1. **Attached to model:** `gwf.npf.to_xarray()` → `resolve_dims()` traverses parent chain to `gwf.dis.get_dims()`
2. **Standalone (Package.load):** dims pre-populated in `_dimension_cache` by `Package.load()`

`Context.to_xarray()` is overridden to walk children, identify codegen v2 packages with griddata fields, call each child's `to_xarray()`, and merge results into the DataTree (see §9.2).

4 new tests in `test_mf6_component.py` cover standalone dims, parent-chain dims, and dask laziness through `to_dataarray()`.

---

## 4. Current state

### Test results (as of 2026-06-18)

Full suite run: `PATH=/home/mreon/.clone/usgs/modflow6/bin:$PATH pytest test -k "not test_init_big_sim"` — **619 passed, 36 skipped, 0 failed**.

**Ruff:** 9 E501 errors in generated files only (see §3.7). All hand-written files clean.

**Mypy:** 0 errors in `flopy4` and `test` (132 source files + 23 test files checked).

| Test file | Passed | Skipped | Notes |
|---|---|---|---|
| `test/test_mf6_codec.py` | 93 | 0 | All fixed as of 2026-06-17 |
| `test/test_mf6_integration.py` | ~90 | 2 | RCHA, EVTA readarray-period write path |
| `test/test_mf6_component.py` | varies | 4 | 2 unrelated TODOs; 2 for `to_dict()` (xattree_asdict misses attrs fields) |
| `test/test_converter_structure.py` | 30 | 5 | Wildcard Chd, old scalar-period Rch, DataFrame round-trip |
| `test/test_dataframe_api.py` | 6 | 22 | DataFrame setter not implemented; G/A old API |
| `test/test_examples.py` | 4 | 0 | circle, quickstart, frenchman-flat, twri; NetCDF sections guarded by `MF6_EXTENDED` env var |
| `test/test_mf6_adapters.py` | varies | 0 | laytyp and has_stress_period_data fixed for codegen v2 |
| `test/test_netcdf_cf_conventions.py` | varies | 2 | osgeo.gdal not in env |
| `test/test_chunked.py` | 17 | 0 | eager + chunked load, Package.load() classmethod, dims_from_grb, round-trip write |

### What is not committed

All dask1 work in this branch is uncommitted. A commit requires explicit instruction. Key changed files:

- `flopy4/mf6/utils/codegen/filters.py` — `field_call()` multi-line, `_python_repr` filter
- `flopy4/mf6/utils/codegen/make.py` — `_ml_field()`, `_python_repr()`, `Record` import injection
- `flopy4/mf6/utils/codegen/templates/package.py.jinja` — full codegen v2 template
- `flopy4/mf6/converter/ingress/structure.py` — `_structure_codegen_v2`, inner-class lookup
- `flopy4/mf6/converter/egress/unstructure.py` — `_unstructure_codegen_v2`, OC no-fill-forward, FILL_DNODATA skip, `_wrap_array` int/dask handling
- `flopy4/mf6/package.py` — base `__attrs_post_init__` + `load()` classmethod; `_compute_ncelldim()`
- `flopy4/mf6/component.py` — `Component.to_xarray()` docstring documents the xattree DataTree gap
- `flopy4/mf6/context.py` — `Context.to_xarray()` overridden to merge codegen v2 griddata children into DataTree
- `flopy4/mf6/utils/grid.py` — `dims_from_grb()` added; `utils/loaders.py` deleted
- `flopy4/mf6/netcdf.py` — `_CodegenV2Spec` non-layered READARRAY shape fix (`ncpl` vs `nodes`)
- `docs/examples/*.py` — updated to codegen v2 constructor API; quickstart uses assignment style for single-instance packages
- `docs/profile/_timer.py`, `run_all.py`, `ff_read.py`, `test_profile_scripts.py` — profiling extensions
- `test/test_chunked.py` — 17 tests for eager/chunked load, `Package.load()` classmethod, `dims_from_grb`, round-trip write
- All 64 generated package files — regenerated from the above

---

## 5. Known gaps

### 5.1 `to_ugrid()` not implemented

The implementation plan listed `to_ugrid(grid) -> xu.UgridDataset` as part of Phase 2. It was not implemented. `xugrid` integration is deferred; the clean path would be a thin wrapper over `to_xarray()` once xugrid supports `xr.Dataset` input directly.

### 5.2 Skipped test gaps

- **RCHA/CHDG (readarray-period, 3 tests):** G/A variant packages use `READARRAY` format for period data — a full-grid array per period rather than a recarray list. The codegen v2 unstructurer handles the write path for these packages (including FILL_DNODATA skipping), but the round-trip codec tests (`test_rcha_period_aux_dump`, `test_rcha_period_double_aux_dump`, `test_chdg_period_aux_dump`) exercise a named-array-block path not yet implemented.
- **PRT-PRP (1 test):** Period release fields use `all_/first/last` dicts in the test; the API changed to `stress_period_data`. Test needs rewriting to match the new PRP period schema.

### 5.3 Advanced packages not validated end-to-end

LAK, SFR, UZF, MAW, and similar packages have jagged `connectiondata` schemas or partial-update period semantics that require additional codegen work. They are generated with the codegen v2 template and their schemas are structurally correct, but they have not been exercised in a full MF6 write-run-compare test. LAK in particular has 4 separate block schemas (`packagedata`, `connectiondata`, `tables`, `outlets`) plus a keystring period schema.

### 5.4 ~~Single-instance package attachment via assignment style~~ (resolved)

**Resolved.** The xattree name registration bug (see §3.4) was the root cause: `Package.__name__.lower()` → `'package'` caused all codegen v2 children to register under the same key. After fixing `__attrs_post_init__` to substitute the concrete class name, `parent=gwf` works correctly for single-instance packages (IC, NPF, OC, STO, DIS). The assignment-style workaround documented in the examples is no longer required, though it still works.

---

## 6. What is not in scope for dask1

### xattree removal from model-level classes

`Component`, `Model`, `Context`, `Gwf`, `Gwt`, `Gwe`, `Prt`, `Simulation`, `Tdis`, `Exchange`, and the `Dis`/`Disv` discretization packages all remain `@xattree` decorated. xattree provides the parent-child tree mechanism (`children`, `parent`), the `MutableMapping` interface on `Component`, xarray DataTree integration (`.data.dataset`), and the `field()`/`dim()`/`array()` type system used by the hand-written packages.

Removing xattree from these classes requires replacing all of the above — a separate architectural milestone, not a task within dask1. The codegen v2 packages inherit from `Package` which is still `@xattree`, but the `@attrs.define` decorator on the subclass takes MRO precedence and suppresses xattree's `__setattr__` hook on those classes.

### ~~Phase 4: chunked loading~~ (complete for griddata packages)

`Package.load(path, dims, chunks)` is implemented as a classmethod on `Package` and inherited by all codegen v2 subclasses. Passing `chunks="auto"` produces dask-backed arrays, one chunk per layer. `dims_from_grb(grb_path)` in `utils/grid.py` resolves dims from a binary grid file for any package. The write path (`_wrap_array` in unstructure.py) computes dask arrays at serialization time, enabling text-format round-trips without an intermediate binary file. 17 tests in `test/test_chunked.py` cover eager load, chunked load, laziness, and write round-trip.

**Remaining for G/A period packages (Rcha, Chdg, etc.):** These packages have full-grid arrays per stress period (`dfn_block == "period"` with READARRAY format). Their data volume scales as `nodes × NPER` — potentially much larger than static griddata for long transient simulations. The current `Package.load()` skips non-griddata fields during dask conversion; period arrays are loaded eagerly. Design for this extension is deferred to a follow-on branch.

---

## 7. Broader direction

dask1 fits between the **Demo** milestone (hand-written packages, prove the concept) and **MVP** (all packages generated, codec functional) on the roadmap in `docs/dev/map.md`.

The architecture is converging on a two-tier structure:

```
Simulation / Model / Exchange     ← @xattree, tree management, DataTree integration
    └── Package subclasses        ← @attrs.define, recarray-first, codec-driven I/O
```

The integration between these two tiers now works for the full example suite. The xattree name registration bug that previously required assignment style for single-instance packages (see §5.3) is resolved. The branch is functionally complete for the scope defined in §3.

The main remaining items before merge readiness are the dead-code cleanup in §9.3 (removing the old codegen template branch and consolidating boilerplate into `Package`) and validation of the advanced packages listed in §5.2. The base-class de-duplication refactors and G/A period chunking are good candidates for a follow-on branch.

---

## 8. Key architectural decisions made on this branch

| Decision | Rationale |
|---|---|
| Recarray over DataFrame as primary period storage | Matches `MFTransientList.get_data()` in flopy 3; zero pandas dependency at rest |
| `object_` dtype for `time_series: true` columns | `float64` silently discards time series names; `object_` holds either float or string |
| No fill-forward in OC egress | Each OC field is only emitted for periods where it is explicitly set; fill-forward semantics belong in the MF6 solver, not in the Python API |
| `use_new_codegen=True` for all packages (not incremental) | The ingress/egress dispatch already keys on `dfn_block` metadata presence; a single regeneration was cleaner than maintaining two template paths long-term |
| `Record` base class for inner-class records | Eliminates ~680 lines of inlined `from_tokens()` across generated files; two-pass keyword+positional parsing handles the full range of MF6 inner-record syntax |
| `__period_schema__` / `__block_schemas__` as ClassVars | Schema drives dtype construction, ingress parsing, and egress column ordering from a single source of truth per class; no separate codec-side column maps needed |
| `Package.load()` on base class rather than per-class generation | The `load()` body is fully polymorphic via `cls` — no per-package variation. Keeping it in `Package` avoids ~55 lines of identical boilerplate per griddata file and makes it available to all subclasses (including future list-input packages). |
| `dims` optional in `Package.load()` | List-input packages (WEL, DRN, etc.) don't need grid dimensions; making `dims=None` default means `load()` can be called without dims for packages that don't need array broadcasting. |
| `_wrap_array` computes dask arrays before wrapping | When writing to MF6 text format, concrete values are needed to choose CONSTANT vs INTERNAL format. Dask arrays are computed at `_wrap_array` time so the writer's `array_how()` can make the right choice without needing a pre-existing external binary file. The large-model "write to OPEN/CLOSE" optimization is separate. |
| G/A period chunking deferred | `has_readarray_period` packages (Rcha, Chdg, etc.) need spatial×temporal chunking — a more complex design than griddata chunking. Deferring avoids conflating the two loading models in Phase 4. |
| `to_xarray()` / `to_dataarray()` use `resolve_dims()` not `grid` arg | The old template emitted `to_xarray(self, grid)` / `to_dataarray(self, field_name, grid)` requiring a `StructuredGrid` or `VertexGrid` object. Package base class calls `self.resolve_dims("nlay", "nrow", "ncol", "ncpl", "nodes")` — works via parent chain (gwf→dis) or standalone via pre-populated `_dimension_cache` (Package.load() pre-populates it with supplied dims). |
| `Package.load()` pre-populates `_dimension_cache` | After `structure_component()` creates the package, `_pkg._dimension_cache.update(dims)` is called so that `to_xarray()` and `to_dataarray()` work on standalone packages (not attached to a model) via the cache path in `resolve_dims(dim_name)`. |
| `to_dataarray()` / `to_xarray()` on `Package` base class with `super()` fall-through | Methods try `"griddata"` fields first, then `"period"` fields (for G/A packages), then call `super().to_xarray()` for packages with neither. The fall-through means the implementation is safe for all Package subclasses — `Tdis` and other non-griddata packages route correctly through `Component.to_xarray()` rather than returning an empty Dataset. |
| `dims_from_grb()` in `utils/grid.py`, not a per-package wrapper | A single utility that extracts `nlay/nrow/ncol/nodes` from a binary grid file can serve any package via `Package.load(dims=dims_from_grb(grb))`. Per-package wrappers (formerly `load_npf()` in `utils/loaders.py`) duplicate the grb-parsing logic and scale poorly. |

---

## 9. Remaining work

### 9.1 Implementation gaps

**`to_dataframe()` setter (5 skipped in `test_dataframe_api.py`).**
`from_dataframe()` / the DataFrame setter path is not implemented for codegen v2 packages. The getter (`to_dataframe()`) works. The setter would round-trip a tidy DataFrame back into `_stress_period_data`.

### 9.2 xarray/DataTree support level and decoupling principle

**Design principle.** A core tenet of codegen v2 / dask1 is progressive decoupling from xattree. Where providing a capability requires introducing new coupling to xattree's internals (DataTree storage, `__setattr__` interception, or tree-init hooks), the preferred choice is to leave the gap and document it rather than add the coupling. New xattree coupling in the Package layer is not acceptable; new xattree coupling in the Context layer is tolerated only where Context is already `@xattree`-decorated and the coupling is pre-existing.

**What is supported (per-package `to_xarray()`).**
Codegen v2 packages expose two clean xarray views built entirely from attrs fields, with no xattree involvement:

- `npf.to_dataarray("k")` → `xr.DataArray` for a single griddata field, shaped by `resolve_dims()`.
- `npf.to_xarray()` → `xr.Dataset` of all set griddata fields.

Dim resolution (`resolve_dims`) walks the parent chain via xattree's DataTree parent pointer when dims are not cached. This is the only xattree touch-point in these methods and is a metadata lookup, not data storage; it would be replaced by a plain Python parent reference in a fully decoupled design.

**What is NOT supported (`package.data` for codegen v2 packages).**
`package.data` returns the xattree-managed `xr.DataTree` node. For codegen v2 packages, this DataTree's dataset is **empty** — griddata fields are stored in attrs `__dict__`, not in the DataTree. Providing `npf.data["k"]` would require a `Package.data` property that intercepts xattree's DataTree storage and enriches it on read. This was implemented and then reverted because it required:

1. Reading from xattree's private `__dict__["data"]` slot.
2. A per-instance recursion guard to handle xattree's tree-init code calling `getattr(self, "data")` during `_find_dimension_in_children`.
3. A setter that writes back into xattree's storage slot.

These are tight couplings to xattree internals. The current decision is to leave this gap. Use `npf.to_xarray()["k"]` in place of `npf.data["k"]`.

**What IS supported at the model level (`gwf.to_xarray()`).**
`Context.to_xarray()` is overridden to walk the context's children, identify codegen v2 packages with griddata fields, call each child's `to_xarray()` (the clean method), and merge the results into a deep copy of the DataTree. This fills the gap for `gwf.to_xarray()["npf"]["k"]`. The coupling is acceptable here because `Context` is already `@xattree`-decorated — the override uses `self.data` and `self.children` which are pre-existing xattree attributes on Context, and calls only the clean per-package `to_xarray()`.

**Future: `Package.to_datatree()` and full Context decoupling (next branch).**
The long-term path is:

1. Add `Package.to_datatree() -> xr.DataTree` as a thin, xattree-independent wrapper over `to_xarray()`. This method is trivial to implement and introduces no coupling.
2. When Context is decoupled from xattree (future branch), update `Context.to_xarray()` to assemble the DataTree from `child.to_datatree()` calls rather than patching into xattree's managed tree. At that point `package.data` can also be implemented cleanly as a property backed by `to_datatree()`, with no guards or internal-slot access.

`to_datatree()` is memory and compute efficient: `xr.DataTree` shares array references with the underlying `xr.Dataset` (no copies), lazy dask arrays remain deferred, and construction overhead is O(1) metadata work.

**Current test baseline (2026-06-17):** 619 passed, 36 skipped, 0 failed (excluding `test_init_big_sim` which uses the removed `Chd(head=...)` xattree API).

- 22 skipped in `test_dataframe_api.py` (DataFrame setter not implemented; G/A variant old xattree API)
- 5 skipped in `test_converter_structure.py` (wildcard Chd API, old scalar-period Rch, DataFrame round-trip)
- 4 skipped in `test_mf6_component.py` (2 unrelated TODOs; 2 for `to_dict()` which uses `xattree_asdict` and misses attrs fields)
- 2 skipped in `test_mf6_integration.py` (RCHA/EVTA array-period write path not yet implemented)
- 2 skipped in `test_netcdf_cf_conventions.py` (missing `osgeo.gdal`)
- 1 skipped in `test_mf6_adapters.py` (marked refactor)
- `docs/profile/ff_read.py` requires pre-built binary output files; its test in `test_profile_scripts.py` skips gracefully if they are absent but the chunk-sweep variants have not been exercised against real data

### 9.3 ~~Dead code and template cleanup~~ (done)

All items in this section have been completed:

- **~~Dead template branch.~~** Removed. Old `not spec.use_new_codegen` blocks (`__period_col_maps__`, `__block_col_maps__`, old `__attrs_post_init__`) deleted from template.
- **~~`_DTYPE_MAP` duplication.~~** ClassVar declaration removed from template; all 64 generated files now inherit from `Package._DTYPE_MAP` via MRO.
- **~~`__attrs_post_init__`, `to_dataframe()`, `stress_period_data` property/setter.~~** All moved to `Package` base class. `__attrs_post_init__` consolidated into `_init_schemas()` / `_init_block_dtype()` / `_init_period_dtype()` / `_broadcast_griddata()`. Template no longer emits any of these. ~3,200 lines eliminated across generated files.
- **~~`to_dataarray()` / `to_xarray()`.~~ (done previously)** Already on `Package` base class.
- **~~Tautology in aux-column injection.~~** Fixed: Jinja-time `{% if block_name == "packagedata" %}` conditional replaces the runtime string comparison.
- **Dead ingress code.** Removed `_list_block_col_info()`, `_parse_list_block_rows()`, `_parse_period_rows()` and dead list-block/period-block passes from `structure_component()` in `structure.py` (-246 lines).
- **Legacy xattree dispatch in Package.** Removed `_get_block()`, `_set_block()`, massive legacy `stress_period_data` getter (FILL_DNODATA iteration), legacy setter (`get_xatspec`/`structure_array`). `package.py` reduced from ~750 to 378 lines.

Template: 236 → 81 lines. Total generated code: ~9,700 → ~8,300 lines.

### 9.6 Dis/Disv/DisBase xattree decoupling (in progress)

Migrate gwf-dis, gwf-disv, and DisBase from `@xattree` to `@attrs.define(kw_only=True, slots=False)`. Replace `field()`/`dim()`/`array()`/`path()` descriptors with `attrs.field(metadata={"dfn_block": ...})`. Keep hand-managed methods (`get_dims()`, `to_grid()`, `from_grid()`, `write()` override). See `docs/dev/checkpoint6.md` for detailed plan.

### 9.4 Profiling enhancements for dask

The profiling infrastructure is partially extended (see §3.8). Phase 4 `load()` now exists, unlocking the dask-specific benchmarks. Remaining work:

- Add a `ff_read.py` variant that exercises `Npf.load(chunks=)` against the frenchman-flat model and compares chunk-sweep timing to the eager baseline.
- Add a `--memory` section to `ff_write.py` to measure peak heap during write under dask vs. numpy-backed arrays.
- Consider memray integration for native-heap measurement (NumPy/dask buffers allocated outside Python's allocator are invisible to `tracemalloc`).
- The `sweep_chunks` helper in `_timer.py` is wired up; validate against real dask arrays using the frenchman-flat model.

### 9.5 G/A period-array chunked loading (future branch)

Packages with `has_readarray_period=True` (Rcha, Chdg, Drng, Evta, Ghbg, Rivg, Welg) store full-grid arrays per stress period. Their data volume is `nodes × NPER`, which can far exceed static griddata for long transient simulations. The current `Package.load()` loads these period arrays eagerly. A future `load()` extension for these packages would need to:

- Accept a `chunks` parameter that applies to the `(nper, nodes)` shape
- Represent `_stress_period_data` as a dask array (or dict of dask arrays) rather than a dict of numpy recarrays
- Update the ingress path (`_structure_codegen_v2`) to populate dask arrays instead of numpy
- Update the egress path to write period blocks chunk-by-chunk (FILL_DNODATA skipping must be preserved)

This is a more complex change than griddata chunking because of the period-keyed data structure and FILL_DNODATA semantics. Defer to a follow-on branch.

---

## 10. Developer context

### 10.1 Project layout

```
flopy4/mf6/
├── package.py              # Package base class (codegen v2 packages inherit from this)
├── component.py            # Component base (xattree-decorated, provides write/to_xarray)
├── context.py              # Context (model-level, to_xarray override)
├── dimensions.py           # DimensionResolverMixin, DimensionProvider protocol
├── record.py               # Record base for inner-class records (from_tokens/to_tokens)
├── converter/
│   ├── ingress/structure.py   # Reads MF6 text → Python objects (structure_component, _structure_codegen_v2)
│   └── egress/unstructure.py  # Python objects → MF6 block dicts (unstructure_component, _unstructure_codegen_v2)
├── codec/
│   ├── reader.py           # Lark grammar parser (loads MF6 text → raw token dicts)
│   └── writer.py           # Block dicts → MF6 text (dumps)
├── utils/codegen/
│   ├── make.py             # build_component_spec, make_module — drives generation
│   ├── filters.py          # Jinja filters (field_call, py_type, python_repr)
│   ├── templates/package.py.jinja  # The template (81 lines)
│   └── dfn2py.py           # CLI entry, _SKIP set
├── gwf/, gwt/, gwe/, prt/, utl/, exg/  # Generated + hand-managed packages
└── spec.py                 # field(), dim(), array(), path() helpers (xattree-era, used by hand-managed files)
```

### 10.2 Codegen

- **Regenerate:** `.pixi/envs/dev/bin/python -m flopy4.cli mf6 sync MODFLOW-ORG/modflow6@develop --no-install --verbose`
- Or: `pixi run generate-classes`
- This downloads DFN files from modflow6 develop branch, regenerates all 64 packages that are (a) already on the filesystem and (b) not in the `_SKIP` set.
- `_SKIP` set (in `dfn2py.py`): `gwf-dis`, `gwf-disv`, `gwt-dis`, `gwe-dis`, `prt-dis`, `sim-tdis`, `utl-ncf`
- Generated files have `# autogenerated file, do not modify` as first line — codegen checks for this.
- **Do not manually edit generated files.** Change the template or `make.py`, then regenerate.

### 10.3 Running tests

```bash
# Full suite (excluding known-excluded old-API test):
pytest test -k "not test_init_big_sim"

# For NetCDF tests in examples (requires extended MF6 binary):
MF6_EXTENDED=1 pytest test

# MF6 binary location (already in PATH):
/home/mjreno/.clone/usgs/modflow6/bin/mf6
```

Baseline: 621 passed, 36 skipped, 0 failed.

### 10.4 DFN system and block patterns

DFN files define MODFLOW 6 component input structure. Key reference docs:
- https://github.com/mjreno/modflow-devtools/blob/develop/docs/md/dfnspec.md
- https://github.com/mjreno/modflow-devtools/blob/develop/docs/md/dfns.md

**Block patterns** (impact codegen and user API):

| Pattern | Example | Storage | Notes |
|---|---|---|---|
| Scalar (options/dimensions) | IC options, NPF options | `attrs.field(metadata={"dfn_block": "options"})` | Key-value pairs |
| Gridded array | NPF `k`, IC `strt` | `NDArray` field, `dfn_block="griddata"` | Shape from dims, layered |
| List (static recarray) | SSM `sources`, LAK `packagedata` | `np.recarray` field + `__*_schema__` ClassVar | Non-repeating block |
| Repeating list (stress) | CHD/WEL/DRN period | `dict[int, np.recarray]` via `_stress_period_data` | `maxbound` dimension, fill-forward |
| Repeating gridded array (G/A) | RCHA/CHDG period | Full-grid array per period | READARRAY format |
| Keystring union | LAK/LKT/LKE period | `role: "keystring"` in schema, `object_` dtype | Union of setting types per feature |
| Advanced partial-update | LAK/SFR/UZF/MAW | No `maxbound`, `shape: []` list | Period replaces per-feature, not full block |

**Package subtypes** (from DFN spec):
- `"stress"`: has `maxbound`, period block replaces all stresses per period
- `"advanced"`: no `maxbound`, partial-update period semantics, has internal continuity equation
- `"utility"`: cross-cutting (ts, obs, ncf)
- `null`: default (OC, etc.)

### 10.5 Architecture (two-tier)

```
Simulation / Model / Exchange     ← @xattree, tree management, DataTree integration
    └── Package subclasses        ← @attrs.define, recarray-first, codec-driven I/O
```

Codegen v2 packages inherit from `Package` (which is still `@xattree`-decorated for tree compatibility). The `@attrs.define` on the subclass takes MRO precedence and suppresses xattree's `__setattr__` hook.

### 10.6 Key design principles

1. **No new xattree dependencies.** Decouple progressively; don't add coupling.
2. **Schema-driven.** `__period_schema__` / `__*_schema__` ClassVars are the single source of truth for dtype construction, ingress parsing, and egress column ordering.
3. **Recarray-first.** Period data is `dict[int, np.recarray]`; pandas/xarray are on-demand views.
4. **Constructable in isolation.** Packages don't need a parent model to instantiate or load.
5. **Dask-compatible.** Griddata fields can hold dask arrays; `_wrap_array` computes at write time.

### 10.7 Linting and type checking

```bash
# Ruff (hand-written files only — .jinja is not Python):
ruff check flopy4/mf6/package.py flopy4/mf6/converter/ingress/structure.py flopy4/mf6/converter/egress/unstructure.py

# Mypy:
mypy flopy4 test
# 0 errors expected (3 pre-existing errors in flopy4/mf6/utils/tmp/ scratch files are ignored)
```
