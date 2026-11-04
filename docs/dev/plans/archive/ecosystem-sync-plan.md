# Ecosystem Sync Plan

**Archived 2026-10-19.** Done: the stacked branches merged (#425, #427, #429, #434, #439, #440, #441, #445, #446, #448, among others), including lazy imports and the TOML spec. Only upstream parts remain (`mf6 --spec`), plus the idea in [`user-dir-classes.md`](../components/user-dir-classes.md). The status line below, "pending review", is out of date.

Discussion: https://github.com/modflowpy/pyphoenix-project/discussions/81

**Status (2026-10-08):** the six steps below are done on stacked branches `sync-python-api` → `sync-safe-writes` → `sync-contract` → `sync-check-at-run` → `sync-install` → `sync-ci-matrix`, pending review. Before that (develop `2d3d4dc`) it was partly implemented, in a
different shape from the design below. The CLI, the contract file and the
compatibility check exist. The direction for the rest was revised on
2026-10-08; see [Revised direction](#revised-direction-2026-10-08) and
[Still to do](#still-to-do). The Design section is kept as the original
intent.

## Motivation

The version compatibility contract between flopy and MF6 is currently implicit. Users must manually coordinate `generate_classes` (syncs flopy to a specific MF6 DFN version) and `get-modflow` (installs a specific MF6 binary), with no enforcement or visibility into whether the two are aligned. Flopy and MF6 must be released in lockstep for users to get a coherent combination.

This plan decouples flopy4 and MF6 releases.

## Design

### Namespace layout

The Programs API is simulator-agnostic (manages mf6, mt3dms, gridgen, etc. uniformly). The DFNs and Models APIs are MF6-specific. This maps onto:

```python
flopy4.programs        # generic: re-export of modflow_devtools.programs
flopy4.mf6.dfns        # mf6-specific: re-export of modflow_devtools.dfns
flopy4.mf6.models      # mf6-specific: re-export of modflow_devtools.models
flopy4.mf6.sync()      # install binary + regenerate classes for a given MF6 version
```

`flopy4.programs` sits at the top level so future simulator namespaces (e.g. `flopy4.mfnwt`, `flopy4.mt3d`) can share it without going through the MF6 namespace.

### The version contract

`MF6_CONTRACT_VERSION` is a static string written into the package by `sync()` and committed to the repo. It is read at import time and compared against the discovered binary. It lives in a generated sidecar so handwritten source stays clean:

```python
# flopy4/mf6/_contract.py — written by sync(), committed, never edited by hand
MF6_CONTRACT_VERSION = "6.6.0"
MF6_DFN_SCHEMA_VERSION = "2"
```

```python
# flopy4/mf6/__init__.py
from flopy4.mf6._contract import MF6_CONTRACT_VERSION, MF6_DFN_SCHEMA_VERSION
```

### Writing to the install location

`sync()` writes generated classes and `_contract.py` directly into the installed package directory in site-packages — the same approach used by current flopy's `generate_classes`. In practice this works because Python packages almost always live in a virtualenv, where site-packages is user-writable.

If the install location is not writable (system Python, read-only container), `sync()` raises a clear error:

```
SyncError: flopy4 is installed to a read-only location ({path}).
Install into a virtual environment and try again, or use
`pip install --user flopy4` for a user-writable install.
```

No silent fallback to a user data directory — a partial sync (contract updated, classes not updated, or vice versa) would be worse than a clear failure.

After a `pip install --upgrade flopy4`, the bundled classes and `_contract.py` are restored to the release version. The compatibility check will then prompt the user to re-sync if their binary is newer.

### Runtime compatibility check

On first use of `flopy4.mf6`, flopy4 resolves the MF6 executable (PATH lookup via `shutil.which`, matching existing flopy behavior) and queries its version with a subprocess call (`mf6 -v`). If the reported version doesn't match `MF6_CONTRACT_VERSION`, a `UserWarning` is emitted with a clear call to action. Silent if no binary is found.

```python
def _check_mf6_compatibility():
    exe = shutil.which("mf6")
    if exe is None:
        return
    binary_version = _query_mf6_version(exe)   # subprocess: mf6 -v, parse stdout
    if binary_version != MF6_CONTRACT_VERSION:
        warnings.warn(
            f"flopy4 is synced to MF6 {MF6_CONTRACT_VERSION} "
            f"but the discovered binary reports {binary_version}. "
            f"Run `flopy4 sync` to regenerate classes for MF6 {binary_version}.",
            UserWarning,
            stacklevel=2,
        )
```

### The sync operation

`sync()` is user-facing. It installs the requested MF6 binary, fetches DFNs for that version, regenerates classes in-place, and updates `_contract.py`:

```python
def sync(version: str | None = None, bindir: Path | None = None) -> SyncResult:
    """Sync flopy4 to a specific MF6 version.

    Installs the MF6 binary, fetches matching DFNs, and regenerates
    input/output classes in the installed package directory.
    If version is omitted, syncs to the version of the discovered binary.
    """
    if version is None:
        version = _query_mf6_version(shutil.which("mf6"))

    _check_install_writable()   # raises SyncError with helpful message if not

    # 1. install binary
    exes = install_program("mf6", version=version, bindir=bindir)

    # 2. query installed binary — this is the source of truth for MF6_CONTRACT_VERSION
    contract_version = _query_mf6_version(exes[0])

    # 3. fetch DFNs for the same ref
    registry = RemoteDfnRegistry(ref=version)
    registry.sync()

    # 4. regenerate classes in-place
    outdir = Path(__file__).parent   # flopy4/mf6/ in site-packages
    _generate_classes(registry, outdir=outdir)

    # 5. update contract
    _write_contract(outdir, version=contract_version, dfn_schema=registry.schema_version)

    return SyncResult(version=contract_version, exes=exes)
```

`MF6_CONTRACT_VERSION` is always the version string reported by the installed binary
(`mf6 -v`), never the ref string passed by the user. This means `"latest"`,
`"develop"`, a tag, or a commit hash are all valid refs — the contract always
records the concrete version the binary reports, which is the single source of
truth tying the binary, the DFNs, and the generated classes together.

### CLI surface

```
flopy4 sync                         # sync to discovered binary's version
flopy4 sync --version 6.6.0        # sync to a specific MF6 release
flopy4 sync --version develop       # sync to MF6 develop (CI use case)
flopy4 status                       # show contract version vs discovered binary
```

## Prerequisites (modflow-devtools gaps)

1. **`query_program_version(exe: Path) -> str`** — call `mf6 -v` and parse stdout, capturing the full version string including any `+shortsha` suffix. Needed both for the runtime compatibility check and for `sync()` when no version is specified.

## Version alignment roadmap

The current design works well for tagged releases: `MF6_CONTRACT_VERSION = "6.6.0"` is unambiguous. It breaks down for `develop` builds, because the DFNs and the binary are sourced independently — two users both synced to `develop` may have different DFN snapshots and different binaries, with no way to detect the mismatch.

### Near-term: commit-grained version strings

The most targeted fix requires coordinated changes in two places:

**1. MF6 binary (upstream) — Meson `vcs_tag()` with a helper script**

A `vcs_tag()` call in `meson.build` runs a small Python script at build time
that produces a `+shortsha` suffix for development builds and an empty string
for releases:

```meson
# meson.build
version_f90 = vcs_tag(
  command: ['python3', 'distribution/vcs_tag_suffix.py'],
  input:   'src/Utilities/version.f90.in',
  output:  'version.f90',
  replace_string: '@VCS_TAG@',
  fallback: '',
)
```

```python
# distribution/vcs_tag_suffix.py
# If HEAD is an exact tag match this is a release — no suffix.
# Otherwise it's a development build — emit '+shortsha'.
try:
    subprocess.check_output(['git', 'describe', '--exact-match', '--tags', 'HEAD'],
                            stderr=subprocess.DEVNULL)
    print('', end='')
except subprocess.CalledProcessError:
    sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
    print(f'+{sha}', end='')
```

```fortran
! src/Utilities/version.f90.in
character(len=*), parameter :: VERSIONTAG = "@VCS_TAG@"
character(len=*), parameter :: VERSION     = VERSIONNUMBER//VERSIONTAG
```

This produces PEP 440-style local version labels:

| Build | `mf6 -v` output |
|-------|----------------|
| Release (exact tag) | `6.6.0` |
| Development | `6.8.0.dev0+abc1234` |

`vcs_tag()` re-runs at every build (not just configure), so the embedded hash
always reflects the current HEAD. The `fallback: ''` ensures a clean release
string when building outside a git repository.

**2. flopy4 — store and check the full version string**

`_contract.py` records only the full version string from the binary and the
DFN schema version — no separate commit field is needed:

```python
# flopy4/mf6/_contract.py — written by sync()
MF6_CONTRACT_VERSION   = "6.8.0.dev0+abc1234"  # full version including +shortsha suffix
MF6_DFN_SCHEMA_VERSION = "2"
```

The compatibility check is a direct string comparison of the binary's reported
version against `MF6_CONTRACT_VERSION`. For release builds the string is a
plain semver (`"6.6.0"`); for development builds it includes the `+shortsha`
suffix — both cases are handled identically with no special-casing.

`_query_mf6_version()` must capture the full version string including the
`+shortsha` suffix (a regex matching only `\d+\.\d+\.\d+` would truncate it):

```python
_MF6_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:\.\w+)?(?:\+[0-9a-f]+)?)")
```

A separate `MF6_DFN_COMMIT` field is not needed. For dev builds the shortsha
is already embedded in `MF6_CONTRACT_VERSION`; for tagged releases there is no
shortsha and `MF6_CONTRACT_VERSION` alone is sufficient. Storing the commit SHA
redundantly would require an extra GitHub API call per sync (two calls for
annotated tags) and would still be useless for the release case.

This approach requires no changes to individual DFN files, no new fields on
`DfnRegistryMeta`, and no new CI infrastructure beyond Meson's built-in
`vcs_tag()` support.

### Mid-term: self-describing MF6 (`mf6 --spec`)

> **Status:** The `mf6 --spec` flag is implemented and working as of MF6
> develop (branch `emit-spec`). See `../modflow6/utils/dfnembed/plan.md` for
> the full MF6-side plan and `../modflow-devtools/dfnspec-plan.md` for the
> devtools serialization work.

The cleanest long-term solution is having the MF6 binary emit its own input
specification directly, making the spec and the binary a single artifact:

```bash
mf6 --spec                  # emit full spec to stdout
mf6 --spec > spec.txt       # capture to file
mf6 --spec | flopy4 sync    # pipe directly to sync
```

Version alignment becomes structurally guaranteed — no registry fetch, no
cross-referencing commit hashes, no `develop` pointer ambiguity. Works offline
(valuable in HPC/air-gapped environments).

**Current output format: DFN text with sentinels**

The initial implementation embeds the raw DFN text verbatim and emits it as a
single stream, with `# --- <name> ---` comment lines separating each component
file (these are legal DFN comments, ignored by all existing parsers):

```
# --- gwf-chd.dfn ---
# --------------------- gwf chd options ---------------------
...

# --- gwf-dis.dfn ---
...
```

`modflow_devtools` can already parse this format. To feed it into the current
`sync()` pipeline (which expects a directory of DFN files), split on sentinels
and write to a temp directory:

```python
def spec_to_dir(mf6_exe="mf6") -> pathlib.Path:
    text = subprocess.check_output([mf6_exe, "--spec"], text=True)
    tmp = pathlib.Path(tempfile.mkdtemp())
    current_name, current_lines = None, []
    for line in text.splitlines():
        if line.startswith("# --- ") and line.endswith(" ---"):
            if current_name:
                (tmp / current_name).write_text("\n".join(current_lines))
            current_name = line[6:-4]
            current_lines = []
        else:
            current_lines.append(line)
    if current_name:
        (tmp / current_name).write_text("\n".join(current_lines))
    return tmp
```

**Future output format: single TOML document**

Once `DfnSpec.dump()` is added to `modflow_devtools`, `mf6 --spec` will switch
to emitting a single TOML document — no sentinels, no splitting, parseable
directly with `tomllib`:

```bash
mf6 --spec | python -c "import sys, tomllib; spec = tomllib.load(sys.stdin.buffer)"
```

The schema falls directly out of `DfnSpec._flat`: each component's `asdict()`
dict nested under its name with a top-level `schema_version`:

```toml
schema_version = "2"

["gwf-chd"]
name = "gwf-chd"
advanced = false
multi = true

["gwf-chd".options.auxiliary]
block = "options"
name = "auxiliary"
type = "string"
...
```

**How `sync()` evolves**

Once `mf6 --spec` emits TOML, `sync()` can drop the registry fetch entirely
and derive everything from the installed binary:

```python
def sync(version: str | None = None, bindir: Path | None = None) -> SyncResult:
    exes = install_program("mf6", version=version, bindir=bindir)
    contract_version = _query_mf6_version(exes[0])

    # replaces: registry = RemoteDfnRegistry(ref=version); registry.sync()
    spec_toml = subprocess.check_output([str(exes[0]), "--spec"])

    _generate_classes_from_spec(spec_toml, outdir=_MF6_PACKAGE_DIR)
    _write_contract(_MF6_PACKAGE_DIR, version=contract_version, dfn_schema="2")
    return SyncResult(version=contract_version, exes=exes)
```

`_generate_classes_from_spec()` loads the TOML blob via `DfnSpec` and passes
it to the existing class-generation machinery. No GitHub API call, no cache,
no `develop` pointer ambiguity.

This approach generalises: any simulator that can emit its own spec gains
flopy4 support without a separate DFN pipeline.

## Phases

### What shipped

- **CLI** (`flopy4/cli.py`, entry point `flopy4`): `flopy4 mf6 sync
  [release_id]` and `flopy4 mf6 status`, not the planned top-level
  `flopy4 sync` / `flopy4 status`.
  - `release_id` is `owner/repo@tag` or a local DFN directory. With none,
    it uses the discovered binary's version, else latest.
  - Fetches DFNs through `RemoteDfnRegistry` (falling back to
    `fetch_dfns` from the repo tree when the release has no `dfns.zip`),
    or reads them with `LocalDfnRegistry`.
  - Regenerates with `dfn2py.make` into the package directory, existing
    files only unless `--all-packages`.
  - `--mf6-version` overrides the recorded version.
- **Contract** (`flopy4/mf6/_contract.py`, written by sync): `MF6_VERSION`
  and `DFN_SCHEMA_VERSION`, not `MF6_CONTRACT_VERSION` /
  `MF6_DFN_SCHEMA_VERSION`. Currently `"develop"` / `"2.0.0.dev3"`.
- **Compatibility check** (`flopy4/mf6/_compat.py`):
  `check_mf6_compatibility()` runs `mf6 -v` and warns on a mismatch.

### Where it differs from the design

- **The check runs at import** (`flopy4/mf6/__init__.py`), not lazily on
  first use as Phase 2 planned.
- **The `+shortsha` suffix is dropped.** `_query_mf6_version` strips
  everything after `+`, the opposite of the near-term roadmap below.
- **A branch-name contract skips the check.** When `MF6_VERSION` isn't
  semver (e.g. `"develop"`, today's value), nothing is compared. So the
  develop case the roadmap targets is unchecked.
- **The version recorded is the DFN source's**, from the tag or
  `--mf6-version`, not the installed binary's `mf6 -v` as the design says.
- **An unknown version warns on import**, rather than staying silent.

### Revised direction (2026-10-08)

These decisions replace parts of the Design section, which is kept as the
original intent. They came from reviewing the design against flopy #2385
(closed: install hooks, multiple executables, tests against generated
code), flopy #1970, and discussions #35 and #81.

- **Sync doesn't install binaries by default.** People manage several
  executables, so installing one shouldn't be tied to regenerating
  classes, in either direction. Sync regenerates classes from one of three
  sources: a release tag, a local DFN directory, or an executable
  (`mf6 --spec`, once upstream ships it). Installing becomes opt-in
  (`--install`), replacing `--no-install`. The `--spec` source replaces the
  design's reason for installing: the spec and the version come from the
  same binary.
- **In-place writes are atomic and tracked.** Generate into a temporary
  directory and swap it in, so a failed sync can't leave classes from mixed
  versions. Record the generated files in `_contract.py`, because files
  that `--all-packages` creates aren't in pip's RECORD and would outlive a
  `pip install --upgrade`, generated from a different version from the
  restored contract. Sync and status detect and remove such orphans.
- **The compatibility check moves off import.** It runs at
  `Simulation.run` against the executable actually used, cached per path,
  and in `flopy4 mf6 status`. Import no longer runs a subprocess or warns
  about an unknown contract.
- **Develop contracts are meaningful.** For branch refs, sync records the
  resolved commit SHA (one API call per sync is cheap), which also gives
  #214 its reproducibility string. The `+shortsha` suffix is kept rather
  than stripped: compare base versions until MF6's `vcs_tag()` lands, then
  compare exactly. Release CI fails if the contract doesn't name a tag.
- **DFNs are stored with the classes.** The typed reader currently fetches
  DFNs over the network at runtime using `MF6_VERSION` as the ref
  (`flopy4/mf6/codec/reader/dfns.py`). With `"develop"` that's a moving
  target that can drift from the generated classes, and it fails offline.
  Sync writes the spec it generated from (as TOML) next to the classes,
  and the reader uses that copy. This also prepares for `mf6 --spec`
  emitting TOML, and covers #81's "emit definition files" idea.
- **No re-exports.** Re-exporting `modflow_devtools.programs`, `dfns` and
  `models` would tie flopy4's public API to devtools APIs that are still
  experimental. Users import devtools directly; the CLI wraps what's worth
  wrapping.
- **A CI version matrix replaces `validate=`.** Test against the latest
  MF6 release and develop on every PR, and document which MF6 versions are
  supported (per #1970). That does more for the "older model from a
  partner" case in #35 than a validation option.

### Still to do

In order:

1. ~~**Python API.**~~ Done on branch `sync-python-api`:
   `flopy4.mf6.sync()` returns a `SyncResult` (version, source, outdir,
   generated files) and the CLI wraps it. Sources: release ID or bare ref,
   local DFN directory; `exe=` raises `NotImplementedError` until
   `mf6 --spec` ships. The `--force` help text is fixed here too.
2. ~~**Safe writes.**~~ Done on branch `sync-safe-writes` (stacked on
   `sync-python-api`). Generation goes to a `.sync-*` staging directory
   inside the output directory (so ruff uses the project config and the
   swap is a same-filesystem rename), is checked with `compile()`, then
   swapped in with rollback. `SyncError` for read-only installs. The
   contract records `GENERATED_FILES`. Orphans are generated modules that
   neither the new sync nor the previous contract lists, and are removed.
   Listed modules with no DFN in the new source are kept with a warning,
   because handwritten `__init__`s import generated modules and removing
   one could break `import flopy4`. Not done: making sync runnable when
   the generated classes fail to import. `flopy4/__init__.py` imports
   `flopy4.mf6`, so that needs lazy imports there; it's out of scope here.
3. ~~**Contract contents.**~~ Done on branch `sync-contract` (stacked on
   `sync-safe-writes`). The contract records `DFN_COMMIT`: the GitHub
   ref's commit (API call, `GITHUB_TOKEN` if set) for remote sources,
   the checkout's HEAD with `-dirty` for local ones. Sync copies the raw
   DFNs into `flopy4/mf6/dfns` (2.4 MB, package data). The typed reader
   reads them, with no network fetch. TOML waits on devtools being able
   to write it. `_query_mf6_version` keeps `+<commit>`. The check compares
   commits when the contract and binary both have one, else base
   versions. The release check is a test that only runs with
   `FLOPY4_RELEASE` set, since there's no release workflow yet.
4. ~~**Compatibility check.**~~ Done on branch `sync-check-at-run`
   (stacked on `sync-contract`). Import no longer runs the check.
   `Simulation.run` checks its `exe`, resolved under the workspace like
   `run_cmd` resolves it, and binary versions are cached by path and
   mtime. An unknown contract now warns at run time, not import.
5. ~~**Opt-in binary install.**~~ Done on branch `sync-install` (stacked
   on `sync-check-at-run`). `--install`/`--bindir` (`install=`,
   `bindir=`) install before any classes change: the `modflow6` release
   for a tag or `latest`, the latest `modflow6-nightly-build` for
   `develop`. Local DFNs and other branches are refused. `--no-install` is
   gone. Tested against real installs of 6.6.3 and the nightly. The
   nightly reports `6.9.0.dev0+14b4a67.dirty`, so MF6 already embeds the
   commit (the `vcs_tag()` roadmap item looks done upstream). The commit
   check now ignores `.dirty`; that fix is on `sync-check-at-run`.
6. ~~**CI version matrix.**~~ Done on branch `sync-ci-matrix` (stacked
   on `sync-install`). A `test-mf6-release` job runs `flopy4 mf6 sync
   latest --install` and the tests, non-blocking for now. Locally against
   6.8.1, the only real failures are test020's MAW inputs, which are
   develop-only. The test models come from the develop models registry.
   Making the job blocking needs release-matched models, or skipping
   develop-only ones. Both test jobs print `flopy4 mf6 status`. The
   support policy is in `docs/mf6-versions.md`. Also fixed: `sync latest`
   404'd, because `latest` was passed to the DFN fetch as a git ref.

Follow-ups:
- ~~`flopy4/mf6/pts.py`~~ deleted on `sync-safe-writes`.
- Make sync runnable when generated classes fail to import (lazy
  imports in `flopy4/__init__.py`). Then, on the same branch, delete
  generated modules the new DFNs lack instead of keeping them. Today
  deleting is unsafe: syncing to 6.5.0 would delete `utl/ncf.py`, which
  `utl/__init__.py` imports, breaking `import flopy4`. Sync itself needs
  that import, so a re-sync couldn't repair it. Once sync works without
  the generated classes importing, a bad sync is recoverable. (6.6.3,
  6.8.1 and develop lack none of the imported modules.)
  **Done** on `sync-lazy-imports`: `flopy4.mf6` loads generated
  components on first use (`__getattr__`; `get_fnames`/`get_ftypes`
  import them all first, so lookups stay complete). Codegen's
  `_has_module` checks the file rather than `find_spec`, which imported
  `utl/__init__`. Sync removes every generated module it didn't
  regenerate; `SyncResult.kept` is gone. A handwritten `__init__` that
  imports a removed module still breaks using the classes, but sync and
  status still run, so a re-sync fixes it.
- Store the spec as TOML once devtools can write it, and sync from
  `mf6 --spec`. **TOML done** on `sync-toml-spec` (devtools fbec2ab, #386,
  fixed the round trip): sync migrates a `.dfn` source to per-component
  TOML in `dfns/` (or copies a TOML source); tests check the stored spec
  equals the source and re-syncing from it reproduces the classes.
  devtools only loads a directory, so it's 129 files, not one. `mf6 --spec`
  still waits on modflow6. History: checked 2026-10-08: devtools can write it
  (`modflow_devtools.dfns.migrate(..., "2.0.0.dev3", fmt="toml")`, `.dfn`
  input only) and `Dfns.load` reads `*.toml`, with the same load time.
  But the round trip is lossy, so this is blocked on devtools:
  - `_serialize_safe` drops `name` from every field dict, including a
    list's `item`, which isn't keyed by name; on load it inherits the
    parent's (`gwf-oc` `output_record` → `output`, `prt-prp`
    `releasesetting` → `perioddata`; 6 OC components plus `prt-prp`).
  - Tuple defaults load as lists (`sim-tdis` `perioddata`), so codegen
    renders `([1.0, 1, 1.0],)`. Fix in devtools (normalize on load) or
    in flopy4 codegen (`make.py` `_default = repr(tuple(...))`, make rows
    tuples).
  Otherwise classes generated from the TOML match those from the `.dfn`
  files exactly (develop, 129 components). Once fixed, sync migrates a
  `.dfn` source to TOML in `dfns/` (copying a TOML source as is). Test:
  re-syncing from the stored `dfns/` reproduces the classes. `mf6 --spec`
  isn't in modflow6 develop yet.

- Maybe, later: generate classes into a per-user, per-version directory
  instead of the installed package. See [`user-dir-classes.md`](../components/user-dir-classes.md).

Upstream parts (MF6 `vcs_tag()`, `mf6 --spec` as TOML) are tracked in the
modflow6 and devtools plans.

## Notes

- **`develop` ref**: Both the Programs and DFNs APIs support `develop` as a ref. `flopy4 mf6 sync MODFLOW-ORG/modflow6@develop` is a first-class use case for CI pipelines testing against nightly MF6 builds.
- **DFN schema versioning**: `_contract.py` records both the MF6 version and the DFN schema version. A future flopy4 / MF6 v2 schema transition won't silently mix incompatible generations (see devtools issue #259).
- **Post-upgrade re-sync**: After `pip install --upgrade flopy4`, bundled classes are restored to the new release version. If the user's binary is newer than the new release, the compatibility check will prompt them to re-sync. Modules a sync created that the release doesn't ship survive the upgrade; the generated-file list in the contract lets sync and status find and remove them.
