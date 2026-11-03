# Generating classes into a user directory

Status: **idea, not planned.** Written 2026-10-08. Revisit once
`mf6 --spec` lands.

## Today

`flopy4 mf6 sync` regenerates the component classes in place, in the
installed `flopy4/mf6` package, with the DFNs (`flopy4/mf6/dfns`) and the
contract (`_contract.py`). Writes are atomic (stage, swap, roll back), and
the contract's file list tracks which modules sync owns.

## The idea

Leave the installed package alone. sync writes classes, DFNs and contract
to a per-user, per-version directory, e.g.
`<platformdirs user_data_dir>/flopy4/mf6/<version or commit>/`, and flopy4
imports the generated modules from the selected directory under their
usual names (`flopy4.mf6.gwf.dis`). The wheel still ships one set (the
release's) as the default.

## Package layout constraint

Generated and handwritten code live in the same package and import each
other:

| dir | generated | handwritten |
|---|---|---|
| `flopy4/mf6` (top) | 5 (`simulation`, `tdis`, `ims`, `ems`, `_contract`) | 31 |
| `gwf`, `gwt`, `gwe`, `prt` | all | none |
| `exg` | 6 | 1 (`__init__`) |
| `utl` | 12 | 2 (incl. `__init__`) |

- generated modules import handwritten bases (`simulation_methods`,
  `model`, `package`, ...)
- handwritten modules import generated classes: `exg/__init__.py`,
  `utl/__init__.py`, the `*_methods` modules (lazily)

So the generated modules have to keep their names and load from somewhere
else.

## Mechanisms

1. **Extend `__path__`.** `flopy4/mf6/__init__.py` puts the selected
   directory first on its `__path__`, and the mixed subpackages (`exg`,
   `utl`) do the same. The all-generated subpackages (`gwf/` ...) are then
   found in the user directory. Top-level generated modules (`simulation`,
   `tdis`, `ims`, `ems`) resolve the same way. Precedent: pywin32's makepy
   writes generated wrappers to a `gen_py` cache directory and imports them
   from there.
2. **Custom importer.** A meta path finder maps the generated module names
   (from the selected contract's `GENERATED_FILES`) to the selected
   directory. More code, but exact: only listed modules are redirected, and
   a missing one gives a clear error rather than falling through to the
   bundled copy.

(2) is safer, since nothing silently mixes the bundled and synced sets.

## Selection

Order, first match wins:
1. explicit: `flopy4.mf6.use("6.6.3")` before the first import of a
   component
2. env var, e.g. `FLOPY4_MF6_VERSION` (needed so spawned worker processes
   make the same choice)
3. maybe: the version of the `mf6` on PATH, if a synced directory matches
   (this turns the run-time compatibility check into selection)
4. the bundled classes

The choice is fixed per process: classes register globally on import
(`FNAMES`/`FTYPES` in `component.py`), so it can't change after the
first component import. `use()` after that raises.

## What it buys

- sync never writes to site-packages: read-only, system, conda and shared
  HPC installs all work. `_check_writable` goes away, and so do files pip
  doesn't know about (left behind by `pip uninstall`) and
  `pip install --upgrade` putting back the release's classes over synced
  ones.
- Several versions side by side. Switching is selecting, not
  regenerating: useful for testing against several MF6 versions, or users
  with more than one binary.
- Simpler writes: generate into a new directory and rename it into place.
  The rollback logic and stale-module tracking (orphans, contract file
  list) mostly go away, since old versions just stay where they are.

## What it costs

- **Static typing and IDEs (the big one).** mypy, pyright and editors
  resolve `flopy4.mf6.gwf.Gwf` from the installed package, so they see
  the bundled classes, not the selected version: wrong completions and
  wrong type errors for anyone using a synced version. Pointing tools at
  the user directory (`extraPaths`, stubs) is awkward with the mixed
  packages.
- Fixed per process (see Selection). Multiprocessing with spawn needs the
  env var.
- Importing code from a user-writable directory. Same trust as a venv the
  user owns, but some locked-down setups will object.
- More moving parts: selection rules, cleaning up old version directories
  (`flopy4 mf6 list` / `prune`?), errors for an incomplete or corrupt
  directory, reporting which set is active in `flopy4 mf6 status`.
- Dev workflow: classes stay committed in the repo for review, so sync
  needs an `--outdir` (or "write into the package") mode for developers.
- Rework: the contract and atomic writes carry over, one per directory;
  the orphan and stale-module handling mostly goes.

## Hybrid (preferred, if we do it)

- The bundled classes in the package are never modified.
- `sync` only writes to the user directory.
- Without a selection, flopy4 uses the bundled classes, exactly as typed.

Users who never sync keep exact types and pay nothing. Only those who
opt into another version pay the typing cost.

## Open questions

- Pickles hold `flopy4.mf6.gwf.dis.Dis`, which resolves to whichever set
  is selected when unpickling. Do we need to record the version in
  pickles / saved files?
- Should a version directory be keyed by version string, commit, or both?
  (develop moves; commit is the real identity.)
- Do the stored DFNs (one TOML spec, once devtools round-trips losslessly)
  live in the same directory? Yes, presumably, for the same pairing reason
  as today.
- How does `mf6 --spec` fit: `sync --exe path/to/mf6` → directory keyed by
  the binary's reported version and commit, selected automatically when
  that binary runs?

## Recommendation

Not now. The current in-package design is simpler and keeps typing exact.
Revisit once `mf6 --spec` lands, because syncing from whatever binary is
on PATH makes several versions side by side more likely to come up. If
we do it, use the hybrid with a custom importer.
