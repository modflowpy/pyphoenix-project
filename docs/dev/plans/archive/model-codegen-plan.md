# Generate the model classes

Status: proposed (2026-10-06), against develop `82d2a99`.

Implemented (2026-10-06) on branch `model-codegen` (worktree
`../pyphoenix-models`), commit `29aeffa` off develop `7e4fdc9`, not pushed.
Differences from the plan:
- `Gwt` already had `dependent_variable_scaling`.
- Breaking changes beyond `_list`:
  - `Gwf.newton` is gone in favor of the DFN's `newtonoptions` record.
  - `Gwf.csub` is a single package; the DFN doesn't mark it `multi`.
  - `Gwf.api` is new.
- Package fields follow DFN (alphabetical) order, with `dis` first, and
  name-file rows are written in that order. The grid union is
  `Dis | Disu | Disv`.
- The netcdf options keep their names (`netcdf_mesh2d_file`, …) through
  a `_PY_NAMES` table. The DFN names would have given `nc_*_file`.
- `Gwf.output` is a property, so it's no longer an attrs field.
- Binding code (`_resolve_bindings`, `_make_binding_blocks`) now looks
  only at `child()` fields. Before, a record option on a model counted
  as a child.
- The unmatched-row warning fires only in blocks holding nothing but
  child fields. It doesn't check DFN ftypes.
- Model registration is unchanged.

## Problem

`Gwf`, `Gwt`, `Gwe` and `Prt` (`flopy4/mf6/{gwf,gwt,gwe,prt}/__init__.py`)
are hand-written and have drifted from the DFNs:

- `Gwt` has no `fmi` or `ist` field, and `Gwe` has no `fmi`. Loading drops
  their name-file rows without a warning. In `test205_gwtbuy-henrytidal`,
  FMI's `FLOW_IMBALANCE_CORRECTION` is lost. The round-trip test still
  passes because neither side has FMI.
- `Gwt.api` is `Api | None`, but the DFN says API can repeat.
- `Gwf` names its list option `_list`; the other models use `list_`.
- `Fmi` and `Ist` aren't exported from `flopy4.mf6.gwt` or `flopy4.mf6.gwe`.

The simulation (`sim-nam`) is already generated, with its behavior in the
`SimulationMethods` mixin. The models should be generated the same way.

## What the DFNs give

- **Options:** the `*-nam` DFN's options block.
- **Packages:** every component whose `parent` is the model's name file.
  gwt-nam has 19 children and gwe-nam has 17.
- **Repeating packages:** the `multi` flag. For GWT these are api, cnc, ist,
  lkt, mwt, sft, src and uzt.

## Rules

1. **Grid packages share a slot.** DIS, DISV and DISU become one field,
   `dis: Dis | Disv | Disu | None`. PRT has no DISU, so it gets
   `Dis | Disv | None`.
2. **Packages sharing a name-file type share a field.** Variants such as
   `chd`/`chdg` and `rch`/`rcha` become one field typed as their union, for
   example `chd: list[Chd | Chdg]`. This is what `_disambiguate_ga_variant`
   already handles at load time.
3. **One slot or a list.** A `multi` package becomes a list defaulting to
   empty; any other becomes `X | None`.
4. **Packages with no class are skipped.** That's GWT's MWT/SFT/UZT and
   GWE's MWE/SFE/UZE for now, using the same test as `_has_class`. They get
   fields once they're generated.
5. **Order and naming:** fields follow the DFN order: options, then
   packages. Each package field is named for its ftype (`npf`, `chd`), and
   the list option is `list_`, which is a breaking change for
   `Gwf(_list=...)`.

## Behavior that stays hand-written

These move into method-only mixins, as `DisMethods` did in #385:

- `ModelMethods`, for all four models: the `grid` property, which all four
  copies of today implement the same way.
- `GwfMethods`: `Output` (`head` and `budget` readers) and the `output`
  attribute.
  - `output` is an attrs field with a `takes_self` factory, so it may need
    to become a cached property, since mixins declare no fields.

`Gwf.NewtonOptions` should come from the DFN's `newtonoptions` record;
check that it does.

## Steps

1. **Codegen** (`utils/codegen/make.py`): build a model's package fields
   from its DFN children using the rules above. Add a model template, or
   extend the component template, and the `MIXINS` entries for the four
   `*-nam` DFNs.
2. **Mixins:** add `model_methods.py` and `gwf_methods.py`.
3. **Regenerate:** write the four `__init__.py` model classes, keeping each
   module's package imports and `__all__`, and add the missing exports.
4. **Diff `Gwf`:** compare it to today's version field by field. Only
   `_list` should change.
5. **Warn on unmatched rows:** a name-file row that no field accepts warns,
   as #380 proposed (`unsupported component`), checked against the DFN
   registry's ftypes rather than `endswith("6")`. This catches packages
   that rule 4 skips.
6. **Tests:**
   - test205 loads with `gwt.fmi.flow_imbalance_correction`.
   - A GWT FMI with PACKAGEDATA round-trips through the name file.
   - Two IST packages round-trip.
   - Two API packages are accepted.
   - An unmatched row warns.
   - Run the smoke tests and the docs examples.

## Open

- Whether to generate `Model` subclass registration (ftype lookup through
  `get_ftype`) or keep it as is. Check what `Simulation` generation does.
- Name collisions between an option and a package. None exist today, but
  codegen should raise if one appears.
