import os
import re
import shutil
import subprocess
import warnings
from os import PathLike

_VERSION_RE = re.compile(r"(?:version\s+|mf6:\s+)(\d+\.\d+\.\d+(?:\.[^\s+]+)?(?:\+\S+)?)", re.I)
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")


def _query_mf6_version(exe: str) -> str | None:
    """The version an MF6 binary reports with ``-v``, including any
    ``+<shortsha>`` suffix a development build carries."""
    try:
        out = subprocess.check_output([exe, "-v"], text=True, stderr=subprocess.STDOUT)
        m = _VERSION_RE.search(out)
        return None if m is None else m.group(1)
    except Exception:
        return None


# Versions reported by binaries, by resolved path and modification time,
# so a check per run doesn't start a process each time.
_versions: dict[tuple[str, int], str | None] = {}


def _binary_version(exe: str) -> str | None:
    """``_query_mf6_version`` for a resolved executable path, cached."""
    key = (exe, os.stat(exe).st_mtime_ns)
    if key not in _versions:
        _versions[key] = _query_mf6_version(exe)
    return _versions[key]


def _split_version(version: str) -> tuple[str, str | None]:
    """Split ``6.8.0.dev0+abc1234`` into the base version and the commit
    (``"6.8.0.dev0"``, ``"abc1234"``). A ``git describe``-style ``g``
    prefix and a ``.dirty`` suffix on the commit are dropped. The commit
    is None for a release."""
    base, _, local = version.partition("+")
    commit = local.split(".")[0]
    if commit.startswith("g"):
        commit = commit[1:]
    return base, commit or None


def _mismatch(mf6_version: str, dfn_commit: str | None, binary_version: str) -> bool | None:
    """Whether a binary's version contradicts the contract, or None if
    there's nothing to compare.

    If both the contract and the binary name a commit, compare commits.
    Otherwise compare base versions, when the contract has one (a branch
    name like ``"develop"`` doesn't).
    """
    base, commit = _split_version(binary_version)
    if commit is not None and dfn_commit is not None:
        return not dfn_commit.startswith(commit)
    if not _SEMVER_RE.match(mf6_version):
        return None
    return _split_version(mf6_version)[0] != base


def check_mf6_compatibility(exe: str | PathLike | None = None) -> None:
    """Warn if an MF6 binary doesn't match the version flopy4.mf6 is
    synced to, or if that version is unknown.

    ``Simulation.run`` calls this for the executable it runs. Does
    nothing when the synced version is a branch name and the binary
    doesn't report a commit to compare.

    Parameters
    ----------
    exe :
        An MF6 executable: a name to look up on PATH, or a path, relative
        to the working directory. If None, looks up ``mf6`` or ``mf6.exe``.
        Does nothing if it isn't found.
    """
    from flopy4.mf6 import _contract

    mf6_version = _contract.MF6_VERSION
    dfn_commit = getattr(_contract, "DFN_COMMIT", None)

    if not mf6_version or mf6_version == "unknown":
        warnings.warn(
            "flopy4.mf6 is synced to an unknown MF6 version. Run `flopy4 mf6 sync` to re-sync.",
            UserWarning,
            stacklevel=3,
        )
        return

    # A branch-name contract with no commit has nothing to compare against.
    if dfn_commit is None and not _SEMVER_RE.match(mf6_version):
        return

    if exe is None:
        exe = shutil.which("mf6") or shutil.which("mf6.exe")
    else:
        exe = shutil.which(os.fspath(exe))
    if exe is None:
        return

    binary_version = _binary_version(exe)
    if binary_version is None or not _mismatch(mf6_version, dfn_commit, binary_version):
        return

    synced = mf6_version if dfn_commit is None else f"{mf6_version} ({dfn_commit[:7]})"
    warnings.warn(
        f"flopy4.mf6 is synced to MF6 {synced} but the binary at '{exe}' "
        f"reports {binary_version}. Run `flopy4 mf6 sync` to re-sync.",
        UserWarning,
        stacklevel=3,
    )
