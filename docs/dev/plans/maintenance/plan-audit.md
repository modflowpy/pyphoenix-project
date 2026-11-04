# Audit of the plans: concepts, terminology and structure

An audit of the live plans as material for a plan to reach flopy 4.x: where
they contradict MF6, what they rely on but don't define, where their
vocabulary departs from MF6 or could borrow from an established field, and
how they could be organized. Each finding says how I'd address it.
[Part 7](#7-order-of-work) puts the fixes in order, and
[Part 8](#8-decisions-for-you) lists what needs your decision.

Baseline: `dev-plans` at `3ff8980c`, and MF6 at `0dd9ed1784` (the local
checkout, 2026-11-03). MF6 paths are relative to the modflow6 repo. The
constraint audit and option classification used MF6 `8aad7bc4a5`, so an MF6
line number there and one here may differ.

**What was read.** All live docs in `docs/dev/` and `docs/dev/plans/`, but
only the archive's index. The drafts `discussion-287-comment.md` and
`discussion-relational-spec-draft.md` were not reviewed closely, apart from a
search for the errors in Part 1, which found one (see F2).

**How far to trust each finding.**

- Part 1 was checked against MF6's docs, DFNs or source, or flopy4's code.
- Parts 2 and 5 come from reading the docs against each other, with the
  sources cited.
- Parts 3 and 4 are recommendations. The terms in Part 3's theory table are
  standard, but whether each one is worth adopting is a judgement.
- Open checks are collected in [Part 9](#9-checks-still-open).

## Summary

- **The trimming worked, but concepts are still defined doc by doc.** Terms
  are defined where they were first needed, and several have since gained
  other meanings elsewhere. No doc owns the vocabulary, though #217 asks for
  one and it's an MMP gate item.
- **Four claims in the DFN spec research need correcting,** and H1, H2 and H4
  rest on them. Bound identity is the important one: MF6 says bound numbers
  can change meaning between periods and boundnames can repeat, so neither is
  a key.
- **Four concepts need defining before more plans build on them:** logical
  content, equivalence, "as given", and absence. The first three decide what
  the MMP gate actually checks.
- **The polymorphism framing is close, and type theory can tighten it.**
  The "parameters" kind is value-dependent, which makes it dependent typing
  rather than parametric polymorphism, and the true parametric cases aren't
  named at all.
- **There is no single plan to 4.x.** `mmp-plan.md` stops at MMP and the rest
  is in `replacing-flopy-mf6.md`, with the sequencing partly duplicated. Six
  MMP issues and one large unmerged branch appear in neither.

## 1. Corrections against MF6

These come first because the hypotheses, the #287 post and the proposed
concepts doc would otherwise inherit them.

### F1. Bound numbers and boundnames aren't identity

**The plans say:** "Each bound has identity (its number, optionally a
boundname), so it can be named, observed, moved or given concentrations"
([`dfn-spec/overview.md`](../dfn-spec/overview.md) line 226). The
classification says `BOUNDNAMES` gives entities identity, and that `MAXBOUND`
"defines bound-number identity" (`option-classification.md` line 279).

**MF6 says:**

- The order of boundaries may change between periods, so "in stress period 1,
  boundary number 2 is the INTERMEDIATE_WELL, whereas in stress period 2,
  boundary number 2 is the DEEP_WELL" (`doc/mf6io/utl_spc.tex:36`).
- For MVR: "the order of these boundaries may change by stress period, which
  must be accounted for in the Mover Package"
  (`doc/mf6io/mf6ivar/dfn/gwf-mvr.dfn`, `id1`).
- Boundnames "can be used to sum recharge rates for entries with the same
  boundname" (`doc/mf6io/gwf/rch.tex:6`, and `evt.tex:5`). So they can repeat
  on purpose: a boundname is a group label, not a key.
- Advanced packages differ: their features "are defined once at the beginning
  of the simulation and they do not change" (`utl_spc.tex:7`).

**Why it matters:**

- A reference to a bound is really `(package, period, position)`, not
  `(package, number)`. The DDL slice's keys and the proposed
  `<=maxbound as a key domain` change accordingly.
- A boundname can't be a primary key, and observing one is an aggregation.
- An edit that reorders a period's rows silently retargets MVR and SPC rows.
  That's a real hazard for an editing tool.
- `dense()`'s row key table and the logical relation for WEL both need the
  period in the key. "Editing a row" isn't well defined across periods unless
  the row has a stable identity, which list entries lack.

**How I'd address it.** Replace "Entities vs. fields" with this distinction,
using MF6's words:

| Entity | Identified by | Stable across periods? | Examples |
|---|---|---|---|
| **feature** | a number declared in PACKAGEDATA (`ifno`) | yes | SFR reach, LAK lake, MAW well, UZF cell |
| **list entry** | position in its period's block | no | WEL, DRN, RIV, GHB, CHD, RCH, EVT |
| **grid entry** | position among the block's non-DNODATA cells ([F2](#f2-the-listarray-split-is-three-way-not-two-way)) | no | WELG, DRNG, RIVG, GHBG, CHDG |
| **column** | the grid (`ncpl`) | yes | RCHA, EVTA |

Then:

1. Rewrite `dfn-spec/overview.md` "Entities vs. fields" and restate H4's key
   table with these four.
2. Correct `option-classification.md` line 279, and `constraint-audit.md` and
   `dfn-spec/overview.md` where they say bound identity comes from the row
   key. Keep the row key idea, but say the key includes the period.
3. Add to the DDL slice: a list entry's key is `(package, period, position)`,
   and boundname is a non-unique indexed column.
4. Check `flopy4/mf6/keys.py`: does a bound reference get checked against the
   right period's rows? (Part 9.)
5. Consider a warning in flopy4 when an edit changes row order in a period
   that MVR or SPC refer to. This is a code question, so it goes in the
   backlog rather than here.

### F2. The list/array split is three-way, not two-way

**The plans say:** "The list/array split is really about identity", with
lists as entities and arrays as a field over the grid, so "RCH plays `bound`
and RCHA doesn't" (`dfn-spec/overview.md` lines 224-232). `dfn-gaps.md` line
48 says "SPC pairs with list packages and SPCA with array packages".

**MF6 and flopy4 say:** that holds for layer arrays, not grid arrays.

- MF6 names three input forms: list-based, layer array-based
  (`READASARRAYS`) and grid array-based (`READARRAYGRID`)
  (`doc/mf6io/gwf/evta.tex:3`, `chdg.tex:4`).
- Grid-array packages number their bounds implicitly. The block's first array
  sets `nodeulist` and `nbound` from its non-DNODATA cells, in node order
  (`src/Utilities/Idm/mf6blockfile/Mf6FileGridArray.f90:253-268`). They then
  go through `nodeu_to_nlist`, where layer arrays go through `layarr_to_nlist`
  (`src/Model/ModelUtilities/BoundaryPackageExt.f90`).
- DRNG, WELG, RIVG and GHBG all have a `mover` option, and flopy4's generated
  classes already give them `"mover_provider": "<=maxbound"`
  (`flopy4/mf6/gwf/drng.py:28`, `welg.py:30`). So array input can play a role
  keyed by bound number.
- `check_flow_package` (`src/Model/ModelUtilities/TspSpc.f90`) requires
  array-based SPC only for `RCHA` and `EVTA`. Its default case, which includes
  the grid-array packages, requires list-based SPC.

The #287 draft repeats this: "RCH declares the `bound` role and RCHA doesn't,
because array input has no bound numbers" (`discussion-287-comment.md` line
125). That's right for RCHA, but the stated reason isn't, because grid arrays
are array input with bound numbers.

**How I'd address it:**

1. Use MF6's three terms throughout (see
   [T1](#t1-departures-from-mf6)), and treat the grid-array form as a list in
   a different encoding, with DNODATA as "no entry".
2. Restate H4's table: SPC `bndno` targets list and grid entries and features,
   and SPCA targets columns. Fix `dfn-gaps.md` line 48 to name RCHA and EVTA.
3. Add a note to `dfn-spec/overview.md` step 6: CHD ↔ CHDG is not the same
   kind of conversion as RCH ↔ RCHA, because both sides have bounds. Grid
   entries lose the boundname and allow at most one entry per cell, which
   gives the partiality conditions. It may be the easier first conversion.
4. Say how grid entries are numbered wherever bound numbers are defined, since
   an MVR row targeting WELG refers to that order.

### F3. `CHDG6` doesn't exist

**The plans say:** the H1 table has a row "binding row | ftype (`CHD6` vs.
`CHDG6`) | component variant" (`dfn-spec/overview.md` line 253).

**MF6 says:** `Chdg` uses `CHD6` (`flopy4/mf6/gwf/chdg.py:17`), `Rcha` uses
`RCH6` (`rcha.py:18`), and the source has no `CHDG6` or similar. Grid-array
input is switched on by `READARRAYGRID` inside the file. This was already
learned once: an archived plan records that writing `CHDG6` broke real `mf6` runs
([`mf6-object-model-plan.md`](../archive/mf6-object-model-plan.md) line 749). The
wrong row came over from
[`polymorphism-hypotheses.md`](../archive/polymorphism-hypotheses.md) line 35.

**How I'd address it.** Delete the row, and state the stronger result: a
variant is never selected at the binding row, only by an option in the file,
so the loader has to read the file's options to pick the class. H1 is unaffected.
The design consequences table already says "discriminate at load by ftype and
`READASARRAYS`"; add `READARRAYGRID` to it.

### F4. Period persistence has four regimes, not one

**The plans say:** "MF6 carries a period's data forward until the next block,
which is a delta encoding" and union records and period blocks are both
"deltas in the layout over state in the logical level"
(`dfn-spec/overview.md` lines 294-297). The representation has two cases: "a
block replaces the last one, but a keystring setting holds"
(`representation.md` line 378).

**MF6 says** (`doc/mf6io/gwf/bcoptions.tex:41-49`, `mvr.tex:86`):

| Input form | A new block | Not given in the block | Empty block |
|---|---|---|---|
| list (CHD, WEL, ...; also MVR) | replaces all entries | removed | clears all |
| layer array (RCHA, EVTA) | replaces the arrays it names | retained | not a way to turn off; give a zero rate |
| grid array (CHDG, WELG, ...) | replaces the arrays it names | retained | clears all |
| advanced (SFR, LAK, MAW, UZF) | changes only what it names | retained | no effect implied; deactivate through settings |

So:

- List blocks are **snapshots**, carried until replaced. That's a step
  function written at its change points, not a delta. An omitted row is
  removed, which a delta can't say.
- Advanced blocks are true **deltas**.
- Layer and grid arrays are per-array snapshots, and differ on the empty block.
- MVR is grouped with the advanced packages by name, but behaves like a list
  (`mvr.tex:86` says so).

**The code is ahead of the plans.** `flopy4/mf6/period_arrays.py:8-20`
documents the layer and grid regimes, and notes that the DFNs and MF6's loader
disagree about grid arrays. Only the plans miss this. The `fill_forward` field
metadata is a boolean, though, so which regime applies is held in per-package
code rather than in the spec, and H2's "one convention can cover both"
doesn't hold as stated.

**How I'd address it:**

1. Rewrite H2 as two hypotheses. *H2a:* union records are sparse tables written
   as deltas, which is what it mostly argues. *H2b:* each period regime is a
   different encoding of a step function, and a logical relation has to be
   stated per regime.
2. Add the table above to the representation's "Period data", and make
   `dense()` follow it. Its current two-case rule misstates layer arrays.
3. Add partiality conditions to the RCH ↔ RCHA conversion: an empty RCH block
   maps to an explicit zero array, not an empty RCHA block.
4. Propose a `persistence` key in place of the `fill_forward` boolean, for
   `dfn-gaps.md` and for flopy4's field metadata. Values: `replace`,
   `per-array`, `per-setting`. The grid/layer difference could be a separate
   flag.
5. Raise the grid array DFN/loader disagreement with MF6, using the note in
   `period_arrays.py`.

### F5. Two open "To check against MF6" items are answered

`dfn-spec/overview.md` lines 532-534:

- **"Whether list RCH/EVT allow several entries in one cell":** yes. "Multiple
  list entries can be specified for a single cell" (`rch.tex:6`, `evt.tex:5`).
- **"Whether EVTA lacks segments":** yes. "Segmented evapotranspiration cannot
  be used with the READASARRAYS option" (`evta.tex:7`).

Delete both. Keep the other two.

### F6. The SDD's package taxonomy is wrong

**The SDD says** (`sdd.md` lines 44-49): a basic package "contains only input
variables applying statically to the entire simulation", and an advanced
package "contains time-varying input variables".

**MF6 says:** "simple stress packages (CHD, WEL, DRN, RIV, GHB, RCH and EVT)"
and "advanced packages (MAW, SFR, LAK, and UZF)" (`bcoptions.tex:49`), both
time-varying. The difference is F4's, plus whether features are defined once
(F1). MF6 also has "hydrologic package" (`gwf/gwf.tex:31`), "internal flow
packages" (`gwf/info_existing_users.tex:22`), and "utility" for OBS, TVK, TVS,
ATS, NCF and HPC.

**How I'd address it.** Rewrite this list in the SDD, using MF6's categories
with their membership. Drop "basic package". "Subpackage" may still be useful
for flopy4's child relation; say that it's flopy4's word (MF6's nearest is
"utility"), and that not every subpackage is a utility.

## 2. Conceptual gaps

### C1. "Logical content" is defined circularly

Layout is what re-encoding leaves unchanged in the logical content, and we find
logical content by asking what re-encoding and runtime memory preserve. The
labels were then made by hand with judgement calls, such as `XORIGIN`, which
"changes nothing MF6 computes" but is logical because it's a fact a conversion
must keep. F1 and F2 show where it strains: if bound identity is logical, RCH
and RCHA aren't "two layouts of one logical relation". If it isn't, MVR's
references aren't logical.

**How I'd address it.** Define logical content by an explicit list of
**observations**: two inputs have the same logical content if nothing on the
list can tell them apart.

| Observation | Example of what it distinguishes |
|---|---|
| MF6's results for this simulation | numerics options |
| what other components can refer to | bound numbers, boundnames, features |
| declared metadata a conversion must keep | `XORIGIN`, `CRS`, units |
| results after a permitted edit (see C4) | `AUXMULTNAME`, arguably `STORAGECOEFFICIENT` |

This is **observational equivalence**, and the choice of list is the design
decision. It makes the options' labels checkable, and gives the partial lens
a precise statement: RCH and RCHA agree on the first observation, and disagree
on the second.

In lens terms, identity is the **complement**: what `get` forgets and `put`
needs back. A layout is logical content plus a complement. RCH → RCHA is
partial because RCHA has nowhere to put RCH's complement when it's non-trivial.

Add this as a section in `dfn-spec/overview.md`, replacing the paragraph under
"Three levels" that begins "We find the logical level...". Have the
re-encoding test refer to it.

### C2. Equivalence has no single definition

The docs use at least five notions, and sometimes mix them:

- FUNC-7 reads as "load, write and run, with identical results".
- `layout-logical-decisions.md` line 217 calls a same-results layout change a
  bug under FUNC-7.
- `mmp-plan.md` line 74 says FUNC-7 "falls out of" tier E, but line 119 says
  the two check different things.
- "Round trip" means load → write → load in `loader-comparison.md`, and
  load → write → run → compare in `aliases-and-codemod.md`.
- "Same heads and budgets" gives no tolerance.
- `export.md`'s `from_xarray(to_xarray(x)) == x` is another notion, resting on
  array-aware equality (#394).

**How I'd address it.** Name a ladder, and use the names in every gate:

| Name | Holds when | Checked by |
|---|---|---|
| **object-equal** | `==` on components (#394) | load → write → load; `from_xarray(to_xarray(x))` |
| **text-equal** | files are the same bytes, perhaps up to whitespace | only where a test asks for it, e.g. snapshots |
| **layout-equal** | same blocks, options, control records and external-file choices | round trip |
| **logically equal** | same after normalizing by the option labels | tier E's input comparison |
| **result-equal** | MF6's heads and budgets agree within a stated tolerance | tier E; MF6's round-trip PRs |

Then restate:

- FUNC-7 as "layout-equal, and result-equal".
- The MMP gate as two lines with different names, removing "falls out of".
- The tolerance, from the existing framework comparison that
  `aliases-and-codemod.md` already relies on. Say what happens for a model
  that flopy3 and MF6 themselves can't reproduce.

The lens laws become test properties, not just vocabulary:

- **GetPut:** a round trip changes nothing, which is layout-equality.
- **PutGet:** what you set is what you read.
- For xarray, state both directions. `from_xarray(to_xarray(x)) == x` is only
  half. The other half, `to_xarray(from_xarray(ds)) == ds`, holds only for a
  canonical dataset, so `from_xarray` needs a stated domain: does it accept
  more than `to_xarray` produces? That's the open "dense form" question in
  `export.md` phase 2.

### C3. "As given" is undefined, and the code departs from it

Rule 1 says the object model holds input as given, and "a constant stays a
constant" (`layout-logical-decisions.md` line 60). But:

- `sdd.md` line 135 broadcasts griddata to full shape at construction, when
  the dimensions are visible.
- `FACTOR` is applied on load and not kept on `simplify-converter`
  (`converter-simplification.md` line 35), though the classification calls it
  layout "by construction".
- Field order is normalized to the DFN's on that branch, and remarks,
  whitespace, case and number formatting aren't discussed.
- Layout lives in three places: option fields, `ArrayIO`/`ListIO`, and
  `WriteContext`. Precedence between them is documented in the code
  (`component.py:289`), but no xarray doc mentions any of them, even though the
  export claims to be lossless and `representation.md` plans to carry layout
  options as an encoding record.

**How I'd address it.** Write a **fidelity table**, one row per layout
feature, deciding whether it's kept and where:

| Layout feature | Kept today? | Should be? | Held in | In the export? |
|---|---|---|---|---|
| `READASARRAYS`, `READARRAYGRID` | yes (class) | yes | class | type tag |
| `STORAGECOEFFICIENT`, `K22OVERK`, ... | yes (option) | yes | field | encoding record |
| `CONSTANT` | yes unless broadcast | decide (below) | value | 0-d, marked |
| `OPEN/CLOSE`, binary | yes | yes | `ArrayIO`/`ListIO` | **unspecified** |
| `LAYERED` | to check | yes | `ArrayIO` | **unspecified** |
| `FACTOR`, `IPRN` | no, on the branch | decide | | |
| field order | no, on the branch | no | | no |
| remarks, whitespace, number format | no | no | | no |

The "kept today" column above needs checking, and is only a starting point.
The rule then reads: *layout-equal means equal on the rows marked "should be"*.
This is where a concrete syntax tree analogy helps: flopy4 holds something
between a CST and an AST, and this table says exactly where.

Resolve the broadcast conflict directly. Either the SDD's construction-time
broadcast goes, or rule 1 becomes "a constant stays a constant unless its
dimensions were visible at construction". I'd remove the broadcast, as the
current behaviour makes the same call give different objects depending on
construction order, which is exactly what #226's decision is trying to avoid.

### C4. Static vs. dynamic uses MF6's clock, not flopy4's

A derivation is static when "every input is fixed once written", such as
`STORAGECOEFFICIENT`, because "the thickness it divides by is fixed". That's
true during an MF6 run. But flopy4 is an editing tool, and the option
classification argues from that for `AUXMULTNAME`. In an edit session, DIS can
change between writes.

So a held `sc` and a held `ss` agree when written, then behave differently
after a `top`/`botm` edit: the effective Ss follows thickness in one and not
the other. That's the same "same values now, different behaviour under change"
argument that made `AUXMULTNAME` logical. Likewise `K22OVERK` with an edit to
`k11`. The unit factors have no such issue, because their inputs are constants.

This doesn't undo the #229 decision: `Sto(sc=...)` holding SC as given is fine,
and `dense()`-style decoded forms are computed on request. It does mean
converting between the two encodings isn't edit-neutral, and the classification
overstates how harmless they are.

**How I'd address it.** Replace the two values with stages, the question being
*when is the rule's result fixed?*

| Bound at | Example | Safe to materialize? |
|---|---|---|
| **constant** (no other inputs) | unit factors, `COMPLEXITY` | yes |
| **edit** (inputs are other input data) | `STORAGECOEFFICIENT`, `K22OVERK` | at write time only |
| **run** (inputs change during the run) | `AUXMULTNAME`, TS/TAS, `LOCAL_Z` | no |

Keep the labels' tallies, since layout/logical doesn't change, but add to rule
3: *a decoded form is computed from the current inputs and never stored.* This
is binding-time analysis, whose terms are static and dynamic
([T3](#t3-theory-worth-adopting)). The existing `checked` column (`load`, `ar`,
`rp`, `ad`) in the constraint audit can use the same stage vocabulary.

### C5. Absence has no single concept

A missing value means different things, and they're treated one by one:

| Meaning | Example | Today |
|---|---|---|
| default applies | DFN `default`, `strt = 1.0` | #240 |
| carried from an earlier period | no block for this period | F4 |
| inapplicable under an option | UZF `pet` without `SIMULATE_ET` | #523 |
| explicitly no stress | DNODATA in a grid array | `FILL_DNODATA` |
| unset by the user | unset list column | `FILL_DNODATA`, `FILL_INT64`, `None` |
| deferred to a series | NaN plus `<name>_tas`, `<column>_ts` | representation |
| cleared | `q={3: None}` | `period_arrays.py` |

`representation.md`'s open question, "which float value for not set", can't be
answered until these are separated, since `FILL_DNODATA` currently means two
different things. #240's defaults belong here too.

**How I'd address it.** Add a section to the representation and the concepts
doc that states each meaning, its encoding in memory, in text files and in
netCDF, and whether `dense()` fills it. Codd's distinction between
applicable-but-missing and inapplicable is a useful starting split. Then settle
#240 and the fill value from that table.

### C6. Ownership, reference and binding aren't related

The SDD says the model is a tree. But exchanges and solutions refer to models,
SPC targets a package, and `Model.flow_model` crosses models. The docs use
parent/child, child field, reference field, binding, binding row, attach and
binding graph without saying how they relate. `layout-logical-decisions.md`
says "the parent/child relation is a binding row", and "binding graph" has no
definition.

**How I'd address it.** One short section:

- **Ownership** is a tree. Each component has at most one parent. It's what
  `DataTree` mirrors, and what writing walks.
- **Reference** is a directed edge between components, stored by name. It's not
  in the tree's structure.
- **Binding** is how a file states either one: a row or option in another file.
  Some bindings create ownership (PACKAGES rows), and some create references
  (a solution's `slnmnames`). An exchange's row does both.
- **Attach** is the Python operation that creates ownership, and **the binding
  graph** is the union of both kinds of edge.

Then #226, #259 and step 5's navigation can say which edges they touch, and
`representation.md` can say references are attrs, not tree edges. Also state
what happens to a reference when its target is renamed or removed.

### C7. Name resolution is specified twice

Dimension resolution goes children, then parent recursively, then own `dims`
(`sdd.md` line 119). The proposed `when` scope chain goes own options and
dimensions, then the model's other components, then the binding's parameters
(`dfn-spec/overview.md` line 355). They differ in order, and neither mentions
the other. `RowContext`, `LoadContext` and "package context" carry overlapping
state too, and row layout's `when` handling reads from them.

**How I'd address it.** Treat them as one concept, the **typing context**: what
a component's fields may depend on. Say in one place what's in it, in what
order, and who supplies it. Then either make the orders agree or explain why
not. Dimension resolution raising on disagreement may make its order
unobservable, in which case say that. This is a doc change now. Whether the code
merges these classes is a later question for the simplification survey.

### C8. Packages with children break the lossless export

`representation.md` line 314 says "Packages give an `xr.Dataset`, contexts an
`xr.DataTree`", and that packages are the tree's leaves. But `Rcha` has
`tas: list[Tas]` and `obs` children (`flopy4/mf6/gwf/rcha.py:68-71`), `Chd` has
`ts` (`chd.py:78`), and the SDD says packages can have children. A `Dataset`
can't hold those, so `from_xarray(to_xarray(rcha)) == rcha` fails as specified,
and `dense_steps` needs the series that would be missing.

**How I'd address it.** Choose, in `representation.md` and `export.md`:

- (a) A package gives a `DataTree` when it has children, and a `Dataset`
  otherwise. Honest, but the return type varies.
- (b) A package always gives a `Dataset`, and only a tree carries children, so
  a package exported alone isn't lossless. This breaks "looks the same whether
  exported alone or pulled out".
- (c) Every component gives a `DataTree`, with a `.to_dataset()` for a leaf.

I'd take (c), for the simplest stated rule and one return type. It does change
the planned `DatasetConvertible` split in phase 3.

### C9. Time has no home

Period, step, `totim`, `start_date_time`, datetime keys and TAS times are spread
over `representation.md`, `datetime-periods.md`, `tas-interpolation.md` and
`xarray/overview.md`. #243 is deferred to export phase 1, but `export.md`
doesn't mention it.

**ATS is missing.** The xarray docs never mention it. For an adaptive period,
"`nstp` and `tsmult` have no effect" (`doc/mf6io/utl_ats.tex`), and step lengths
depend on convergence. So:

- `tas-interpolation.md`'s step view, `(nstp_total, ...)`, can't be computed
  before a run for those periods.
- The representation's "the period of each step" mapping is a run result for
  them, not an input.

**How I'd address it.** A section in the period and time doc (Part 4) defining
the axes (`iper`, step, simulation time, calendar time) and how each is
derived. `step_array` should raise on an ATS period before a run, naming the
period. Period-level views are unaffected. A stepping view could later take its
steps from the output's times.

### C10. Component, DFN, class and instance aren't separated

"A component is one DFN" (`dfn-spec/overview.md` line 43), while the SDD treats
components as instances in a hierarchy. Five names identify a kind of thing
(`gwf-npf`, `Npf`, `NPF6`, `ModflowGwfnpf`, the type tag), and one identifies an
instance (`pname`, or `name`). In code, `Tdis`, `Solution` and `Exchange` are
`Package` subclasses and `Simulation` and `Model` are `Context`
(`flopy4/mf6/context.py`), and `export.md` relies on the latter without defining
it.

**How I'd address it.** Part 4's object levels section.

### C11. Grids: closed or open, and not all defined

`dfn-spec/overview.md` treats the grid as a parameter chosen from a set. FUNC-5
is a must-have at MVP and says new types can be added, so the set is open. But
`representation.md` line 238 has the dims for DIS2D, DISV2D and DISV1D as "not
yet defined", and they're an open question in `xarray/overview.md`. OLF and CHF
users would get fallback dims at MMP.

**How I'd address it.** State the grid's interface: its index set, cellid
width, dims and coordinates, one row per grid type. That's what FUNC-5's
extensibility would mean. Fill in the three rows, or put them on the MMP
decision list as explicitly deferred.

## 3. Terminology

### Precedence

When choosing a term, prefer in order:

1. **MF6's term**, if MF6 has one. Users read mf6io.
2. **A domain standard** (CF, UGRID, xarray, SQL), at that domain's boundary.
3. **An established theory term**, in developer design docs only.
4. **A new word**, only with a definition in the glossary.

### T1. Departures from MF6

| Plans | MF6 | Recommendation |
|---|---|---|
| "array variant", "`*A`", "G/A" (only in `converter-simplification.md` among live docs, undefined) | list-based, layer array-based, grid array-based | Adopt MF6's. It also fixes F2's confusion. |
| basic/advanced package (SDD) | simple stress, advanced, hydrologic, utility | See F6. |
| `bound` (54 lines) | "boundary", "boundary number", "entry"; `bound`, `nbound` in code | Keep `bound` as the role's name. In prose use F1's feature, list entry and grid entry. |
| `ftype` for all components | `mtype`, `exgtype`, `slntype`, `ftype` (`sim-nam.dfn`, `gwf-nam.dfn`) | Keep the unified attribute, and note the mapping in the glossary and SDD. |
| `per`, `kper`, `<name>_period`, "period key" | `iper` in the block header (1-based), `kper` in code | Pick one per context and state the base. Keep `per` 0-based in the representation, say in the glossary that it's `iper - 1`, and use `kper` only for flopy3 parity. |
| `stress_period_data` on OC, STO and others | PERIOD block | A public API choice: see D5. |
| "MF6 NetCDF (grouped)" | MF6 doesn't read it | See D3. Naming our format as MF6's implies an endorsement it doesn't have yet. |
| "namefile" (7) and "name file" (1) | "name file" (163 vs. 7 in mf6io) | Use "name file" in prose. |
| "fill forward", "carry forward" | "continue to apply", "retain" | Use "fill forward" as the xarray-world term, but only with a regime from F4. |
| "component" | IDM: `component` = `GWF`, `subcomponent` = `RCHA`; docs: "Stress Package Component (SPC)" | Keep flopy4's meaning. Note the difference for anyone reading IDM. |
| `user node` | `reduced node`, `user node` in source | Already consistent. Keep, and define both. |
| `x_world`, "world" | not used in DIS's docs; the DFN says "lower-left corner of the model grid" | Keep. Define it against flopy3's local/model coordinates. |

Already well aligned, so keep them: provider/receiver in the mover role names,
feature, boundname, control record, time-array series, cellid.

### T2. Overloaded terms

Line counts are from the live docs. Each gets a ruling, which the rename pass
then applies.

| Term | Senses in the docs | Proposed ruling |
|---|---|---|
| **layout** (183 lines, 17 docs) | MF6 file; runtime memory; NetCDF grouped/ungrouped; cell flat/layered; row | "Layout" alone means MF6 file layout. NetCDF: **profile** (D3). Cells: **cell indexing**. Rows: **row format**. Memory: "memory arrangement". |
| **package** (36 "the package") | MF6 package; the future Python package | Always the MF6 sense. The other is `mf6xr` (working name). Mostly `xarray/overview.md` and `export.md`. |
| **spec** (110) | DFN spec; `representation.md`; `flopy4.spec`; `mf6 --spec`; codegen's spec | Never bare: "DFN spec", "representation spec". |
| **view** (65) | computed form; SQL view; `flow_model` as a view; a row over `ItemTable` | A **view** is computed from held data, never stored, and states if it's read-only or two-way. Say "SQL view", and "row proxy" for `ItemTable`. |
| **context** (30) | `Context` class; binding context; `RowContext` etc.; MF6 memory context | "Binding arguments" for H3's sense; "typing context" for C7. Define `Context`, or rename the class (D6). |
| **rule** (124) | named FK rule; "the rule" (layout/logical); codemod rule; compat rule; K-kinds | "Named rule" for DFN; "**the as-given principle**" for the rule; "rewrite rule" for codemod; "constraint" for K-kinds. |
| **tag** (24+12) | type tag; `binding`/`schema` option tags; variant discriminator; DFN tagged; `modflow_input` tag | "Tagged" stays DFN. "Type tag" stays. **Discriminator** for variants. **Option attribute** for `binding`/`schema`. |
| **contract** (15) | `_contract.py`; data contract; import-linter contract; "input contract" | "Sync contract"; "data contract"; "import-linter contract"; "input rules". |
| **schema** (29) | DFN schema version; `schema` option tag; export schema; schema polymorphism; database schema | "DFN schema version"; "shape-determining option" for the tag; "representation" for export. |
| **level** (49) | layout/logical/runtime; H1's "where the tag sits"; `arity` | "Level" for the three levels only. H1's column becomes "site". |
| **output** (a label) | also `CONTINUE`, `NOCHECK`, `MAXERRORS`, `HPC6` | **directive** ("run directive" is the doc's own phrase). See D2. It's also not a level, though `constraint-audit.md` line 173 lists it as one. |
| **dynamic** (22) | derivation; DFN's `dynamic` key; "dynamic scope" | Binding-time words for derivations (C4). Keep the DFN key's name. |
| **kind** (53) | K-kinds; lens kinds; polymorphism kinds; `Dim.kind`; key kinds; `Header.kind` | "Key domain" instead of key kind. Others fine, qualified. |
| **field** (179) | attrs/DFN field; "a field over the grid" | Only the first. Use "gridded quantity" for the second. |
| **layered** | cell indexing; MF6's `LAYERED` | Always backtick and capitalize the keyword. |
| **sparse** (23) | sparse table; `sparse` library; `dense(sparse=True)` | See S6. |
| **row / entry / item / record / line** | list row; `entry` dim; `Item`; `Record`; DFN record; "control record" | **Row** for tables, and **entry** for an MF6 boundary row. `<field>_row` and `entry` dims should agree (S6). |

### T3. Theory worth adopting

Each row says what the term buys, so it can be dropped if it doesn't earn its
place. Only the "adopt in docs" ones should reach the plans' vocabulary, and
all belong in a side column of the glossary.

| Current wording | Established term | What it buys | Recommendation |
|---|---|---|---|
| layout / logical, "as given" | physical / logical schema; physical data independence (ANSI-SPARC) | The framework has a name and a literature. Views are the external schema. | Mention. Keep "layout", which MF6 people follow. |
| object model holds layout | concrete vs. abstract syntax tree | "Layout-preserving" becomes exact (C3). libcst is the model. | Adopt in docs. |
| lens | get, put, the lens laws, complement (Foster et al.; Bohannon et al. for relational lenses) | Identity as complement (C1). Laws as tests (C2). The view-update problem is exactly `from_xarray` of a dense view. | Adopt in docs. |
| re-encoding test | observational / contextual equivalence | Removes C1's circularity. | Adopt in docs. |
| static / dynamic derivation | binding-time analysis (partial evaluation) | Stages (C4). Already the same words. Beware "binding", which means something else here. | Adopt "stage" and "bound at" with care, or "fixed at". |
| "three kinds of polymorphism" | Cardelli–Wegner: parametric, inclusion, overloading, coercion; plus sums | See Part 4's type model. | Rename to "three kinds of variation". |
| sum type, arm | sum type, variant, arm | Already right. | Keep. |
| role, key | trait + associated type | H4 already says so. | Keep. |
| `(pname1, id1)` | dependent pair, `Σ(p: Package). Key(p)` | Explains why discriminated unions don't fit, more exactly than `schema-polymorphism.md`'s "tag on a different row". | Adopt in type model. |
| component parameter (H3) | dependent function, or an ML functor | Says it's parameterized by a value, unlike `list[T]`. | Adopt in type model. |
| `<=maxbound` | bounded index, `Fin n` | With F1: `Fin(nbound(p))`, dependent on the period. | Mention. |
| `k > 0`, `THTS > THTR` | refinement types | Places the numeric range gap (K2) in the same frame as the rest. | Mention. |
| `AUXILIARY`, `BOUNDNAMES` columns; `when` | row polymorphism; dependent records | Explains what `schema` options do: they're type-level. | Mention. |
| "dimension polymorphism" | shape polymorphism | Grid as a bounded parameter, `Model[G: Grid]`, with cellid as `G`'s associated type. Answers `schema-polymorphism.md`'s last open question. | Adopt in type model. |
| `dict[int, list[Item]]`, `Union[T, Ref]` | parametric type constructors, `Periodic[T]`, `Deferred[T]` | Names the real parametric cases. Could simplify `spec` and codegen. | Adopt in type model. |
| `_coerce_item_list`, `LegacyKwargs`, field converters | coercion | Separates "accepts many forms" from "is many types". | Mention. |
| period blocks | snapshot vs. delta; step function at change points | F4. | Adopt in docs. |
| missing values | Codd's applicable and inapplicable marks | C5. | Mention. |
| union records | entity-attribute-value | Already used. | Keep. |
| `dense` row key table | functional dependency: a dense form exists when key → value is a function | `duplicates=` is what to do when it isn't, and it unifies the table's rows. | Mention in representation. |

**A caution.** These are aids to precision, not requirements. Nothing here needs
a formal model, the user docs shouldn't use most of it, and MF6 developers
reading #287 shouldn't need it. Lead with plain statements and give the term
once in parentheses. If a term doesn't simplify a real decision, drop it.

## 4. Overview documents to add

Publish `concepts.md`. The others can stay under `plans/` until they settle,
then move through [`dev-docs.md`](dev-docs.md)'s process.

### 4.1 `docs/dev/concepts.md` (#217)

Two tiers on one page. **Users:** simulation, model, package, utility, exchange,
solution; stress period, time step; list-based, layer array, grid array;
feature, entry, boundname; `to_xarray`, `dense`. **Developers:** DFN, field,
binding, view, layout, representation, sync.

Glossary columns: term, meaning, MF6's term, flopy3's term, theory term (optional).
It also holds the rulings from T2, every acronym (MMP is expanded only in a
GitHub milestone description; also IDM, GRB, HDS, CBC, XMI, BMI, TVK, TVS), and
project shorthand (registry corpus, scoreboard, tier A-E, sync, dev3,
materialize, compat layer, legacy engine, `flopy4` vs. FloPy 4 vs. flopy 4.x).

### 4.2 The object levels (a section of the SDD)

| Level | Example | Identified by |
|---|---|---|
| DFN | `gwf-npf` | component name; also the type tag |
| class | `flopy4.mf6.gwf.Npf` | Python path; `ftype` `NPF6` |
| instance | `gwf.npf` | `name` (MF6's `pname`, `mname`) |
| file | `model.npf` | file name |

With the hierarchy (`Component`, `Context`, `Package`, and why `Tdis`, `Solution`
and `Exchange` are `Package`s), the taxonomy (F6), and C6's ownership and
reference. This replaces the current SDD "Concepts".

### 4.3 `dfn-spec/type-model.md`

The one place for what varies and what determines it. It replaces
`schema-polymorphism.md` and "Three kinds of polymorphism":

| Construct | Example | Determined by | Term | In Python |
|---|---|---|---|---|
| variant | SFR period row | a discriminator in the row | sum type | `Union` of arm classes |
| enum | `status` | closed set | finite sum | `Literal` |
| input form | RCH / RCHA | option in the file | sum at component level; layouts of one relation | separate classes |
| role | `mover_provider` | what the target declares | trait + associated type | registry / Protocol |
| polymorphic reference | `(pname1, id1)` | another value in the row | dependent pair | checked at resolve time |
| component parameter | SPC `target` | the binding | dependent function, functor | navigation property |
| conditional column | `boundname` | an option | dependent record | `when` |
| open columns | `aux` | an option's value | row polymorphism | tuple sized by name list |
| sized inline array | `pxdp` | a dimension | length-indexed | `shape` |
| bounded key | `<=maxbound` | a dimension | bounded index | `fk` |
| numeric range | `k > 0` | constant | refinement | not yet |
| shape | griddata | the grid | shape polymorphism | `GRID_DIMS` |
| periodic data | `dict[int, T]` | block presence | type constructor | `Periodic[T]` |
| deferred value | `T \| TimeSeriesRef` | the file | type constructor | `Deferred[T]` |
| accepted input forms | tuple or dict row | caller | coercion | converters |

Also here: C7's typing context, the scope chain with one order, and the unified
form of `when`.

A check against the code that this needs: whether the table matches what codegen
and `spec.py` do. Rows for `Periodic` and `Deferred` are proposals for naming,
and aren't necessarily classes.

### 4.4 `fidelity.md`

C1's observations, C2's equivalence ladder with the gate each rung serves, C3's
fidelity table, and the lens laws as test properties. Tier E, FUNC-7 and the
round-trip suite cite it.

### 4.5 `periods-and-time.md`

F4's regimes, C9's axes and ATS, `iper`/`per`/`kper`, and datetime keys' place.
`representation.md`'s "Period data" and "Time" then state only encodings, and
link here. #243 closes against it.

### 4.6 Absence (in `representation.md`)

C5's table, as a new section.

## 5. Plan structure and cruft

### S1. One road to 4.0

`mmp-plan.md` covers to MMP, with "After MMP" as a stub. `replacing-flopy-mf6.md`
has Phases, Parallel tracks, Before-X lists, and Longest chain, some repeating
`mmp-plan.md`.

**Address:** rename `mmp-plan.md` to `road-to-4.0.md`, or supersede it. One
sequence (Tracks), one set of gates (MMP, `4.x` cut, rc1, GA), one decision
table. `replacing-flopy-mf6.md` keeps the analysis and designs: where we stand,
question 1, layout, compat layer, tests, MF6 versions, and sizing. Its "Order of
work" and "Critical path" sections move to the road doc. The published roadmap
shouldn't depend on unpublished links, so decide whether `plans/` gets published
or the road doc stands alone.

### S2. Requirements lag the plan

- The SRS has no requirement for migration, compat or the legacy engine, the
  largest body of 4.x work. Add them ("same result or a clear error" is one).
- "Feature parity" at GA (`map.md` line 46) is undefined, while `model_splitter`
  is planned as legacy-only. Define parity as an inventory, with each flopy3
  feature marked as supported, legacy-only or dropped.
- NFR-4 (older MODFLOW programs, GA) has no plan beyond a mention in integration
  question 6. Plan it or change it.
- FUNC-8's `?1 km?` placeholder remains.
- FUNC-7 is a "could" at MVP, but its substance is a gate item for MMP. Raise it
  and move it.

### S3. The MMP gate misses work

- **`simplify-converter` isn't in `mmp-plan.md`.** It's 43 commits rewriting
  ingress and egress, and `datetime-periods.md` step 3 targets a function it
  deletes (`converter-rebase.md` line 171). Add it to Track A or a new track, and
  state the ordering against Track C.
- **MMP milestone issues in no live plan:** #160, #199, #200, #220, #282, #343.
  #243 only appears in passing. The milestone's 24 also include PRs #367 and #433.
- **#282/#367 (attrs vs. pydantic)** is the largest. It's open in the milestone,
  "stale" in the archive, and a stated condition in `xarray/overview.md`. It
  needs a decision: see D4.
- **From `map.md`, with no gate item:** maintenance and release plans, MF6
  version support plan, adapted examples, imod-python features, performance.
- **Track items without a gate:** `xarray/overview.md` steps 3-8 aren't placed in
  any track, except lazy xugrid and grid composition under G.

### S4. Contradictions to resolve

| Between | Conflict | Resolution |
|---|---|---|
| `map.md:36`, `mmp-plan.md:17` | betas begin at MMP, or end at it | `map.md` follows the 2026-11-03 decision. Then say what gate starts the betas. |
| `xarray/overview.md:201`, `replacing-flopy-mf6.md:266` | whether the move into flopy needs dropping the grid inheritance | The second: they become internal imports. Keep step 4 for extraction reasons, and say so. |
| `mmp-plan.md:74`, `:119` | FUNC-7 and tier E | C2. |
| `mmp-plan.md:99`, #258 | "component naming" vs. field names (name or longname) | Correct the label. |
| `replacing-flopy-mf6.md` layout, `export.md` | layout lists `mixins`; export deletes `mixins.py` | Drop it from the layout. |
| `schema-polymorphism.md`, `dfn-spec/overview.md` | two kinds vs. three, unions vs. classes, `variant_of` required vs. optional | Replace (4.3). |
| `layout-logical-decisions.md`, `sdd.md` | constant stays vs. broadcast | C3. |

### S5. Broken or stale references

- "Question 2" means a section (`replacing-flopy-mf6.md:241`) and an open question
  (`:492`). `mmp-plan.md` says "integration N". Rename the sections to "Should
  the engine go into 3.x?" and "How to do the replacement", and label the open
  questions **I1-I7** everywhere.
- `mmp-plan.md:99` cites an "Open decisions" section, which is "Open questions".
- `mmp-plan.md` and `export.md` cite `overview.md` "Open".
- `backlog.md:14` cites "step 4" of `record-unify.md`, which no longer has steps.
- `dev-docs.md:41` says to remove `_toc.yml` entries that are already gone.
- `converter-rebase.md` refers to `typed-loader-wiring.md`, which is archived.
- `schema-polymorphism.md` cites `discussion-287-comment.md` (an untracked draft)
  and devtools' `context-refs-plan.md`.
- `dfn-spec/overview.md`'s link text says `../components/reference-fields-notes.md`,
  but the link goes to the archive.
- `sdd.md` and `srs.md`'s doctoc tables of contents have dead anchors
  (`#conceptual-model`, `#object-model`, `#conventions`, `#use-cases`), and `sdd.md`
  says "The produce".
- `dfn-spec/overview.md`'s table of docs omits `schema-polymorphism.md`.

A small link check found the dead anchors and missing files. It doesn't catch
references to quoted section names or "step N". Adding a link check to CI for
`docs/dev/` would keep the former from coming back.

### S6. Duplication and consistency

- The DIS coordinates table is in both `representation.md` and
  `rotated-grid-index.md`. Keep the former, as `dev-docs.md` page 3 can link it.
- The level and label definitions are in both `dfn-spec/overview.md` and
  `layout-logical-decisions.md`. Link rather than repeat, once #287 is posted.
- `record-unify.md` and its backlog item overlap. Keep the plan.
- Two `overview.md` files make link text ambiguous, since `mmp-plan.md` shows both
  as `overview.md`. Rename the xarray one, whose real subject is
  `package-boundary.md`.
- `converter-rebase.md` is an agent runbook (worktree paths, "don't fetch or push").
  Fine while the work runs, then archive it, and don't treat it as a design doc.
- `dense(sparse=True)` returns the sparse table (`export.md` phase 2). Drop the
  argument; the export is already sparse.
- In the representation, period arrays have `<name>_period` while lists have `per`,
  and `entry` while other lists have `<field>_row`. Make one rule.
- The two-file split of `xarray/overview.md` and `representation.md` holds up,
  and I wouldn't change it.

### S7. Reference hygiene

- 249 bare `#N` references span this repo, devtools, modflow6, xattree, xugrid and
  flopy, and #35 means different things in different docs. Keep bare numbers for
  this repo only, and qualify the rest (`devtools#405`).
- Ten commit pins (`000f63c3`, `8d25e4b7`, `721503fe`, ...) make "current" hard to
  judge. Each doc states one baseline at the top, as most now do. Say whether the
  plan or the code wins when they differ.
- The MF6 commits differ too (`8aad7bc4a5`, `48f34498f3`). That's fine for
  reports, if stated.
- Reports such as `loader-comparison.md` and the two studies are point-in-time
  results, mixed with plans in the index. Mark them as reports.
- `test.md` is largely overtaken by tiers A-E. Merge it into the road doc or
  rewrite it against the tiers.

## 6. What I'd leave alone

- **The layout/logical framing.** The tests are sound, and F1-F4 refine its details
  rather than undermining it. The option split and its tallies stand.
- **"Layout" and "lens" as words.** Well defined once qualified, and neither has a
  better plain alternative here.
- **The constraint audit's taxonomy,** apart from the `output` level slip.
- **Separate classes for input forms.** The design consequence still holds under F2.
- **The archive.** It's as last written, so don't correct it.

## 7. Order of work

Sizes as in `replacing-flopy-mf6.md`: small is days, medium is weeks. These are
docs changes, except where marked.

| # | Work | Findings | Size | Needs |
|---|---|---|---|---|
| 1 | Correct the DFN spec docs, and check the #287 drafts for the same errors | F1-F5 | small | |
| 2 | Fix contradictions and stale references that need no decision | S4, S5, F6 | small | |
| 3 | Make the decisions | D1-D8 | small | you |
| 4 | Write `fidelity.md`, and restate the MMP gate and FUNC-7 | C1-C4, S2 | small to medium | 1, D7 |
| 5 | Write `concepts.md` and the term rulings | T1, T2, 4.1 | medium | 3 |
| 6 | Rename pass across live docs, one commit per term | T2, S6, S7 | small | 5 |
| 7 | Write `type-model.md`; archive `schema-polymorphism.md` | T3, C7, 4.3 | medium | 1, 5 |
| 8 | Write `periods-and-time.md`, the representation's absence section, and the package-children decision | F4, C5, C8, C9 | medium | 1, D1 |
| 9 | Rewrite the SDD's Concepts | C6, C10, C11, 4.2 | small | 5 |
| 10 | Merge sequencing into one road doc | S1, S3 | small | 3, 4 |
| 11 | Triage the MMP milestone against it | S3 | small | team, 10 |

**Why this order:**

- Step 1 goes first, as the #287 post and everything after inherit it. Hold the
  post until it's done.
- `fidelity.md` comes before the glossary because the gates depend on it, and
  Track A is the longest chain.
- The rename pass waits for the rulings, so it happens once. Doing it per term
  keeps the diffs reviewable and the commits revertable.
- Steps 4 and 8 feed Track A and export phase 1, so they're useful even if the rest
  stops there.

**Code that follows, not part of this work:** `keys.py` period-aware references
(F1), row-order warning (F1), a `persistence` metadata key (F4), `dense()` matching
the regimes (F4), `step_array` on ATS (C9), removing the broadcast (C3), export
return types (C8). Each goes to the plan it belongs to.

## 8. Decisions for you

| # | Decision | Recommendation | Depends on it |
|---|---|---|---|
| D1 | A package's export: `Dataset` or `DataTree` (C8) | always a `DataTree` | export phase 1 |
| D2 | Rename the `output` label to `directive`, including CSVs | yes, before #287 is posted | classification, audit |
| D3 | What to call our NetCDF forms | "flopy4 archive" for grouped until MF6 reads it; "MF6 NetCDF" only for ungrouped; "profile" for the pair | representation, `mf6xr` |
| D4 | #282/#367: attrs or pydantic | close both as decided for attrs, if you agree: the archive calls the plan stale and develop has moved on, but I haven't read the #282 thread | xattree v2, Track B |
| D5 | `stress_period_data` on OC, STO and similar | keep it, documented as flopy4's uniform name; changing it now costs more than the inaccuracy | Track B, compat |
| D6 | The `Context` class name | keep, and define it. Rename only with Track B's API changes | concepts |
| D7 | Round-trip fidelity for `FACTOR`, `IPRN`, order, remarks; result tolerance | `FACTOR` and `IPRN` kept, the rest not; tolerance from the framework comparison | Track A, `simplify-converter` |
| D8 | How much theory vocabulary reaches the docs | T3's "adopt in docs" set, in design docs, and never in user docs | concepts, type model |

## 9. Checks still open

- **`keys.py` and periods.** Does a `bound` reference check against the referring
  row's period? Not read for this audit.
- **SPC `bndno` on LAK.** `dfn-spec/overview.md` line 202 says connection *n*, with
  key `<=nlakeconn`. SPC's DFN says "the boundary package feature number". MF6's
  `check_flow_package` compares `MAXBOUND` to the flow package's `NBOUND`, and for
  MAW `maxbound = sum(ngwfnodes)`. Whether advanced packages can be SPC targets at
  all needs checking against `tsp-ssm.f90`.
- **What OBS means on a layer array.** RCHA and EVTA have `obs_filerecord`, though
  they have no bounds or boundnames. This tests F1's table.
- **Empty list blocks in flopy4.** `period_arrays.py` handles grid arrays. Whether
  list `None` or `[]` round-trips as an empty block wasn't checked.
- **The fidelity table's "kept today" column.** A starting estimate from the docs,
  not tested.
- **Grid entry numbering.** Established from the block's first array, in node order,
  per `Mf6FileGridArray.f90`. Confirm with an MF6 developer that it's a stable
  behaviour to rely on. I found the count documented in mf6io, but not the
  numbering.
- **The #287 drafts.** Searched for the errors in Part 1 only, which found line
  125 of the comment draft. Not reviewed otherwise, so read them again after step 1.
