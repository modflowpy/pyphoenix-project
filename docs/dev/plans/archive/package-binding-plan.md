# Package-level binding

A package can name another component's input file in a file record, e.g.
`TS6 FILEIN rates.ts` in WEL's options. flopy4 should hold that file as an
attached `Ts`, load it with the package, and write the record from it, the
same way a model holds its packages. Most of the machinery exists. This is
what's missing.

## What exists

- **Component tree** (`component.py`). Any attrs field typed as a component
  (single, list or dict) is a child (`child_field_candidates`). It gets
  `_parent`, top-down and bottom-up attach, naming and collision checks,
  `_children`, and a recursive `write()`. This already works for packages
  under packages: `Dis.ncf` is written this way.
- **Bindings** (`converter/binding.py`, `_resolve_bindings`,
  `_make_binding_blocks`). This is for contexts only: a row `<FTYPE> <fname>
  [terms]` in a binding block (`packages`, `models`, `exchanges`,
  `solutiongroup`).
  - On load, ingress matches each row's token to a child field's class,
    loads the file and attaches it. Dimension providers load first, and
    their dims are passed to the rest.
  - On write, the rows are generated from the attached children.
  - `_make_binding_blocks` returns `{}` for anything that isn't a `Context`.
- **`subpackage(file_field=...)`** (`spec.py`, `6fecd21`). This is the
  package-level half. Codegen emits `ncf: Optional[Ncf]` next to `ncf_file`
  for each record in `SUBPACKAGES` (only `ncf_filerecord` today). On write,
  `Package._sync_subpackage_files` names the child's file in the path field.
  Nothing loads it.
- **Path fields** (`spec.path`). Each file record is a `Path` (or
  `list[Path]` when the record repeats) with a `_keyword` (`ts6`). Ingress
  fills it from `<KEYWORD> FILEIN <path>` rows (`file_fields` in
  `structure_component`).

## What's missing

### 1. Loading

On load, `Package.load` / `structure_component` should, for each path field
that has a child field:

- read the path(s);
- load each file as the child's class;
- attach the result.

Reuse `_resolve_bindings`'s pieces rather than writing a second loader:

- target lookup by ftype, including the G/A-variant disambiguation (TAS has
  none, but SPC/SPCA would);
- the `Package.load(..., dims=..., name=...)` call;
- `child.filename = Path(fname)`.

TAS needs the parent's grid dims passed to it (`tas_array` is `nodes`- or
`ncpl`-shaped); TS, OBS, ATS and NCF don't need any.

Paths in a file record are relative to the simulation's working directory,
not the parent file's directory. `Package.load` passes `workspace=path.parent`,
which is only right when every file sits in the simulation directory. For a
package loaded through a model, the workspace should come from the
simulation.

### 2. List children

`subpackage()` and `_sync_subpackage_files` assume a single child:

- TS and TAS records repeat (`ts_file: list[Path]`), so their child is
  `ts: Optional[list[Ts]]`. Syncing has to give each child its own file
  name.
- `Package.default_filename` stems from the parent's name, so two `Ts`
  children of one WEL would both default to `wel.ts`. It should use the
  child's own resolved name, which the tree already makes unique.

### 3. Path field vs. child field

Contexts have no separate path field: the binding row is generated from the
child. Packages keep both (`ncf_file` and `ncf`) and sync them one way, child
to path. That leaves:

- **What if both are set and disagree?** Today the user's path wins silently.
- **A path with no child** is a reference to a file flopy4 didn't load or
  doesn't manage. That should stay possible, e.g. for an OBS file before
  `utl-obs` is generated, or a hand-written TS file the user only wants to
  point at.

Options:

- **(a) Keep both, sync both ways.** On load, set both. On write, derive the
  path from the child when there is a child. Smallest change; it's what
  NCF does now plus loading.
- **(b) Derive the path field from the children.** It becomes a read-only
  property when a child field exists, the same as a context's binding rows.
  Cleaner, but it loses "point at a file without loading it".
- **(c) Union-typed field** (`ts: list[Ts | Path]`). One field, but every
  consumer has to handle both.

I'd start with (a), and raise on write when the path and the child's
filename are both set and differ.

### 4. Which records link to which component

- **Now:** add to `SUBPACKAGES` in `make.py`. `_subpackage_field_spec` picks
  `Optional[X]` or `Optional[list[X]]` from the path field's type.
- **Later:** replace the table with `File.component` once the dev3
  migration carries it (`../modflow-devtools/subpackage-links-plan.md`).

From the legacy DFNs' `# flopy subpackage` / `# mf6 subpackage` lines:

| record | component | used by | flopy4 class exists? |
|---|---|---|---|
| `ncf_filerecord` | utl-ncf | `*-dis`, `*-disv` | yes (wired, write only) |
| `ts_filerecord` | utl-ts | ~25 stress/advanced packages | yes |
| `tas_filerecord` | utl-tas | gwf-rcha, gwf-evta, utl-spca | yes |
| `obs_filerecord` | utl-obs | most stress packages, exchanges | no (utl-obs not generated) |
| `ats_filerecord` | utl-ats | sim-tdis (hand-written `Tdis`) | yes |
| `tvk_filerecord` / `tvs_filerecord` | utl-tvk / utl-tvs | gwf-npf / gwf-sto | no |
| `hpc_filerecord` | utl-hpc | sim-nam | yes |
| `mvr`/`mvt`/`mve_filerecord`, `gnc_filerecord` | gwf-mvr / gwt-mvt / gwe-mve, gwf-gnc | exchanges | mvr, gnc yes |
| SSM/SSE `fileinput` rows (`pname spc6 filein <f>`) | utl-spc | gwt-ssm, gwe-sse | no |

Notes:

- `Tdis` is hand-written, so ATS is wired by hand rather than by codegen.
- `hpc_filerecord` is on the simulation name file, which is a context. HPC
  could go through either path.
- SSM/SSE `fileinput` isn't an options record: the file is a column in a
  list row, keyed by `pname`. It needs a different shape, so leave it until
  the rest works.
- MVR and GNC appear twice: under a model (a model binding row in `gwf-nam`'s
  packages block) and under an exchange (a file record). The exchange case
  waits on exchange support (#3 in the remaining issues).

### 5. Write

Writing mostly works already, since children are written recursively. What's
left: `_sync_subpackage_files` for lists, the conflict check from §3, and
making sure every linked child is written once. A child reachable both as a
model package and as a file record shouldn't be.

### 6. Time-series names (separate, later)

Once `Ts` objects are attached, a package can check that every
time-series name used in a `time_series=True` column is defined in one of
its `Ts` children. Optionally, it could also accept a series directly and
generate the `Ts`. This is an API decision, not binding work.

## Order

1. List children in `subpackage()` / `_sync_subpackage_files` / codegen, plus
   per-child default file names.
2. Load path: file record → child, reusing `_resolve_bindings`'s lookup and
   load. Test with NCF (already generated) and TS.
3. Add `ts_filerecord` and `tas_filerecord` to `SUBPACKAGES`. Regenerate.
4. Path/child conflict check on write.
5. ATS on `Tdis` by hand; OBS once `utl-obs` is generated; TVK/TVS once
   generated.
6. Switch `SUBPACKAGES` to `File.component` when devtools lands.
7. SSM/SSE `fileinput`, exchange MVR/GNC: separately.

## Tests

- Load a WEL with two `TS6 FILEIN` lines: two `Ts` children, names and rows
  intact, `ts_file` matching.
- Round trip: write the package, check the records and the TS files, load
  again, compare.
- RCHA with a `TAS6` file: the child gets the grid dims.
- DIS with `NCF6 FILEIN`: `dis.ncf` is loaded (currently `None`).
- A path field with no child file present: load doesn't fail, the path is
  kept, `ts` is `None`.
- Conflict: `ts_file` and the child's filename differ, so write raises.
