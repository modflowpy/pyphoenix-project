# Constraint audit: results

Working notes, 2026-11-03. Carries out `constraint-audit-plan.md`. MF6 at
`8aad7bc4a5`, DFNs from the devtools dev3 snapshots.

Data and scripts are in `constraint-audit/`:

| File | What |
|---|---|
| `dfn_pass.py` → `dfn-constraints.csv` | pass 1: 2,245 constraint-bearing DFN keys |
| `mf6_sites.py` → `mf6-checks.csv` | pass 2: all 1,279 `store_error`/`store_warning` sites with message and regex cluster |
| `sample.py` → `mf6-sample.csv` | passes 2–3: 166 hand-labelled instances (159 MF6 sites, 7 rules found only in mf6io prose) |

## Summary

- **The layering holds for constraints too.**
  - Every constraint triggered by a layout option is either a layout
    constraint or a condition on where a partial lens is defined.
  - There are no exceptions: the one apparent case (`AUXMULTNAME`) turned
    out to be a logical option once the derivation axis was added.
  - Logical constraints are triggered by logical options, dimensions, the
    presence of other components, or the binding.
- **`when` and binding are one construct, with a wider scope than `when`
  has today.**
  - Conditional presence (K4) and co-occurrence (K8) have the same form:
    *predicate over context ⇒ element present or absent*.
  - What differs is where the predicate's variables live: the component's
    own options and dimensions, sibling components, or the binding row.
  - Three cases cross between the two:
    - `MODELNAMES`, an option MF6 requires to equal the binding context;
    - `FLOW_PACKAGE_NAME`, an option that overrides a default supplied by
      the binding;
    - `MOVER`, an option that gates a role other components refer to.
  - K8 also has a second half that isn't presence: consistency between
    bound components (same grid, same solution, mirrored exchange tables).
    Those are join assertions.
- **Most of the input contract is in Fortran only.**
  - Of the sample, the DFN expresses 20 instances fully and 26 partly, out
    of 166.
  - It covers grammar, shapes, required fields, and keys and references
    within one file.
  - It covers almost none of the following:
    - numeric domains (K2: 1 of 27);
    - option coherence (K5: 0 of 14);
    - co-occurrence (K8: 1 of 19);
    - temporal rules (K9: 0 of 7);
    - structural rules (K10: 0 of 18).
- **A DDL covers most of what's logical.**
  - CHECK, FK, PK/UNIQUE and NOT NULL take 94 of the 166.
  - Multi-table assertions take 39. Standard SQL has `CREATE ASSERTION`,
    but no engine implements it, so in practice these are queries.
  - 31 have no DDL form:
    - 19 of those are layout, as they should be;
    - 7 are run-state, numerics, or external-file and build checks;
    - the 5 genuine logical misfits are monotone row order (2), graph
      acyclicity (1) and geometric predicates (2).

## The kinds

Counts are from the hand-labelled sample. I picked the sample for coverage,
so the proportions describe the sample, not MF6 as a whole.

DFN column: expressible in the DFN today (yes / partly / no). DDL column:
the construct a logical spec would use.

| Kind | n | Level | DFN y/p/n | Typical arity | Config/data | DDL |
|---|---|---|---|---|---|---|
| K1 lexical / format | 10 | layout | 3/1/6 | row, field | data | none (grammar) |
| L lens domain (new) | 6 | layout | 0/0/6 | component, multi | config | none (encoding domain) |
| K2 type and domain | 27 | logical | 1/3/23 | field (22), row (4) | data 18, config 9 | CHECK |
| K3 shape and dimension | 10 | logical | 2/5/3 | table | **cfg-data 7** | CHECK(count = dim) |
| K4 conditional presence | 19 | logical (1 layout) | 5/1/13 | component | data | NOT NULL / conditional |
| K5 option coherence | 14 | logical 9, layout 4, output 1 | 0/2/12 | component | **config 13** | CHECK on the options row |
| K6 keys and uniqueness | 12 | logical | 3/1/8 | table, multi | data | PK / UNIQUE |
| K7 referential | 21 | logical | 5/12/4 | multi (11) | data 13, config 7 | FK |
| K8 co-occurrence | 19 | logical | 1/0/18 | multi (18) | **config 16** | assertion |
| K9 temporal | 7 | logical | 0/1/6 | multi, field | data | FK(period), ordering |
| K10 structural / physical | 18 | logical | 0/0/18 | multi (9), row | **data 18** | assertion (join on grid) |
| not input | 3 | runtime | — | — | — | — |

Revisions to the provisional taxonomy:

- **New kind L, lens domain.** These constraints say where a layout's
  partial lens is defined:
  - `READASARRAYS` excludes `SURF_RATE_SPECIFIED` and `NSEG > 1`
    (`gwf-evt.f90:202, 291`);
  - TAS isn't available for DISU (`BoundaryPackage.f90:1252`);
  - EVTA requires a non-DISU grid (prose);
  - layered NetCDF isn't supported for DIS int2d;
  - binary list input isn't supported for text columns.

  They look like K5 option coherence, but they're the partiality conditions
  of section 1 of the directions doc, which MF6 enforces. They belong with
  the lens, not with the logical constraints. Step 5's conversion code
  should report exactly these.
- **K8 splits in two.**
  - **K8a, co-occurrence:** if A is present, B must be (or must not be).
    MVR needs MVT, LKT needs LAK, CSUB requires `SS = 0` in STO, XT3D
    excludes GNC, and OLF needs DFW.
  - **K8b, consistency between bound components:**
    - the GWF and GWT grids are identical (`exg-gwfgwt.f90:231`);
    - exchanged models share a solution;
    - GWT-GWT exchange data mirrors GWF-GWF (`exg-gwfgwt.f90:447`);
    - the number of exchanges equals the number of GNCs.

  K8a has the `when` form. K8b doesn't: those are equality joins.
- **K10 is mostly joins against the grid**, not a separate physics layer.
  Examples:
  - `TOP > BOT`;
  - SURFDEP ≤ cell thickness;
  - lake `belev` ≥ cell bottom;
  - UZF area ≤ cell area;
  - release point in cell;
  - MAW screen vs. cell.

  The remainder are graph properties of one table: SFR reciprocity, upstream
  fractions summing to 1, acyclicity. The grid is the table every
  structural constraint joins against, which fits "grid as parameter"
  (directions doc §3). Only 1 of 18 is runtime (time step too small).
- **K1 splits into grammar, which the DFN covers, and ordering conventions,
  which it doesn't.** The ordering conventions:
  - period numbers increasing;
  - solution-group blocks consecutive;
  - ICELL2D in sequence;
  - CXS rows grouped by section;
  - DISU `JA` with self first.

  All of these are layout.

## Layering check

Constraints sorted by what triggers them (sample):

| Trigger | Layout constraints | Logical constraints |
|---|---|---|
| unconditional | 11 | 64 |
| a dimension | — | 17 |
| a logical option | — | 17 |
| a data discriminator in the row (`obstype`, `ctype`, `condeqn`) | — | 4 |
| another component's presence | — | 12 |
| the binding | 4 (lens domain) | 21 |
| a layout option | 7 | **0** |
| an output option | — | 2 |

- **Layout option → logical constraint: none.**
  - The one candidate was `BoundaryPackage.f90:1331`: `AUXMULTNAME` must
    name an aux column.
  - `AUXMULTNAME` has since been relabelled logical. It declares a dynamic
    derivation (`option-classification-results.md`, "The derivation axis").
  - The constraint was never evidence either way: any option that names a
    column carries such a reference.
- **Layout constraints triggered by layout options:**
  - `K22OVERK` requires K22;
  - `FLOW_REDUCTION_LENGTH` requires `AUTO_FLOW_REDUCE`;
  - `UNIT_CONVERSION` excludes `LENGTH_`/`TIME_CONVERSION`;
  - `MODELNAMES` ⇔ exchange binding;
  - the lens-domain cases.

  These are coherence rules within the layout layer, as expected.
- **Output options with logical prerequisites: a small new finding.**
  - DFW `SAVE_VELOCITY` requires `ANGLDEGX` in the discretization
    (`swf-dfw.f90:1350`).
  - DISU's `VERTICAL_OFFSET_TOLERANCE` parameterizes a K10 check.

  A run directive can't change results, but it can need logical data to
  carry out. That's harmless for the split. Note it for the output/"run
  directive" category: some directives have preconditions.

Verdict: **the layering holds at the constraint level.** Each constraint
belongs to one level. The only constraints that look like they cross
levels are lens-domain conditions, and those belong to the lens.

## `when` vs. binding

The plan's hypothesis was that K4 is triggered by schema options and K8 by
binding options or context, and that both can be written in one form.

**What the DFN uses `when` for today:** 50 uses, testing only 3 options.

| Option | Uses | Label |
|---|---|---|
| `boundnames` | 46 | logical/schema |
| `modelnames` | 3 | layout |
| `surf_rate_specified` | 1 | logical/schema |

**What MF6 actually conditions on, across K4 and K8a:**

| Predicate over | Examples | Expressible as `when` today? |
|---|---|---|
| own options | sorption → `BULK_DENSITY`, `DISTCOEF`, `SP2`; decay → `DECAY`, `DECAY_SORBED`; `NON_VERTICAL_WELLS` → ANGLEDATA block; `BOUNDNAMES` → boundname | yes for fields; there's no block-level `when` |
| own dimensions | `NTABLES > 0` → TABLES block; `NRELEASETIMES > 0` → RELEASETIMES block | no (but these are K3 counts: `count(rows) = dim`) |
| own data, same row | `obstype` → ID2 required / boundname forbidden; `ctype` → `connlen > 0`; `cprior` → divflow range | union arms, already modelled as discriminated rows |
| other fields present | ANGLE2 → ANGLE1; K22 → ANGLDEGX in DIS | no |
| sibling components | GWF MVR active → MVT; CSUB → STO `SS = 0`; XT3D → no GNC; LKT → LAK | no |
| binding row | exchange-bound MVR → `MODELNAMES`; SSM `pname` → flow package; SFT name defaults to SFR name | no |

The form is the same throughout: `when = <predicate>`, with the predicate's
names resolved in a scope chain:

1. the component's own options and dimensions;
2. the model's components;
3. the binding's parameters.

This fits H3 (directions doc §3): a binding parameter is a name in the outer
scope. `MODELNAMES` shows it most clearly. The option exists only so the
file can state its binding context, and MF6 rejects it whenever it
disagrees with the binding (`gwf-mvr.f90:785-798`). With a binding
parameter, the option goes away: the mover's `mname` column is filled from
the binding when it isn't written.

**Verdict: supported, for K4 and K8a.** K8b (consistency between bound
components) doesn't have this form and needs join assertions. For step 3,
`[params]` should give binding parameters names that `when` can test,
rather than adding a second conditional construct.

## Coverage

DFN constraint keys (pass 1, all 146 components):

| Kind | DFN keys | Rows |
|---|---|---|
| K1 | `index`, `netcdf`, `layered`, `case_sensitive`, `write_if_empty` (+ the grammar itself) | 323 |
| K2 | `valid` (32, all enums), `allow_zero` (2); no numeric ranges | 34 |
| K3 | `shape` 348: grid 212, `<=dim` 56, aux 44, local 36; `dims` 253 | 601 |
| K4 | required (no `optional`) 332, `when` 50 | 382 |
| K6 | `pk` 55 | 55 |
| K7 | `fk` 58 (9 cross-component), `time_series` 173, `model` 13, `dynamic` 7 | 251 |
| K8 | `parent` 145, `multi` 145, `component` 136, `component_ftype` 10 | 436 |
| K9 | `fill_forward` 70 | 70 |
| K5, K10 | — | 0 |
| (fill) | `default` 93: absence semantics, not a constraint | 93 |

MF6 has 1,279 sites: 1,203 errors and 76 warnings. Another 398
`store_error_filename`/`_unit` calls only add a file name to an error and
aren't counted as sites. Regex clusters estimate ~13% are not input:
I/O, programmer errors, numerics.

Of the sampled sites, MF6 checks 118 at load and 29 at allocate-and-read
(`ar`). It checks 14 at read-and-prepare (`rp`), once per period, and 5 at
advance (`ad`), once per time step. Late checks are almost all
cross-component (K7, K8, K10 joins), plus time-series coverage, which fails
only during integration at `ad` (`TimeSeries.f90:552-601`). A spec-level
validator has the whole simulation at load and could run all of them up
front.

## Gap list

Report only. No edits to devtools or modflow6.

**Only in Fortran, and expressible in the DFN as it stands:**

- **Field `when` on the MST arrays:**
  - `bulk_density`, `distcoef` and `sp2` under `sorption`;
  - `decay` and `decay_sorbed` under the decay options;
  - `sp2` only for Freundlich or Langmuir, which needs a value test, not
    just presence.

  The same applies to the GWE counterparts. The `schema` tags from the
  option classification name exactly these options.
- `pk` on the SSM SOURCES `pname` (`tsp-ssm.f90:820`), MVR PACKAGES
  (`gwf-mvr.f90:917`), and the LAK/MAW/SFR "specified more than once" checks
  where they aren't already marked.
- `valid` for string enums that are checked in Fortran but not declared:
  - SFR `cprior`;
  - LAK `claktype` and `couttype`;
  - MAW `condeqn`;
  - IMS `complexity`, `under_relaxation`, `no_ptc_option` and
    `rclose_option`.

  Their descriptions list the values, but there's no `valid` key. 32 `valid`
  keys exist, mostly on OC `rtype`, the advection scheme and sorption.

**Only in Fortran, needing new DFN syntax:**

- **Numeric domains** (K2). This is the biggest gap by count: the "sign/value"
  regex cluster alone has 165 sites. A `range` or `min`/`max` key, with
  open/closed bounds, would cover `> 0`, `≥ 0` and `[0, 1]`. Row-level
  comparisons need an expression: `THTS > THTR`, `DTMIN < DTMAX`,
  `telev ≥ belev`.
- **Option coherence** (K5): a `conflicts`/`requires` key on options. NPF
  alone has 7 such rules (`gwf-npf.f90:1715-1757`).
- **Block-level `when`:** `ANGLEDATA` under `NON_VERTICAL_WELLS`, and
  `DIVERSIONS` only when some reach has `ndv > 0`.
- **Co-occurrence and requiredness of components** (K8a). `multi = false`
  says at most one, but nothing says at least one. Examples: DIS is required
  in every model, IC and NPF in GWF, DFW in OLF. Nothing expresses MVR ⇒ MVT
  or LKT ⇒ LAK.
- **Cross-component dimensions:** SPC `MAXBOUND` must cover the flow
  package's bounds (`TspSpc.f90:347`).
- **Key kinds on roles:** the SPC↔SPCA pairing is enforced in Fortran
  (`TspSpc.f90:360-380`) and only implied by DFN naming. This is H4 from
  the directions doc, now confirmed against MF6.

**Only in prose (mf6io, hand-written; 209 rule-like sentences, 7 checked):**

- DISV vertices in clockwise order (`gwf/disv.tex`): not enforced.
- A TAS file can be associated with only one package (`gwf/tsi.tex`): no
  check found.
- LKT needs a corresponding LAK, and the advanced transport packages take
  their flow package's name by default (`gwt/sft.tex`, `lkt.tex`). These
  are enforced indirectly, through the name lookup (`gwt-sft.f90:206`).
- PRT/GWT through FMI need particular GWF output (`SAVE BUDGET ALL`, and
  heads for all layers). FMI checks part of this (`tsp-fmi.f90:676-688`).
  The rest is a constraint on another run's output.

**Only in the DFN:** none found in the sample. The DFN's `pk`/`fk`/`shape`
rules all have Fortran counterparts where I looked. I didn't check this
systematically.

**Catalog-adjacent:** time-series coverage is checked only at `ad`. A
spec could state it as `TS times ⊇ simulation span`, unless
`extendToEndOfSimulation` applies, and check it up front.

## For step 2 (DDL slice)

1. Put **dimensions in as first-class values**. K3 is mostly
   `count(rows) = dim` or `≤ dim` (7 of 10 relate configuration to data).
   The question in the directions doc about whether `MAXBOUND` is layout or
   identity becomes concrete: `MAXBOUND` is a CHECK bound on a table's row
   count. Bound identity comes from the row key (`<=maxbound` as a PK
   domain), not from the dimension.
2. **The grid is a table everyone joins against.** K10 assertions join
   package rows to cell geometry. The DDL slice should include the grid as
   a relation (cell → top, bot, area, idomain). Model it as a parameter,
   not per package.
3. **Use a scope chain for `when`** (own options → model → binding
   parameters), and drop `MODELNAMES` in favour of a binding parameter.
4. **Use CHECK on the options row for K5.** A component's options form a
   one-row table, so option coherence is a row-level CHECK. This confirms
   the config/data axis: configuration constraints are schema-level and
   can be checked without data.
5. **Expect the misfits:** monotone row order (LAK table stages, PRP release
   times, PXDP), SFR acyclicity, and geometric predicates (point in cell,
   clockwise). These need functions or recursive queries. Keep them as
   named checks, the way rules work today.
6. **Lens-domain constraints (L) go with the lens**, not in the logical
   schema. They're the step 5 partiality conditions.

## Limits

- The regex clusters agree with hand labels only 31% of the time (49 of
  158). Don't read the cluster counts as kind counts. They're message
  shapes ("must be > 0" covers K2 and K10).
- The sample is purposive: families were chosen in advance, and within
  each family I chose instances for variety. A random sample of ~50 would
  give per-kind proportions for MF6 as a whole, if those are needed.
- Of the mf6io prose, I checked 7 of 209 hand-written rule sentences in
  detail. The 799 rule sentences in the generated `mf6ivar` duplicate DFN
  descriptions. They're the "only in description text" category, and I
  didn't parse them.
