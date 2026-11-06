# Constraint audit

DFNs from the modflow-devtools `v2.0.0.dev3` snapshots, MF6 source at
`8aad7bc4a5`. Part of the spec
research; terms (layout, logical, lens, binding, option labels) are defined
in [overview.md](overview.md#concepts).

## Question

What kinds of rule must a valid MF6 simulation satisfy, and for each kind:

- **where is it enforced**: in the DFN, in MF6's Fortran, in the mf6io
  docs only, or some combination?
- **which level does it belong to**: layout, logical, or runtime?
- **could the DFN express it today**, and could a logical spec built on
  database constructs (CHECK, keys, assertions) express it?

This is a taxonomy with coverage numbers, not a list of every check.

Three things hang on the answer:

- **The spec is thin on constraints.** The dev3 DFNs have 50 `when` keys
  and 32 `valid` keys. MF6 has about 1,280 error and warning sites. Most of
  the input contract exists only in Fortran.
- **It tests the layering a second time.** If a rule triggered by a layout
  option constrains logical content, the layout/logical split leaks.
  That's the constraint-level counterpart of a mixed option.
- **It sets the requirements for the DDL slice** (overview step 3): which
  database constructs a logical layer needs, and what doesn't fit any.

It also has practical uses: a source for generated flopy4 validation, and a
concrete list of DFN gaps for MF6 developers ([dfn-gaps.md](dfn-gaps.md)).

## Findings

- **The layering holds for constraints.** No rule triggered by a layout
  option constrains logical content. The rules that look like they cross
  levels say where a layout is *defined*: `READASARRAYS` can't be combined
  with `SURF_RATE_SPECIFIED`, because the array form has nowhere to put
  PETM0. Those belong with the layout (they're its partiality conditions),
  not with the model.
- **Conditional fields and package co-occurrence are one construct.**
  "`boundname` only with `BOUNDNAMES`" and "MVR needs MVT" have the same
  form: a condition implies that something is present or absent. What
  differs is where the condition's names come from: the component's own
  options, its sibling packages, or its binding. So `when` could cover
  both, if its names resolved through those scopes in turn. MVR's
  `MODELNAMES` option exists only to restate the binding, which supports
  overview H3.
- **Most of the contract is in Fortran only.** The DFN fully expresses 20
  of the 166 sampled rules and partly expresses 26 more. It covers grammar,
  shapes, required fields, and keys within a file. It covers almost no
  numeric ranges (1 of 27), option conflicts (0 of 14), package
  co-occurrence (1 of 19), time rules (0 of 7) or geometric consistency
  (0 of 18).
- **Database constructs cover most of what's logical.** CHECK, foreign
  keys, primary keys and NOT NULL cover 94 of the 166. Multi-table
  assertions cover 39 more; most of those are joins against the grid
  (`TOP > BOT`, lake bed above cell bottom). Only 5 logical rules fit no
  construct: ordered sequences, stream-network acyclicity, and
  point-in-cell geometry.
- **MF6 checks some rules late.** 19 sampled checks run per stress period
  or per time step, not at load, and nearly all of them are
  cross-component. A spec-level validator has the whole simulation at load
  and could run them all up front.

## The kinds

The final taxonomy, roughly from local to global. The codes are short
handles used in the tables below and in the CSV.

| Code | Kind | Meaning | Examples |
|---|---|---|---|
| K1 | lexical / format | the file's grammar, and ordering conventions | keywords, record syntax, block order, `OPEN/CLOSE`; period numbers increasing, DISU `JA` with self first |
| L | lens domain | where a layout is defined at all | `READASARRAYS` excludes `SURF_RATE_SPECIFIED` and `NSEG > 1`; no TAS on DISU; binary list input has no text columns |
| K2 | type and domain | one value's type and range | enums, `K > 0`, `0 ≤ SY ≤ 1`; within a row, `THTS > THTR` |
| K3 | shape and dimension | sizes, and counts against dimensions | arrays sized by the grid; list rows ≤ `MAXBOUND`; `NCVERT` = vertex count |
| K4 | conditional presence | an element exists only under a condition | aux columns = `AUXILIARY` names; boundname only with `BOUNDNAMES`; sorption arrays only with `SORPTION` |
| K5 | option coherence | options that exclude or require each other | NPF's seven rules (`gwf-npf.f90:1715-1757`) |
| K6 | keys and uniqueness | no duplicates | unique package names; "specified more than once" |
| K7 | referential | a value names something that must exist | cellid in the grid with `IDOMAIN > 0`; boundnames, TS names, MVR packages, exchange models |
| K8a | co-occurrence | if component A is present, B must (or must not) be | MVR needs MVT; LKT needs LAK; CSUB requires `SS = 0` in STO; XT3D excludes GNC; OLF needs DFW |
| K8b | consistency between bound components | equalities across components the binding connects | GWF and GWT grids identical; exchanged models share a solution; GWT-GWT exchange data mirrors GWF-GWF |
| K9 | temporal | rules about periods and times | period numbers ≤ `NPER`; TS times cover the run |
| K10 | structural / physical | geometry and graph consistency | `TOP > BOT`; UZF area ≤ cell area; SFR connections reciprocal; upstream fractions sum to 1 |

L wasn't in the starting taxonomy. Lens-domain rules look like option
coherence (K5), but they're the partiality conditions of a lens
([overview](overview.md#lenses)), which MF6 enforces. They belong with the
lens. A converter between layouts (overview step 6) should report exactly
these.

K8 split in two during the audit. K8a has the same form as `when`. K8b
doesn't: those are equality joins.

K10 turned out to be mostly **joins against the grid**, not a separate
physics layer: `TOP > BOT`, SURFDEP ≤ cell thickness, lake `belev` ≥ cell
bottom, UZF area ≤ cell area, release point in cell, MAW screen vs. cell.
The rest are graph properties of one table (SFR reciprocity, upstream
fractions, acyclicity). Only 1 of 18 is runtime (time step too small).

## Method

### Sources

1. **DFN snapshots.** A script over every constraint-bearing key: `shape`,
   `when`, `valid`, `optional`, `pk`, `fk`, file `component`,
   `[observations]` and so on. Each key is mapped to a kind.
2. **MF6 source.** Every `store_error` and `store_warning` site, with the
   nearest message literal (messages are usually built a few lines above
   the call with `write(errmsg, ...)`), clustered by message shape ("out of
   range", "not found", "duplicate", ...). Then a hand-labelled sample by
   component family: all the generic IDM checks, then one or two packages
   per family (GWF: DIS/DISU, NPF, SFR, MVR; GWT: SSM, FMI; PRT: PRP;
   SWF/CHF; exchanges; IMS; TDIS/ATS). A family stopped when three
   packages in a row added no new kind.
3. **mf6io docs.** Prose rules ("must", "only if", "cannot") checked
   against the DFN and Fortran, to catch rules enforced nowhere.
4. **The option labels** from
   [option-classification.md](option-classification.md), to classify what
   each conditional rule is triggered by.

### What each sampled rule records

| Column | Values | Meaning |
|---|---|---|
| kind | K1–K10, L | from the table above |
| level | layout, logical, runtime | runtime means it depends on simulated state or numerics, not input alone |
| arity | field, row, table, component, multi, sim | how much input the rule spans |
| config/data | config, data, cfg-data | whether it constrains configuration (options, dimensions), data (arrays, rows), or relates the two (row count ≤ `MAXBOUND`) |
| trigger | unconditional, an option (with its label), a dimension, another component's presence, the binding | what switches the rule on |
| DFN | yes, partly, no | expressible with dev3 DFN keys today |
| DDL | CHECK, PK, FK, NOT NULL, assertion, none | the database construct a logical spec would use |
| severity | error, warning | |
| checked | load, `ar`, `rp`, `ad` | the MF6 phase that checks it: load, allocate-and-read, once per period, once per time step |

### Predictions, written before looking

- K1 is layout. K2–K9 are logical. K10 is mostly logical, some runtime.
- A logical rule triggered by a layout option would be a leak.
- K4 is triggered by `schema` options, K8 by `binding` options or context.
  If both can be written in one form, that supports one construct for
  `when` and binding parameters.
- The DFN covers most of K1–K3 and little of K5–K10.
- K2 maps to CHECK, K4 to NOT NULL, K6 to primary keys, K7 to foreign keys,
  K8 to assertions. K9 and K10 are the likeliest misfits.

All held, except that K10 fits better than expected (grid joins), and L
and the K8 split were new.

### Scope

In: input rules for all model types, exchanges, solutions and utilities in
dev3. Out: convergence and other numerics failures, I/O errors (file not
found, unit conflicts), and internal assertions guarding programming
errors. Those are counted as "not input" so the totals reconcile.

## Results

### Counts per kind

From the hand-labelled sample of 166 rules (159 MF6 sites and 7 rules found
only in mf6io prose). The sample was chosen for coverage, so the
proportions describe the sample, not MF6 as a whole.

| Kind | n | Level | DFN yes / partly / no | Typical arity | Config/data | DDL |
|---|---|---|---|---|---|---|
| K1 lexical / format | 10 | layout | 3 / 1 / 6 | row, field | data | none (grammar) |
| L lens domain | 6 | layout | 0 / 0 / 6 | component, multi | config | none (encoding domain) |
| K2 type and domain | 27 | logical | 1 / 3 / 23 | field (22), row (4) | data 18, config 9 | CHECK |
| K3 shape and dimension | 10 | logical | 2 / 5 / 3 | table | relates config to data: 7 | CHECK (count = dim) |
| K4 conditional presence | 19 | logical (1 layout) | 5 / 1 / 13 | component | data | NOT NULL / conditional |
| K5 option coherence | 14 | logical 9, layout 4, output 1 | 0 / 2 / 12 | component | config 13 | CHECK on the options row |
| K6 keys and uniqueness | 12 | logical | 3 / 1 / 8 | table, multi | data | PK / UNIQUE |
| K7 referential | 21 | logical | 5 / 12 / 4 | multi (11) | data 13, config 7 | FK |
| K8 co-occurrence and consistency | 19 | logical | 1 / 0 / 18 | multi (18) | config 16 | assertion |
| K9 temporal | 7 | logical | 0 / 1 / 6 | multi, field | data | FK (period), ordering |
| K10 structural / physical | 18 | logical | 0 / 0 / 18 | multi (9), row | data 18 | assertion (join on grid) |
| not input | 3 | runtime | — | — | — | — |

Two patterns stand out in the config/data column. Option coherence (K5)
and co-occurrence (K8) are almost entirely configuration, so they can be
checked without reading any data. Shape rules (K3) mostly relate
configuration to data (row count against `MAXBOUND`).

### Layering

Rules sorted by what switches them on:

| Trigger | Layout rules | Logical rules |
|---|---|---|
| unconditional | 11 | 64 |
| a dimension | — | 17 |
| a logical option | — | 17 |
| a value in the same row (`obstype`, `ctype`, `condeqn`) | — | 4 |
| another component's presence | — | 12 |
| the binding | 4 (lens domain) | 21 |
| a layout option | 7 | **0** |
| an output option | — | 2 |

- **No logical rule is triggered by a layout option.** One candidate,
  `AUXMULTNAME` must name an aux column (`BoundaryPackage.f90:1331`), is
  triggered by an option the classification labels logical (a dynamic
  derivation). And any option that names a column carries a reference like
  this, whatever its level.
- **Layout rules triggered by layout options** are coherence rules within
  the layout: `K22OVERK` requires K22; `FLOW_REDUCTION_LENGTH` requires
  `AUTO_FLOW_REDUCE`; `UNIT_CONVERSION` excludes `LENGTH_`/
  `TIME_CONVERSION`; `MODELNAMES` must match the exchange binding; and the
  lens-domain rules.
- **Some output options have logical prerequisites.** DFW `SAVE_VELOCITY`
  requires `ANGLDEGX` in the discretization (`swf-dfw.f90:1350`), and
  DISU's `VERTICAL_OFFSET_TOLERANCE` parameterizes a K10 check. A run
  directive can't change results, but it can need logical data to carry
  out. That's harmless for the split.

### Conditional presence and co-occurrence

The DFN's `when` key has 50 uses today, testing only three options:

| Option | Uses | Label |
|---|---|---|
| `boundnames` | 46 | logical, schema |
| `modelnames` | 3 | layout |
| `surf_rate_specified` | 1 | logical, schema |

MF6 conditions on much more, across K4 and K8a:

| Condition over | Examples | Expressible as `when` today? |
|---|---|---|
| own options | sorption → `BULK_DENSITY`, `DISTCOEF`, `SP2`; decay → `DECAY`, `DECAY_SORBED`; `NON_VERTICAL_WELLS` → ANGLEDATA block; `BOUNDNAMES` → boundname | for fields, yes; there's no block-level `when` |
| own dimensions | `NTABLES > 0` → TABLES block; `NRELEASETIMES > 0` → RELEASETIMES block | no, but these are really K3 counts: `count(rows) = dim` |
| a value in the same row | `obstype` → ID2 required, boundname forbidden; `ctype` → `connlen > 0`; `cprior` → divflow range | already modelled, as union arms |
| other fields present | ANGLE2 → ANGLE1; K22 → ANGLDEGX in DIS | no |
| sibling components | MVR active → MVT; CSUB → STO `SS = 0`; XT3D → no GNC; LKT → LAK | no |
| the binding row | exchange-bound MVR → `MODELNAMES`; SSM `pname` → a flow package; SFT's name defaults to SFR's | no |

The form is the same throughout: *condition ⇒ element present (or
absent)*. Only the scope of the condition's names varies. Resolving them in
a chain (own options and dimensions, then the model's components, then the
binding's parameters) would let one `when` construct cover every row of
this table. Binding parameters (overview H3) then need to be names `when`
can test, not a second conditional construct.

Three cases sit right on the boundary between a component's own options and
its binding:

- `MODELNAMES`, an option MF6 requires to agree with the binding context
  (`gwf-mvr.f90:785-798`). With a binding parameter it goes away: the
  mover's `mname` column is filled from the binding when not written.
- `FLOW_PACKAGE_NAME`, an option that overrides a default the binding
  supplies.
- `MOVER`, an option that gates a role other components refer to.

K8b (consistency between bound components) doesn't fit this form. It
needs join assertions.

### DFN coverage

Constraint-bearing DFN keys, over all 146 components:

| Kind | DFN keys | Rows |
|---|---|---|
| K1 | `index`, `netcdf`, `layered`, `case_sensitive`, `write_if_empty` (and the grammar itself) | 323 |
| K2 | `valid` (32, all enums), `allow_zero` (2); no numeric ranges | 34 |
| K3 | `shape` 348 (grid 212, `<=dim` 56, aux 44, local 36); `dims` 253 | 601 |
| K4 | required fields (no `optional`) 332, `when` 50 | 382 |
| K6 | `pk` 55 | 55 |
| K7 | `fk` 58 (9 cross-component), `time_series` 173, `model` 13, `dynamic` 7 | 251 |
| K8 | `parent` 145, `multi` 145, `component` 136, `component_ftype` 10 | 436 |
| K9 | `fill_forward` 70 | 70 |
| K5, K10 | none | 0 |
| (not a constraint) | `default` 93: what absence means | 93 |

MF6 has 1,279 sites: 1,203 errors and 76 warnings. Another 398
`store_error_filename`/`store_error_unit` calls only add a file name to an
error and aren't counted. By message shape, about 13% are not input
(I/O, programming errors, numerics).

### When MF6 checks

Of the sampled sites, MF6 checks 118 at load, 29 at allocate-and-read
(`ar`), 14 once per stress period (`rp`) and 5 once per time step (`ad`).
The late checks are almost all cross-component (K7, K8, K10 joins), plus
time-series coverage, which fails only during integration at `ad`
(`TimeSeries.f90:552-601`).

## Carried into the DDL slice

Where each kind should finally live is in [factoring.md](factoring.md), which narrows items 3 and 4
below for what gets authored in the DFN. These are folded into the plan in
[overview.md](overview.md#step-3-the-ddl-slice):

1. **Dimensions as first-class values.** K3 is mostly `count(rows) = dim`
   or `≤ dim`. `MAXBOUND` is a CHECK bound on a table's row count; a
   bound's key comes from the row, and includes the period (`<=maxbound` as
   the domain of the position), not from the dimension.
2. **The grid as a table everyone joins against** (cell → top, bot, area,
   idomain), supplied as a parameter rather than per package.
3. **A scope chain for `when`** (own options → model → binding
   parameters), with `MODELNAMES` replaced by a binding parameter.
4. **CHECK on the options row for K5.** A component's options form a
   one-row table, so option coherence is a row-level CHECK, checkable
   without data.
5. **Named checks for the misfits:** monotone row order (LAK table stages,
   PRP release times, PXDP), SFR acyclicity, geometric predicates (point
   in cell, clockwise vertices). These need functions or recursive queries.
6. **Lens-domain rules (L) go with the lens**, not in the logical schema.

## Limits

- The message-shape clusters agree with the hand labels only 31% of the
  time (49 of 158). Don't read cluster counts as kind counts: "must be
  > 0" covers both K2 and K10.
- The sample is purposive. Families were chosen in advance, and instances
  within each for variety. A random sample of ~50 would give per-kind
  proportions for MF6 as a whole, if those are needed.
- Of the mf6io prose, 7 of 209 hand-written rule sentences were checked in
  detail. The 799 rule sentences in the generated `mf6ivar` docs duplicate
  DFN descriptions and weren't parsed.
- "Only in the DFN" (a DFN rule with no Fortran counterpart) wasn't checked
  systematically. None turned up in the sample.

## Data

In [data/constraint-audit/](data/constraint-audit):

| Script → output | What |
|---|---|
| `dfn_pass.py` → `dfn-constraints.csv` | 2,245 constraint-bearing DFN keys, one row each, with inferred kind |
| `mf6_sites.py` → `mf6-checks.csv` | all 1,279 `store_error`/`store_warning` sites with message and message-shape cluster |
| `sample.py` → `mf6-sample.csv` | the 166 hand-labelled rules; the labels live in the script |

To reproduce:

```
python dfn_pass.py <devtools>/autotest/dfns/__snapshots__/v2.0.0.dev3 \
    ../option-classification/options-labelled.csv <out>
python mf6_sites.py <modflow6>/src <out>
python sample.py <out>
```
