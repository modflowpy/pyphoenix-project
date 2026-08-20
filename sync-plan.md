# Ecosystem Sync Plan

## Motivation

The version compatibility contract between flopy and MF6 is currently implicit. Users must manually coordinate `generate_classes` (syncs flopy to a specific MF6 DFN version) and `get-modflow` (installs a specific MF6 binary), with no enforcement or visibility into whether the two are aligned. Flopy and MF6 must be released in lockstep for users to get a coherent combination.

The motivation here is to make the contract explicit, so a user can determine whether the flopy mf6 module is compatible with a given binary.

## Design

### Contract

An auto-generated file e.g. `_contract.py` can contain the version contract.

```python
# flopy4/mf6/_contract.py
MF6_VERSION = "6.7.0"
MF6_VERSION   = "6.8.0.dev0+abc1234"  # or development version including +shortsha suffix
DFN_SCHEMA_VERSION = "2.0.0.dev1"
```

```python
# flopy4/mf6/__init__.py
from flopy4.mf6._contract import MF6_VERSION, DFN_SCHEMA_VERSION
```

This can be read at import time in order to compare against the version string emitted by an MF6 executable. If the reported version doesn't match `MF6_CONTRACT_VERSION`, a warning can be shown or an error raised. For instance:

```python
def _check_mf6_compatibility():
    exe = shutil.which("mf6")
    if exe is None:
        return
    binary_version = _query_mf6_version(exe)   # subprocess: mf6 -v, parse stdout
    if binary_version != MF6_CONTRACT_VERSION:
        warnings.warn(
            f"flopy4.mf6 is synced to MF6 {MF6_CONTRACT_VERSION} "
            f"but the discovered executable is {binary_version}. "
            f"Run `flopy4 mf6 sync` to sync to {binary_version}.",
            UserWarning,
            stacklevel=2,
        )
```

### CLI

The main UX can be a single `flopy mf6 sync [version]` command. By default, this can sync to an MF6 discovered on the path, or installing the latest if none is available. Custom versions can also be requested. After installing an executable and obtaining the corresponding DFNs, the sync command regenerates the `flopy4.mf6` module, including `_contract.py`.

```shell
flopy4 mf6 sync  # sync to discovered binary's version, or get latest if no binary found
flopy4 mf6 sync 6.6.0  # sync to a specific MF6 release
flopy4 mf6 sync develop  # sync to MF6 develop branch
flopy4 mf6 status  # show discovered mf6 and sync status
```

## Prerequisites

A function to get an mf6 executable's version string by calling `mf6 -v`. Capture the full version string including any `+shortsha` suffix.

Probably more I haven't thought of yet.

## Questions

Should we always use the DFNs API to retrieve DFNs? Or get them from the MF6 distribution when we install MF6? Seems cleaner to always use the API (see recent work we've done on streamlining it, see dfns.md in the docs) but it might be wasteful, since the DFNs will be included in distributions going forward.

