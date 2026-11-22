# Package naming plan

One rule for default package names and one for default filenames, plus a
write-time check that no two components share a file. Agreed with the user
on 2026-10-19, after the period-data guide turned up two WEL packages both
written to `model.wel`.

Priorities: a simple, predictable user experience, and maintainability.

## Background

- **The bug.** Default filenames were `{model}.{class}`, so two packages of
  one type wrote the same file, and the second silently overwrote the
  first. MF6 still ran, reading one file twice.
- **Stopgap on `period-data-guide`.** Commit `79e36834` names a package's
  file `{model}.{name}` only when a same-class sibling exists. This plan
  replaces it.
- **PR #491 (mjreno, merged).** It made explicit names survive a rewrite
  (an explicit `name="wel"` was being renamed `wel0`, which broke GWT SSM's
  reference to it). It did this with a `_NAME_UNSET` sentinel default and
  a `_name_given` flag set in `__attrs_post_init__`. It also numbers list
  children by concrete class (`rcha0`, not `rch0`). Verified by applying
  its diff to `e0d94b86`, it has two regressions, because names assigned
  automatically are never marked as given, and `_set_child_parents`
  re-resolves every child's name on each `_children` access:
  - **Renumbering.** Delete `wel0`, and `wel1` becomes `wel0` on the next
    access. Anything referring to `wel1` by name (SSM, MVR) breaks.
  - **Lost renames.** `w.name = "north"` after attaching reverts to `wel0`
    on the next access.
- **Old attempt.** The `package-names` branch/worktree (Oct 9, unmerged)
  named the first child without an index (`wel`, `wel1`). The user chose
  numbering from 0 instead, so that branch is superseded. Don't delete it
  without asking.
- **flopy3 comparison.** In `names-and-paths.txt`. flopy3 numbers
  multi-packages `chd_0`, `chd_1`, and checks for filename clashes via
  `package_filename_dict`. We keep the clash check, and not its lenient
  lookup (by type or prefix) or its warn-and-replace behaviour.

## The rules

### Names

- **A given name is kept as is**, and raises a `ValueError` if a sibling
  already has it. This covers `name=`, a name-file pname on load, a
  `parent[key] = child` key, and assigning `.name` later.
- **An unnamed child in a single-child field** takes its class name:
  `dis` for `Dis`, `disv` for `Disv` (even though the field is `dis`),
  `npf`, `ic`.
- **An unnamed child in a list field** takes its class name plus the first
  free index from 0: `wel0`, `wel1`, `chd0`, `chdg0`, `rcha0`, `ts0`.
  Simulation's abstract-base lists follow the same rule: `gwf0`, `ims0`,
  `gwfgwf0`. Indexes count per class, since the name includes the class.
- **Once assigned, a name stays.** An automatic name is stored, and is then
  kept like a given one. Deleting a sibling never renumbers anything.
- **A detached component** (not attached to a parent) has `name=None`
  until it's attached.
- **`parent[key] = child` needs the key and the name to agree.** If the
  child's name is `None`, it takes the key. If it has a different name,
  raise a `ValueError`: `gwf["north"] = Wel(name="south")` is an error, not
  a silent rename. (Today `__setitem__` overwrites the name.) This also
  applies to a component moved from another parent, which keeps the name
  it had there; the error says to rename it or use that name as the key.
- **Renaming is assigning `.name`.** A clash with a sibling raises on the
  next access to the parent's children, not at the assignment, since
  `name` has no hook. Renaming doesn't update references to the old name
  elsewhere: `Ims(models=[...])`, GWT SSM sources, MVR package names,
  exchange model names. Those are the user's to update (see Out of scope).
  Automatic names never change on their own, so references to them stay
  valid.

Field names are no longer used for naming anywhere. Lookups already go by
`.name` (`__getitem__`, `__setitem__`, `__delitem__`), so `gwf.dis` still
holds a DISV named `disv`.

### Filenames

The default for a package is `{stem}.{name}.{ext}`:

- **`ext`** is the name-file ftype, lowercase, without the `6`: what a
  user writes in a name file's packages block. Use `component_ftype(cls)`
  (`converter/binding.py:12`), e.g. `CHD6` → `chd`.
  - Most packages: `wel`, `chd`, `disv`, `npf`, `ts`, `obs`, `tas`, `ncf`.
  - The grid and array variants (`Chdg`, `Drng`, `Evta`, `Ghbg`, `Rcha`,
    `Rivg`, `Spca`, `Welg`) take their base ftype: a CHDG file is `.chd`,
    an RCHA file `.rch`. The names still differ (`chd0` vs `chdg0`), so a
    CHD and a CHDG in one model don't collide: `model.chd0.chd`,
    `model.chdg0.chd`.
  - Solutions: `IMS6` → `ims`.
  - Exchanges: the ftype is `GWF6-GWF6`. Drop the `6`s and the hyphen:
    `gwfgwf`. This matches flopy3, whose exchange `package_type` is
    `gwfgwf` (default file `{sim}.gwfgwf`, `flopy/mf6/mfpackage.py:1870`),
    and the DFN name `exg-gwfgwf`. Settled (2026-10-19).
- **`stem`** depends on the parent:
  - under a model, the model's name;
  - under the simulation, the simulation's name;
  - under a package (a subpackage named by a file record: TS, TAS, OBS,
    NCF…), the parent's filename without its suffix. So `model.wel0.wel`
    has the child `model.wel0.ts0.ts`, and a parent given
    `filename="north.wel"` has `north.ts0.ts`.
  - with no parent, the component's own name, or its class name if it has
    none.
- **Not packages:**
  - a model is `{name}.nam`, unchanged;
  - the simulation is `mfsim.nam`, unchanged.
- **One `filename` property.** It returns the filename that was set, or
  else the default, worked out fresh on each read. There's no separate
  "resolved" accessor. Setting it to `None` goes back to the default.
- **A set filename doesn't follow a rename.** This covers an explicit
  `filename=` and a loaded package, whose filename comes from the name
  file. Renaming a loaded package keeps its original file, which matches
  what's on disk. Only a default filename follows the name: after
  `w.name = "north"`, the next write gives `model.north.wel`, and its
  subpackages follow (`model.north.ts0.ts`, with the WEL's `ts6` record
  naming that file, since the record is built at write time). The old file
  stays in the workspace; that's harmless, since MF6 reads the name file.

### Known limitation: attaching by plain assignment is lazy

`parent=`, `Wel(..., parent=gwf)` and `gwf["north"] = w` attach a child
at once. A plain assignment (`gwf.wel = [w]`) or a list mutation
(`gwf.wel.append(w)`) doesn't: the child gets its `_parent` and name only
when the parent's `_children` is next read (`component.py:351`). In
between, `w.name` is `None` and `w.filename` is `wel.wel.wel`, not
`model.wel0.wel`. Writing is unaffected, since a write goes through the
parent, which reads `_children` first. This PR doesn't close the gap; see
"Follow-up: attach on assignment".

Examples:

| Component | Name | File |
|---|---|---|
| One WEL | `wel0` | `model.wel0.wel` |
| A second WEL | `wel1` | `model.wel1.wel` |
| A CHD and a CHDG | `chd0`, `chdg0` | `model.chd0.chd`, `model.chdg0.chd` |
| An RCHA | `rcha0` | `model.rcha0.rch` |
| A DISV | `disv` | `model.disv.disv` |
| An IC | `ic` | `model.ic.ic` |
| A TS file under the first WEL | `ts0` | `model.wel0.ts0.ts` |
| A WEL named `north` | `north` | `model.north.wel` |
| TDIS | `tdis` | `<sim>.tdis.tdis` |
| An IMS solution | `ims0` | `<sim>.ims0.ims` |
| A GWF-GWF exchange | `gwfgwf0` | `<sim>.gwfgwf0.gwfgwf` |
| An unnamed model | `gwf0` | `gwf0.nam` |

Default filenames can't collide: names are unique among siblings, and the
stem is unique per parent. Explicit filenames still can, hence the check.

### Collision check

Before writing, a simulation (or a model or package written on its own)
walks its tree and reads each component's `filename`. It raises a `ValueError` naming both components if two resolve to
the same path relative to the workspace. Compare the paths case-insensitively
(`casefold()` on the POSIX form), since macOS and Windows filesystems are
case-insensitive.

## Steps

### 0. Set up

1. Fetch the latest `develop`. The user said to do this once the plan is
   approved, but confirm in the moment, per CLAUDE.md. It should include
   #491.
2. Create a branch `package-naming` from the latest `develop`. Don't reuse
   the old `package-names` branch.
3. Read the merged #491 code in `flopy4/mf6/component.py`:
   - `_NAME_UNSET`
   - `_name_given`
   - `__attrs_post_init__`
   - `_is_default_child_name`
   - `_resolve_child_name`
   - `to_dict`

   Read `_RESERVED_FIELD_NAMES` in `flopy4/attrs_xarray.py` too. Line
   numbers below are from before #491 and will have shifted.
4. Check whether `period-data-guide` (with `79e36834`) has merged. If not,
   this branch still replaces `default_filename` wholesale. Expect a
   trivial conflict in `package.py`, and resolve it in favour of this
   plan.

### 1. Names: `Optional[str]`, not a sentinel and a flag

In `flopy4/mf6/component.py`:

- `name: Optional[str] = attrs.field(default=None)`. Update the docstring:
  `None` means not given yet, and attaching resolves it.
- Remove `_NAME_UNSET` and the `_name_given` field, along with their
  handling in `__attrs_post_init__`.
- Remove `"_name_given"` from:
  - the `to_dict` filter;
  - `_RESERVED_FIELD_NAMES` in `flopy4/attrs_xarray.py`.
- Replace `_is_default_child_name(child)` with `child.name is None`.
  Inline it if it's then trivial.
- Rewrite `_resolve_child_name(used, kind, child)`. Drop the `field_name`
  and `by_class` parameters.
  - **Given (`child.name is not None`):** if the name is in `used`, raise
    the existing collision error; otherwise return it.
  - **`kind == "only"`:** return `type(child).__name__.lower()`.
  - **`kind == "list"`:** return `f"{cls}{i}"` for the first `i` from 0
    not in `used`.
  - Update its docstring to state the rules above.
- Delete `_names_by_class` and every `by_class=` argument:
  `_set_child_parents` (≈ line 435–443) and `_attach_to_parent_field`
  (≈ line 529).
- `_set_child_parents` also names period-row children (≈ line 421, which
  passes `f.alias or f.name`). Use the list rule, by class.
- **The collision check in `_set_child_parents`.** It builds `used`
  incrementally. A given name must still raise on a clash, but a child's
  own stored name mustn't count as a clash with itself on re-resolution.
  The current code adds each resolved name to `used` after resolving it,
  so re-running on stored names works, provided every stored name is
  treated as given. Check this with the deletion and rename tests below.
- **`__setitem__`** sets `value.name = key`. Change it to: if
  `value.name` is `None`, set it to `key`; if it equals `key`, fine;
  otherwise raise `ValueError` (see the rules). Confirm it still raises on a
  clash with a different child already under `key`, except when replacing
  that child in place.

**Places that read a name before attaching** may now see `None`. Grep
`\.name\b` in `flopy4/mf6/` and check each read that can happen on a
detached component:
- `__repr__`/`repr`: show the class name, or `None`.
- `default_filename` with no parent: falls back to the class name (see
  step 2).
- `Model.default_filename`: `{name or cls}.nam`.
- Standalone `write()` of a model or package.
- `NetCDF` variable naming (`netcdf.py` ≈ 760, `f"{package_name}_{param}"`
  for multi-packages): runs at write time, after resolution, so names are
  set. Confirm.
- `Binding.from_component` (`converter/binding.py:39`): runs at write
  time. Confirm.
- Loading (`structure_component`, `converter/ingress/structure.py`): passes
  the pname as `name=`, so it's given. A name-file row without a pname
  leaves `name=None`, so it gets the automatic name.

### 2. Filenames

- Add a helper on `Component`, `_file_ext()`, returning
  `component_ftype(type(self)).lower().replace("6", "").replace("-", "")`.
  Check there's no import cycle with `converter/binding.py`. If there is,
  move `component_ftype` somewhere both can import, or import it inside
  the method. Check that every class with a file gets an ftype from it
  that MF6 recognises, especially subpackages (`Ts` → `TS6`, `Obs` →
  `OBS6`, `Tas` → `TAS6`, `Ncf` → `NCF6`) and period-row table files
  (`laktab`, `sfrtab`…), whose names may not follow the pattern.
- `Package.default_filename` (`package.py:778`), replacing both the
  `79e36834` sibling check and the subpackage branch:

  ```python
  def default_filename(self) -> str:
      parent = self._parent
      if isinstance(parent, Package):  # named by a file record
          stem = Path(parent.filename or parent.default_filename()).stem
      elif parent is not None:
          stem = parent.name
      else:
          stem = self.name or type(self).__name__.lower()
      name = self.name or type(self).__name__.lower()
      return f"{stem}.{name}.{self._file_ext()}"
  ```

  `Path(...).stem` drops only the last suffix (`model.wel0.wel` →
  `model.wel0`), which is what we want.
- **Remove these overrides** so they inherit the rule:
  - `Solution.default_filename` (`solution.py:14`, fixed
    `solution.<slntype>`, which has the same collision bug with two
    solutions);
  - `Exchange.default_filename` (`exchange.py:17`, `{name}.exg`).

  Check the base `Component.default_filename` (`component.py:470`) is
  still right for anything left using it. Exchanges and solutions are
  `Package`s? Confirm they inherit `Package.default_filename`. If not,
  give them the same rule.
- **Keep these overrides:**
  - `Model.default_filename` (`model.py:36`, `{name}.nam`, with the
    `None` fallback above);
  - `Simulation` (`simulation_methods.py:17`, `mfsim.nam`).
- **Check the simulation's name.** Confirm `Simulation.name` is always set.
  If it can be `None` or a default, decide what the stem is for TDIS, IMS
  and exchanges (probably the default name, e.g. `sim`).

### 3. Stop saving default filenames

Agreed to do this (2026-10-19), since it's small. Sized beforehand:
- 10 source sites read `.filename`, and most already use
  `filename or default_filename()`:
  - `package.py:781`
  - `__init__.py:169`
  - `egress/unstructure.py:45`
  - `binding.py:51`
- About 6 tests read `.filename` after a write without setting it:
  - `test_mf6_component.py:1396`, `:1397` and `:2239`
  - `test_mf6_integration.py:2909` and `:2913`
  - `test_mf6_sync_dims.py:41`

Loaded components get `filename` from the name file, so they're
unaffected. After a rename, the old file is left in the workspace, which is
harmless, since MF6 reads the name file.

Today the first `write()` or `.path` saves the default into `filename`:
- `component.py:451` (`path`);
- `component.py:659` (`write`, with a TODO calling it a temp hack);
- `context.py:24`;
- `package.py:729` (`_name_file_children`).

That makes the filename depend on history: rename a package after its
first write, and its file keeps the old name. With deterministic defaults
the saving isn't needed.

- Make `filename` a property over a private attrs field, so there's one
  accessor (the user's preference, 2026-10-19):
  ```python
  _filename: Optional[Path] = attrs.field(
      default=None, alias="filename", converter=attrs.converters.optional(Path)
  )

  @property
  def filename(self) -> Path:
      return self._filename or Path(self.default_filename())

  @filename.setter
  def filename(self, value) -> None:
      self._filename = None if value is None else Path(value)
  ```
  `Component(filename=...)` still works through the alias. The class is
  `slots=False` (`component.py:245`), so the property is fine there.
- Remove the four saving sites above. At `package.py:781`,
  `__init__.py:169`, `egress/unstructure.py:45` and `binding.py:51`, replace
  `x.filename or x.default_filename()` with `x.filename`.
- Only code that needs to know whether a filename was *set* reads
  `_filename`. Expected: serialization, and the simulation's `mfsim.nam`
  check (`simulation_methods.py:23`), which should check `sim._filename`
  is `None` or `mfsim.nam`. Anything else reading `_filename` is a smell.
- Code that iterates attrs fields and names `filename` now sees
  `_filename`: `package.py:812` (`_exclude`), `component.py:711`
  (`data.pop("filename")`), `attrs_xarray.py` field filtering, `to_dict`,
  unstructure and any `attrs.evolve`. Check each.
- `root` (`component.py:466`) reads `filename` to check for an absolute
  path. With the property it computes the default, which doesn't call
  `root`, so no recursion; confirm.
- Tests: `test_mf6_component.py:1391` asserts `ncf.filename is None`
  before a write; change it to assert the default. The tests listed above
  that read `.filename` after a write should pass unchanged.
- If this turns out to touch much more than these sites and their tests
  (for example, something that needs `filename` set for reasons other than
  writing), stop. Keep the saving, and note it as a follow-up. It's
  separate from the naming bug.

### 4. Collision check

- Add a function, e.g. `_check_filenames(root)` in `component.py`, that
  walks the tree from the component being written. Use `_children`
  recursively, including package children like TS and OBS. It maps
  `filename.as_posix().casefold()` to the component, and raises
  on a repeat:
  `ValueError("model.wel0.wel is the file for both <Wel wel0> and <Wel north>; give one a different filename")`.
- Call it once at the top-level `write()`: the component with no parent,
  or the one `write()` was called on. Not in every recursive child write.
  `Component.write` (`component.py:641`) recurses into children, so either
  check `self._parent is None` there, or add it to `Simulation.write` and
  standalone writes. Pick whichever keeps it in one place.
- Paths are relative to the workspace. Treat an absolute `filename` as is.
- Out of scope: external array files (OPEN/CLOSE) written by
  `external.py`. Mention it in the PR as a possible follow-up.

### 5. Tests

New tests, probably in `test/mf6/test_mf6_component.py`, near
`test_several_packages_of_a_type_default_filenames` (from `79e36834`,
which these replace).

**Names:**
- a single child gets its class name: a `Dis` → `dis`, and a `Disv` in the
  `dis` field → `disv`;
- list children: two WELs → `wel0`, `wel1`; a CHD and a CHDG → `chd0`,
  `chdg0`;
- an unnamed `Gwf` in a simulation → `gwf0`, and an `Ims` → `ims0`;
- an explicit `Wel(name="wel")` stays `wel`, and an unnamed sibling WEL
  becomes `wel0`;
- an explicit name that clashes with a sibling raises;
- **deleting:** two WELs, delete `wel0`, access `gwf` again, and the other
  is still `wel1`. A new WEL added then gets `wel0`. (Regression for #491.)
- **renaming after attaching:** `w.name = "north"`, access `gwf` again,
  and it's still `north`. (Regression for #491.)
- `gwf.wel = [Wel(...), Wel(...)]` (plain assignment): names are resolved
  on the next access, and after reading `gwf`, `gwf.wel[0].filename` is
  `model.wel0.wel` (pins down the known limitation);
- a detached `Wel(...).name is None`;
- `gwf["north"] = Wel(...)` names it `north`.
- `gwf["north"] = Wel(name="north")` is fine, and
  `gwf["north"] = Wel(name="south")` raises.

**Loading:**
- a name file with a pname keeps it;
- a row without a pname gets the automatic name.

Check that existing load tests cover these, and add them if not.

**Filenames:**
- model-level: `model.wel0.wel`, `model.disv.disv`, `model.chdg0.chd`,
  `model.rcha0.rch`, and a CHD and a CHDG in one model writing separate
  files;
- simulation-level: `<sim>.tdis.tdis`, `<sim>.ims0.ims`, and an exchange;
- a subpackage: `model.wel0.ts0.ts`, and under a parent with
  `filename="north.wel"`, `north.ts0.ts`;
- an explicit `filename=` is used;
- standalone, with no parent;
- step 3, if done: rename after a write, and the next write uses the new
  name.
- `filename` returns the default before any write, and `w.filename = None`
  goes back to it;
- a loaded package renamed keeps its loaded filename.

**Collision check:**
- two packages with the same explicit `filename=` raise at `sim.write()`;
- names differing only in case raise;
- a model with several of each type writes without raising.

**End to end:** the period-data guide (two WELs, a TS, an EVT) writes and
runs. `test/test_examples.py -k period-data` covers it once `mf6` is on
the `PATH`.

### 6. Update existing tests, snapshots, examples and docs

- **Literal auto-names** (`"wel0"`, `"chd0"`, `"ts0"`, …) appear in:
  - `test_mf6_period_lists.py` (8)
  - `test_mf6_codec.py` (5)
  - `test_mf6_netcdf.py` (5)
  - `test_mf6_integration.py` (5)
  - `test_mf6_io_roundtrip.py` (5)
  - `test_mf6_adapters.py` (2)
  - `test_mf6_component.py` (2)
  - `test_mf6_grammar_gen.py` (2)
  - `test_mf6_codegen.py` (1)
  - `test_mf6_netcdf_cf_conventions.py` (1)

  Most list names are unchanged (`wel0`). Look for single children whose
  name changes (`dis` → `disv`), models (`gwf` → `gwf0`), and tests
  asserting filenames (`.wel`, `.chd`, `solution.ims`, `.exg`). Some
  matches may be grammar tokens or MF6 text, not names. Check each.
- **Snapshots:** `test/mf6/__snapshots__/test_mf6_load_all_models/`. Loaded
  packages keep their pnames and filenames from the name file, so changes
  should be limited to single children without a pname (e.g. a DISV:
  `dis` → `disv`). Regenerate with `pixi run -e dev pytest
  test/mf6/test_mf6_load_all_models.py --snapshot-update` (the snapshot
  plugin is from `modflow_devtools.snapshots`). Review the diff rather
  than accepting it wholesale.
- **Examples:** grep `docs/examples/*.py` for package names and filenames:
  `gwf["…"]`, `.name ==`, `solution.ims`, `mymodel.chd`. Regenerate the
  notebooks that change. `twri.ipynb` was already out of date with its
  script, so don't re-execute it blindly.
  - Regenerate with `PATH="$PWD/.pixi/envs/dev/bin:$PATH" pixi run -e docs
    python scripts/update_ghpages.py --example <name>`. The docs env has no
    `mf6`.
  - Never `git checkout` a notebook before syncing. `jupytext --sync` will
    copy the newer notebook over the `.py`. If a notebook needs
    resetting, touch the `.py` afterwards.
  - Strip stderr outputs afterwards, since they contain local paths.
- **Docstrings:** `Component.name`, `_resolve_child_name`, `_set_child_parents`,
  `_children` (its docstring mentions the class-name default), and
  `Package.default_filename`.
- **`docs/dev`:** grep for naming and filename descriptions. Don't edit the
  plan files in the project root or `archive/`.

### 7. Verify

- `pixi run -e dev ruff check` and `ruff format --check` on the touched
  files, plus `codespell`.
- `pixi run -e dev mypy` on the touched modules. `name` becoming
  `Optional[str]` will show up at the places that read it.
- Run the touched test files, and `test/mf6/test_mf6_load_all_models.py`.
- Run `pixi run -e dev smoke`, which CLAUDE.local.md asks for after
  library changes. Not the full suite.
- Write and run the period-data guide, and check the output folder:
  `model.wel0.wel`, `model.wel1.wel`, `model.wel0.ts0.ts`, and normal
  termination in `mfsim.lst`.

### 8. Commit and PR

- Suggested commits:
  1. names: `Optional[str]`, class names, no renumbering;
  2. default filenames `{stem}.{name}.{ext}`, and drop the `Solution` and
     `Exchange` overrides;
  3. stop saving default filenames (if done);
  4. filename collision check;
  5. tests, snapshots, examples and docs, either with each change or
     separately.
- Don't push or open a PR unless the user asks at the time.
- **The PR description must call out the visible changes:**
  - default filenames are now `{stem}.{name}.{ext}`, with `ext` the
    name-file ftype (`model.wel` → `model.wel0.wel`, `model.npf` →
    `model.npf.npf`, `model.rcha` → `model.rcha0.rch`, `solution.ims` →
    `<sim>.ims0.ims`, `<name>.exg` → `<sim>.gwfgwf0.gwfgwf`);
  - a default filename no longer changes depending on whether the package
    has been written (if step 3 is done);
  - single children are named by class (`dis` → `disv` for a DISV);
  - unnamed models are numbered (`gwf0`);
  - automatic names no longer renumber when a sibling is deleted, and a
    rename after attaching sticks (fixes the regressions from #491);
  - writing raises if two components resolve to the same file;
  - `parent[key] = child` raises if the child already has a different
    name;
  - `filename` always returns a path (the default if none was set), and a
    default filename follows a rename; a set or loaded filename doesn't.

## Follow-up: attach on assignment

A separate PR after this one, to close the known limitation. Sketch:

- **A hook for whole-field assignment.** The class is `slots=False`, so
  either attrs `on_setattr` on child fields or a `Component.__setattr__`
  that, for a child field, attaches the new value(s) (stamp `_parent`,
  resolve the name) and detaches the old ones (`_parent = None`, the name
  kept). Pick whichever also covers fields added by subclasses without
  per-field wiring; `__setattr__` probably.
- **A list proxy for list fields**, so `append`, `extend`, `insert`,
  `__setitem__`, `+=` attach and `pop`, `remove`, `del`, `clear` detach.
  Like xattree's `DataTreeList` (`../xattree/xattree/__init__.py:47`),
  with these differences:
  - **Don't key children by list index.** `DataTreeList` names children
    `f"{prefix}{index}"`, so deleting one renumbers the rest (the same
    bug as #491), and its `insert` overwrites the item at that index
    instead of inserting. Names come from `_resolve_child_name` and are
    stored, as in this PR.
  - **Subclass `list` rather than `MutableSequence`**, so the 23
    `isinstance(..., list)` checks in `flopy4/mf6`, equality, cattrs and
    repr keep working. That means overriding every mutator, since `list`
    doesn't route them through one method; test each.
  - Wrap the value in the proxy in the hook (and on init), so assigning a
    plain list still gives a proxy.
- **Keep the access-time pass** (`_set_child_parents` on `_children`) as
  a safety net, at least at first. Not every attach goes through a hook:
  children inside period-data rows (`_period_row_children`) are reached
  through row data, not a child field, and a list built elsewhere and
  mutated before assignment is only seen when assigned. With the hooks in
  place, the pass should find nothing to do; once that's confirmed, it
  could run only before a write.
- **Tests:** after `gwf.wel = [w]`, and after `gwf.wel.append(w)`,
  `w.name == "wel0"` and `w.filename` is `model.wel0.wel` without reading
  `gwf` first; removing a child clears its `_parent` and keeps its name;
  each list mutator attaches or detaches.

## Out of scope

- Model subdirectories, moving external files with the workspace, and
  quoting filenames with spaces (from `names-and-paths.txt`).
- Collision checks for external array files.
- Lenient lookup by type or prefix (flopy3's `get_package`).
- Attaching on plain assignment or list mutation (see "Follow-up: attach
  on assignment").
- Updating references on rename. Renaming a component doesn't update other
  places that name it (`Ims(models=[...])`, SSM sources, MVR packages,
  exchange model names). That would be its own feature.
