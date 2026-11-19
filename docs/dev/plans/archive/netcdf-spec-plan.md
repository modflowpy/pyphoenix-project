# NetCDF spec: what belongs in devtools, what stays in flopy4

## Background

flopy4 currently has two independent object models:

1. **The MF6 input object model** — `Package`/`Component` and friends
   (`flopy4/mf6/{component,package,item,record,row}.py`), attrs-based,
   generated from the DFN corpus via `flopy4/mf6/utils/codegen/{make,filters}.py`.
   This is what users construct/populate to build a simulation.
2. **The MF6 NetCDF I/O object model** — `NetCDFModel`/`NetCDFPackage`/
   `NetCDFParam` and friends (`flopy4/mf6/netcdf.py`, ~950 lines), pydantic
   (`BaseModel`)-based, hand-written directly in flopy4. This describes the
   structure of an MF6-conformant NetCDF file (dims, CF attribute
   conventions, per-package/per-param layout) and converts a live
   `Model`/`Package` into one.

This plan is about #2. It came out of a discussion (see issue #282,
"Consider switching attrs -> pydantic") about whether flopy4's *object
model* needs JSON Schema, and whether that's actually the right layer for
it. Conclusion there: JSON Schema earns its keep on artifacts meant for
external/cross-tool interop (a file format, an API payload) — not
necessarily on an in-memory object model whose job is ergonomic
construction. The DFN spec is exactly the former, and devtools already
treats it that way. NetCDF should follow the same split, but doesn't yet.

## The existing precedent: DFN spec in devtools

- The DFN corpus (what packages/blocks/fields exist, their types, dims,
  `pk`/`fk` relationships) lives in `modflow_devtools.dfns`, pydantic-native
  as of schema `2.0.0.dev3`.
- flopy4 consumes it at codegen time (`flopy4/mf6/utils/codegen/{make,filters}.py`)
  to generate the attrs-based `Package` subclasses under `flopy4/mf6/{gwf,gwt,gwe,prt,utl,exg}/`.
  The generated classes don't carry pydantic anywhere themselves — they're
  attrs, built from pydantic-described metadata.
- This migration ([`mf6-object-model-plan.md`](mf6-object-model-plan.md)'s Phase 0.6a) landed in
  `6cdfb2a` (2026-08-19). It already gets JSON Schema generation for the
  DFN spec for free (`model_json_schema()` on the devtools side) — this is
  what the issue's "free JSON schema" motivation was actually about,
  independent of whatever flopy4's own `Package`/`Component` classes are
  built on.
- Net effect: **spec lives in devtools (shared, versioned, machine-readable,
  schema-native); object model lives in flopy4 (whatever's ergonomic for
  construction)**. Two different concerns, two different owners.

## Current state of the NetCDF side

`flopy4/mf6/netcdf.py` does *not* follow this split — it's simultaneously
the spec and the consumer, and it's the *only* machine-readable encoding of
the MF6 NetCDF format that exists anywhere:

- The actual spec is prose: the [MODFLOW 6 NetCDF format wiki
  page](https://github.com/MODFLOW-ORG/modflow6/wiki/MODFLOW-NetCDF-Format),
  owned by the modflow6 core team, referenced from `docs/dev/sdd.md`
  ("NetCDF" section). It is not structured or versioned anywhere.
- flopy4 hand-encodes that format as pydantic classes directly in
  `netcdf.py`: `NetCDFModel`, `NetCDFPackage`, `NetCDFParam`,
  `NetCDFModelAttrs`, `NetCDFParamAttrs`, `NetCDFParamEncodings`, all
  implementing an `NetCDFInput` ABC that requires `.jsonschema()` (→
  `self.model_json_schema()`) as a first-class method. The team already
  treats this as a spec-shaped artifact worth generating JSON Schema for —
  it just isn't anywhere but flopy4.
- Helper logic (`_cf_var_attrs`, `dimmap`) encodes MF6's own NetCDF
  conventions: CF `grid_mapping`/`coordinates`/`mesh` attrs, dimension name
  mapping (`layer`/`y`/`x`/`nmesh_face`) per structured vs. vertex grid.
  This is pure "what does a conformant file look like" — spec content, no
  flopy4-specific state involved.
- This is exercised, not aspirational: `docs/examples/{frenchman-flat,twri,circle}/netcdf_*`
  are real generated outputs.

One nuance vs. the DFN case: *which package fields are NetCDF-eligible* is
already spec-driven from devtools — dev3 DFN field objects carry a real
`netcdf` attribute (`flopy4/mf6/utils/codegen/filters.py:442-443`,
`getattr(f, "netcdf", False)`), which codegen threads into the generated
`Package` field's attrs metadata (`flopy4/mf6/spec.py:65-66`). `netcdf.py`'s
`_PackageSpec` (`netcdf.py:80-126`) then reads that metadata back off
`attrs.fields(cls)` to decide which fields become NetCDF variables and
what shape/dims they get. **So per-field eligibility is already correctly
sourced from devtools.** What's missing from devtools is the *container*
format — how a `NetCDFModel`/`NetCDFPackage`/`NetCDFParam` document is
structured, and the CF/dimension conventions that govern it.

## Where NetCDF differs from DFN (and why that matters)

DFN's devtools schema formalizes something MF6 already emits as structured
text — the `.dfn` files themselves — and went through `dev1`→`dev2`→`dev3`
revisions with devtools as the convergence point for multiple consumers.
The NetCDF format has no structured source anywhere yet; formalizing it in
devtools would be the *first* machine-readable encoding of a spec the
modflow6 core team owns via a wiki page. That raises the bar: this isn't
"port flopy4's existing hand-rolled classes into devtools unilaterally," it's
"get the modflow6 core team (the issue thread already names @mjreno as the
collaborator on this) to agree the schema is right, ideally formalizing the
wiki page's content in the process." Moving prematurely risks devtools
carrying a schema that's really just flopy4's private opinion, dressed up
as shared infrastructure.

## Recommended phased plan

**Phase A — now: stay in flopy4, treat `netcdf.py` as the working
prototype.** No structural change yet. This mirrors how DFN's own schema
lived and iterated inside consumer-adjacent code before devtools' dev3
stabilized it. Keep building out NetCDF support here while the mjreno
collaboration and the format itself are still evolving.

**Phase B — trigger: format stabilizes + core-team alignment.** Split
`netcdf.py` into:

- A pure structural/spec module → new devtools module (e.g.
  `modflow_devtools.netcdf`), pydantic, versioned the way `dfns` is
  (`dev1`/`dev2`/... or plain semver — team call). Candidates for the move:
  `NetCDFModelAttrs`, `NetCDFParamAttrs`, `NetCDFParamEncodings`, the shape
  of `NetCDFModel`/`NetCDFPackage`/`NetCDFParam` themselves, `_cf_var_attrs`,
  `dimmap`. This is the part that answers "what does a valid MF6 NetCDF
  file look like" — no flopy4 object touched anywhere in it.
- flopy4-side binding/consumption glue that **stays**, regardless of this
  split: `NetCDFModel.from_model()` (walks a live `Model`'s attrs `Package`
  fields via `_attrs.fields(type(package))`, reads `block`/`netcdf`/`shape`
  metadata, broadcasts scalars, builds the params list — this is
  application logic connecting flopy4's object model to the spec, not spec
  content itself), `_PackageSpec`/`get_spec`/`_pkgclass` (same reason —
  they read *flopy4's* `Package` classes), `to_dataset()`/`to_netcdf()`
  and the rest of flopy4's own xarray/dask I/O mechanics.

**Phase C — flopy4 imports the devtools spec classes** the same way
`netcdf.py`/`codegen/{make,filters}.py` already import
`modflow_devtools.dfns` today, and its own binding layer subclasses/wraps
them rather than re-declaring the structure.

## What stays in flopy4 either way

Regardless of timing, the following are flopy4-owned application concerns,
not spec, and don't move:

- Binding a live simulation's field values into NetCDF variables
  (`from_model()`, `_PackageSpec`).
- I/O mechanics: `to_xarray()`, `to_netcdf()`, dask/xarray laziness choices.
- Anything specific to *flopy4's* representation of a package/model (its
  attrs field metadata, its dimension-resolution machinery in
  `flopy4/dimensions.py`) — devtools has no reason to know flopy4 uses
  attrs (or, per issue #282, might later use pydantic) for its own object
  model.

## Open questions for the team

1. Who drives the devtools-side module — is this a joint effort with
   mjreno/the modflow6 core team, given they own the wiki-page spec it
   would formalize? Does formalizing it in devtools also mean updating or
   replacing the wiki page as the source of truth?
2. Versioning scheme: mirror `dfns`' `devN` convention, or start at a
   stable version since this is greenfield (no legacy consumers to keep
   compatible)?
3. Sequencing against other in-flight work: [`mf6-object-model-plan.md`](mf6-object-model-plan.md)
   Phase 0.6a step 3 (codec reader path still on legacy
   `modflow_devtools.dfn`) is still open, and any attrs→pydantic move for
   flopy4's own object model (issue #282) is a separate, orthogonal
   decision. Recommend not running all three architecture changes
   concurrently — DFN reader-path cleanup and this NetCDF split don't
   depend on each other, but reviewer/contributor bandwidth does.

## Non-goals

This plan doesn't take a position on attrs vs. pydantic for flopy4's own
`Package`/`Component` object model (issue #282) — that's independent. If
that migration happens, consuming devtools' (pydantic) NetCDF spec classes
from a pydantic-based flopy4 object model would be slightly more uniform,
but it isn't required: flopy4 already consumes pydantic-based DFN spec
classes into attrs objects today with no friction, and would do the same
here.
