# Reference fields: generic resolve and check

Status: done on `reference-fields` (`57056f57`..`7b230198`), to be merged
as is. Copy semantics changed after this plan: see [`reference-fields.md`](../components/reference-fields.md)
("retarget on join"); the "deepcopy like pickle" section below is superseded.
Next: "References from DFN keys", at the end.

Stacked on #497 (`exchange-models`). Branch `reference-fields`, worktree
`.claude/worktrees/reference-fields`.

## Problem

#496/#497 made the *declaration* of a reference field generic
(`reference()`), but everything that *uses* one is still written per field:

| Place | Per-field code |
|---|---|
| `Simulation.__setstate__` | lists `sln.models`, `exgmnamea`, `exgmnameb` |
| `_apply_binding_terms` (ingress) | `isinstance` Exchange/Solution, assigns fields by hand |
| `_solution_models` / `_exchange_models` | each repeats find + "isn't in the simulation" + type check |
| `Model.exchanges` | goes through `_exchange_models()` |
| `Binding.from_component` | `isinstance` Exchange/Solution |
| `Exchange.model_types` / `_model_type` | slice `dfn_name` 3 chars at a time |

A new reference field means touching each of these. The field doesn't say
what collection it resolves against or what it accepts, so callers hard-code
both.

## Design

Put the target and constraint in the field's metadata:

```python
reference(many=True, among="models", accepts=None, required=False)
```

- `among`: the field of the owner's parent the references resolve against
  (a solution's or exchange's parent is the simulation; `among="models"`).
- `accepts`: optional `(owner, target) -> bool`; a resolved target it
  rejects is an error on write.
- `required`: (single references only) a missing value is an error on write.

Value helpers in `flopy4/spec.py` alongside `reference_names` /
`referenced` (and `reference()` itself moves there from `flopy4/mf6/spec.py`);
the ones that need the tree are `Component` methods:

- `resolve(value, candidates)`: names -> the candidate of that name
  (case-insensitively, as MF6 does), objects kept, field shape kept.
  Unresolved names stay. Never uses truthiness (an empty component is falsy).
- `Component._resolved(name)`: `resolve` against `getattr(owner._parent, among)`.
- `Component._resolve_references()`: set each reference field of each of the
  component's children to its resolved value. Used by unpickling (replaces
  the hand-written list in `Simulation.__setstate__`).
- `Component._reference_errors()`: missing required, not in `among`, rejected
  by `accepts`, for each child. `Simulation.write` raises on any.

Call sites then:

- `Simulation.__setstate__` -> `resolve_references(self)`.
- `Simulation.write` -> `reference_errors` + `_solution_models(check=True)`;
  `_solution_models` keeps only solution rules (empty list = all; each model
  solved exactly once); `_exchange_models` and `_find_model` are deleted.
- `Model.exchanges` -> filter `sim.exchanges` on resolved references.
  No generic reverse lookup: `Model.solution` / `Model.exchanges` are
  read-only properties, and `solution` has solution-only semantics.
- `_apply_binding_terms` -> generic: reference fields in order, a single
  one takes one term, a list takes the rest; resolved with `resolve`
  against the models loaded so far.
- `Binding.from_component` -> Solution keeps `_solved_models()`; anything
  else with reference fields writes their names, in field order.
- Exchange model types: from the registry (`FNAMES[f"{t}-nam"]`), splitting
  the exchange's pair where both halves are model types instead of slicing
  3 characters. Generated packages load lazily, so each candidate model
  package is imported first (`Exchange.model_classes`, cached). Expressed as `accepts` on `exgmnamea` / `exgmnameb`.
  (Codegen is external, so the base `Exchange` declares this, not the
  generated classes.)
- `Solution.models` -> `accepts=lambda sln, m: sln.solves(m)`; the
  "can't solve" check moves to the generic one.

Also: a validator on single references (str, component or None).

## Optional: deepcopy like pickle

Copy references as names; the outermost copy calls `resolve_references`
on itself. Drops `_PENDING_REFERENCES` and `_copied`. Behavior change: a
lone copied solution/exchange holds names, not the original models (same
as unpickling). Separate commit so it can be dropped.

## Error messages

Generic, naming the owner, the field and the target:

- `exg0 has no exgmnameb`
- `exg0 refers to 'nope' in exgmnameb, which isn't in the simulation`
- `exg0 (Gwfgwt) can't refer to 'b' (Gwf) in exgmnameb`

Tests matching the old messages are updated.

## Testing

`pixi run -e dev smoke` plus `test/mf6/test_mf6_component.py` and any
test file touched.

## Next: references from DFN keys

### Why

Which way a reference points (solution -> models, exchange -> models) is
hand-coded: `reference()` declarations on the `Exchange` / `Solution` base
classes, and explicit Exchange / Solution branches in `Binding` and ingress.
It isn't arbitrary: in `mfsim.nam`, `models.mname` is a key, and the
`exchanges` / `solutiongroup` rows' model-name columns refer to it. Each row
belongs to its exchange / solution, so the reference sits on that component.
But nothing in the DFNs says so. The devtools v2 schema already has the
vocabulary (`pk`, `fk = "[component.]block.field"`, used for MVR's `pname1` /
`pname2`). sim-nam just isn't annotated.

### devtools side (another agent)

Plan: `~/dev/modflow-devtools/sim-nam-model-keys-plan.md`. In short:

- `models.mname`: `pk = true` (MF6 rejects duplicate names; checked in
  `SimulationCreate.f90`)
- `exgmnamea`, `exgmnameb`, `slnmnames`: `fk = "models.mname"`
- `utl-hpc.partitions.mname`: `fk = "sim-nam.models.mname"`
- schema: allow `fk` on string-dtype Arrays (for `slnmnames`); today Array
  `fk` must be integer (a per-cell zone index)

### flopy4 side (here)

Codegen is in `flopy4/mf6/utils/codegen` (`make.py`; base classes chosen by
`_base_class`, ~line 1350).

1. **Find the binding row.** For a component whose parent is sim-nam, find
   the sim-nam list row that binds it (the row with its type and file:
   `exchanges` for `exg-*`, `solutiongroup` for `sln-*`, `models` for
   models). Its columns with `fk` to `models.mname` are the component's
   reference fields, in row order. Single String -> `reference(many=False)`,
   string Array -> `reference()`. `required` follows the column's
   optionality.
2. **Generate the fields** on the generated classes (`Gwfgwf.exgmnamea`, ...,
   `Ims.models`) instead of declaring them on the bases. Name: keep the DFN
   column name (`exgmnamea`); for the solution, `slnmnames` vs our `models`
   needs a decision: rename in codegen (as `sim-nam` -> `simulation`) or
   accept `slnmnames`. Lean: keep `models` via a codegen rename table, since
   it's public API.
3. **Checks stay in code.** `check` (`_connects`, `_cant_solve`) can't be
   attached to a generated field from the base class. Options: a base-class
   hook `_reference_problem(field, model) -> str | None` that
   `_reference_errors` calls, replacing the field's `check` metadata. Lean:
   the hook, and drop `check` from `reference()`.
4. **Generic Binding / ingress again.** `Binding.from_component` writes the
   reference fields' names in field order; `_apply_binding_terms` assigns
   trailing terms in that order (a single field takes one, a list the rest).
   We dropped this before because order was our declaration order; now it's
   the DFN row order, which is the file's. The Solution special case
   (`_solved_models()`: the only solution listing none solves all) stays.
5. **Fallback.** Until devtools ships the annotations, the DFNs we sync from
   won't have them. Either wait to merge until a devtools release has them,
   or keep the hand declarations as a fallback when no `fk` is found. Lean:
   wait. A fallback would mean two sources of truth.
6. **Package references later.** MVR's `pname1` / `pname2` are already
   `fk = "packages.pname"`; the same codegen path could cover them when we
   get there (inside records, though: see the notes doc).

### Testing

Develop against a local devtools branch (install it editable in the pixi dev
env, or point sync at locally migrated DFNs), regenerate, then run
`test_mf6_component.py`, `test_mf6_load_all_models.py`, codegen tests, and
smoke. Generated-file diffs should only add the reference fields to exchange
and solution classes.

### Status (flopy4 side)

Branch `dfn-references` (off develop `46ef2fab`), commit `dc86e843`, local
only. Steps 1-4 done: `_binding_row` / `_reference_specs` in codegen, the
`slnmnames -> models` rename table, `_reference_problem` hook (`check`
dropped from `reference()`; `many` added to its metadata), generic
`Binding` terms and `_apply_binding_terms`. Generated exchange/solution
modules were produced from DFNs annotated in-process (the cached develop
DFNs aren't at the contract commit, so only the annotation's diff was
applied). `test_reference_fields_from_keys` annotates the fixture DFNs
itself until devtools ships the keys. Remaining: once devtools releases,
re-sync and drop the test's annotation helper; don't `sync` before then
(it would regenerate exchanges/solutions without reference fields).

Update: devtools #396 (b7c43566) merged with the sim-nam keys (`mname` pk;
`fk = "models.mname"` on `exgmnamea`, `exgmnameb`, `slnmnames`; utl-hpc
`partitions.mname` fk `sim-nam.models.mname`). `dfn-references` now pins it
(commit after dc86e843); sync at the contract commit reproduces the committed
modules exactly, `_with_model_keys` is gone, and the mixin gap check follows
base classes into leaf subclasses (it flagged `Solution.models`).
