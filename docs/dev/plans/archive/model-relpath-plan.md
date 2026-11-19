# Model directories

Status: implemented (2026-10-07) on branch `model-relpath`, on top of
`load-context` `54b8383`. Decisions taken where the draft left options:

- Egress prefixes the token after every `FILEIN`/`FILEOUT` in a model's
  unstructured blocks (rows and block headers), plus namefile rows via
  `Binding`. All 94 path fields but the exchanges' `exgfile` have a
  direction, and exchanges are simulation-level, so this covers them.
- Ingress walks a component's parsed kwargs (records, items, blocks;
  not child components) and makes every `Path` model-relative.
- `Model.workspace` is a property over the inherited attrs field;
  `update_child_attr` and `Context.write`'s `cd` are gone, and
  `Component.path` uses the enclosing context's workspace.
- A loaded model's directory is its namefile's. `relpath` may leave the
  simulation directory (`../x`); paths are normalized, not rejected.
- NetCDF: nothing is written implicitly (callers pass `to_netcdf` a
  path), and `NC6 FILEIN` paths go through the same prefixing.

## Problem

A model is a `Context` and has a `workspace`, but under a simulation that
workspace is only a copy of the simulation's. `Context.workspace` has
`on_setattr=update_child_attr`, so setting the simulation's workspace
overwrites every model's, and `__attrs_post_init__` takes the parent's
when none is given. A model's workspace means something of its own only
when the model stands alone. The separate `Context` hardly earns its
keep.

MF6 lets models live in subdirectories, and users think of them that way
("the GWF model is in `gwf/`"). Today flopy4 holds such a model with
filenames that carry the directory: `gwf.filename == "gwf/m.nam"`,
`gwf.dis.filename == "gwf/m.dis"`. That round-trips (the `load-context`
branch makes it load), but:

- moving a model to another directory means rewriting every one of its
  packages' filenames, and its output files';
- a model built standalone and then attached to a simulation can't keep
  its own directory;
- a user who sets `head_file="m.hds"` on a model "in `gwf/`" gets the
  file in the simulation directory, because MF6 resolves paths there.

## Design

A model stores where its directory is relative to the simulation's, and
its files' paths are relative to its own directory. The translation
happens only at the file boundary, on load and on write. MF6's rule,
that every path in every file is relative to the simulation directory,
stays the one the files follow. `LoadContext.workspace` stays the
simulation directory.

```python
@attrs.define(kw_only=True, slots=False)
class Model(Context, ABC):
    relpath: Path = field(default=Path("."), converter=Path)
    """The model's directory, relative to the simulation's."""

    @property
    def workspace(self) -> Path:   # parent's workspace / relpath, or its own
        ...
```

- **Workspace is derived, not copied.** A model's `workspace` is
  `parent.workspace / relpath` under a simulation, and its own (settable,
  as now) when standalone. `update_child_attr` stops copying the
  simulation's workspace onto its models, so the two can't disagree.
  Setting a model's `workspace` under a simulation sets `relpath` to its
  path relative to the simulation's.
- **Model filenames are relative to the model directory.** `dis.filename
  == "m.dis"`, `oc.head_file == "m.hds"`, `wel.obs.filename == "m.obs"`.
  The model's own `filename` is relative to its directory too
  (`"m.nam"`), and the simulation's `GWF6` row gets `relpath / filename`.
- **The simulation's own files** (TDIS, IMS, exchanges) keep paths
  relative to the simulation directory. An exchange's paths aren't in
  any one model's directory.

### Load

- `_resolve_bindings` on `Simulation`: for a `GWF6 gwf/m.nam m` row,
  `relpath = Path("gwf/m.nam").parent`, and the model's `filename` is
  `m.nam`.
- Inside the model's files, every path read (namefile rows, file
  records, `FILEIN`/`FILEOUT` paths, row children) is stored relative to
  the model's directory: `os.path.relpath(path, relpath)`, with POSIX
  separators. A path outside the model's directory becomes `../x`.
  Reading still resolves files with `context.resolve` against the
  simulation directory. Only the stored path changes.
- `LoadContext` gains `relpath: Path = Path(".")` (the directory of the
  model being loaded, relative to the workspace), set in the model's
  child context and inherited by its packages and their children, with a
  `relative(path) -> Path` method for the stored form.
- OPEN/CLOSE paths aren't stored (the arrays are read in), so they need
  no change.
- A standalone `Gwf.load(path, context=LoadContext(workspace=sim))` gets
  `relpath = path.parent` relative to the workspace, as in a simulation.
  Without a context, `relpath = "."` and the workspace is the namefile's
  directory, as now.

### Write

Every path a model's files write gets `relpath /` prefixed:

- namefile rows (`binding.py`, `Binding.from_component`'s `fname`), both
  the model's `PACKAGES` rows and the simulation's `MODELS` row;
- file records naming children (`unstructure.py`, `_child_path`) and
  plain path fields (`_path_to_tuple`, the `FILEIN`/`FILEOUT` branches
  around `unstructure.py` L276–280);
- external array files, if the writer produces any (`macros.jinja`'s
  `external` branch writes `OPEN/CLOSE <value>`; check where that value
  comes from and whether it's a path flopy4 wrote);
- the files themselves: `Component.path` for a package is
  `Path.cwd() / filename`, relying on `Context.write`'s `cd`. Under this
  plan it should be `model.workspace / filename`, without the `cd`.

The unstructure hooks don't know the component's model, so the prefix
has to reach them. Two ways:

1. Each package finds its model (walk `_parent` to the nearest `Model`)
   and prefixes its own paths, through one helper
   (`_file_path(component, path) -> Path`) that every path site calls.
2. A write-side counterpart of `LoadContext` carries `relpath` down the
   write, set by `Model.write`. `WriteContext` is thread-local and holds
   user settings, so that isn't the place for it (same reasoning as
   [`load-context-plan.md`](load-context-plan.md)).

Prefer 1 unless the write path is reworked to pass an explicit context
anyway.

### Round trip

Loading a simulation and writing it back keeps every path in every file,
byte for byte, as long as the paths are inside the model's directory.
For a path outside it, the file's path and the written path name the
same file but may be spelled differently (`gwf/../shared/x` →
`shared/x`; normalize).

## Open questions

- Which directory a loaded model gets when its files are spread out
  (namefile in `gwf/`, packages in `shared/`). Proposal: the namefile's
  directory, always. Packages outside it get `../` paths.
- Whether `relpath` can leave the simulation directory (`../other`).
  MF6 allows it. Proposal: allow, normalize, don't special-case.
- `NetCDFModel` and NetCDF export write their own files; check how they
  name them.
- A user who sets `head_file="gwf/m.hds"` on a model with
  `relpath="gwf"` today's way gets `gwf/gwf/m.hds`. That's a behavior
  change for code written against the current flat convention; say so in
  the changelog.

## Steps

1. `Model.relpath`, derived `workspace`, `update_child_attr` no longer
   overwriting models. Unit tests: moving the simulation moves its
   models; setting a model's workspace sets `relpath`.
2. Write side: the path helper, used by namefile rows, file records and
   path fields; `Component.path` from the model workspace. Test: a model
   with `relpath="gwf"` and plain filenames writes `gwf/m.nam`,
   `gwf/m.dis`, `DIS6 gwf/m.dis` in its namefile, and `HEAD FILEOUT
   gwf/m.hds` in OC.
3. Load side: `LoadContext.relpath` and `relative()`, set for a model's
   children. Tests: the `load-context` subdirectory fixture loads with
   `relpath == "gwf"` and `dis.filename == "m.dis"`; write-back keeps the
   files byte for byte.
4. Run an MF6 simulation with a model in a subdirectory end to end
   (write, run, check the head file lands in `gwf/`).
5. Touched test files, ruff, mypy, smoke.

## Non-goals

- Changing how MF6 paths resolve on read. `LoadContext.workspace` stays
  the simulation directory.
- Simulation-level files (TDIS, IMS, exchanges) in subdirectories. Their
  paths stay as written.
