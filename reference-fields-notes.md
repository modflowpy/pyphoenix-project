# Reference fields: design notes

How the reference-field mechanism from #496/#497 was reviewed, refactored,
evaluated and trimmed. Branch `reference-fields` (stacked on #497, now on
develop).

## Starting point (#496, #497)

A *reference field* holds components a component refers to but doesn't own:
a solution's `models`, an exchange's `exgmnamea` / `exgmnameb`. Values are
model objects or names; names are looked up late (at write). A component
given no parent joins its references' simulation.

#497 generalized the field declaration (`reference(many=False)`) and the
"join your references' parent" hook. Everything that *used* a reference was
still written out per field:

- `Simulation.__setstate__` listed `sln.models`, `exgmnamea`, `exgmnameb`
- ingress `_apply_binding_terms` and `Binding.from_component` branched on
  `isinstance(Exchange / Solution)`
- `_solution_models` and `_exchange_models` each repeated the lookup, the
  "isn't in the simulation" error and a type check
- `Model.exchanges` went through `_exchange_models()`
- `__deepcopy__` used a memo key (`_PENDING_REFERENCES`) to defer mapping
  references to copies, with an order caveat for `deepcopy([ims, gwf])`

## First pass: make use of references generic

Put target and constraint in field metadata
(`reference(many, among, accepts, required)`) and write resolve / check
once: `flopy4.spec.resolve`, `Component._resolved`,
`_resolve_references`, `_reference_errors`. Exchange model types from the
class registry instead of slicing the DFN name. Ingress and `Binding`
assigned / wrote reference fields in field order. Deepcopy copied
references by name (as pickling does) and resolved them in the copied
parent.

A reverse lookup (`referrers`) was proposed and dropped: `Model.solution`
and `Model.exchanges` are read-only properties, and `solution` has
solution-only semantics (a lone solution listing nothing solves all).

## Evaluation: was it a real simplification?

Partly. Library code went +216 / −183 (net +33).

Real wins:

- **Deepcopy**: memo bookkeeping and the order caveat gone; copy and pickle
  follow one rule. (Behavior change: a lone copied solution / exchange holds
  names, not the original models.)
- **Simulation**: `_exchange_models` and `_find_model` gone, setstate is
  one call, the "isn't in the simulation" error written once.
- **Correctness**: single references validated; loaded and built exchanges
  get models the same way.

Lateral moves or worse:

- Registry-based `model_classes`: ~25 lines (lazy imports, cache) for a
  2-line slice; every MF6 model type has 3 letters. It also broke under
  xdist (registry not populated until the model package was imported).
- Generic `Binding` branch read worse than the explicit one, and Solution
  stayed special-cased anyway.
- Field-order ingress silently coupled namefile term order to declaration
  order.
- The "can't solve" check was split across the generic check and
  `_solution_models` (for implied models).
- Generic error messages lost specifics ("needs a GWT model").

Does the generality pay off? The likely next references are package names:
`flow_package_name` (LKT/SFT/MWT/UZT, GWE equivalents), SSM `pname`, MVR
`mname`/`pname`. They mostly point across models (GWT/GWE package to GWF
package) and several live inside rows/records, not top-level fields.
`among` (resolve against the referrer's own parent) wouldn't reach them,
so it was a parameter with one value, generalizing toward cases it
wouldn't serve.

## Trims

- Dropped `among`: references resolve among the parent's `models`.
- `model_types` back to slicing the DFN name's 3-letter halves (documented).
- Explicit Exchange branches back in ingress and `Binding`
  (`flopy4.spec.resolve` kept for the lookup).
- `accepts` -> `check`, returning the problem or None, so messages are
  specific again. A solution's check (`_cant_solve`) is also used for the
  lone solution's implied models, so that message exists once.

After trims: +186 / −166 (net +20), mostly docstrings. Kept: generic
resolve / check, deepcopy-by-name, validator.

## Commits

- `57056f57` resolve and check reference fields generically
- `4e141f3d` copy references by name, as pickling does (droppable)
- `c2245862` test ids for invalid exchange cases (Windows tmpdir paths;
  also failing on develop)
- `d45be932` trim reference fields to what they're used for
- (next) keep references on copy, retarget them on joining a simulation

## Copy semantics: retarget on join

Copying references by name (`4e141f3d`) lost something: a lone copied
solution / exchange held names, so it no longer followed a model rename.
The original memo approach kept objects but needed deferred-resolution
bookkeeping. Third option, adopted:

- Deepcopy keeps reference fields as-is (the original model objects).
- When a component *joins* a simulation (construction with `parent=`,
  `.parent = sim`, `sim[key] = x`, a child field's assignment or list
  append, or a copied simulation adopting its copied children), each
  reference to a model object that isn't among that simulation's models
  is retargeted to its model of the same name (`flopy4.spec.retarget`,
  `Component._retarget_references`). Unmatched ones are kept, and error
  on write.
- References to the simulation's own models, and names, are left alone.
  Nothing retargets at write, so replacing a model under a solution that
  refers to the old one is still a dangling-reference error.
- Pickling still reduces references to names; unpickling a simulation
  resolves them.

Outcomes: `deepcopy(sim)` refers to the copied models (any field order);
`deepcopy([ims, gwf])` keeps the originals; a lone copy follows renames;
a lone copy added to another simulation refers to that simulation's
models.

## When package references come

Revisit then, with the real cases in hand: the lookup would need to reach
another model's packages (via the exchange connecting them), and
references inside records need a story too. Don't generalize `reference()`
before that.
