import re
import shutil
import subprocess
import warnings
from pathlib import Path

_compat_checked = False

_MF6_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:\.\w+)?(?:\+[0-9a-f]+)?)")


class MF6VersionError(Exception):
    """Raised when an MF6 binary's version cannot be determined."""


def _query_mf6_version(exe: str | Path) -> str:
    """Run ``<exe> -v`` and return the first ``X.Y.Z`` version string found.

    Parameters
    ----------
    exe : str or Path
        Path to the MF6 executable.

    Raises
    ------
    MF6VersionError
        If the binary cannot be run or its output contains no version string.
    """
    try:
        result = subprocess.run(
            [str(exe), "-v"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
    except FileNotFoundError as e:
        raise MF6VersionError(f"Executable not found: {exe}") from e
    except PermissionError as e:
        raise MF6VersionError(f"Permission denied running {exe}") from e
    except subprocess.TimeoutExpired as e:
        raise MF6VersionError(f"Timed out querying version from {exe}") from e

    match = _MF6_VERSION_RE.search(output)
    if not match:
        raise MF6VersionError(
            f"Could not parse version from {exe} output:\n{output}"
        )
    return match.group(1)


def _check_mf6_compatibility() -> None:
    """Warn if the MF6 binary on PATH differs from the contract version.

    Idempotent — runs at most once per process. Silent when no MF6 binary
    is found or its version cannot be determined.
    """
    global _compat_checked
    if _compat_checked:
        return
    _compat_checked = True

    from flopy4.mf6._contract import MF6_CONTRACT_VERSION

    exe = shutil.which("mf6")
    if exe is None:
        return

    try:
        binary_version = _query_mf6_version(exe)
    except MF6VersionError:
        return

    if binary_version != MF6_CONTRACT_VERSION:
        warnings.warn(
            f"flopy4 is synced to MF6 {MF6_CONTRACT_VERSION} "
            f"but the discovered binary reports {binary_version}. "
            f"Run `flopy4 sync` to regenerate classes for MF6 {binary_version}.",
            UserWarning,
            stacklevel=2,
        )
