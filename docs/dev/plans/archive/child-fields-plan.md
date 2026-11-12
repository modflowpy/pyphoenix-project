# Child fields from DFN component links

Replace codegen's hardcoded `BINDINGS` and `SUBPACKAGES` tables
(`flopy4/mf6/utils/codegen/make.py`) with one rule driven by the DFN, and
`spec.subpackage()` with one `spec.child()` decorator. Builds on
`../modflow-devtools/subpackage-links-plan.md` and supersedes parts of
[`package-binding-plan.md`](package-binding-plan.md) (see "Relation to other plans").

## Background

Some fields name the input file of another component. There are three
syntaxes, but one concept:

| Case | Syntax | Target |
|---|---|---|
| Subpackage (`ncf`, `ts`, `obs`, `tvk`, ...) | record `NCF6 FILEIN <file>` | fixed (`utl-ncf`) |
| Simulation TDIS | tagged scalar `TDIS6 <file>` | fixed (`sim-tdis`) |
| Name-file rows: models, exchanges, solutions, model packages | list row `<type> <file> [terms]` | picked by the row's type column |

flopy4 holds the child component instead of the filename, and generates the
record or row from it.

- **Contexts** (simulation, models): already work this way at runtime.
  - Egress: `_make_binding_blocks`, `converter/egress/unstructure.py:35`.
  - Ingress: `_resolve_bindings`, `converter/ingress/structure.py:454`.
  - `converter/binding.py:Binding`.
- **Packages:** `subpackage(file_field=...)`, `spec.py:166`, emits a child
  next to a path field (`ncf` beside `ncf_file`).
  - `Package._sync_subpackage_files` (`package.py:360`) copies the child's
    filename into the path field.
  - Nothing loads the child.

The dev3 DFNs don't say which fields are links, so codegen hardcodes them:

- `SUBPACKAGES`: record name → component. Only `ncf_filerecord` today.
- `BINDINGS`: sim-nam field → `ChildField(py_name, type, factory, imports,
  converter)` for `tdis6`, `models`, `exchanges`, `solutiongroup`.

In dev3, the filename columns are plain `String`: `tdis6`, `mfname`,
`exgfile`, `slnfname`, `*-nam` `fname`. The file record filenames are
`File(direction="in")` with no link.

The DFN already has everything else needed to pick the targets:

| Components | Parent | Type / subtype |
|---|---|---|
| `{gwf,gwt,gwe,prt,chf,olf}-nam` | sim-nam | type `model` |
| `exg-*` | sim-nam | subtype `exchange` |
| `sln-ims`, `sln-ems` | sim-nam | subtype `solution` |
| `sim-tdis` | sim-nam | — |

## Decisions already made

- **Follow the DFN for names.** No `solutiongroup` → `solutions` override:
  the field becomes `Simulation.solutiongroup`. This is a breaking rename;
  update its callers (see step 3).
- **Fixed-target names come from the target's module name**
  (`filters.module_name`): `sim-tdis` → `tdis`, `utl-ncf` → `ncf`,
  `utl-ts` → `ts`.
- **Conversions live on the child class, not in codegen.**
  - `convert_time` (`simulation_methods.py`) becomes `Tdis.coerce(Time)`.
  - The four copies of `convert_grid` (in `gwf`, `gwt`, `gwe` and `prt`
    `__init__.py`) become `Dis.coerce` / `Disv.coerce` (from a grid).
  - `from_time` and `from_grid` already live on those classes.
- **The child is the source of truth for the filename.** A linked field is
  replaced by the child field, with no parallel path field, the same way
  binding lists already work.
  - The path field stays only when the target has no generated flopy4 class
    (e.g. `obs_filerecord` until `utl-obs` is generated).
  - So "point at a file flopy4 doesn't manage" still works for those.

## DFN side (devtools, done by the user; do not implement here)

Add to `File` in `modflow_devtools/dfns/schema.py`:

```python
class File(InputFieldBase):
    direction: Literal["in", "out"]
    component: str | list[str] | None = None  # component(s) this file is input for
    component_ref: str | None = None          # sibling field naming the instance's type
```

**`component`** is a selector in the vocabulary of `parent`:

- It takes concrete names or type names, extended to subtypes (`exchange`,
  `solution`).
- It matches only components that can be children of the field's own
  component. So `"package"` in `gwf-nam` means gwf-nam's packages.

**`component_ref`** works like `fk_ref`: it names a sibling column whose
value (the ftype token) picks the concrete component. Without it, the
selector must resolve to exactly one component.

**Annotations:**

| Field | `component` | `component_ref` |
|---|---|---|
| `sim-nam.timing.tdis6` | `sim-tdis` | — |
| `sim-nam.models.mfname` | `model` | `mtype` |
| `sim-nam.exchanges.exgfile` | `exchange` | `exgtype` |
| `sim-nam.solutiongroup.slnfname` | `solution` | `slntype` |
| `*-nam.packages.fname` | `package` | `ftype` |
| `*_filerecord` filenames | from legacy `# flopy subpackage` lines | — |

**Migration:**

- Retype the five name-file filename columns from `String` to
  `File(direction="in")`.
- Subpackage links come from the legacy annotations, as in
  `subpackage-links-plan.md`.
- Name-file links come from a small table in `migrate_to_v2_0_0_dev2.py`,
  next to `_OC_RTYPE_VALID`.

**Also:**

- `tdis6` should be required: mf6 errors with "TIMING block variable TDIS6
  is unset" (`SimulationCreate.f90:191`), but the DFN marks it `optional`.
- Optional: mark `mname` as pk, and `exgmnamea`, `exgmnameb` and
  `slnmnames` as fk to `models.mname`.

## flopy4 side

### 1. `spec.child()`

In `flopy4/mf6/spec.py`, replace `subpackage()` with:

```python
def child(block: str | None = None, default=None, converter=None):
    return attrs.field(
        default=default,
        converter=converter or coerce_child,
        metadata={"child": True, "block": block} if block else {"child": True},
    )
```

**`coerce_child`** passes `None` and component instances through. Otherwise
it tries each candidate class's `coerce` classmethod, in the attribute's
type order. It needs the field's type, so do it as an attrs `field_transformer`,
or have it resolve candidates lazily via `child_field_candidates`. Pick
whichever is simpler.

- Values are bare, list or dict; it coerces each element.
- It raises a `TypeError` naming the accepted types.

**Children are still detected by type.** `child_field_candidates`, used
across `component.py`, `unstructure.py` and `structure.py`, keeps doing
that. `metadata["child"]` makes it explicit for codegen and readers. Don't
rewrite the tree code to key on it unless it simplifies something.

**Migrate the hand-written uses:**

- Model package fields: `field(block="packages", ...)` in `gwf`, `gwt`,
  `gwe` and `prt` `__init__.py` become `child(block="packages", ...)`.
- Delete `convert_grid` in favour of `coerce`.
- Add `Tdis.coerce` in `tdis_methods.py`, and `Dis.coerce` / `Disv.coerce`
  on their method mixins. Generated classes get methods only through
  mixins (`MIXINS` in make.py), so check that DIS and DISV have one.

### 2. Loading and writing package-level children

Dropping the path field means a package's linked children have to load, or
loading a DIS with `NCF6 FILEIN` loses the reference.

- **Load:** in `structure_component`, for each record replaced by a child,
  load the file as the child's class and set `child.filename`. Reuse
  `_resolve_bindings`'s pieces rather than adding a second loader:
  - class lookup by ftype, including G/A-variant disambiguation;
  - `Package.load(..., dims=..., name=...)`;
  - workspace handling.
  - Paths are relative to the simulation workspace, not the parent file's
    directory ([`package-binding-plan.md`](package-binding-plan.md) §1).
- **Write:** emit `<KEYWORD> FILEIN <child.filename>` from the child. The
  keyword and direction come from the DFN record. The path field's current
  `_keyword` / `direction` metadata (`spec.path`) moves onto the child
  field's metadata.
  - Delete `_sync_subpackage_files` and the `file_field` metadata.
- **Repeating records** (`ts_filerecord`, `tas_filerecord`) give
  `list[Ts]`. Each child gets its own default filename
  ([`package-binding-plan.md`](package-binding-plan.md) §2).

### 3. Codegen

In `make.py`, replace the following with one link-driven pass:

- `BINDINGS`, `ChildField`, `_child_field_spec`;
- `SUBPACKAGES`, `_subpackage_field_spec`;
- the `skip=frozenset(bindings)` plumbing.

**Overlay until devtools lands.** The installed devtools `File` has no
`component` field, and pydantic may reject unknown attributes. So add a
flopy4-side overlay, plus one accessor that reads the DFN first and falls
back to it:

```python
# (component, dotted field path) -> (component selector, component_ref)
# Remove once the dev3 DFNs carry File.component (modflow-devtools).
LINKS: dict[tuple[str, str], tuple[str | list[str], str | None]] = {
    ("sim-nam", "tdis6"): ("sim-tdis", None),
    ("sim-nam", "models.mfname"): ("model", "mtype"),
    ("sim-nam", "exchanges.exgfile"): ("exchange", "exgtype"),
    ("sim-nam", "solutiongroup.slnfname"): ("solution", "slntype"),
    ("*", "ncf_filerecord.ncf6_filename"): ("utl-ncf", None),
}

def field_link(component, path, field): ...
```

`field_link` checks `getattr(field, "component", None)` first. It must not
care whether the field is `String` or `File`: in dev3 today, the
name-file columns are `String`.

**Selector resolution:**

- Candidates are components that match the selector by name, type or
  subtype, and whose `parent` includes this component.
- Error if it resolves to nothing.
- Error if a link without `component_ref` resolves to more than one.
- Put the check in `check_mixins`, or rename that to `check_tables`.

**Emit rules** (the field is the one holding the link):

| Shape | Emitted field |
|---|---|
| Fixed target, scalar or non-repeating record | `<module_name>: Optional[X] = child(block=...)` |
| Fixed target, repeating record | `<module_name>: list[X] = child(block=..., default=Factory(list))` |
| Fixed target, required field | `<module_name>: X = child(block=..., default=Factory(X))` |
| `component_ref` list whose candidates share a flopy4 base (Model, Exchange, Solution) | `<list name>: dict[str, Base] = child(block=..., default=Factory(dict))` |
| `component_ref` list of packages | fan out, one field per package (see below) |

- The "required" row is `tdis` once `tdis6` is required. In the overlay,
  record `tdis6` as required: until devtools fixes it, an overlay entry
  may override `optional`.
- Choose the base class with `_base_class` logic. Import the base from
  `flopy4.mf6.{model,exchange,solution}`.
- The whole list block (or record) is replaced by the child field. Its
  other columns (`mtype`, `mname`, `exgmnamea`, ...) are derived from the
  child by `Binding.from_component`. So skip the list block property and
  its column attributes.
- **Package fan-out** (model name files) is not needed until gwf-nam etc.
  are generated. Implement it then. Known wrinkles:
  - DIS/DISV/DISU share one field `dis` (one grid per model).
  - G/A variants share an ftype and become `list[Union[Chd, Chdg]]`.
  - `multi` decides `list` vs `Optional`.
  - Mirror the hand-written `Gwf` (`gwf/__init__.py:183`).

**Imports:** collect child classes' imports the way `extra_imports` does
today. Use `_component_module` (`make.py:1035`) for the module path.

**Regenerate**, then check the generated `Simulation`:

- it has `tdis`, `models`, `exchanges`, `solutiongroup`;
- `dis.py` / `disv.py` (gwf, gwt, gwe, prt) have
  `ncf: Optional[Ncf] = child(...)` and no `ncf_file`.

**Rename `solutions` → `solutiongroup`.**

- About 47 references under `flopy4/`, `test/`, `docs/examples` and
  `docs/profile`.
- Find them with:
  `grep -rn '\.solutions\b\|solutions=' --include='*.py' --include='*.ipynb'`.
- The `.ipynb` files in `docs/examples` pair with the `.py` files. Check
  whether they're jupytext-synced before editing both.
- `Solution` objects are keyed by name in a dict; only the attribute name
  changes.

### 4. Tests

- **Codegen:**
  - `test_simulation_spec` (`test/mf6/test_mf6_codegen.py`) expects
    `solutiongroup`.
  - The subpackage test at `test_mf6_codegen.py:827` monkeypatches
    `SUBPACKAGES`; switch it to `LINKS`.
  - New: an unknown selector, and an ambiguous selector without
    `component_ref`, both raise.
- **Coercion:**
  - `Simulation(tdis=Time(...))` still works.
  - `Gwf(dis=StructuredGrid(...))` still works.
  - A wrong type raises `TypeError`.
- **Subpackage round trip:**
  - Load a DIS with `NCF6 FILEIN`: `dis.ncf` is loaded and named.
  - Write it back and compare the records.
  - Use `../modflow6/autotest` or an existing NCF test model, if any.
- **mf6 heads:** use the round-trip script in the session scratchpad, or
  the integration tests. Check test001a_Tharmonic, test020_mawconfined,
  test032_sfr and test028_sfr_rewet: heads must be identical.

## Order

1. `child()` + `coerce` (`Tdis`, `Dis`, `Disv`), hand-written models
   switched, `convert_grid`/`convert_time` deleted. No codegen change yet;
   the smoke suite passes.
2. Codegen: `LINKS` overlay + `field_link` + emit rules. Delete `BINDINGS`,
   `ChildField`, `SUBPACKAGES`. Regenerate. `solutions` → `solutiongroup`
   rename.
3. Package-level child load/write (§2), with NCF. Drop the `ncf_file` path
   fields.
4. Extend `LINKS` to `ts_filerecord` and `tas_filerecord` (list children).
5. Later: devtools lands `File.component` → delete `LINKS`. Package fan-out
   when model name files are generated.

Steps 1–2 make a PR; 3–4 make another.

## Relation to other plans

- [`package-binding-plan.md`](package-binding-plan.md):
  - §1 (loading), §2 (list children) and §5 (write) still apply. Here they
    are step 3–4.
  - §3: this plan picks option (b), deriving the path from the child, for
    linked records whose target has a flopy4 class. Unlinked records keep
    their path field.
  - §4's table: becomes `LINKS` entries, later `File.component`.
- `../modflow-devtools/subpackage-links-plan.md`: this plan extends its
  `File.component` with selectors and `component_ref`. Update that plan
  rather than writing a second devtools one.

## Working notes

- Use pixi for everything: `pixi run -e dev <cmd>`. Not uv or `.venv`.
- **Regenerate:**
  `pixi run -e dev python -W ignore -m flopy4.mf6.utils.codegen.dfn2py -d ../modflow6/doc/mf6io/mf6ivar/dfn --existing-only`
  - Codegen must be idempotent: a second run leaves no diff.
- **Smoke:**
  `MPLBACKEND=Agg pixi run -e dev pytest -q -n auto --smoke -p no:cacheprovider`
  - Run only the smoke suite; CI runs the full suite.
- **Lint:** `pixi run -e dev ruff check . && pixi run -e dev ruff format --check . && pixi run -e dev mypy flopy4`
- Keep comments light.
- Don't commit `.vscode/settings.json`.
- Never push, pull or comment on GitHub without an explicit request.
