# Reference fields

**Status: implemented** (#496, #497 and later refactors on develop).
This records the design, what was tried and dropped, and what's deferred.

## What they are

A **reference field** holds components a component refers to but doesn't
own: a solution's `models`, an exchange's `exgmnamea`/`exgmnameb`. Values
are model objects or names. Names are looked up late, at write. A component
created without a parent joins the simulation its references belong to.

## Design

- **Generated from the DFNs.** A column of the component's row in its
  parent's name file with an `fk` to the parent's models is a reference
  field, declared with `flopy4.spec.reference(many, required, alias)`.
- **Resolved and checked once, generically.** `flopy4.spec.resolve`,
  `Component._resolved`, `_resolve_references` and `_reference_errors` do
  this for every reference field. References resolve among the parent's
  (the simulation's) models.
- **Each component says what it accepts.** `_reference_problem(field,
  model)` returns a specific message, or `None`. An exchange checks the
  model type on each side ("needs a GWT model b"), taking the types from
  its ftype (`GWF6-GWT6` → `("gwf", "gwt")`). A solution checks that it
  can solve the model (`_cant_solve`), and the same check covers a lone
  solution's implied models, so that message exists once.

### Copying, pickling and joining

- **Deepcopy keeps reference fields as they are** (the original model
  objects).
- **Joining a simulation retargets them.** When a component joins a
  simulation (construction with `parent=`, `.parent = sim`, `sim[key] = x`,
  a child field's assignment or list append, or a copied simulation
  adopting its copied children), each reference to a model object that
  isn't among that simulation's models is retargeted to the simulation's
  model of the same name (`flopy4.spec.retarget`,
  `Component._retarget_references`). Unmatched references are kept and
  error on write.
- References to the simulation's own models, and references held as names,
  are left alone. Nothing retargets at write, so replacing a model under a
  solution that refers to the old one is still a dangling-reference error.
- **Pickling** reduces references to names. Unpickling a simulation
  resolves them.

So `deepcopy(sim)` refers to the copied models, in any field order;
`deepcopy([ims, gwf])` keeps the originals; a lone copy follows renames;
and a lone copy added to another simulation refers to that simulation's
models.

## Tried and dropped

- **A reverse lookup (`referrers`).** `Model.solution` and
  `Model.exchanges` are read-only properties, and `solution` has
  solution-only semantics (a lone solution listing nothing solves every
  model), so a generic reverse lookup didn't fit.
- **`among`**, a parameter saying where to resolve. Every use resolved
  against the referrer's parent, and the likely next references (below)
  wouldn't be served by it.
- **Copying references by name**, as pickling does. A lone copied solution
  or exchange then held names and stopped following model renames. The
  earlier approach, deferring the mapping with a deepcopy memo key, kept
  objects but needed order-sensitive bookkeeping. Retarget-on-join keeps
  objects without the bookkeeping.

## Deferred: package references

The likely next references are package names: `flow_package_name`
(LKT/SFT/MWT/UZT and the GWE equivalents), SSM `pname`, MVR
`mname`/`pname`. Most point across models (a GWT/GWE package to a GWF
package), and several live inside rows or records, not top-level fields.
The lookup would need to reach another model's packages through the
exchange connecting them, and references inside records need their own
design.

Don't generalize `reference()` before then. Binding-graph navigation
([../spec/overview.md](../spec/overview.md#step-5-binding-graph-navigation))
is the likely shared mechanism for both.
