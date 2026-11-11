# Binding navigation, and one conversion

Written 2026-11-11. This is step 4 of [ddl-next-steps.md](ddl-next-steps.md#4-binding-navigation-and-one-conversion),
which is steps 5 and 6 of the [overview](overview.md#step-5-binding-graph-navigation). Nothing here
is started.

## Where this starts

Step 3 put binding parameters in the DFN schema, on devtools' `binding-params` branch
(`/Users/wbonelli/dev/modflow-devtools-binding-params`). It went past the
[sketch](parameter-sketch.md) in one way that matters here: binding now works like a function call.

- A component declares `params` as a signature, with `type` and an optional `rule`.
- The `file` field that binds it passes `args`. Each argument names exactly one thing: a column of
  the binding row, following its `fk`, or one of the binder's own parameters.
- The binder isn't a parameter. It's the file's owner, as `self` is, so `utl-obs` declares none.
- An unpassed parameter is unset: GNC and MVR under a model get no models.
- `flow_model` stays a rule. No binding edge reaches a transport model from its flow model, so
  that one lookup runs backward, from the model to the exchanges that name it. A follow-up could
  make it a parameter, passed by `mfsim.nam`, which has the pairing: see
  [flow-model-param.md](flow-model-param.md).

| Binder's `file` field | Passes | To |
|---|---|---|
| `sim-nam` `exchanges.exgfile` | `{ model1 = "exgmnamea", model2 = "exgmnameb" }` | all 8 exchanges |
| `exg-gwfgwf` `mvr6_filename`, `gnc6_filename` | `{ model1 = "model1", model2 = "model2" }` | `gwf-mvr`, `gwf-gnc` |
| `gwt-ssm`, `gwe-ssm` `fileinput.spc6_filename` | `{ target = "pname" }` | `utl-spc`, `utl-spca` |

**The flopy4 side waits** until the DFNs switch: the branch merges, and flopy4 regenerates against
it. Parts A and B below are flopy4. Part C, the conversion, depends on none of this and can start
any time.

[bindings-as-attribute-grammar.md](bindings-as-attribute-grammar.md) maps this onto attribute
grammars, and draws some predictions for the design below from it.

## The goal

Simpler concepts in the spec, and simpler code in flopy4. Where the two conflict, or where either
grows, stop and decide rather than build through it.

**The test of the construct:** every parameter in a real simulation resolves from its binder's
`args`, along binding edges, using one function. The owner is implicit. `flow_model` is the only
lookup that runs backward. Anything else that needs its own search is a finding, to record and
not to work around.

## Before the flopy4 side

Settle these before the branch merges, since flopy4 would be written against them. Each is short.

- [x] **Unset vs. default.** Done in `896a2050`. Say in `dfnspec.md` that unset means null everywhere, and that a
  cellid whose model is null means its owner's model. Today, GNC's cellid reads unset `model1` as
  "this model", and MVR's `when = "model2"` reads unset `model2` as absent. Both behaviours are
  right, but they read as two meanings of "unset".
- [x] **An argument may go through a rule.** Done in `896a2050`. SSM's `pname`, which `target` is passed, has
  `rule = "flow_model"` on its `fk`. Say that following an argument's `fk` applies its rule, and
  that the parameter's own `rule` (`no_advanced_transport`) applies after that.
- [ ] **The SSM row** (see open questions).
- [ ] **The OBS checks** (see open questions).
- [x] Update `ddl-next-steps.md`'s step 3 entry.
- [ ] Push `216c8d75` and `896a2050` with the user's OK.

## Open questions

### The SSM row

A parameter comes from the binding row. flopy4 has two kinds of binding row:

- **Name-file rows** (`sim-nam`'s `models` and `exchanges`, a model's `packages`) aren't stored as
  rows. Their columns are spread onto the child: `exchange.exgmnamea` already holds the model
  object, as a reference field. So `Exchange.model1` exists today, under another name.
- **Other rows** are real rows in the parent. SSM's `Fileinput(pname, spc)` holds the SPC file as
  a field. `keys.py` gets back to that row by scanning the parent (`_binding_package`).

`args` on a name-file row is the mapping codegen needs: it names which column is which
parameter. The question is the other kind. Can the SPC reach its row without a scan?

- **A back-reference** to the row, set when the child is attached. It's general, but it's new
  state to keep right on every attach and copy.
- **Spread SSM's row onto the SPC**, as name-file rows are. It's uniform, but `pname` is SSM's
  data, so it would be duplicated, or moved out of SSM.
- **Keep the scan,** inside the one resolver, for non-name-file rows. There are only two binders
  (the SSMs), so it's cheap, but it's a second path.

Decide with the user. Whichever it is, it should also cover `LoadContext.models` (below).

The [attribute grammar reading](bindings-as-attribute-grammar.md#what-it-suggests-for-flopy4)
leans to the back-reference. An argument is an equation of the binding, so evaluating it needs the
binding row, and name-file children already have theirs, spread onto them. A back-reference gives
every child the same thing.

### The OBS checks

`keys.py` misses 22 broken OBS copies that MF6 rejects. Those were the sketch's main argument for
parameters. The branch dropped `obstype`'s `fk` and the reserved `observations` key. That was
right, since a reserved name is a one-off, but now nothing in the DFN declares the check.

The spec already says the target's `[observations]` table declares its types, and picks the arm
for `id` and `id2`. The question is whether that sentence is enough for a consumer to check:

- that `obstype` is one of the target's types;
- that `id` and `id2` name rows of the target, by position, boundname or cellid, for that type.

If it is, the check is generic code over `[observations]`, and the DFN needs nothing. If not,
decide what's missing. Start from the 22 copies: sort them by which of the two checks catches
them.

## A: navigation in flopy4

### What there is today

Navigation is spread over several mechanisms, each with its own lookup:

| Where | What | Becomes |
|---|---|---|
| `keys.py` `_unbound` | walks up to the nearest ancestor with references (MVR's `mname`) | `param()` |
| `keys.py` `_binding_package`, `_ssm_package` | scans the parent for the row holding this file (SPC) | `param()`, plus the `no_advanced_transport` rule |
| `keys.py` `_flow_model` | finds exchanges that name the model | the `flow_model` rule, on `Model.exchanges` |
| `keys.py` `_context`, `_instance`, `_row` | follow a path `fk` | stay. Path `fk`s aren't parameters |
| reference fields (`flopy4/spec.py`, #501) | a name-file row's model names, on the child | generated parameters |
| `LoadContext.models`, `_exchange_widths` | an exchange's models, by position `"1"`, `"2"`, inherited by GNC, MVR and OBS when loading | `param()`, by name |
| `gwf/mvr.py` | `rule="exchange_models"` on `mname`, `mname1`, `mname2` | `fk` to `model1`, `model2` (regenerated) |
| `utl/spc.py` | `rule="ssm_package"` on `bndno` | `key="bound", param="target"` (regenerated) |
| 6 generated classes | `cellid_(model="1")` and `"2"` | `"model1"`, `"model2"` (regenerated) |

### The design

- **Parameters are generated attributes on the child,** from its DFN's `params`. Reference fields
  become the case where the argument names a name-file row column. The renames come from `args`,
  so codegen guesses nothing. This replaces the row-column guessing in `binding-rows-plan.md`'s
  design, and the two plans should agree before either is built.
- **One resolver,** used by `keys.py`, loading (`LoadContext`) and writing. Roughly:
  ```python
  def param(component, name):
      arg = binding_args(component)[name]       # from the binder's file field
      if arg is None:
          return None
      if arg in component.parent.params:
          return param(component.parent, arg)
      return follow_fk(binding_row(component), arg)  # applies the fk's rule
  ```
  Then the parameter's own `rule`, if any. `binding_row` is the SSM row question. In attribute
  grammar terms this is a demand-driven evaluator of inherited attributes, with three kinds of
  equation: a copy rule (the parent's parameter), a reference (a row column's `fk`), or null.
- **No caching, at first.** The tree is mutable, and no chain is longer than two links (`sim-nam`
  to the exchange to the mover), so a cache would cost invalidation for little gain. Add one only
  if profiling asks for it.
- **`flow_model` reads `Model.exchanges`,** which already collects the exchanges naming a model: a
  collection attribute. Nothing else in the design should need one. If something does, it's a
  finding.
- **The owner is `_parent`.** `Obs.target` is just that, with no parameter.
- **Writers set `MODELNAMES`** from `model2`, so users never do. Its `when = "model2"` with
  `optional = false` says when it's written.

### Tasks

- [ ] Regenerate against the merged branch, and fix what breaks (the table's last three rows)
- [ ] Generate parameters, and fold reference fields into them
- [ ] The resolver, with `binding_row` as decided
- [ ] Move `LoadContext.models` onto it, keyed by parameter name
- [ ] Check when loading can resolve `flow_model`. Every parameter is known before its child loads,
  since the parent's binding row is read first. `flow_model` isn't: it needs `sim-nam`'s
  exchanges, which come after its models. Find where flopy4 loads exchanges relative to models,
  and whether a load-time check of SSM's `pname` needs a second pass, or waits until the
  simulation is built
- [ ] Implement `flow_model` on `Model.exchanges`
- [ ] Writers set `MODELNAMES`
- [ ] Delete what the table says becomes `param()`

## B: `keys.py` on the resolver

- [ ] `mname`, `mname1`, `mname2` check against `model1` and `model2`
- [ ] `bndno` checks against `target`'s `bound` key set. A target that doesn't play `bound` is an
  error, not a skip, so SPC on RCHA or EVTA is reported. This is the role error from step 3's
  to-do list
- [ ] SPCA's target is RCHA or EVTA, by its parameter's `type`
- [ ] The OBS checks, in whatever form the open question settles on
- [ ] Rerun `key_errors` on the corpus and the 49 built models. Compare with the slice's rules on
  the 53 and 78 broken copies, as stages 2 and 3 did

## C: RCHA ↔ RCH

The overview's step 6. RCHA is common, at 92 packages in 87 models, and `v_rch_rate` has run on
real data, including twri since #545, so there's a test bed.

- Convert through an explicit intermediate: a rate per cell per period.
- Report what can't convert, with the conditions from the overview's "Lenses": `READASARRAYS`
  excludes `SURF_RATE_SPECIFIED`, there's no TAS on DISU, and so on.
- Without `FIXED_CELL`, MF6 moves recharge to the highest active cell at run time, so a static
  conversion is exact only with `FIXED_CELL`, or where the top cell is always active. Say which,
  per model.
- **Done when** each RCHA model in the corpus converts to RCH and back, or reports why not, and
  converted models run in `mf6` with matching budgets.
- If that's clean, EVT ↔ EVTA and CHD ↔ CHDG follow. CHD ↔ CHDG renumbers entries, so MVR and SPC
  rows referring to them must follow, which is where it meets part A.

twri is already a known case: 15 of its 225 recharge cells are CHD cells, where MF6 applies no
recharge, and `v_rch_rate` reports the rate as written.

## Measures

Count before and after, in flopy4:

- lookups that search for a binding (functions, not lines);
- lines in `keys.py`, `load_context.py` and the reference-field code;
- mechanisms that know an exchange has two models (today: reference fields, `LoadContext`,
  `keys.py`, generated `"1"`/`"2"`).

## Fails if

- A parameter on a real simulation needs a lookup other than `param()` and `flow_model`.
- flopy4 ends up with more navigation code than it started with.
- The OBS checks need a construct used only by OBS.

Then the call-site form isn't enough, and that goes back to the spec before more code.

## Predictions, written before looking

- Every parameter resolves through `param()`. The SSM row is the only awkward part, and ends up
  as a scan kept inside the resolver.
- `LoadContext.models` folds in easily, and is the biggest simplification, since loading is
  where positions `"1"` and `"2"` leak furthest.
- The OBS type check needs nothing new in the DFN. The id checks need the target's row keys by
  arm, which the `[observations]` tables already imply.
- The SPC role error finds nothing in the corpus, which has no SPC, and only the 49 built models
  test it.
- RCHA → RCH is clean on most of the corpus, with `FIXED_CELL` absent as the main partiality.

Added after mapping bindings onto attribute grammars
([bindings-as-attribute-grammar.md](bindings-as-attribute-grammar.md)), still before looking:

- `param()` needs no cache. Resolving every parameter in the largest built model takes well under a
  millisecond each.
- Loading resolves every parameter in one pass, top down, and `flow_model` is the one exception:
  checking SSM's `pname` at load time needs the exchanges, so it runs after the simulation is
  built, or not at load time at all.
- `Model.exchanges` is the only collection needed. `flow_model` is a one-line lookup in it.
- The SSM row settles as a back-reference, and name-file reference fields become a special case of
  it, not the other way round. This
  revises the first prediction above, which said a scan.
