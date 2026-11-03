# Option classification: results

Working notes, 2026-11-03. Carries out `option-classification-plan.md`.
Data: `option-classification/options-labelled.csv` (one row per distinct name,
with category, tags, evidence and notes) and `options-labelled.md`.
Scripts: `option-classification/inventory.py` (snapshots → `options.csv`) and `label.py` (labels → `options-labelled.*`).
MF6 source checked at `~/dev/modflow6` `8aad7bc4a5`.

## Verdict

**The split holds at the option level.** None of the three failure criteria
is met:

| Criterion | Result |
|---|---|
| > ~10% of distinct names mixed | 1 of 224 (0.4%) |
| any mixed option in a core flow component | none (the one case is CSUB) |
| mixed cases cluster around one construct | one case, so no cluster |

The earlier caveat, `AUXMULTNAME`, is resolved. It wasn't a mixed option.
It showed that the re-encoding test was underspecified. A second axis,
**derivation**, settles it structurally (see "The derivation axis" below):
`AUXMULTNAME` declares a rule MF6 re-evaluates during the run, so it's
logical.

## Tally

| Category | Distinct | % | Occurrences |
|---|---|---|---|
| layout | 20 | 8.9 | 38 |
| logical | 121 | 54.0 | 437 |
| output | 82 | 36.6 | 559 |
| mixed | 1 | 0.4 | 1 |

Tags: `binding` 17, `schema` 12.

Most option occurrences are output (559 of 1,035), and only 38 are layout.
The options block is mostly a run-directive block that has model settings
mixed into it.

## The mixed case

**CSUB `HEAD_BASED`** (`gwf-csub.f90:622-624, 670`). It turns on the
head-based formulation (`lhead_based`), which is logical. It also sets
`IPCH`, which means the preconsolidation values are read as heads. That is
the same encoding `INITIAL_PRECONSOLIDATION_HEAD` selects on its own. So one
keyword carries a formulation choice and an encoding choice, and you can't
choose the encoding separately. In a two-layer spec it would split into a
logical setting plus a layout default that it forces.

## The derivation axis

`AUXMULTNAME` sat between two categories because the re-encoding test had
two readings of "same logical content":

- **Same values now (extensional).** Multiply the multiplier in and MF6
  computes the same `bound`.
- **Same behaviour under change (intensional).** With the factorisation,
  changing the aux column changes the rate. Without it, nothing changes.

These are the same answer today with different behaviour after an update,
the way a view and a materialised view are. Options like this one don't
pick an encoding. They **declare a derivation**: a quantity computed from
other quantities. The question that decides them is structural. Can an
input to the rule change during the run, so that MF6 re-evaluates it?

| derivation | Meaning | Test |
|---|---|---|
| none | no rule: an encoding choice, a value, a switch, a reference, a directive | — |
| static | every input is fixed once its value is written, so materialising the result loses nothing | where MF6 evaluates it |
| dynamic | an input can change during the run (TS/TAS, TVK/TVS, simulated state), and MF6 re-evaluates the rule | same |

The result. Rows are categories, columns are derivation values, and
`option-classification/options-labelled.csv` has a `derivation` and a
`derivation_basis` column:

| | none | static | dynamic |
|---|---|---|---|
| layout | 6 | 14 | **0** |
| logical | 115 | 1 | 5 |
| output | 82 | 0 | 0 |
| mixed | 0 | 1 | 0 |

Readings:

- **No layout option has a dynamic derivation.** The axis agrees with the
  split everywhere except at `AUXMULTNAME`, which it moves.
- **Dynamic derivations:**
  - `AUXMULTNAME` (value × aux at every use: `gwf-wel.f90:766`,
    `gwf-rch.f90:271`, `gwf-chd.f90:427`; the aux value may be a TS);
  - `AUXDEPTHNAME` (depth-scaled DRN conductance in `drn_cf`/`drn_fc`);
  - `TS6`/`TAS6` (interpolation);
  - `LOCAL_Z` (simulated saturation).

  `AUXMULTNAME` and `AUXDEPTHNAME` turn out to have the same structure: an
  aux column with a role in a live formula. The contrast I drew between
  them before doesn't hold.
- **Most layout options are static derivations** (14 of 20): constant unit
  factors, ratios and fractions of fixed geometry, and CSUB offsets from
  the initial state. Only 6 are pure encoding choices: `READASARRAYS`,
  `READARRAYGRID`, `NC_FILERECORD`, `MODELNAMES` and the two times-file
  records. The cross-component and computed lens kinds below are static
  derivations whose inputs live elsewhere.
- **`K22OVERK` is static, which corrects an earlier claim.**
  - K22 is decoded at load (`gwf-npf.f90:1987`), and each TVK K22 write is
    decoded against K11 at that moment (`gwf-tvk.f90:239`).
  - A later change to K11 alone doesn't propagate.
  - So the ratio isn't kept as a rule. Each value is decoded once.
- **`STORAGECOEFFICIENT` is static too,** although MF6 decodes it at use
  (`SsCapacity`): the thickness it divides by is fixed.
- **`THICKSTRT`** is a static derivation that stays logical. No input
  column holds the result, so there's nothing to materialise into.
- **CSUB `HEAD_BASED`** is still the one mixed option. Its mixed part is a
  forced static derivation (`IPCH`).

What this means:

1. **The logical layer needs derived attributes** (generated columns) as
   well as base tables. A dynamic derivation is a logical generated column.
   A static one can be materialised by the lens.
2. **flopy4 should keep dynamic derivations, not materialise them.** It's an
   editing tool, so users expect an edit to the aux column to follow
   through. That matters more there than in MF6, which only runs a
   snapshot.
3. **Step 2 test:** model one boundary package with `AUXMULTNAME` as a
   generated column.

## What the layout options look like

The layout options aren't all simple syntax switches. Their lenses fall into
four kinds. This is the main new finding. It refines §1 of the directions
doc, and step 5 (conversion) has to handle all four.

| Lens kind | Options | What re-encoding needs |
|---|---|---|
| syntactic | `NC_FILERECORD`, `MODELNAMES`, `COMPLEXITY`, `RELEASE_TIMESFILERECORD`, `TRACK_TIMESFILERECORD` | the file alone |
| cross-component | `K22OVERK`/`K33OVERK` (NPF + TVK), `STORAGECOEFFICIENT` (STO + TVS), `LENGTH_`/`TIME_CONVERSION` (DFW + CXS), `UNIT_CONVERSION` (SFR), `CELL_FRACTION` (CSUB + DIS) | other components' data, such as the TVK schedule or DIS thickness |
| computed | CSUB `SPECIFIED_INITIAL_*` (3), `INITIAL_PRECONSOLIDATION_HEAD`, `COMPRESSION_INDICES` | a model calculation: initial effective stress from STRT, TOP/BOT and geostatic load |
| partial | `READASARRAYS`, `READARRAYGRID`, `FLOW_REDUCTION_LENGTH` | a domain restriction: not every instance has an image in the other encoding |

Computed lenses are the uncomfortable kind. They're still layout by the
test, since the result is determined by input. But a converter would have to
reimplement part of CSUB's initialisation. Treat them as one-way (export
only), or accept that MF6 is the only exact converter.

Options that look like layout but aren't:

- `LOCAL_Z` (PRT) scales by simulated saturation at release time
  (`prt-prp.f90:706`).
- `FIXED_CONDUCTANCE` (CHF/OLF–GWF) turns off depth smoothing and the
  wetted-perimeter area.
- `THICKSTRT` changes what thickness means for conductance.
- `TS6`/`TAS6` interpolate within a period, which period data can't express
  without changing TDIS.

## Refinements to the categories

- **Output is really "run directive".** Besides file and listing output, it
  covers validation (`NOCHECK`, `MAXERRORS`, `VERTICAL_OFFSET_TOLERANCE`,
  `COORDINATE_CHECK_METHOD`), logging and profiling, non-convergence policy
  (`CONTINUE`) and parallel partitioning (`HPC6`). None of these changes
  what's computed. I kept the label to avoid adding a category. Consider
  renaming it.
- **Tags apply to output too.** `OBS6`, `HPC6` and `NCF6` are output plus
  `binding`. Update the plan: tags aren't limited to logical options.
- **Schema covers more than ADD COLUMN.** It includes process switches that
  decide which arrays exist (`SORPTION`, the `*_DECAY` options,
  `SURF_RATE_SPECIFIED`), roles assigned to columns (`AUXMULTNAME`,
  `AUXDEPTHNAME`), and key references (`TEMPERATURE_SPECIES_NAME` → a VSC
  packagedata row; `FLOW_PACKAGE_AUXILIARY_NAME` → another package's
  column). The last two are also bindings.
- **Numerics are logical.** Solver, Newton and XT3D settings change computed
  values, so they're logical. `DEPENDENT_VARIABLE_SCALING` is borderline,
  since its effect on results is round-off only.

## Cross-checks against the memory catalog

1. **"Layout options have no runtime memory effect": fails for 13 of the original 21,
   and the failure is informative.** MF6 keeps a flag in runtime memory
   (`ik22overk`, `istor_coef`, `lengthconv`, `precon_head`, ...).
   - Some values are decoded at the point of use (`istor_coef`).
   - Others are decoded when written, and the flag is kept to decode later
     writes (`ik22overk` for TVK). See the derivation axis above.

   So runtime memory isn't a normal form. It's one more layout, as
   the plan already suspected. The check should be restated as "layout
   options have no effect on *derived* quantities", which the catalog can't
   express. For the API: a BMI caller that writes `k22` under `K22OVERK`
   writes a ratio, and nothing in the catalog says so.
2. **"Output options touch only internal/output vars": passes.** All 39
   runtime vars reached by output options are print flags, file units or
   file names, export flags, or check settings (`ipakcb`, `iprpak`,
   `*fn`, `export_nc`, `ichkmeth`, `voffsettol`, ...). They're all
   candidates for `__INTERNAL__`, which agrees with api_overhaul's
   inventory.
3. **"Logical options reach a parameter-set variable": can't be tested
   yet.** 87 of 141 non-output names have no `source` mapping at all. Where
   a mapping exists, it's to an `ar`-time scalar flag. The catalog has no
   `settable` flag yet, only `readonly`, and none of these set it. So the
   predicate can't be evaluated.

## Gap list for the memory catalog

Report only, no edits to devtools.

- **Probable error:** `iprpak.source = "save_flows"` in `gwe-ctp` and
  `gwt-cnc`. It should probably be `ipakcb`.
- **`bound` has no `source` in any stress package**, list variants
  included. The multi-column mapping (value columns → `bound` rows) has no
  syntax. Array variants (`*A`, `*G`) also lack `source` on `nodelist`. A
  `source` expression language needs: column lists, a cell lens
  (cellid → reduced node), and array → list projection with a layer index
  (`IRCH`/`IEVT`) or a NODATA mask.
- **Options with a clear runtime effect but no mapping:**
  - **The variable is catalogued, but has no `source`.** `auxiliary`
    (`naux`, `auxname_cst` in `gwf-chd`).
  - **The variable isn't catalogued at all** (checked in `gwf-chd` and
    `gwf-dis`):
    - `boundnames` (`inamedbound`), `auxmultname` (`iauxmultcol`), `mover`
      (`imover`);
    - the DIS georeference variables (`xorigin`, `yorigin`, `angrot`);
    - `fixed_cell`, `newtonoptions`;
    - solver options (`complexity`, `no_ptcrecord`, the ATS fractions);
    - the GWT/GWE `scheme`/`xt3d_*` options.
  - Full list: rows with blank `memory` in the CSV.
- **Partial coverage:** the same option is mapped in some components and
  not others. `save_flows` 51/79, `print_input` 43/78, `print_flows`
  41/72, `length_`/`time_conversion` 3/5, `cvoptions` 1/2, and the OC
  file records.
- **Lazy-decoding flags** (cross-check 1) should be documented on the
  variable they qualify (e.g. on `k22`: "ratio to `k11` when `ik22overk`").
  Otherwise a catalog consumer can't interpret the value.

## Next

- `AUXMULTNAME` is settled (logical, dynamic derivation). Criterion 2
  holds.
- Step 2 (DDL slice) can go ahead. Carry these into it: the four lens kinds;
  `MAXBOUND` (from the plan); and the `RELEASETIMES` encodings (block,
  options record, file).
- Step 3: the `binding` and `schema` lists are in the CSV (`tags` column).
