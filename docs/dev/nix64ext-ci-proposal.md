# Proposal: Extended MODFLOW 6 Binaries for Linux/Mac CI

## Problem Statement

### The flopy4 gh-pages gap

flopy4 (pyphoenix-project) publishes documentation to GitHub Pages via a `docs.yml` CI workflow. The docs include Jupyter notebooks under `docs/examples/` that demonstrate real MODFLOW 6 simulations. These notebooks must be executed to produce cell outputs before rendering — `jupyter-book` is configured with `execute_notebooks: "off"` and renders pre-stored outputs only.

Executing the notebooks requires the **extended MODFLOW 6 executable** (`mf6ext`), which includes PETSc, NetCDF, and parallel solver support needed to run the full example models.

The current CI situation:
- `extended-win.yml` downloads `win64ext` from `modflow6-nightly-build` and runs example *tests* on Windows only
- `docs.yml` runs on `ubuntu-latest` and has no access to an extended binary
- The gh-pages deploy job (`docs.yml`) therefore cannot execute notebooks in CI

The current workaround is to run a local script (`scripts/update_ghpages.py`) that syncs and executes the notebooks using a locally installed extended binary, commit the updated `.ipynb` files, and let CI render the pre-executed outputs. This is functional but:
- Requires every contributor with notebook changes to have a local extended build installed
- Is easy to forget, leaving stale notebook outputs in the repo
- Cannot be part of an automated merge-to-develop → deploy pipeline

### Broader ecosystem impact

The gh-pages notebook gap is one symptom of a larger problem: **extended MODFLOW 6 testing is currently Windows-only across the entire `modflowpy` ecosystem** because the extended binary is only available as a pre-built download for Windows.

In this repo, `extended-win.yml` is a separate, platform-restricted workflow precisely because of this constraint — not because there is any fundamental reason the extended tests shouldn't run on Linux and Mac. Building the extended binary from source with PETSc and NetCDF dependencies is complex enough that it is not practical to do in CI without a pre-built artifact. The Windows-only download makes Windows the path of least resistance.

If `linux64ext` and `mac64ext` artifacts were available via `install-modflow-action`, the immediate consequences would be:

- Extended example tests in this repo would run on all three platforms, catching platform-specific regressions currently invisible in CI
- The `extended-win.yml` workflow would be absorbed into the standard cross-platform test matrix rather than being a one-off Windows-only job
- Other `modflowpy` repositories with similar extended test gaps would benefit with minimal per-repo effort — just adding the `install-modflow-action` step and the appropriate `ostag`

The notebook execution / gh-pages deployment use case is a secondary beneficiary of the same change. The primary value is enabling full cross-platform extended CI testing across the ecosystem without requiring any repo to build the extended binary from source.

---

## Proposed Solution

### 1. `modflow6-nightly-build`: add Linux and Mac extended artifacts

Extend the nightly build CI matrix to produce `linux64ext` and `mac64ext` (and potentially `mac64armext` for Apple Silicon) artifacts alongside the existing `win64ext`. These binaries would be:

- Uploaded to the nightly GitHub release as release assets, using a consistent naming convention (e.g. `mf6ext_linux64.zip`, `mf6ext_mac64.zip`)
- **Not documented** in the release notes or README — omitted from the user-facing download table and changelog
- **Not advertised** as supported distributions

The intent is that a user browsing the repo would not know to look for them. A brief note in `CONTRIBUTING.md` or similar can document that extended Linux/Mac artifacts exist for CI tooling use only, with no support or stability guarantees.

The reasons these builds are not promoted to general users are:

- **glibc compatibility (Linux)**: Linux binaries are built against a specific minimum glibc version. A binary built on Ubuntu 22.04 will not run on older enterprise distros (e.g. RHEL 7 / CentOS 7 with glibc 2.17). Unlike Windows, there is no single Linux ABI that works universally — a general-purpose Linux distribution would need multiple variants to be broadly useful, a maintenance burden not justified for a CI-internal artifact.
- **Architecture fragmentation (Mac)**: Apple Silicon (`aarch64`) and Intel (`x86_64`) require separate binaries. `macos-latest` on GitHub Actions has shifted to ARM, but many user machines are still Intel, and building a universal binary adds complexity. Providing one architecture without the other would generate user confusion and support requests that `win64ext` does not face.

This approach reuses the existing build infrastructure with minimal additional overhead — the extended build jobs are primarily a CI matrix addition.

### 2. `modflow-devtools` / `install-modflow-action`: add Linux/Mac extended support

Update `install-modflow-action` (and the corresponding Python utilities in `modflow-devtools`) to:

- Know the asset naming convention for `linux64ext` and `mac64ext` artifacts
- Construct the correct download URL from the nightly release tag
- Expose the new ostag values (e.g. `linux64ext`, `mac64ext`, `mac64armext`) as supported options

From a consumer's perspective, enabling extended binaries in a Linux CI job would look identical to the existing Windows pattern:

```yaml
- name: Install extended modflow6 executables
  uses: modflowpy/install-modflow-action@v1
  with:
    repo: modflow6-nightly-build
    ostag: linux64ext
```

`install-modflow-action` is the only documented path to these artifacts, making it the effective access gate even though the assets are technically public on the release.

### 3. flopy4 `docs.yml`: execute notebooks in CI

Once `linux64ext` is available via `install-modflow-action`, the `docs.yml` workflow can be updated to execute notebooks directly:

```yaml
- name: Install extended modflow6 executables
  uses: modflowpy/install-modflow-action@v1
  with:
    repo: modflow6-nightly-build
    ostag: linux64ext

- name: Sync and execute notebooks
  run: pixi run -e docs update-ghpages
  env:
    MF6_EXTENDED: "1"

- run: pixi run -e docs build-docs
```

The local `scripts/update_ghpages.py` workflow remains useful for contributors previewing changes, but notebook execution becomes part of the automated deploy pipeline.

---

## Considerations

### Support burden

Once the Linux/Mac extended artifacts exist in the release, users will eventually discover and use them directly regardless of documentation intent. A clear note in the nightly build repo (e.g. `CONTRIBUTING.md`) should explain that these artifacts are not promoted because a single binary cannot serve the full range of Linux distributions (glibc variation) or cover both Mac architectures — not because extended builds are unsupportable in principle, as `win64ext` demonstrates. Users should be directed to `install-modflow-action` as the supported access path and made aware that direct use on non-GitHub-Actions environments may encounter compatibility issues.

### Build reliability

Extended builds have significantly more dependencies than standard builds (PETSc, NetCDF, and optionally MPI). Linux and Mac extended build jobs will likely fail more often than the Windows counterpart. Recommendations:

- Mark extended Linux/Mac build jobs as `continue-on-error: true` or otherwise non-blocking on the overall nightly release, so a failed extended build does not delay standard binary availability
- Consider a separate release cadence or artifact channel if extended build failures become frequent

### Platform variants

"Multiple of each" could mean:

- **glibc targets**: a binary built against glibc 2.31 (Ubuntu 20.04 baseline) runs on any newer glibc but not older. If the nightly build CI uses Ubuntu 22.04, it won't run on older enterprise distros. This is unlikely to matter for GitHub Actions (`ubuntu-latest`) but worth noting.
- **Architecture**: `mac64armext` (Apple Silicon / `aarch64`) vs `mac64ext` (Intel / `x86_64`). GitHub Actions `macos-latest` now defaults to ARM, so both may eventually be needed.

The pragmatic starting point is one artifact per platform (`linux64ext`, `mac64ext`) targeting the same OS versions used by GitHub Actions runners, and expanding only if a concrete need arises.

### Where build responsibility lives

`modflow-devtools` and `install-modflow-action` provide the *download and installation* mechanism. The *build* responsibility stays with the `modflow6` / `modflow6-nightly-build` repo, which already owns the extended Windows build pipeline. This keeps concerns cleanly separated.

---

## Summary of Repository Changes

| Repo | Change |
|---|---|
| `modflow6-nightly-build` | Add `linux64ext` and `mac64ext` build jobs to CI matrix; upload artifacts to release; omit from release notes |
| `modflow-devtools` / `install-modflow-action` | Add `linux64ext`, `mac64ext`, `mac64armext` as supported `ostag` values; document as the canonical access path |
| `pyphoenix-project` (`extended-win.yml`) | Expand to cross-platform extended test matrix using `linux64ext` / `mac64ext`; retire as a Windows-only workflow |
| `pyphoenix-project` (`docs.yml`) | Add `install-modflow-action` step with `linux64ext`; run `update-ghpages` in CI before `build-docs` |
| `pyphoenix-project` (`scripts/update_ghpages.py`) | Unchanged — remains useful for local preview |
| Other `modflowpy` repos | Extended CI testing enabled on Linux/Mac by adding `install-modflow-action` step — no source build required |
