# Option classification

**Status: done** (2026-11-03). DFNs from the modflow-devtools
`v2.0.0.dev3` snapshots, MF6 source at `8aad7bc4a5`. Part of the spec
research; terms (layout, logical, lens, binding, derivation) are defined in
[overview.md](overview.md#concepts).

## Question

Is the layout/logical split clean at the level of options? If MF6's
options sort cleanly into "how the file is written" and "what the model
is", the split can become a logical layer in the spec. If many options are
both, the two-layer idea is in trouble, and we keep it only as a design
principle for flopy4.

## Findings

- **The split holds.** Of 224 distinct option names, 20 are layout, 121
  logical, 82 output, and 1 mixed (CSUB `HEAD_BASED`). None of the failure
  criteria fixed beforehand is met.
- **Most option occurrences are output** (559 of 1,035), and only 38 are
  layout. The options block is mostly a run-directive block with model
  settings mixed in.
- **Options that declare a rule split by whether the rule is live.** A
  *static* derivation (every input fixed) can be computed once without
  loss. A *dynamic* one (an input can change during the run) is model
  content. No layout option is dynamic. 14 of the 20 layout options are
  static derivations.
- **Layout lenses come in four kinds**: syntactic, cross-component,
  computed and partial. A converter between layouts has to handle all
  four, and the computed kind means reimplementing part of CSUB's
  initialisation.
- **Runtime memory is not a normal form.** For 13 of the 21 options
  checked as layout, MF6 keeps a decoding flag in runtime memory. So memory is one more
  layout, and a memory-level API (BMI) caller can't tell from the catalog
  that, say, `k22` holds a ratio under `K22OVERK`.

## Method

### Categories

One primary label per distinct option name, decided by one question,
"layout or not?", plus two optional tags.

| Label | Meaning | Examples |
|---|---|---|
| layout | an encoding choice: re-encode the data to match, toggle the option, and the logical content is unchanged | `READASARRAYS`, `STORAGECOEFFICIENT`, `K22OVERK` |
| logical | describes the model: settings (including numerics), column and identity declarations, references to other components, descriptive metadata | `MOVER`, `FIXED_CELL`, `XT3D`, `AUXILIARY`, `BOUNDNAMES`, `XORIGIN`, `CRS` |
| output | a run directive that doesn't change what's computed: print and save, validation, logging, non-convergence policy, parallel partitioning | `PRINT_INPUT`, `SAVE_FLOWS`, `NOCHECK`, `MAXERRORS`, `CONTINUE`, `HPC6` |
| mixed | partly layout, partly something else | CSUB `HEAD_BASED` |

Output gets its own label because input formats mix three kinds of thing:
how data is written, what the model is, and what to do with it. Output
options fail the re-encoding test, but they don't describe the model
either. Only a straddle between layout and the rest counts as mixed.

Tags, which apply to logical and output options:

- **`binding`**: attaches or names another component (`OBS6 FILEIN`,
  `TS6 FILEIN`, `TAS6`, `FLOW_PACKAGE_NAME`, `NCF6`, `HPC6`). These are the
  candidates for binding parameters (overview H3).
- **`schema`**: decides the shape of the logical relations, not values in
  them:
  - columns: `AUXILIARY` adds them, `BOUNDNAMES` adds a name column other
    components can refer to;
  - process switches that decide which arrays exist: `SORPTION`, the
    `*_DECAY` options, `SURF_RATE_SPECIFIED`;
  - roles assigned to columns: `AUXMULTNAME`, `AUXDEPTHNAME`;
  - key references: `TEMPERATURE_SPECIES_NAME` (a VSC packagedata row),
    `FLOW_PACKAGE_AUXILIARY_NAME` (another package's column). These two are
    also bindings.

  Most `when` conditions test a `schema` option.

### Decision test

Applied in order, stopping at the first that fits:

1. **Re-encoding test.** Toggle the option and re-encode the data to match.
   Is the logical content the same? If yes, **layout**.
2. Does it only change files, listing output or checking? **output**.
3. Otherwise **logical**. Add `binding` if it names or attaches another
   component, and `schema` if it adds columns or gives entities identity.
4. If step 1 is partly yes (some of the effect is re-encoding, some isn't),
   **mixed**, with a note saying which part is which.

Runtime memory is a proxy for logical content that only works one way. A
difference in runtime memory (excluding output and file-unit variables)
shows an option isn't layout. No difference doesn't show it is.
Georeference options (`XORIGIN`, `CRS`, `LENGTH_UNITS`) change nothing MF6
computes, but they're facts about the model that a conversion must keep, so
they're logical.

Evidence, in order of preference: the `[memory]` catalog (`source`,
`readonly`, `set_in`); the DFN description; MF6 source. The evidence for
each label is recorded in the CSV, so a disagreement can be traced back.

### The derivation axis

Applying the re-encoding test to `AUXMULTNAME` exposed an ambiguity in
"same logical content":

- **same values now**: multiply the multiplier in, and MF6 computes the
  same `bound`;
- **same behaviour under change**: with the multiplier kept separate,
  changing the aux column changes the rate; with it multiplied in, nothing
  changes.

These are the same answer today with different behaviour after an edit,
the way a view and a materialised view are. Options like this don't pick an
encoding; they **declare a derivation**. So each option also gets a
derivation value:

| Derivation | Meaning |
|---|---|
| none | no rule: an encoding choice, a value, a switch, a reference, a directive |
| static | every input is fixed once written, so materialising the result loses nothing |
| dynamic | an input can change during the run (TS/TAS, TVK/TVS, simulated state), and MF6 re-evaluates the rule |

The test is structural: where does MF6 evaluate the rule, and can its
inputs change between evaluations? The CSV's `derivation_basis` column
records the answer for each option.

### Failure threshold

Fixed before labelling. The two-layer idea is in trouble if any of these
hold:

- more than ~10% of distinct option names are mixed;
- any mixed option is in a core flow component (DIS/DISV/DISU, NPF, STO,
  IC, or the standard boundary packages);
- the mixed cases cluster around one construct (e.g. all the NetCDF
  options), which would mean a missing concept rather than noise.

### Scope

- **In:** options blocks, all 146 components. 1,035 option fields, 224
  distinct names. The ~20 most common names (`save_flows` ×79,
  `print_input` ×78, `print_flows` ×72, `obs_filerecord` ×59,
  `auxiliary` ×51, `boundnames` ×48, ...) cover most occurrences; 144 names
  occur exactly once.
- **Out:** field-level array tags (`CONSTANT`, `INTERNAL`, `OPEN/CLOSE`,
  `NETCDF`, `LAYERED`, `FACTOR`, `IPRN`), which are layout by construction;
  non-options blocks (dimensions, griddata, periods).

Only 282 of the 1,035 option fields have a runtime memory variable whose
`source` names them, so the catalog was evidence, not an oracle. Most
labels were made by hand.

## Results

### Tally

| Category | Distinct | % | Occurrences |
|---|---|---|---|
| layout | 20 | 8.9 | 38 |
| logical | 121 | 54.0 | 437 |
| output | 82 | 36.6 | 559 |
| mixed | 1 | 0.4 | 1 |

Tags: `binding` 17, `schema` 12.

| Threshold criterion | Result |
|---|---|
| > ~10% of distinct names mixed | 1 of 224 (0.4%) |
| any mixed option in a core flow component | none (the one case is CSUB) |
| mixed cases cluster around one construct | one case, so no cluster |

### The mixed case

**CSUB `HEAD_BASED`** (`gwf-csub.f90:622-624, 670`) turns on the
head-based formulation (`lhead_based`), which is logical. It also sets
`IPCH`, so preconsolidation values are read as heads: the same encoding
`INITIAL_PRECONSOLIDATION_HEAD` selects on its own. One keyword carries a
formulation choice and an encoding choice, and the encoding can't be chosen
separately. In a two-layer spec it would split into a logical setting plus
a layout default that it forces.

### Derivations

| | none | static | dynamic |
|---|---|---|---|
| layout | 6 | 14 | **0** |
| logical | 115 | 1 | 5 |
| output | 82 | 0 | 0 |
| mixed | 0 | 1 | 0 |

- **No layout option has a dynamic derivation.** The two axes agree.
- **Dynamic derivations**, all logical:
  - `AUXMULTNAME`: value × aux column at every use (`gwf-wel.f90:766`,
    `gwf-rch.f90:271`, `gwf-chd.f90:427`), and the aux value may be a TS;
  - `AUXDEPTHNAME`: depth-scaled DRN conductance (`drn_cf`/`drn_fc`);
  - `TS6`/`TAS6`: interpolation within a period;
  - `LOCAL_Z` (PRT): scales by simulated saturation at release time
    (`prt-prp.f90:706`).

  `AUXMULTNAME` and `AUXDEPTHNAME` have the same structure: an aux column
  with a role in a live formula.
- **Most layout options are static derivations** (14 of 20): constant unit
  factors, ratios and fractions of fixed geometry, and CSUB offsets from
  the initial state. Only 6 are pure encoding choices: `READASARRAYS`,
  `READARRAYGRID`, `NC_FILERECORD`, `MODELNAMES` and the two times-file
  records.
- **`K22OVERK` is static.** K22 is decoded at load (`gwf-npf.f90:1987`),
  and each TVK write of K22 is decoded against K11 at that moment
  (`gwf-tvk.f90:239`). A later change to K11 alone doesn't propagate, so
  the ratio isn't kept as a rule.
- **`STORAGECOEFFICIENT` is static too,** although MF6 decodes it at use
  (`SsCapacity`): the thickness it divides by is fixed.
- **`THICKSTRT` is static but logical.** No input column holds its result,
  so there's nothing to materialise into.

What this means:

1. The logical layer needs **derived attributes** (generated columns) as
   well as base tables. A dynamic derivation is a logical generated column.
   A static one can be materialised by the lens. (Overview H5.)
2. **flopy4 should keep dynamic derivations, not materialise them.** It's
   an editing tool, so users expect an edit to the aux column to follow
   through. That matters more there than in MF6, which only runs a
   snapshot.

### Lens kinds

The layout options aren't all simple syntax switches:

| Lens kind | Options | What re-encoding needs |
|---|---|---|
| syntactic | `NC_FILERECORD`, `MODELNAMES`, `COMPLEXITY`, `RELEASE_TIMESFILERECORD`, `TRACK_TIMESFILERECORD` | the file alone |
| cross-component | `K22OVERK`/`K33OVERK` (NPF + TVK), `STORAGECOEFFICIENT` (STO + TVS), `LENGTH_`/`TIME_CONVERSION` (DFW + CXS), `UNIT_CONVERSION` (SFR), `CELL_FRACTION` (CSUB + DIS) | other components' data, such as the TVK schedule or DIS thickness |
| computed | CSUB `SPECIFIED_INITIAL_*` (3), `INITIAL_PRECONSOLIDATION_HEAD`, `COMPRESSION_INDICES` | a model calculation: initial effective stress from STRT, TOP/BOT and geostatic load |
| partial | `READASARRAYS`, `READARRAYGRID`, `FLOW_REDUCTION_LENGTH` | a domain restriction: not every instance has an image in the other encoding |

Computed lenses are the uncomfortable kind. They're layout by the test,
since the result is determined by input, but a converter would have to
reimplement part of CSUB's initialisation. Treat them as one-way (export
only), or accept that MF6 is the only exact converter.

### Options that look like layout but aren't

- `LOCAL_Z` (PRT): depends on simulated saturation.
- `FIXED_CONDUCTANCE` (CHF/OLF–GWF): turns off depth smoothing and the
  wetted-perimeter area.
- `THICKSTRT`: changes what thickness means for conductance.
- `TS6`/`TAS6`: interpolate within a period, which period data can't
  express without changing TDIS.
- Numerics (solver, Newton, XT3D settings) change computed values, so
  they're logical. `DEPENDENT_VARIABLE_SCALING` is borderline, since its
  effect on results is round-off only.

### Cross-checks against the memory catalog

The labels were made independently of the memory catalog and of
modflowapi's planned variable classification, so agreement is evidence for
both.

1. **"Layout options have no runtime memory effect": fails for 13 of the
   21 options checked, informatively.** (The 21 include `AUXMULTNAME`,
   labelled logical after the derivation axis was added.) MF6 keeps a flag in runtime memory
   (`ik22overk`, `istor_coef`, `lengthconv`, `precon_head`, ...). Some
   values are decoded at the point of use (`istor_coef`); others are
   decoded when written, with the flag kept to decode later writes
   (`ik22overk` for TVK). So the check should read "layout options have no
   effect on *derived* quantities", which the catalog can't express.
2. **"Output options touch only internal or output variables": passes.**
   All 39 runtime variables reached by output options are print flags,
   file units or names, export flags, or check settings (`ipakcb`,
   `iprpak`, `*fn`, `export_nc`, `ichkmeth`, `voffsettol`, ...), all
   candidates for modflowapi's `__INTERNAL__` context.
3. **"Logical options reach a settable model parameter": can't be tested
   yet.** 87 of 141 non-output names have no `source` mapping at all, and
   the catalog has no `settable` flag yet, only `readonly`.

The catalog gaps these turned up are in [dfn-gaps.md](dfn-gaps.md#memory-catalog).

### For later steps

- **DDL slice:** the four lens kinds; `MAXBOUND`, which looks like a
  preallocation hint (layout) but defines bound-number identity through
  `<=maxbound`; the three `RELEASETIMES` encodings (block, options record,
  file); `AUXMULTNAME` as a generated column.
- **Parameter syntax sketch:** the `binding` and `schema` lists are in the
  CSV's `tags` column.
- **xarray representation:** options appear by label (logical as data,
  layout as encoding, output off the data). See
  [layout-logical-decisions.md](layout-logical-decisions.md#track-c-the-representation).

## Data

In [data/option-classification/](data/option-classification/):

| File | What |
|---|---|
| `inventory.py` → `options.csv`, `options.md` | one row per distinct option name: occurrences, components, DFN type, first description sentence, runtime memory variables whose `source` names it |
| `label.py` → `options-labelled.csv`, `options-labelled.md` | the hand labels merged in (category, tags, derivation, evidence, notes), plus the tallies |

To reproduce:

```
python inventory.py <devtools>/autotest/dfns/__snapshots__/v2.0.0.dev3 <out>
python label.py <out>
```

The labels themselves live in `label.py`.
