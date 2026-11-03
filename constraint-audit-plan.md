# Constraint audit: plan

Working notes, 2026-11-03. Follows `option-classification-results.md`. Serves as
the requirements pass for step 2 (DDL slice) in `discussion-287-directions.md`.

## Goal

List the kinds of constraint a valid MF6 simulation must satisfy, and for each
kind record:

- **where it lives:** the DFN, MF6 Fortran, or both;
- **which level it belongs to:** layout, logical, or runtime;
- **whether the DFN can express it today**, and whether a DDL-style logical
  spec could.

This is a taxonomy with coverage numbers, not a full list of every check.
Instances are sampled until new ones stop producing new kinds.

## Why

- **The spec is thin on constraints.** dev3 snapshots have 50 `when` and 32
  `valid` keys. MF6 has 1,594 `call store_error` sites in 174 files (rough
  count; it includes `store_error_filename` and repeats). Most of the input
  contract exists only in Fortran.
- **It tests the layering a second time.** Each constraint should belong to
  one level. A constraint that spans levels is the constraint-level
  counterpart of a mixed option, e.g. a `when` that tests an encoding
  option.
- **It sets the requirements for step 2.** The kinds map onto DDL constructs
  (CHECK, NOT NULL, PRIMARY KEY, FOREIGN KEY, multi-table assertions). What
  doesn't map is the interesting result.
- **It tests the `when` = binding hunch.** If conditional presence and
  component co-occurrence have the same form, `when` and binding parameters
  may be one construct with two sources (component options vs. context).
- **Practical uses:** a source for generated flopy4 validation, and a
  concrete DFN gap list for MF6 developers.

## Taxonomy (provisional, to revise from the evidence)

Ordered roughly from local to global.

| # | Kind | Examples |
|---|---|---|
| K1 | lexical / format | keywords, record syntax, block order, file-reference forms, `OPEN/CLOSE` |
| K2 | type and domain | enums, `K > 0`, `0 ≤ SY ≤ 1`, integer vs. real |
| K3 | shape and dimension | arrays sized by grid dims, list rows ≤ `MAXBOUND`, `NCVERT` = vertex count |
| K4 | conditional presence | aux columns = `AUXILIARY` names; boundname column only with `BOUNDNAMES`; `when` |
| K5 | option coherence | options that exclude or require each other |
| K6 | keys and uniqueness | unique package names; duplicate cellids allowed or not (varies by package) |
| K7 | referential | cellid in grid and `IDOMAIN > 0`; boundnames, TS names, MVR packages, exchange models exist |
| K8 | co-occurrence and cardinality | one DIS per model; GWF needs NPF and IC; TVK needs NPF; GWT needs FMI or a GWF-GWT exchange; MVR needs `MOVER`; each model in one solution |
| K9 | temporal | period numbers ascending and ≤ `NPER`; TS times cover the run; ATS periods valid |
| K10 | structural / physical | `TOP > BOT`; DISU `JA` symmetric, `IHC` consistent; SFR/LAK connectivity; vertex geometry |

Expect K10 to split: some checks are model content (`TOP > BOT`), some are
numerics (thin-cell warnings), and some guard MF6's own assumptions.

## Attributes recorded per kind (and per sampled instance)

- **level:** layout / logical / runtime-only. "Runtime-only" means it
  depends on simulated state or numerics, not on input alone.
- **arity:** one field, one row, one table, one component, several
  components, the whole simulation.
- **config/data:** whether it constrains configuration (options,
  dimensions), data (arrays, rows), or relates the two (e.g. `MAXBOUND`
  vs. row count). This is the second axis from the earlier discussion.
- **trigger:** unconditional, or conditional on an option, a dimension, or
  another component's presence.
- **where:** DFN key (`shape`, `when`, `valid`, `optional`, file
  `component`, `[observations]`), MF6 file:line, mf6io prose, or a
  combination.
- **DFN-expressible today:** yes / partly / no.
- **DDL-expressible:** which construct, or "no" with a reason.
- **severity:** error vs. warning (MF6 has `store_warning` too).
- **checked when:** IDM load, `df`/`ar`, `rp` (per period), or `ad` (per
  step). Late checks suggest constraints that depend on data not available
  at load.

## Sources

1. **DFN snapshots** (devtools `autotest/dfns/__snapshots__/v2.0.0.dev3/*.toml`):
   `shape`, `when`, `valid`, `optional`, `default`, file `component`,
   `[observations]` arms, and the block structure itself.
2. **MF6 source** (`~/dev/modflow6`, record the commit): `store_error`,
   `store_warning` and `ustop` sites, plus the error messages around them.
   Generic IDM checks (`src/Utilities/Idm/`) are mostly K1–K3 and apply to
   everything. Package checks are where K4–K10 live.
3. **mf6io docs** (`doc/mf6io`): prose rules ("must", "only if", "cannot")
   that neither of the above encodes. Used to catch rules that are enforced
   nowhere.
4. **The option labels** (`option-classification/options-labelled.csv`):
   the `schema` and `binding` tags should line up with K4 and K7/K8
   triggers.

## Passes

### Pass 1: DFN, mechanical

Script over the snapshots. One row per constraint-bearing key. Columns:
component, block, field, key, value, and inferred kind (shape → K3,
`when` → K4, `valid` → K2, file `component` → K8, ...). Then tally by kind
and component. Also list each `when` condition and what it tests: a `schema`
option, an encoding option, or something else. That's the first layering
check.

Output: `constraint-audit/dfn-constraints.csv` and a short summary.

### Pass 2: MF6 checks, sampled

1. Extract all `store_error`/`store_warning` sites with file, line,
   enclosing routine and the nearest message literal. Messages are usually
   built a few lines above the call with `write(errmsg, ...)`. Script it
   and accept some misses.
2. Cluster by normalised message ("out of range", "not found", "must be
   greater than", "duplicate", ...). Counts per cluster show where the bulk
   is.
3. Read by component family: all generic IDM checks, then one or two
   packages per family (GWF: DIS/DISU, NPF, SFR, MVR; GWT: SSM, FMI; PRT:
   PRP; SWF/CHF; exchanges; IMS; TDIS/ATS). Label each read instance with
   a kind and the attributes above.
4. Stop a family when three packages in a row add no new kind or attribute
   combination. Extend if one does.

Output: `constraint-audit/mf6-checks.csv` (all sites, clustered) and
`constraint-audit/mf6-sample.csv` (labelled sample).

### Pass 3: docs, targeted

Grep mf6io for "must", "only", "cannot", "required", "not allowed". For
families read in pass 2, check each rule against the DFN and Fortran rows.
Record rules found only in prose.

### Pass 4: classify and cross-check

Merge into one table of kinds with counts, levels, coverage, and DDL
mapping. Run the checks below.

## Checks and expected findings

Fixed before looking, so the results can surprise us:

- **Layering:** K1 is layout. K2–K9 are logical. K10 is mostly logical,
  some runtime. A logical-kind constraint whose trigger is a layout option
  is a leak. So is a layout check that depends on another component's
  data, except for the cross-component and computed lenses we already know
  about.
- **`when` vs. binding:** K4 triggers should be `schema` options. K8
  triggers should be `binding` options or context. If K4 and K8 instances
  can be written in one form, record that as evidence for the unified
  construct.
- **Coverage:** most of K1–K3 should be in the DFN, and most of K5–K10
  should not. Report the fraction per kind.
- **DDL fit:** K2 → CHECK, K4 → NOT NULL/conditional, K6 → PRIMARY KEY,
  K7 → FOREIGN KEY, K8 → multi-table assertions or binding rules, K3 →
  needs dimensions as first-class values. K9 and K10 are the likeliest
  misfits.

## Scope

- **In:** input constraints for all model types, exchanges, solutions and
  utilities in dev3.
- **Out:** convergence and other runtime numerics failures, I/O errors
  (file not found, unit conflicts), internal assertions that guard
  programming errors rather than input. Count these in a "not input"
  cluster so the totals reconcile, but don't classify them.
- **No edits** to devtools, modflow6 or modflowapi. Gaps go in a list.
  Commit nothing. Post nothing to GitHub.

## Done when

- the kinds table has counts, level, DFN coverage and DDL mapping for each
  kind;
- the `when` triggers are classified, with a verdict on `when` vs. binding;
- the layering check has a written result, listing any leaks;
- there's a gap list: rules that are only in Fortran, only in prose, or
  only in the DFN;
- findings to carry into step 2 are listed;
- `discussion-287-directions.md` gets a one-line pointer. Check for the vim
  swap file first.
