# Option classification: plan

Working notes, 2026-11-03. Step 1 of the plan in `discussion-287-directions.md`.
Coordinates with the memory catalog work in `../modflowapi/api_overhaul.md`,
`../modflowapi/variable-flags-plan.md` and devtools
`memory-catalog-modflowapi-consumption-plan.md`.

## Goal

Find out whether the layout/logical split is clean at the level of options.
Sort every option in the DFNs into categories using a stated test, with a
failure threshold fixed before we start. If the split holds, it becomes the
basis for a logical spec layer. If not, we keep it as a design principle for
flopy4 and leave the spec alone.

## Levels, revised for the memory catalog

There are four levels, not three. Two of them are already in the spec or
heading there.

| Level | What it is | Specified by |
|---|---|---|
| File layout | MF6 input text / NetCDF | DFN blocks and fields |
| Input memory | `__INPUT__` context, filled by IDM; mirrors file fields | generated `*idm.f90`, from the DFN |
| Runtime memory | package variables (`bound`, `nodelist`, `hcof`, ...) | DFN `[memory]` catalog (v2.0.0.dev3) |
| Logical | tables, keys, relations | nothing yet |

What the catalog adds:

- **Runtime memory is where layouts converge.** In dev3, `gwf-rch` and
  `gwf-rcha` declare the same runtime variables (`nodelist`, `bound`,
  `auxvar`, `hcof`, `rhs`, `simvals`, ...). The only extra one is
  `export_nc` in RCHA, which is itself a layout/output option. That's direct
  evidence for H1: the two variants are two encodings of one thing.
- **Runtime memory is not the logical layer.** It contains solver artifacts
  (`hcof`, `rhs`), reduced node numbers, and `maxbound`-sized arrays. And it
  has changed layout without any input change: MF6 6.4.3 split `BOUND` into
  per-column arrays in `__INPUT__` (`../modflowapi/idm-memory-layout-change.md`).
  Memory is one more layout. We find the logical layer by triangulating:
  what both file and runtime memory preserve.
- **`source` is the layout lens.** Catalog entries point from memory to
  input (`nodelist.source = "cellid"` in RCH). In RCHA, `nodelist` and
  `bound` have no `source`, because the mapping (columns → bounds at the
  `irch` layer) can't be written as a field list. Those missing `source`
  expressions are exactly the partial lenses from §1 of the directions doc.
  Our conversion work (step 5) and the catalog's `source` syntax are the
  same problem, approached from two sides.
- **A pitch to MF6 developers.** "RCH and RCHA are equivalent" becomes
  "both produce the same runtime `nodelist` and `bound`". That claim can be
  checked against code they maintain.

## Categories

The verdict depends on one question: **layout or not?** So there's one
primary label with four values, and two optional tags that collect input
for later steps. Classifying shouldn't stall over a tag.

### Primary label

| Label | Meaning | Examples (provisional) |
|---|---|---|
| layout | an encoding choice. Re-encode the data to match, toggle the option, and the logical content is unchanged. | `READASARRAYS`, `READARRAYGRID` (check) |
| logical | describes the model: settings, column and identity declarations, references to other components, descriptive metadata | `MOVER`, `FIXED_CELL`, `XT3D`, `AUXILIARY`, `BOUNDNAMES`, `XORIGIN`, `CRS` |
| output | a directive about the run; changes only what is printed or written | `PRINT_INPUT`, `PRINT_FLOWS`, `SAVE_FLOWS`, `BUDGET FILEOUT`, `EXPORT_ARRAY_*` |
| mixed | partly layout, partly something else | none known yet |

Why output is a label of its own: input formats mix three kinds of thing,
namely how data is written, what the model is, and what to do with it.
Output options fail the re-encoding test, but they aren't model
descriptions either. They're also the variables api_overhaul plans to move
to `__INTERNAL__`.

Only a straddle across layout and the rest counts as mixed. An output file
written by a child component is output plus binding, which is fine.

### Tags (optional; mostly logical, but `binding` also applies to output, e.g. `OBS6`)

- **`binding`:** attaches or names another component (`OBS6 FILEIN`,
  `TS6 FILEIN`, `TAS6`, `FLOW_PACKAGE_NAME`, `NCF6`). These are expected to
  become binding parameters under H3, so this list is the input for step 3.
- **`schema`:** decides the *shape* of the logical relations, not values in
  them: which columns exist, and whether entities have identity.
  `AUXILIARY` is `ADD COLUMN`. `BOUNDNAMES` adds a name column that other
  components can then refer to as a key. These are schema statements
  embedded in the data, and they're what most `when` conditions test. The
  constraints that follow from them (aux columns match `AUXILIARY`, the
  boundname arm needs `BOUNDNAMES`) are consequences, not tags. This list
  is input for step 3 too. If schema options parameterize a component by
  its own options the way bindings parameterize it by context, `when` and
  binding parameters may be one construct with two sources.

Corrections to the directions doc: `PRINT_INPUT` is output, not layout.
`BOUNDNAMES` is logical/schema, not layout: without it, bounds have no
names, so the column doesn't exist logically. It isn't merely left
unwritten.

Out of scope here, noted for step 2: dimension values like `MAXBOUND` look
like layout (preallocation hints), yet they also define bound-number
identity through `<=maxbound`.

## Decision test

Apply in order. Stop at the first that fits.

1. **Re-encoding test.** Toggle the option and re-encode the data to match.
   Is the logical content the same? If yes → **layout**.
2. Does it only change files or listing output? → **output**.
3. Otherwise → **logical**. Add `binding` if it names or attaches another
   component, and `schema` if it adds columns or gives entities identity.
4. If step 1 is partly yes (some of its effect is re-encoding, some isn't)
   → **mixed**. Record which part is which.

Caveat on step 1: runtime memory is a *proxy* for logical content, and it
only works in one direction. A difference in runtime memory (excluding
output and file-unit variables) shows the option isn't layout. No
difference doesn't show that it is. Georeference options (`XORIGIN`, `CRS`,
`LENGTH_UNITS`) change nothing MF6 computes, but they're facts about the
model, and a conversion must keep them. They're logical.

Evidence, in order of preference:

- the `[memory]` catalog (`source`, `readonly`, `set_in`);
- the DFN description;
- MF6 source (`~/dev/modflow6`) for anything still unclear;
- api_overhaul's internal-variable inventory. File unit numbers and print
  flags (`iprpak`, `ipakcb`, `I*OUT`) are slated for `__INTERNAL__`, and
  an option whose only runtime effect is one of those is output.

Record the evidence used for each label, so a disagreement can be traced
back to it.

## Failure threshold (fixed now, before looking)

The two-layer spec idea is in trouble if any of these hold:

- more than ~10% of distinct option names are mixed;
- any mixed option in a core flow component (DIS/DISV/DISU, NPF, STO, IC, or the
  standard boundary packages);
- the mixed cases cluster around one construct (e.g. all the NetCDF options),
  which would mean a missing concept rather than noise.

Otherwise the split holds at the option level, and we go on to step 2 (DDL
slice).

## Inventory

Source: devtools `autotest/dfns/__snapshots__/v2.0.0.dev3/*.toml`. It has
the same option fields as dev2, plus `[memory]` and `[observations]`.

Size, measured 2026-11-03:

- 146 components, 1,035 option fields, 224 distinct names.
- The ~20 most common names cover most occurrences: `save_flows` ×79,
  `print_input` ×78, `print_flows` ×72, `obs_filerecord` ×59,
  `auxiliary` ×51, `boundnames` ×48, ...
- 144 names occur exactly once. That's where the work is, and where mixed is
  most likely to show up.
- Only 282 of the 1,035 option fields have a runtime memory variable with
  `source` naming them. Unmapped: all `obs_filerecord`, `auxiliary`,
  `boundnames`, `ts_filerecord`, `mover`, the grid-georeference group, and
  some of `print_*` / `save_flows`. So the catalog is **evidence, not an
  oracle**. Most labels will be made by hand.

Script output (in `option-classification/`, untracked): one row per distinct
name, with:

- name, occurrence count, components (all, or a count if more than 10);
- DFN type, and whether it's a keyword, value, or record (filerecord);
- the first sentence of the description (flag where descriptions differ
  across components);
- runtime memory variables whose `source` includes it, with their `readonly`
  and `set_in` values;
- empty columns: category, evidence, notes.

Write it as a CSV for editing, plus a Markdown rendering for reading.

## Scope

- **In scope:** options blocks, for all components.
- **Out of scope for now:** field-level tags (`CONSTANT`, `INTERNAL`,
  `OPEN/CLOSE`, `NETCDF`, `LAYERED`, `FACTOR`, `IPRN`). They are layout by
  construction. List them in one table at the end, so the count is complete.
- **Also out:** non-options blocks (`dimensions`, `griddata`, periods).
  Those are step 2.

## Working order

1. Write and run the inventory script. Commit nothing yet.
2. Label the top ~20 names first. They're quick, and they calibrate the
   test.
3. Label the singletons, grouped by component family (GWF, GWT/GWE, PRT,
   SWF/CHF/OLF, exchanges, solutions, utl). Read MF6 source for unclear ones.
4. Tally by category, list the mixed cases with an explanation for each, and
   check against the threshold.
5. Write up: verdict, mixed cases, catalog gaps found (below), and corrections
   to the directions doc.

## Coordination with the memory catalog

What we take from it:

- `[memory]` entries as evidence for step 1 of the test.
- `[observations]` (dev3, 63 components): observation types declared on the
  target package, with arms `cellid | boundname`. That's H3's "the binding
  supplies the parameter" already in practice for OBS. Step 3 should build
  on it and not invent a parallel construct. It also agrees with
  api_overhaul's conclusion that observation-type definitions should point
  to variables, not the reverse.

What we give back (as a list, for whoever works on the catalog; no edits to
devtools or modflowapi from this exercise):

- Options with a clear runtime effect but no `source` mapping (catalog
  gaps).
- Missing `source` lenses for array variants (RCHA, EVTA, CHDG and the
  other `*G` grid variants), with a note on what syntax they'd need.
- Output options whose runtime variables belong in `__INTERNAL__`, cross-checked
  against api_overhaul's inventory.

Consistency checks between the two classifications. Each was developed
independently, so agreement is evidence for both:

- Layout options should have **no** runtime memory effect, only `__INPUT__`
  effects.
- Output options should touch only variables api_overhaul marks internal (file
  units, print flags) or `output`.
- Logical options should reach at least one variable that falls in
  variable-flags-plan's `parameter` set (`settable ∧ ¬prognostic ∧ lifetime ≥
  period`), or change which runtime variables exist. Exception: descriptive metadata such as georeference.

Shared concept to define once: devtools gap 3 proposes `Dim.kind` (`grid`
vs. `count`) so that consumers stop guessing grid dimensions from names.
That's the memory-level form of §2's entity/field key kinds (bound number
vs. grid column). One definition should serve both: the key kind of a role
and the kind of a dimension. Raise this when either is designed. Don't
settle it here.

## Done when

- every distinct option name has a category and its evidence;
- the threshold check has a written verdict;
- the gap list and the cross-check results exist;
- `discussion-287-directions.md` is updated with the verdict.
