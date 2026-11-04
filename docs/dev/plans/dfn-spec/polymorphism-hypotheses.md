# #287: where the contours point

Working notes, 2026-11-02. Not for posting as is. Builds on
`discussion-287-comment.md` (draft), `discussion-relational-spec-draft.md`,
[`schema-polymorphism.md`](schema-polymorphism.md), [`reference-fields-notes.md`](../archive/reference-fields-notes.md) and devtools
`relational-model-plan.md`.

The draft sorts what we've found into three kinds of polymorphism: sum types
(variants), interfaces (roles) and maybe parametric (grids), plus rules for
name resolution. Taking each a step further, three hypotheses come out. They
reinforce each other, and each changes something in the tentative designs.

1. **Almost every sum type in MF6 input is a layout choice, not a logical
   one.** The logical layer may need no sum types beyond enums and the grid
   type.
2. **List and array variants differ in whether bounds have identity**
   (entities vs. fields). That difference, not the variant itself, is what
   leaks into keys. Key *types* on roles handle it without declaring
   variants.
3. **A component is parameterized by its binding context.** Rules are
   mostly formal parameters that the binding row fills in. This collapses
   most rules, CellID `model = "1"/"2"`, OBS, SPC, GNC and grid dependence
   into one construct that many components would use.

---

## 1. Most sum types are layout

### Tags sit at every level of nesting

Every variant we've found is chosen by a tag. Where the tag sits:

| Level | Tag | Chooses | Logical or layout? |
|---|---|---|---|
| binding row | ftype (`CHD6` vs `CHDG6`) | component variant | layout |
| file options | `READASARRAYS` | component variant (RCH vs RCHA) | layout |
| field | `CONSTANT` / `INTERNAL` / `OPEN/CLOSE` / `NETCDF`, `LAYERED` | array encoding / data source | layout |
| row | union keyword (`STATUS`, `RATE`, `DIVERSION`, ...) | which attribute a row sets | layout (see below) |
| model | discretization type (DIS / DISV / DISU) | the grid's domain | **logical** |

The array control records are a sum type flopy4 already handles without
ever calling it polymorphism. `NETCDF` belongs in the same row. It's another
answer to "where are this array's values?", not a schema condition. That
corrects the draft, which puts `NETCDF` with `when` and MOVER as
option-conditional schema.

### Union records are attribute updates

SFR's period block is a log of updates to reach attributes. `ifno STATUS
INACTIVE` and `ifno RATE 0.1` set two columns of one logical row,
`(reach, kper) → status, rate, stage, ...`. The keyword names the column.
That's entity-attribute-value encoding of a sparse wide table. The arms with
their own key (`DIVERSION idv divflow`) set columns of a child table keyed
by `(reach, idv)`.

So the relational plan's "union record convention" question (variant tables,
sparse columns or EAV) has an answer. Logically the columns are sparse. In
layout the file uses EAV, and the keyword is the attribute name. Union
records then aren't a logical sum type at all, and "databases don't have sum
types" stops being a gap.

This needs checking per case. OC's `SAVE HEAD ALL` / `PRINT BUDGET STEPS 1 3`
reads more like `(action, rtype) → step selection`, which still fits a
table. MAW `connstatus` and the LAK/UZF period settings look like SFR. A
counterexample would be an arm whose fields don't belong to one table.

### Periods are the same pattern

MF6 carries a period block forward until the next one. That's a delta
encoding of a step function over periods. The relational plan's "sparse
plus fill rule vs. dense" question is the same as for union records: the
logical layer holds the state (a step function), and the layout writes
changes. Union records and period blocks are both **deltas in layout over
state in logic**. One convention can cover both.

### Logical sum types left over

- Enums (`status`, `connection type`, ...). These are plain column domains.
- The grid type, which changes the domain every array is indexed by.
  Section 3 treats that as a parameter, not a variant.

If the DDL slice confirms this, the logical layer needs no sum types, and
the list of candidate languages gets simpler. SQL DDL, Frictionless and our
own TOML all become viable.

### What "functionally equivalent" means

#287 calls RCH and RCHA functionally equivalent. That's only partly true,
and saying how makes it useful:

- RCHA → RCH always works. Each column's value becomes a bound at the
  `irch` layer.
- RCH → RCHA works only when each column has at most one entry, all on one
  layer per column, with no boundnames, no per-bound aux the array can't
  hold, and nothing referring to bound numbers. MF6 lists allow several
  entries in one cell.
- EVT → EVTA also needs `nseg = 1`, since EVTA has no segments (check).

Equivalence holds for the hydrologic effect, the source term per cell per
period. It doesn't hold for *identity*: bound numbers, boundnames,
observations, movers and SPC all refer to bounds. In lens terms, each layout
is a partial lens onto one logical relation. Conversion goes through the
relation and is defined where both lenses are. flopy4 can implement it once,
not once per variant pair, and its error messages fall out of the
conditions above.

---

## 2. Entities vs. fields

The list/array split is really this:

- **List variant: a collection of entities.** Each bound has identity (its
  number, optionally a boundname). It can be named, observed, moved, or
  given concentrations by SPC.
- **Array variant: a field over the grid.** A value per column (or per
  cell). Its only identity is the cell.

Roles attach to identity, so RCH has `bound` and RCHA doesn't. But SPCA
still refers to RCHA, through the grid domain: an SPCA array is keyed by
column, the same as RCHA's. So **both SPC and SPCA are "keyed by the
target's key"**. They differ only in what that key is:

| Referrer | Target | Shared key |
|---|---|---|
| SPC `bndno` | RCH, WEL, SFR, LAK, ... | the target's bound number (`<=maxbound`, `ifno`, `<=nlakeconn`, ...) |
| SPCA arrays | RCHA, EVTA | the target's column (`ncpl`) |

In PL terms, a role is a trait, and its key is an **associated type**. Each
`[keys]` entry is a trait impl that states the key path. If the role also
states what kind of key it is (bound number vs. grid column), then
"SPCA binds only to array variants" is just a key-type mismatch, caught by
the ordinary check. **No `variant_of` is needed for checking.**

`variant_of` (or `layout_of`) could still help docs group the alternatives,
but it no longer carries validation.

This also says where roles should be *defined*. Today a role exists only
through its impls. Target-side declaration is what keeps the set open
(Haskell instances and Rust impls work the same way), but the trait itself
needs one home: its key kind, who may refer to it, and its prose. That
answers the relational plan's open question about first-class roles: yes, a
central `[roles.*]` declaration, with per-component `[keys]` as impls.

---

## 3. Components are parameterized by their binding

### Rules as parameters

The draft calls rules "closer to dynamic scope". A better name: **a file is
a parameterized component, and the row that binds it supplies the
arguments.** That's an ML functor or a constructor's dependency injection.
Once a parameter is declared, a reference to it is lexical again.

| Component | Parameter | Supplied by | Today |
|---|---|---|---|
| `utl-spc` / `utl-spca` | `target`: a package playing `bound` | SSM `fileinput` row (`pname`) | rule `ssm_package` |
| `gwf-mvr` | `models`: one or two models | model namefile (this model) or exchange (`exgmnamea`, `exgmnameb`) | rule `exchange_models` |
| `gwf-gnc` | `models`, as for MVR | model or exchange | CellID `model = "1"/"2"` |
| exchange cellids | `models` | the exchange's own name columns | CellID `model = "1"/"2"` |
| `utl-obs` | `target`: its parent package | the package's `OBS6 FILEIN` | none (see below) |
| `utl-ts` / `utl-tas` | `target`: its parent package | the package's `TS6` / `TAS6` | none |
| every package | `grid`: its model's discretization | the model | implicit in cellid encoding |

Every child file is in this table. That clears the bar #405 set for
syntax: a construct used by enough fields that a second consumer could
implement it from the spec alone. Rules failed that test one at a time.
Together, as parameters, they pass it.

It also matches the relational plan's observation #1, that "a rule is a
parent key or join the format leaves out". The parameter is that omitted
parent key column. The PL framing and the relational framing reach the same
place from opposite sides, which is some evidence the concept is real.

### OBS: all three at once

OBS is the best test case, and it isn't on our list yet:

- **Parameter.** An OBS file belongs to the package that binds it.
- **Associated items.** The valid `obstype`s depend on the target type,
  which is the `observations[obstype]` pattern: another trait with
  per-package impls.
- **Sum type.** `id` is a union (`cellid | index | boundname`). Which arm
  applies depends on the `obstype` in the same row, and the `boundname` arm
  on the *target's* `BOUNDNAMES` option, which is a cross-file `when`.

If one design handles OBS cleanly, it'll handle MVR and SPC.

### What stays a rule

- **`flow_model`** (SSM `pname`). The GWT model's flow model isn't supplied
  by any binding row of SSM. It comes from a GWF-GWT exchange that names
  the model, or from FMI's `GWFBUDGET` file when there's no flow model in
  the simulation. In that case SSM's `pname` should match a package name in
  the budget file (to check against MF6). That's a genuine view, and it has
  its own sum type (exchange or file). It stays a named rule.
- **`mover_enabled`** becomes `when` on the key set (#407). It's an
  option-based refinement of the role, not a context.

So the rule registry would shrink from four entries to one.

### Grid as parameter: re-encoding vs. regridding

Treating the grid as a parameter sorts #287's mesh example:

- **Re-encoding** keeps the domain and changes how cells are named. DIS
  cellid `(k, i, j)` ↔ node, or a DIS model's NetCDF written as structured
  vs. UGRID layered mesh. That's a bijection, it's lossless, and it's
  layout. It's mechanical, so flopy4 can do it in general.
- **Regridding** changes the domain (DIS → an arbitrary DISV). That's
  interpolation, not schema, and it's out of scope for the spec.

#287's "converting a structured model to a UGRID mesh representation"
is mostly the first kind. Under this framing it's cheap.

---

## How the tentative designs change

| Draft says | Revised |
|---|---|
| Component variants are sum types; flopy4 uses discriminated unions | They're layouts of one relation, related by partial lenses. Keep separate classes (users write `Rcha`), discriminate at load (ftype + `READASARRAYS`), and add conversion through the logical relation. Discriminated unions are for typed slots and the loader, not the object model at large. |
| Declare `variant_of` to check SPCA → RCHA | Key kinds on roles check it. `variant_of` / `layout_of` is optional and only for docs. |
| Rules are "dynamic scope" | They're parameters filled by the binding. Lexical, given the declaration. |
| `when`, MOVER, `READASARRAYS` and `NETCDF` should share one vocabulary | `when` and MOVER yes. `READASARRAYS` and `NETCDF` are layout tags, in the same family as `CONSTANT` / `INTERNAL`. Different construct. |
| Union records have no relational equivalent | Sparse columns with EAV layout. Same pattern as period blocks: deltas over state. |
| Grid: per-component variant or model parameter? | Model parameter. Conversions are re-encodings (layout) or regridding (out of scope). |

A side question this raises: options themselves split into **layout
flags** (`READASARRAYS`, the `LAYERED` and `NETCDF` tags) and **logical
settings** (`MOVER`, `SURF_RATE_SPECIFIED`, `FIXED_CELL`). This is too
coarse. `PRINT_INPUT` is an output directive, and `BOUNDNAMES` declares
identity (schema). See [`option-classification.md`](option-classification.md) for the full
categories. `when` can test either kind, but the spec should say which
kind each option is. Field `when` on a layout flag means a column that's
always there logically but only written sometimes. On a logical setting, it
means a column that only exists sometimes. That settles the relational
plan's "is `when` logical or layout?": it depends on the option.

---

## Plan

In order. Each step answers a question and is cheap to abandon.

1. **Classify options (desk exercise, devtools).** Script out every option
   in the DFNs, then label each as layout, logical or both by hand.
   Detailed in [`option-classification.md`](option-classification.md) (categories, decision test,
   failure threshold, memory catalog coordination).
   *Answers:* whether the layout/logical split is clean at the option level.
   Wherever "both" shows up often, the two-layer idea is in trouble.
   **Done (2026-11-03), see [`option-classification.md`](option-classification.md): the split
   holds.** Of 224 names, 20 are layout, 121 logical, 82 output, and 1 mixed
   (CSUB `HEAD_BASED`). Layout lenses come in four kinds: syntactic,
   cross-component, computed and partial. The RCHA partial lens above is one
   of them.
   **Derivation axis.** The `AUXMULTNAME` borderline case showed that the
   re-encoding test was underspecified. It can mean the same values now, or
   the same behaviour under change. Options that declare a rule ("this
   quantity is computed from those") are now marked `none`, `static` or
   `dynamic`:
   - No layout option is dynamic.
   - 14 of 20 layout options are static derivations.
   - `AUXMULTNAME` is dynamic. MF6 applies the multiplier at each use,
     against an aux value that can be a TS. That makes it logical, alongside
     `AUXDEPTHNAME`, TS/TAS and `LOCAL_Z`. Criterion 2 holds.

   Consequence: the logical layer needs **derived attributes** (generated
   columns), and flopy4 should keep dynamic derivations unmaterialised.
1b. **Constraint audit (desk exercise).** **Done (2026-11-03), see
   [`constraint-audit.md`](constraint-audit.md).**
   - The layering holds for constraints. The only layout-to-logical crossings
     are lens-domain conditions (new kind L), which MF6 enforces and which
     are step 5's partiality conditions.
   - `when` and binding parameters fit one form: a predicate resolved in a
     scope chain (own options → model → binding).
   - `MODELNAMES` is a binding parameter written as an option.
   - The DFN expresses 46 of 166 sampled constraints at least partly. It
     misses numeric domains, option coherence, co-occurrence and the grid
     joins.

   The original plan for this step:
   Make a taxonomy of
   the constraints a valid simulation must satisfy (K1 format through K10
   structural/physical). For each kind, record its level, its DFN coverage
   and the DDL construct it would need. Sources: DFN keys, MF6
   `store_error` sites (sampled) and mf6io prose. Detailed in
   [`constraint-audit.md`](constraint-audit.md).
   *Answers:* whether constraints respect the layering the way options do;
   whether `when` and binding parameters are one construct (feeds step 3);
   and what step 2's DDL has to express.
   It also adds a second axis that crosses layout/logical:
   **configuration vs. data**.
   - Options and dimensions are configuration, which maps to DDL schema.
   - Arrays and rows are data, which maps to table contents.
   - The weak spots sit where the two meet: `MAXBOUND`/`NODES` (configuration
     derived from data) and `IDOMAIN` (data that acts as structure).
     `AUXMULTNAME` was on this list, but it's a derivation, not a mix of
     configuration and data (see step 1).
2. **DDL slice (already planned, sharper verdict).** Add OBS to the slice,
   for one package. Test the hypotheses directly:
   - H1: no logical sum types except enums and the grid.
   - H2: union records and period blocks are both sparse tables plus deltas.
   - H3: every rule except `flow_model` is a parent key column, i.e. a
     parameter.
   - H4: SPC/SPCA pairing is a key-kind match.
   - H5: dynamic derivations are generated columns. Model one boundary
     package with `AUXMULTNAME`.
3. **Parameter syntax sketch (devtools, paper only).** Write `[params]`
   (name open) for SPC, MVR, GNC, OBS and TS, and write how binding rows
   supply them. Then rewrite `ssm_package`, `exchange_models` and CellID
   `model` in it. Keep it if the result is smaller than the rules plus
   CellID `model`. Drop it otherwise.
   From 1b, also:
   - make parameters names that `when` can test;
   - replace MVR `MODELNAMES` with the `models` parameter;
   - check that the K8a co-occurrence rules (MVR ⇒ MVT, LKT ⇒ LAK) can be
     written in the same form.
4. **Binding-graph navigation (flopy4).** This is the "when package
   references come" revisit in [`reference-fields-notes.md`](../archive/reference-fields-notes.md). Add explicit
   navigation (`Spc.target`, `Mvr.models`, `Obs.target`, `Model.flow_model`),
   implemented once over the binding graph. Then have `keys.py` and
   reference fields both use it. It's worth doing whatever happens in the
   spec, because both already need it.
5. **One conversion end to end (flopy4).** RCHA ↔ RCH through an explicit
   intermediate (per-cell rate per period). Report partiality with the
   conditions from section 1. If that's clean, EVT ↔ EVTA and CHD ↔ CHDG
   follow. If not, we learn where "one logical relation" breaks.
6. **Then post.** Revise the #287 comment with whatever survives steps 1 to
   3. Probably shorter: the taxonomy, the three hypotheses, and the plan.
   The relational draft stays a separate discussion.

## What would change our minds

- An option that's irreducibly both layout and logical, used widely
  (step 1).
- A union record whose arms don't fit one table (step 2).
- A child file whose context isn't supplied by its binding row, beyond
  `flow_model` (step 3). Each one is another rule, and if there are enough
  of them, the parameter construct isn't paying for itself.
- Conversion needing per-pair special cases beyond the stated conditions
  (step 5).
- Many constraints of a logical kind triggered by layout options
  (step 1b). These would be the constraint-level counterpart of mixed
  options.

## To check against MF6

- Whether list RCH/EVT allow several entries in one cell (assumed yes, as
  for WEL).
- Whether EVTA lacks segments.
- What SSM `pname` refers to when FMI reads flow from a `GWFBUDGET` file.
- Whether OBS `id`'s `boundname` arm depends only on the target's
  `BOUNDNAMES`.
