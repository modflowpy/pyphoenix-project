# Load context

**Archived 2026-10-19.** Done: merged as #418 ("load context"), `flopy4/mf6/load_context.py`.

Status: ready (2026-10-07), against develop `a6c52c8`. Replaces the
"thread-local load context" note in [`links-from-dfns-plan.md`](links-from-dfns-plan.md)
("Later") and the "Load context" item in [`open-followups.md`](../open-followups.md).

## Problem

Loading passes what it knows down the tree one argument at a time.
`structure_component` takes `dims`, `workspace`, `name` and `parent`;
`Package.load`, `_load_file_child`, `_parse_rows` and `_resolve_bindings`
each pass some of them on. Every new fact the reader needs becomes another
argument on every layer. Three problems follow from this.

1. **Paths resolve against the wrong directory.** MF6 resolves every
   relative path in every input file against the simulation's working
   directory, the one holding `mfsim.nam`. flopy4 resolves each path
   against the directory of the file that names it (`workspace=path.parent`
   in `_load_mf6` and `Package.load`). `_load_file_child` tries
   `Path.cwd()` first, and its docstring says loading a simulation sets
   the cwd to the workspace, but nothing does. So a model kept in a
   subdirectory fails to load:

   ```
   mfsim.nam:   GWF6 gwf/m.nam m
   gwf/m.nam:   DIS6 gwf/m.dis dis
   ```

   `Simulation.load("mfsim.nam")` raises `FileNotFoundError: .../gwf/gwf/m.dis`.
   MF6 runs this layout. It loads only if the cwd happens to be the
   simulation directory, and then only for file records (`_load_file_child`),
   not namefile rows (`_resolve_bindings` uses `workspace` alone).
2. **Exchanges between grids can't be read.** An exchange's cellids each
   take the width of their own model's grid: 3 for DIS, 2 for DISV, 1 for
   DISU. The exchange file doesn't say which, and the row can't settle it
   (5 tokens could be 3+2 or 2+3). The reader needs the two models' grids.
   Today it guesses one width from the row length, so a DIS–DISV exchange
   reads `cellidm1=(0, 0)` instead of `(0, 0, 1)`, and every column after
   it is shifted. The same goes for the exchange's GNC.
3. **Each new fact means another argument everywhere.** The first
   exchange fix (in the working tree, see below) added `ncelldims` to
   `Package.load`, `structure_component`, `_parse_rows` and
   `_load_file_child`. It works, but it's a public `load` argument only
   exchanges use, and a second way to say grid widths next to `dims`.

## Design

One object, `LoadContext`, carries what a file's reader needs to know
about where the file sits in the simulation. It's passed down explicitly,
and each level derives its children's context from its own.

```python
@attrs.frozen
class LoadContext:
    workspace: Path                 # the simulation directory; relative paths resolve here
    dims: Mapping[str, int] = {}    # grid dims in scope (the model's DIS, or given)
    parent: type | None = None      # class of the component whose file named this one
    models: Mapping[str, Model] = {}           # models loaded so far, by name
    exchange: tuple[Model, Model] | None = None  # the models an exchange connects

    def resolve(self, path) -> Path: ...         # workspace / path, absolute paths as is
    def ncelldim(self, item_cls, rows) -> int | Mapping[str, int]: ...
```

Use `attrs.evolve` to derive a child's context (new `dims` after DIS loads,
`parent=cls` for a file child, `exchange=(a, b)` for an exchange).

- **Explicit, not thread-local.** `WriteContext` is thread-local because
  it holds user settings that apply across a whole write. A load context
  changes at every level of the tree (dims, parent, exchange models), so a
  thread-local stack would have to be pushed and popped around every child
  load, and the dependency would be hidden. Passing it keeps the reader's
  inputs visible in signatures, and loads in parallel threads stay
  independent.
- **Public signatures shrink, not grow.**
  - `Component.load(path, format, name)` is unchanged.
  - `Package.load(path, dims=None, name=None)` keeps `dims` for standalone
    loads (`Npf.load(path, dims={...})`, documented and tested). `parent`
    and `ncelldims` go away and their information moves into the context.
  - A keyword-only `context: LoadContext | None = None` on `load` lets a
    caller load a standalone file with the simulation directory as its
    base (`Gwf.load("sim/gwf/m.nam", context=LoadContext(workspace="sim"))`).
  - `structure_component(raw, cls, *, context, name=None)` replaces
    `dims`/`workspace`/`parent`.
- **Default workspace.** With no context, the loaded file's own directory,
  as today. For `Simulation.load` that's the simulation directory, which is
  the correct base for everything below it.
- **Paths.** Every relative path read during a load goes through
  `context.resolve`:
  - namefile rows (`_resolve_bindings`);
  - file records (`_load_file_child`);
  - `OPEN/CLOSE` (`_resolve_open_close_rows`, `_read_open_close_values`);
  - row children (LAK/SFR `TAB6`).

  `Path.cwd()` goes from `_load_file_child`. (`Component.path` and
  `Context`'s default `workspace` also use `Path.cwd()`, but for writing
  and construction, not loading. They're out of scope.)
- **Loaded components keep their paths as written.** A model loaded from
  `gwf/m.nam` gets `workspace` = the simulation directory and
  `filename = gwf/m.nam`, so writing it back keeps the layout. Today
  `_load_mf6` sets `workspace = path.parent` and `filename = path.name`,
  and `_resolve_bindings` then overwrites `filename` with the row's path.
  Check the write side with a round-trip test (below), and fix it if
  needed.
- **Cellid widths.** `_parse_rows` asks `context.ncelldim(item_cls, rows)`:
  - Under an exchange (`context.exchange` set), each cellid column takes the
    width of its model's grid, picked by `Exchange.cellid_models` (0 for
    `exgmnamea`, 1 for `exgmnameb`), as a mapping by column name.
  - Otherwise as today: from `context.dims` if they say, else from the row
    length (`item.infer_ncelldim`).
  - If either exchange model has no discretization package, fall back to
    the row length, as today.
- **Exchange loading.** `_resolve_bindings` on `Simulation` loads the
  models block before the exchanges block, which is field order. When
  loading an exchange row, `GWF6-GWF6 ab.exg a b`, it looks up `a` and
  `b` in the models loaded so far (case-insensitively, as MF6 does) and
  passes `exchange=(model_a, model_b)` in the exchange's context. The
  exchange's GNC, MVR and OBS inherit that context, so GNC's columns
  resolve too.

## Starting point

The working tree on `develop` has a first exchange fix (uncommitted).
Keep:

- `Item.from_tokens(ncelldim: int | Mapping[str, int])` and its
  per-column `cellid_width` (`flopy4/mf6/item.py`);
- `Exchange.cellid_models` (`flopy4/mf6/exchange.py`). The DFNs don't
  say which model a column refers to; MF6 hard-codes it too
  (`src/Utilities/Idm/mf6blockfile/StructArray.f90` ~L376–385,
  `src/Exchange/GhostNode.f90` ~L773–792). A schema attribute is proposed
  in `../modflow-devtools/cellid-model-plan.md`. Until it lands, the
  table stays;
- `test_load_exchange_between_grids` (`test/mf6/test_mf6_namefile_load.py`).

Replace with the context:

- the `ncelldims` parameter on `Package.load`, `structure_component`,
  `_parse_rows` and `_load_file_child`;
- `_exchange_ncelldims` in `structure.py`. Its lookup becomes
  `LoadContext.ncelldim`.

## Steps

1. Add `LoadContext` (`flopy4/mf6/load_context.py`) with `resolve` and
   `ncelldim`. Unit tests: absolute paths pass through; relative paths
   join the workspace; widths from dims, from rows, and per column under
   an exchange.
2. Make `structure_component`, `_parse_rows`, `_load_file_child`,
   `_resolve_bindings`, `_load_mf6` and `Package.load` take or build
   the context. Remove `dims=`/`workspace=`/`parent=` from
   `structure_component`, and `parent=`/`ncelldims=` from `Package.load`.
   Update callers and tests that pass them.
3. Route every relative path through `context.resolve`, and remove
   `Path.cwd()` from `_load_file_child`. Fix its docstring.
4. Set `exchange=` when loading an exchange, and drop the `ncelldims`
   plumbing.
5. Tests:
   - the subdirectory layout above loads, and the model's DIS is found;
   - writing that simulation back and reloading it keeps `gwf/m.nam` and
     `gwf/m.dis`;
   - `test_load_exchange_between_grids` still passes;
   - loading with a cwd other than the simulation directory works (no
     `Path.cwd()` dependence);
   - `Package.load(path, dims=...)` standalone still works.
6. Run the touched test files, ruff, mypy, and the smoke tests
   (`pixi run -e dev smoke`). Not the full suite. The smoke run's 17
   `test_mf6_typed_grammar_corpus` failures ("Model 'mf6/large/...' not
   in registry") are about the environment and fail without these changes
   too.
7. Update [`open-followups.md`](../open-followups.md): remove "Load context", and note the
   mixed-grid exchange fix as done.

## Non-goals

- `Path.cwd()` in `Component.path` and `Context`'s default `workspace`
  (writing and construction, not loading).
- Dimension resolution after loading (`resolve_dims` walking parents) is
  unchanged. The context only covers what the reader needs while the
  tree is still being built.
- Hard-coding which model each column refers to stays until the
  devtools schema carries it.
