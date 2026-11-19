# Binding rows: generate them once, interpret them generically

Follow-up to #501 (reference fields generated from the DFNs' model-name
keys). Goal: one generated description of each name-file binding row, and
one generic piece of code that reads and writes rows from it, instead of
row shape being reconstructed by heuristics in several places.

Objectives, in tension:
- derive as much as possible from the DFNs
- keep the implementation simple
- generated classes reflect their DFNs accurately

## Problem

A binding row registers a child component in its parent's name file
(sim-nam `models`/`exchanges`/`solutiongroup`, a model nam's `packages`).
The DFNs describe every row completely (v2 schema `2.0.0.dev3`, devtools
`b7c43566`):

| role | marked by | sim `exchanges` | sim `models` | sim `solutiongroup` | `<model>-nam` `packages` |
|---|---|---|---|---|---|
| type | column named by the File's `component_ftype` | `exgtype` | `mtype` | `slntype` | `ftype` |
| file | `File` with `component_ftype` | `exgfile` | `mfname` | `slnfname` | `fname` |
| child's own name | `pk` | — | `mname` | — | `pname` (**not marked yet**, see devtools plan) |
| references | `fk` (to `models.mname`) | `exgmnamea`, `exgmnameb` | — | `slnmnames` (string Array) | — |

Each component DFN also has its `ftype` (`GWF6-GWT6`, `IMS6`, `CHD6`;
`gwf-chd` and `gwf-chdg` are both `CHD6`).

Codegen discards the roles: a parent gets `child(block="exchanges")` and
nothing more. Runtime then rebuilds row shape in:

1. `converter/binding.py` `component_ftype(cls)`: ftype guessed from the
   Python class name (exchange name slicing, 4-letter `g`/`a` suffix,
   `slntype`). `component.py` `get_ftypes()` builds the token registry from
   those guesses, qualifying collisions by model prefix. `package.py`
   derives the default file extension from it.
2. `converter/binding.py` `Binding.from_component._get_binding_terms`
   (egress): `isinstance` cascade (Solution -> `_solved_models`; reference
   fields; Model/Package -> name).
3. `converter/ingress/structure.py` `_resolve_bindings` (ingress):
   `row[2]` is the pname unless Exchange/Solution; `_exchange_models`
   separately gives an exchange its models for its load context;
   `_apply_binding_terms` sets references after the load.
4. `utils/codegen/make.py` (#501): `_binding_row` searches back from the
   child to its row to generate reference fields; `_REFERENCE_NAMES`
   renames `slnmnames` -> `models`.

Nothing ties these together.

## Design

### 1. Generated `ftype`

Codegen emits the DFN's ftype on every component class:

```python
class GwfGwt(Exchange):
    ftype: ClassVar[str] = "GWF6-GWT6"
```

- Delete `component_ftype`'s heuristics; callers read `cls.ftype`
  (`get_ftypes`, `Package` default extension, `_resolve_bindings`
  matching, `attrs_xarray`'s G/A note).
- Handwritten bases (`Model`, `Exchange`, `Solution`, `Package`) declare
  `ftype: ClassVar[str]` without a value. `Solution.slntype` likely goes
  too (derive from `ftype` if still needed).
- The G/A pairs keep sharing an ftype (as in MF6); `get_ftypes`' collision
  handling and `_disambiguate_ga_variant` (peek at READASARRAYS /
  READARRAYGRID) stay. That's MF6 behavior, not a heuristic.
- Check: models' ftype (`GWF6`) comes from `<model>-nam`'s `ftype`, and
  exchange/solution tokens match what `component_ftype` produced, so no
  name file changes. The round-trip snapshot tests (#498) will tell.

### 2. Generated `row=` on child fields

Codegen, building a parent's child field for a list with a
`component_ftype` file column (`_child_field_spec`'s `component_ftype`
branch), emits the row as the child attribute each column maps to, in
column order:

```python
models: list[Model] = child(block="models", row=("ftype", "filename", "name"))
exchanges: list[Exchange] = child(
    block="exchanges", row=("ftype", "filename", "exgmnamea", "exgmnameb")
)
solutiongroup: list[Solution] = child(
    block="solutiongroup", row=("ftype", "filename", "slnmnames")
)
packages-style fields: child(block="packages", row=("ftype", "filename", "name"))
```

Role -> attribute: type column -> `ftype`; file column -> `filename`;
`pk` column -> `name`; `fk` column -> the reference field of the same
(safe) name. A column with no role: error at codegen (forces the DFN
annotation rather than a guess).

Keyword file records (`TDIS6 FILEIN`, `HPC6`), which aren't rows, are
untouched (`_keyword` children).

`flopy4.spec.child` gains `row: tuple[str, ...] | None`, kept in metadata.

### 3. One generic `Binding`

`converter/binding.py` becomes the single row <-> child mapping, driven by
the field's `row`:

- egress: `[value(child, a) for a in row]`; `ftype` upper, `filename` as
  posix, references as names (`reference_names`), list values spread
  (only the last column may be a list); trailing empty name dropped as now.
- ingress: given the row and the target class (matched by `cls.ftype`,
  G/A disambiguation as now), assign columns in order: `name` -> `name=`
  load kwarg, reference columns resolved against the models loaded so far
  (`resolve`, case-insensitive), a list column takes the rest.
- References are resolved **before** the child loads and passed in, so an
  exchange's load context comes from its own `exgmnamea`/`exgmnameb`.
  Delete `_exchange_models`, the pname-unless-Exchange/Solution branch and
  `_apply_binding_terms`.
- `_make_binding_blocks` (egress) and `_resolve_bindings` (ingress) call
  into `Binding` and keep only traversal (blocks, numbered
  SOLUTIONGROUP, dims providers first, unknown-row warnings).

Handwritten semantics that stay (the DFNs can't say them):
- `_reference_problem` (Exchange: model types per side; Solution:
  `solves`).
- A lone solution listing no models solves them all: a hook for a
  reference column's written value when empty, e.g.
  `Component._row_value(attr)` overridden by `Solution` to return
  `_solved_models()` for its models column. Keep it the only override.

### 4. Reference generation folded into the row pass

Build one index over the DFNs, component name -> (parent, row record),
once per codegen run (in `make_modules` / `build_component_spec`'s
caller), from the same lists `_child_link` resolves. Both the parent's
`row=` and the child's reference fields come from it. Delete
`_binding_row`.

## Open decisions

- **`slnmnames` vs `models`.** Generating names from the DFN makes the
  field `slnmnames` (consistent with `exgmnamea`), and `_REFERENCE_NAMES`
  goes. Recommended: DFN name, optionally a read-only `models` alias
  property on `Solution`. Decide before step 4; touches
  `Solution`/`simulation_methods`/`model.py` (`Model.solution`), tests,
  docs/examples using `Ims(models=...)`.
- **`pname` as `pk`.** Resolved: devtools `7f72ae21` (#400) marks
  `<model>-nam.packages.pname` as `pk` (plan:
  `~/dev/modflow-devtools/archive/pname-pk-plan.md`). Step 2 needs flopy4's
  devtools pin moved past it (currently `07d1273a` in `pixi.lock`) and a
  DFN re-sync. No hardcoded name-column rule is needed.

## Steps

Each a separate commit/PR, each verified with targeted tests plus the
round-trip snapshot tests (#498) touching name files.

1. Generated `ftype`; delete `component_ftype`. Sync at the contract commit
   (`flopy4 mf6 sync MODFLOW-ORG/modflow6@<DFN_COMMIT> --mf6-version
   <MF6_VERSION>`, not bare `sync`, which takes the latest release when no
   binary is on PATH).
2. `row=` on generated child fields; generic `Binding` for egress and
   ingress; delete the `isinstance` branches, `_exchange_models`,
   `_apply_binding_terms`.
3. Row index in codegen; reference fields from it; delete `_binding_row`;
   settle `slnmnames`.

Expected net: less handwritten code than today; every row's shape in one
generated place, one interpreter.

## Notes

- Run tests through `pixi run -e dev`, targeted (`-k`), not whole files or
  the full smoke suite.
- `_mixin_fields.py` now looks for attributes a base class lacks on its
  leaf subclasses (#501); generated `ftype`/fields on subclasses rely on it.
