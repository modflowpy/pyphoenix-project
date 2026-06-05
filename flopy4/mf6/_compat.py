import re
import shutil
import subprocess
import warnings

_VERSION_RE = re.compile(r"(?:version\s+|mf6:\s+)([\d]+\.[\d]+\.[\d]+(?:\.\S+)?)", re.I)


def _query_mf6_version(exe: str) -> str | None:
    try:
        out = subprocess.check_output([exe, "-v"], text=True, stderr=subprocess.STDOUT)
        m = _VERSION_RE.search(out)
        return m.group(1) if m else None
    except Exception:
        return None


def check_mf6_compatibility(exe: str | None = None) -> None:
    """Warn if a discovered MF6 binary doesn't match the synced version.

    Does nothing when the synced version is ``"unknown"`` or a branch
    name (non-semver).

    Parameters
    ----------
    exe :
        Path to an MF6 executable. If None, searches PATH for ``mf6``
        or ``mf6.exe``. Does nothing if no binary is found.
    """
    from flopy4.mf6._contract import MF6_VERSION

    # Skip if version is unknown or a branch name rather than a semver tag.
    if not MF6_VERSION or MF6_VERSION == "unknown":
        warnings.warn(
            "flopy4.mf6 is synced to an unknown MF6 version. Run `flopy4 mf6 sync` to re-sync.",
            UserWarning,
            stacklevel=3,
        )
        return

    if exe is None:
        exe = shutil.which("mf6") or shutil.which("mf6.exe")
    if exe is None:
        return

    binary_version = _query_mf6_version(exe)
    if binary_version is None or binary_version == MF6_VERSION:
        return

    warnings.warn(
        f"flopy4.mf6 is synced to MF6 {MF6_VERSION} but the binary at '{exe}' "
        f"reports {binary_version}. Run `flopy4 mf6 sync` to re-sync.",
        UserWarning,
        stacklevel=3,
    )
