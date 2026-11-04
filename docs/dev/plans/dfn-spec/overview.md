# The MF6 input spec: layers, polymorphism and bindings

Research on whether the DFN spec should describe MF6 input at two levels,
logical and layout, and what that means for flopy4 ([discussion
#287][d287]). This is the entry point: it defines the vocabulary the other
docs in this folder use, states the hypotheses and the evidence so far,
and lists the next steps. [layout-logical-decisions.md](layout-logical-decisions.md)
applies the rule to specific flopy4 issues.

| Doc | What it is |
|---|---|
| this one | concepts, hypotheses, plan |
| [option-classification.md](option-classification.md) | every DFN option labelled layout, logical or output |
| [constraint-audit.md](constraint-audit.md) | the kinds of constraint a valid simulation must satisfy, and where each is enforced |
| [dfn-gaps.md](dfn-gaps.md) | what those two studies found missing from the DFNs and the memory catalog, for MF6 and devtools developers |
| [layout-logical-decisions.md](layout-logical-decisions.md) | the rule applied to open MMP issues (#226, #229, #259, #345, #523) |
| `data/` | scripts and CSVs behind the two studies |

[d287]: https://github.com/modflowpy/pyphoenix-project/discussions/287

## Where this comes from

Two threads met here.

- **Schema polymorphism (#287).** Some MF6 concepts come in several forms:
  RCH or RCHA, a structured grid or a UGRID mesh, ASCII arrays or NetCDF
  variables. #287 asked how the spec and flopy4 should represent that.
- **Polymorphic references.** Adding primary and foreign key metadata to
  the DFNs (modflow-devtools #405, #406, #407; flopy4 #535) ran into
  references whose target type varies. An MVR row points at a row in
  *whichever* package `pname1` names: WEL, LAK, SFR and so on.

Putting both in one picture raised a bigger question: should the DFN spec
describe MF6 input at two levels, a **logical** one (tables, columns, keys)
and a **layout** one (how the text format writes them down)? Much of what
#287 calls polymorphism turns out to be a layout difference. The rest of
this doc builds that case and says how we're testing it.

## Concepts

### Components and bindings

A **component** is one DFN, which is one kind of input file: `gwf-wel`,
`utl-spc`, `sim-nam`.

A **binding** is the row in another file that attaches a component to the
simulation. Examples:

- a `PACKAGES` row in a model namefile (`WEL6 model.wel wel-1`);
- a `MODELS` or `EXCHANGES` row in the simulation namefile;
- an SSM `FILEINPUT` row naming an SPC file and the flow package it
  applies to;
- a package's `OBS6 FILEIN`, `TS6 FILEIN` or `TAS6 FILEIN` option.

The **binding context** is what the binding row knows and the file itself
doesn't: which model the package is in, which two models an exchange
connects, which flow package an SPC file belongs to. Many MF6 rules depend
on it. An exchange's mover file, for example, may refer only to the
exchange's two models.

### Three levels

MF6 input can be described at three levels:

| Level | What it is | Specified by today |
|---|---|---|
| **layout** | how the file writes things down: blocks, keywords, arrays vs. lists, `CONSTANT`/`INTERNAL`/`OPEN/CLOSE`, `LAYERED`, unit factors | the DFNs |
| **logical** | what the data is: tables, columns, keys, and the settings that change what the model computes | nothing |
| **runtime memory** | MF6's own variables (`bound`, `nodelist`, `hcof`, ...) | the DFN `[memory]` catalog (schema v2.0.0.dev3) |

There's also an **input memory** level between layout and runtime: the
`__INPUT__` memory context that IDM fills, which mirrors the file's fields.

Runtime memory is not the logical level. It holds solver artefacts
(`hcof`, `rhs`), reduced node numbers and `maxbound`-sized arrays, and its
own layout has changed without any input change (MF6 6.4.3 split `BOUND`
into per-column arrays). It's one more layout. We find the logical level
by asking what file input and runtime memory both preserve.

Example: RCH (list input) and RCHA (array input, `READASARRAYS`) are two
layouts of one logical relation, a recharge rate per cell per period. MF6's
memory catalog agrees: both declare the same runtime variables
(`nodelist`, `bound`, `auxvar`, `hcof`, `rhs`, ...).

### Lenses

A **lens** is the mapping between a layout and the logical relation: how
to read the logical content out of a file, and how to write it back. The
term comes from bidirectional programming.

A lens is **partial** if some logical content has no image in that layout.
RCHA → RCH always works: each column's rate becomes a bound in the `irch`
layer. RCH → RCHA works only when each column has at most one entry, all
in one layer, with no boundnames, no per-bound aux the array can't hold,
and nothing referring to bound numbers. EVT → EVTA also needs `NSEG = 1`
and no `SURF_RATE_SPECIFIED`, which MF6 enforces (`gwf-evt.f90:202, 291`).

The option classification found four kinds of lens:

| Kind | Re-encoding needs | Examples |
|---|---|---|
| syntactic | the file alone | `NC_FILERECORD`, `MODELNAMES`, `COMPLEXITY` |
| cross-component | other components' data | `K22OVERK` (needs the TVK schedule), `STORAGECOEFFICIENT` (needs cell thickness) |
| computed | a model calculation | CSUB `SPECIFIED_INITIAL_*` (initial effective stress from STRT, TOP/BOT and geostatic load) |
| partial | a domain restriction | `READASARRAYS`, `READARRAYGRID`, `FLOW_REDUCTION_LENGTH` |

The memory catalog's `source` key (`nodelist.source = "cellid"` in RCH) is
a lens written down. In RCHA, `nodelist` and `bound` have no `source`,
because the array-to-list mapping can't be written as a field list. Those
missing `source` expressions are exactly the partial lenses.

### Option labels

Every option in the DFNs has been labelled
([option-classification.md](option-classification.md)):

- **layout**: an encoding choice. Toggle the option, re-encode the data to
  match, and the model is unchanged (the **re-encoding test**).
  `READASARRAYS`, `STORAGECOEFFICIENT`.
- **logical**: describes the model. Settings, column and identity
  declarations, references, descriptive metadata. `MOVER`, `XT3D`,
  `BOUNDNAMES`, `XORIGIN`.
- **output**: a run directive. Changes only what's printed, saved or
  checked. `PRINT_INPUT`, `SAVE_FLOWS`, `MAXERRORS`.
- **mixed**: partly layout, partly not. Only one exists (CSUB
  `HEAD_BASED`).

Two optional tags:

- **`binding`**: the option attaches or names another component
  (`OBS6 FILEIN`, `TS6 FILEIN`, `FLOW_PACKAGE_NAME`).
- **`schema`**: the option decides which logical columns or tables exist,
  or whether entities have identity. `AUXILIARY` adds columns,
  `BOUNDNAMES` adds a name column other components can refer to,
  `SORPTION` decides which arrays exist.

And a second axis, **derivation**, for options that declare a rule
("this quantity is computed from those"):

- **none**: no rule.
- **static**: every input to the rule is fixed once written, so computing
  the result once loses nothing. `STORAGECOEFFICIENT` divides by cell
  thickness, which doesn't change.
- **dynamic**: an input can change during the run (a time series, TVK,
  simulated state), and MF6 re-evaluates the rule each time.
  `AUXMULTNAME` multiplies by an aux column that may be a time series.

No layout option is dynamic. A dynamic derivation is model content, so it
belongs at the logical level, and an editing tool like flopy4 should keep
the rule rather than its result.

### Configuration vs. data

A second split crosses the first. **Configuration** is options and
dimensions, which map to a database schema. **Data** is arrays and rows,
which map to table contents. The awkward cases sit where the two meet:
`MAXBOUND` and `NODES` are configuration derived from data, and `IDOMAIN`
is data that acts as structure.

### Three kinds of polymorphism

Polymorphism means one position (a field, a slot, a reference) can hold or
point at things of more than one type. MF6 input has three kinds.

**Sum types (variants).** One concept takes one of a closed set of forms,
and a tag says which: RCH or RCHA, chosen by `READASARRAYS`; an SFR period
row that sets `STATUS` or `RATE` or `DIVERSION`, chosen by the keyword. In
Python, a discriminated union.

**Interfaces (roles).** A reference whose target type isn't fixed, only
what the target must be able to do. MVR's `(pname1, id1)` points at a
package and a number in it; WEL, LAK and SFR can all be targets, and each
says what `id1` numbers (a bound for WEL, an outlet for LAK, a reach for
SFR). The set is open: a new mover-capable package joins without changing
MVR. In Python, a Protocol or a registry from role to implementers.

The spec expresses roles today. A target declares the roles it plays and
its key in each:

```toml
# gwf-lak
[keys]
mover_provider = "outlets.outletno"
mover_receiver = "packagedata.ifno"

# gwf-wel, and the other standard boundary packages
[keys]
mover_provider = "<=maxbound"
bound = "<=maxbound"
```

and a foreign key names the role instead of a target path:

```toml
# gwf-mvr period id1 / id2
fk = { scope = "pname1", key = "mover_provider" }
fk = { scope = "pname2", key = "mover_receiver" }
```

SPC's `bndno` shows why the role matters. It means "boundary *n* of the
flow package this SPC file applies to", and what a boundary is depends
entirely on the target: the *n*th entry for WEL, reach *n* for SFR,
connection *n* for LAK.

**Parameters.** A reference can also be fixed in type but vary in *where
to look*. Exchange MVR's `mname1` must be one of the exchange's two models;
SSM's `pname` must be a package of the paired flow model. The answer
depends on the binding context, not the file. The spec handles these today
with named **rules** on the foreign key, defined in prose and implemented
by consumers:

| Rule | Used by | Meaning |
|---|---|---|
| `exchange_models` | MVR `mname`, `mname1`/`mname2` | one of the two models of the exchange that binds this mover |
| `flow_model` | SSM `pname` | a package of the flow model the GWF-GWT/GWE exchange pairs with this transport model |
| `ssm_package` | SPC `bndno` (with role `bound`) | a bound of the flow package named by the SSM row that binds this SPC file |
| `mover_enabled` | MVR `packages.pname` | the named package has `MOVER` set (#407 replaces this with `when` on the key set) |

Hypothesis 3 below says most rules are really parameters of the component,
filled in by its binding.

### Entities vs. fields

The list/array split is really about identity:

- **List variant: a collection of entities.** Each bound has identity (its
  number, optionally a boundname), so it can be named, observed, moved or
  given concentrations by SPC.
- **Array variant: a field over the grid.** A value per column or cell. Its
  only identity is the cell.

Roles attach to identity, so RCH plays `bound` and RCHA doesn't. SPCA
still refers to RCHA, through the grid: an SPCA array is keyed by column,
like RCHA's. Both SPC and SPCA are keyed by their target's key. They
differ only in what kind of key that is:

| Referrer | Target | Shared key |
|---|---|---|
| SPC `bndno` | RCH, WEL, SFR, LAK, ... | the target's bound number (`<=maxbound`, `ifno`, `<=nlakeconn`, ...) |
| SPCA arrays | RCHA, EVTA | the target's column (`ncpl`) |

## Hypotheses

Five hypotheses, each testable and each cheap to abandon. The short labels
(H1–H5) are used in the other docs.

### H1: the logical level needs no sum types beyond enums and the grid

Every variant we've found is chosen by a tag. Where the tag sits:

| Level | Tag | Chooses | Level of the choice |
|---|---|---|---|
| binding row | ftype (`CHD6` vs. `CHDG6`) | component variant | layout |
| file options | `READASARRAYS` | component variant (RCH vs. RCHA) | layout |
| field | `CONSTANT`/`INTERNAL`/`OPEN/CLOSE`/`NETCDF`, `LAYERED` | array encoding, or where the values are | layout |
| row | union keyword (`STATUS`, `RATE`, `DIVERSION`, ...) | which attribute a row sets | layout (H2) |
| model | discretization type (DIS/DISV/DISU) | the grid's domain | **logical** |

`NETCDF` belongs with the array control records. It answers "where are
this array's values?", not "which parts of the schema exist?".

What's left at the logical level is enums (`status`, connection type, ...),
which are plain column domains, and the grid type, which changes the domain
every array is indexed by. The grid is better treated as a parameter of
the model than as a variant (see "Grid as parameter" below).

If H1 holds, the candidate languages for a logical layer get simpler: SQL
DDL, Frictionless and a relational subset of our own TOML all become
viable, though none has sum types.

**What "functionally equivalent" means.** #287 calls RCH and RCHA
functionally equivalent. They give the same source term per cell per
period, so the hydrologic effect is the same. They don't have the same
*identity*: bound numbers, boundnames, observations, movers and SPC all
refer to bounds, and RCHA has none. Each layout is a lens onto one logical
relation, and conversion goes through the relation where both lenses are
defined. flopy4 can implement that once, not once per variant pair, and
its error messages fall out of the partiality conditions.

**Evidence:** supported so far. The option classification found almost no
option that is both layout and logical, and the constraint audit found no
logical constraint triggered by a layout option. The DDL slice tests it
directly.

### H2: union records and period blocks are sparse tables written as deltas

SFR's period block is a log of updates to reach attributes. `1 STATUS
INACTIVE` and `1 RATE 0.1` set two columns of one logical row,
`(reach, period) → status, rate, stage, ...`. The keyword names the column.
That's entity-attribute-value (EAV) encoding of a sparse wide table. Arms
with their own key (`DIVERSION idv divflow`) set columns of a child table
keyed by `(reach, idv)`.

Period blocks follow the same pattern. MF6 carries a period's data forward
until the next block, which is a delta encoding of a step function over
periods. Union records and period blocks are both **deltas in the layout
over state in the logical level**, and one convention can cover both.

So union records aren't a logical sum type, and "databases don't have sum
types" stops being a gap. This needs checking per case. OC's
`SAVE HEAD ALL` / `PRINT BUDGET STEPS 1 3` reads more like
`(action, rtype) → step selection`, which still fits a table. MAW
`connstatus` and the LAK/UZF period settings look like SFR. A
counterexample would be an arm whose fields don't belong to one table.

**Evidence:** untested. The DDL slice tests it.

### H3: a component is parameterized by its binding

A rule like `exchange_models` is "dynamic scope": the answer depends on
where the file is bound. A better way to see it: **a file is a
parameterized component, and the row that binds it supplies the
arguments.** Once the parameter is declared, a reference to it is ordinary
lexical scope again.

| Component | Parameter | Supplied by | Today |
|---|---|---|---|
| `utl-spc` / `utl-spca` | `target`: a package playing `bound` | SSM `FILEINPUT` row (`pname`) | rule `ssm_package` |
| `gwf-mvr` | `models`: one or two models | model namefile (this model) or exchange (`exgmnamea`, `exgmnameb`) | rule `exchange_models` |
| `gwf-gnc` | `models`, as for MVR | model or exchange | CellID `model = "1"/"2"` |
| exchange cellids | `models` | the exchange's own name columns | CellID `model = "1"/"2"` |
| `utl-obs` | `target`: its parent package | the package's `OBS6 FILEIN` | nothing |
| `utl-ts` / `utl-tas` | `target`: its parent package | the package's `TS6` / `TAS6` | nothing |
| every package | `grid`: its model's discretization | the model | implicit in the cellid encoding |

Every child file is in this table. That clears the bar devtools #405 set
for new spec syntax: a construct used by enough fields that a second
consumer could implement it from the spec alone. Rules failed that test one
at a time. As parameters, together, they pass it.

It also matches a relational reading: a rule is a parent key column the
file format leaves out, and the parameter is that column.

**OBS is the hardest case,** and a good test: it needs all three kinds of
polymorphism at once.

- Parameter: an OBS file belongs to the package that binds it.
- Interface: the valid `obstype`s depend on the target's type
  (`[observations]` arms, declared per package).
- Sum type: `id` is `cellid | index | boundname`. Which arm applies depends
  on `obstype` in the same row, and the `boundname` arm on the *target's*
  `BOUNDNAMES` option.

**What stays a rule.** `flow_model` (SSM `pname`) isn't supplied by any
binding row of SSM. It comes from a GWF-GWT exchange naming the model, or
from FMI's `GWFBUDGET` file when there's no flow model in the simulation.
That's a genuine view, with its own sum type (exchange or file), and stays
a named rule. `mover_enabled` becomes `when` on the key set (#407). So the
rule registry would shrink from four entries to one.

**`when` and binding parameters are one construct.** The constraint audit
found that conditional presence (`when`) and component co-occurrence
("MVR needs MVT") have the same form: a predicate over context implies an
element is present or absent. What differs is where the predicate's names
live. Resolve them in a scope chain:

1. the component's own options and dimensions;
2. the model's other components;
3. the binding's parameters.

MVR's `MODELNAMES` shows it most clearly. The option exists only so the
file can state its binding context, and MF6 rejects it whenever it
disagrees with the binding (`gwf-mvr.f90:785-798`). With a `models`
parameter, the option goes away.

**Evidence:** supported by the constraint audit. The parameter syntax sketch
tests whether the construct is smaller than what it replaces.

### H4: SPC/SPCA pairing is a key-kind match

If a role states what *kind* of key it uses (a bound number or a grid
column), then "SPCA binds only to array variants" is a key-kind mismatch,
caught by the ordinary foreign key check. No `variant_of` declaration is
needed for validation. One could still help docs group the alternatives.

In programming-language terms, a role is a trait, and its key is an
associated type. Each `[keys]` entry is a trait impl. That also says roles
need one home: a central `[roles.*]` declaration (key kind, who may refer
to it, prose), with per-component `[keys]` as the impls. Declaring impls on
the target side keeps the set open, as MF6 itself does.

The same concept appears in devtools' proposed `Dim.kind` (`grid` vs.
`count`), the memory-level version of key kinds. One definition should
serve both.

**Evidence:** supported. The constraint audit confirmed that MF6 enforces the
SPC↔SPCA pairing in Fortran (`TspSpc.f90:360-380`), and the DFN only
implies it by naming.

### H5: dynamic derivations are generated columns

From the derivation axis above: the logical level needs derived attributes
(generated columns) as well as base tables. A dynamic derivation like
`AUXMULTNAME` is a logical generated column. A static one can be
materialised by the lens.

**Evidence:** untested. The DDL slice models one boundary package with
`AUXMULTNAME` to check.

## Grid as parameter: re-encoding vs. regridding

Treating the grid as a model parameter sorts #287's mesh example into two
operations:

- **Re-encoding** keeps the domain and changes how cells are named: DIS
  cellid `(k, i, j)` ↔ node number, or a DIS model's NetCDF written as
  structured vs. UGRID layered mesh. That's a bijection, it's lossless, and
  it's layout. flopy4 can do it in general.
- **Regridding** changes the domain (DIS → an arbitrary DISV). That's
  interpolation, not schema, and it's out of scope for the spec.

#287's "converting a structured model to a UGRID mesh representation" is
mostly the first kind, so it's cheap.

## Design consequences

Where the hypotheses lead, for the spec and flopy4:

| Question | Answer |
|---|---|
| Are component variants (RCH/RCHA) sum types in flopy4? | No. Keep separate classes (users write `Rcha`), discriminate at load by ftype and `READASARRAYS`, and convert between them through the logical relation. Discriminated unions are for typed slots and the loader. |
| Does the spec need `variant_of` to check SPCA → RCHA? | No. Key kinds on roles check it (H4). `variant_of` is optional, for docs. |
| Do `when`, MOVER, `READASARRAYS` and `NETCDF` share one construct? | `when` and MOVER do (H3). `READASARRAYS` and `NETCDF` are layout tags, in the same family as `CONSTANT`/`INTERNAL`. |
| What's the relational form of union records? | Sparse columns, written as EAV (H2). |
| Is the grid a per-component variant or a model parameter? | A model parameter. Conversions are re-encodings (layout) or regridding (out of scope). |
| Is `when` logical or layout? | It depends on the option it tests. `when` on a logical option means a column that only sometimes exists. On a layout option, it means a column that always exists but is only sometimes written. |
| How should flopy4 hold layout choices? | As given. Logical forms are views. See [layout-logical-decisions.md](layout-logical-decisions.md). |

## Plan

In order. Each step answers a question and is cheap to abandon.

| # | Step | Where |
|---|---|---|
| 1 | **Option classification.** Label every DFN option, with a failure threshold fixed beforehand. | desk |
| 2 | **Constraint audit.** Classify the constraints a valid simulation must satisfy by kind, level, DFN coverage and the database construct each would need. | desk |
| 3 | **DDL slice.** Hand-write SQL DDL for a slice of components covering every hard case. | devtools |
| 4 | **Parameter syntax sketch.** Write `[params]` for SPC, MVR, GNC, OBS and TS, and rewrite the rules in it. | devtools, paper only |
| 5 | **Binding-graph navigation.** `Spc.target`, `Mvr.models`, `Obs.target`, `Model.flow_model`, implemented once. | flopy4 |
| 6 | **One conversion end to end.** RCHA ↔ RCH through an explicit logical intermediate. | flopy4 |
| 7 | **Post** a summary to #287, after steps 3-4. | GitHub |

Steps 1 and 2 are done: the split holds for options
([option-classification.md](option-classification.md)), and the layering
holds for constraints, with `when` and binding fitting one form
([constraint-audit.md](constraint-audit.md)).

### Step 3: the DDL slice

The slice: binding lists, WEL, RCH/RCHA, SFR, LAK and MVR, SSM and SPC,
GNC, exchanges, and OBS for one package. It tests whether every construct
translates to tables and keys, whether the rules are short enough as views
to put in the spec, and which language fits. It tests the hypotheses
directly:

- H1: no logical sum types except enums and the grid;
- H2: union records and period blocks are sparse tables plus deltas;
- H3: every rule except `flow_model` is a parent key column;
- H4: SPC/SPCA pairing is a key-kind match;
- H5: model one boundary package with `AUXMULTNAME` as a generated column.

From the earlier steps, also:

- put **dimensions in as first-class values**. Most shape constraints are
  `count(rows) = dim` or `≤ dim`, so `MAXBOUND` is a CHECK bound on a
  table's row count. Bound identity comes from the row key, not from the
  dimension.
- include **the grid as a relation** (cell → top, bot, area, idomain),
  supplied as a parameter. Most structural constraints (`TOP > BOT`, lake
  bed above cell bottom, UZF area ≤ cell area) are joins against it.
- put **option coherence** ("these options exclude each other") in a CHECK
  on the options row: a component's options are a one-row table.
- carry the four lens kinds and the three `RELEASETIMES` encodings (block,
  options record, file).
- expect a few misfits that need functions or recursive queries: monotone
  row order, SFR acyclicity, point-in-cell geometry. Keep them as named
  checks.

A flopy4 counterpart: export a simulation to SQLite or DuckDB, and write
the key checks as SQL queries to compare with `keys.py`.

### Step 4: parameter syntax sketch

Write `[params]` (the name is open) for SPC, MVR, GNC, OBS and TS, and how
binding rows supply them. Rewrite `ssm_package`, `exchange_models` and
CellID `model` in it. Keep it if the result is smaller than the rules plus
CellID `model`; drop it otherwise. Also:

- make parameters names that `when` can test;
- replace MVR `MODELNAMES` with the `models` parameter;
- check that co-occurrence rules (MVR ⇒ MVT, LKT ⇒ LAK) can be written in
  the same form.

The DFN's `[observations]` tables (dev3, 63 components) already declare
observation types on the target package. Build on them rather than adding
a parallel construct.

### Step 5: binding-graph navigation

Add explicit navigation (`Spc.target`, `Mvr.models`, `Obs.target`,
`Model.flow_model`), implemented once over the binding graph, and have
`keys.py` and reference fields
([../components/reference-fields-notes.md](../archive/reference-fields-notes.md))
both use it. This is worth doing whatever happens in the spec, because both
already need it. #226 and #259 need the same attach operation; see
[layout-logical-decisions.md](layout-logical-decisions.md).

### Step 6: one conversion

RCHA ↔ RCH through an explicit intermediate (per-cell rate per period),
reporting partiality with the conditions from "Lenses" above. If that's
clean, EVT ↔ EVTA and CHD ↔ CHDG follow. If not, we learn where "one
logical relation" breaks. The partial-lens constraints the constraint audit
found (`READASARRAYS` excludes `SURF_RATE_SPECIFIED`, no TAS on DISU, and
so on) are exactly what the conversion should report.

## What would change our minds

- An option that's irreducibly both layout and logical, used widely
  (step 1: not found).
- Many logical constraints triggered by layout options (step 2: not
  found).
- A union record whose arms don't fit one table (step 3).
- A child file whose context isn't supplied by its binding row, beyond
  `flow_model` (step 4). Each one is another rule, and if there are enough,
  the parameter construct isn't paying for itself.
- Conversion needing per-pair special cases beyond the stated conditions
  (step 6).

## To check against MF6

- Whether list RCH/EVT allow several entries in one cell (assumed yes, as
  for WEL).
- Whether EVTA lacks segments.
- What SSM `pname` refers to when FMI reads flow from a `GWFBUDGET` file.
- Whether OBS `id`'s `boundname` arm depends only on the target's
  `BOUNDNAMES`.
