# Ecosystem Sync Plan

Discussion: https://github.com/modflowpy/pyphoenix-project/discussions/81

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

### Mid-term: self-describing MF6

The cleanest long-term solution is making the MF6 binary emit its own input
specification directly:

```
mf6 --dump-spec [--format toml|json]
```

`flopy4 sync` would then become:

```python
exes = install_program("mf6", version=version, bindir=bindir)
spec = subprocess.check_output([str(exes[0]), "--dump-spec", "--format", "toml"])
_generate_classes_from_spec(spec, outdir=_MF6_PACKAGE_DIR)
```

Version alignment becomes structurally guaranteed — the spec and the binary
are the same artifact. No registry fetch, no cross-referencing commit hashes,
no `develop` pointer ambiguity. Works offline (valuable in HPC/air-gapped
environments).

**Implementation in Fortran/Meson (build-time embedding)**

A Meson `custom_target` converts the DFN files to a single TOML blob and
generates a Fortran source file containing it as a string constant:

```meson
dfn_embed = custom_target('embed_dfns',
  input:   dfn_files,
  output:  'dfn_embed.f90',
  command: [python, 'scripts/embed_dfns.py', '@INPUT@', '@OUTPUT@'],
  build_by_default: true,
)
```

`mf6 --dump-spec` writes that constant to stdout. Binary size increases
modestly (the full DFN set is on the order of a few hundred KB uncompressed).
No changes to MF6's core logic are required — it is a build system change plus
a new CLI flag.

This approach also generalises: any simulator that can emit its own spec gets
flopy4 support without a separate DFN pipeline.

## Phases

### Phase 1 — Re-export devtools APIs

- Add `flopy4/programs.py`: re-export `modflow_devtools.programs` public surface
- Add `flopy4/mf6/dfns.py`: re-export `modflow_devtools.dfns` public surface
- Add `flopy4/mf6/models.py`: re-export `modflow_devtools.models` public surface
- Update `flopy4/__init__.py` to expose `programs`
- Update `flopy4/mf6/__init__.py` to expose `dfns`, `models`
- Add `modflow-devtools` as a hard dependency in `pyproject.toml`

### Phase 2 — Contract constant and compatibility check

- Add `flopy4/mf6/_contract.py` (committed; set to whichever MF6 version the current bundled classes were generated from)
- Import `MF6_CONTRACT_VERSION` and `MF6_DFN_SCHEMA_VERSION` in `flopy4/mf6/__init__.py`
- Implement `_query_mf6_version()` and `_check_mf6_compatibility()` in `flopy4/mf6/_compat.py`
- Trigger `_check_mf6_compatibility()` lazily on first meaningful use, not at module import top-level

### Phase 3 — `sync()` and CLI

- Implement `flopy4/mf6/sync.py`: `sync()`, `SyncResult`, `_check_install_writable()`, `_generate_classes()`, `_write_contract()`
- Wire `_generate_classes()` to the existing class-generation machinery, parameterized by DFN registry and output directory
- Expose `sync` from `flopy4.mf6`
- Add `flopy4 sync` and `flopy4 status` CLI commands

### Phase 4 — Validation with Models API

- After sync, optionally run a smoke test: copy a small example model via `flopy4.mf6.models.copy_to()`, run it with the newly installed binary, assert clean exit
- Opt-in via `sync(validate=True)`

## Notes

- **`develop` ref**: Both the Programs and DFNs APIs support `develop` as a ref. `flopy4 sync --version develop` is a first-class use case for CI pipelines testing against nightly MF6 builds.
- **DFN schema versioning**: `_contract.py` records both the MF6 version and the DFN schema version. A future flopy4 / MF6 v2 schema transition won't silently mix incompatible generations (see devtools issue #259).
- **Post-upgrade re-sync**: After `pip install --upgrade flopy4`, bundled classes are restored to the new release version. If the user's binary is newer than the new release, the compatibility check will prompt them to re-sync. This is the expected flow; no special handling needed.
