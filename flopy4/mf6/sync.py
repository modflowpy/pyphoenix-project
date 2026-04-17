import os
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings(
    "ignore", message=".*modflow_devtools.dfns.*experimental.*"
)
warnings.filterwarnings(
    "ignore", message=".*modflow_devtools.programs.*experimental.*"
)

from modflow_devtools.dfns import RemoteDfnRegistry  # noqa: E402
from modflow_devtools.models import copy_to  # noqa: E402
from modflow_devtools.programs import install_program  # noqa: E402

from flopy4.mf6._compat import MF6VersionError, _query_mf6_version  # noqa: E402

_MF6_PACKAGE_DIR = Path(__file__).parent
"""flopy4/mf6/ — the install location for generated files."""

_GRAMMAR_GEN_DIR = (
    _MF6_PACKAGE_DIR / "codec" / "reader" / "grammar" / "generated"
)
"""Where generated Lark grammars live."""

_SMOKE_TEST_MODEL = "mf6/test/test001a_Tharmonic"
"""Small steady-state GWF model used as the sync smoke test."""


class SyncError(Exception):
    """Raised when sync() cannot complete (e.g. read-only install location)."""


@dataclass
class SyncResult:
    """Result of a successful sync() call."""

    version: str
    exes: list[Path]
    validated: bool = False


def _check_install_writable() -> None:
    """Raise SyncError if the flopy4/mf6 package directory is not writable."""
    if not _MF6_PACKAGE_DIR.is_dir() or not os.access(_MF6_PACKAGE_DIR, os.W_OK):
        raise SyncError(
            f"flopy4 is installed to a read-only location ({_MF6_PACKAGE_DIR}).\n"
            "Install into a virtual environment and try again, or use\n"
            "`pip install --user flopy4` for a user-writable install."
        )


def _generate_classes(registry, outdir: Path) -> None:
    """Regenerate Lark grammars from *registry* into *outdir*."""
    from flopy4.mf6.codec.reader.dfn2lark import generate

    files_dir = registry._files_dir
    if files_dir is None or not files_dir.exists():
        raise SyncError(
            "Registry files directory not found. "
            "Call registry.sync() before _generate_classes()."
        )
    grammar_dir = outdir / "codec" / "reader" / "grammar" / "generated"
    generate(files_dir, grammar_dir)


def _write_contract(
    outdir: Path,
    *,
    version: str,
    dfn_schema: str,
) -> None:
    """Write _contract.py into *outdir*."""
    contract_path = outdir / "_contract.py"
    contract_path.write_text(
        "# written by sync(), committed, never edited by hand\n"
        f'MF6_CONTRACT_VERSION = "{version}"\n'
        f'MF6_DFN_SCHEMA_VERSION = "{dfn_schema}"\n'
    )


def _run_smoke_test(exe: Path) -> None:
    """Copy a small example model to a temp dir and run the MF6 binary in it.

    Raises
    ------
    SyncError
        If the model files cannot be copied or the binary exits non-zero.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workspace = copy_to(tmp, _SMOKE_TEST_MODEL)
        if workspace is None:
            raise SyncError(
                f"Smoke-test model '{_SMOKE_TEST_MODEL}' could not be copied. "
                "Ensure the modflow_devtools model registry is populated."
            )
        result = subprocess.run(
            [str(exe)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )

    if result.returncode != 0:
        raise SyncError(
            f"Smoke test failed (exit {result.returncode}).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def sync(
    version: str | None = None,
    bindir: Path | None = None,
    validate: bool = False,
) -> SyncResult:
    """Sync flopy4 to a specific MF6 version.

    Installs the MF6 binary, fetches matching DFNs, and regenerates
    Lark grammars in the installed package directory.
    If *version* is omitted, syncs to the version of the discovered binary.
    If *validate* is True, runs a small example model with the installed
    binary after regenerating classes and raises SyncError on failure.
    """
    if version is None:
        exe = shutil.which("mf6")
        if exe is None:
            raise SyncError(
                "No MF6 binary found on PATH and no version specified. "
                "Provide --version or install MF6 first."
            )
        try:
            version = _query_mf6_version(exe)
        except MF6VersionError as e:
            raise SyncError(f"Could not determine MF6 version: {e}") from e

    _check_install_writable()

    # 1. install binary
    exes = install_program("mf6", version=version, bindir=bindir)

    # 2. query the installed binary — this is the source of truth for the contract
    try:
        contract_version = _query_mf6_version(exes[0])
    except MF6VersionError as e:
        raise SyncError(f"Could not determine version of installed binary: {e}") from e

    # 3. fetch DFNs for the same ref
    registry = RemoteDfnRegistry(ref=version)
    registry.sync()

    # 4. regenerate grammars in-place
    _generate_classes(registry, outdir=_MF6_PACKAGE_DIR)

    # 5. update contract
    _write_contract(
        _MF6_PACKAGE_DIR,
        version=contract_version,
        dfn_schema=str(registry.schema_version),
    )

    # reset the once-flag so the next Simulation() triggers a fresh check
    import flopy4.mf6._compat as _compat
    _compat._compat_checked = False

    if validate:
        _run_smoke_test(exes[0])

    return SyncResult(version=contract_version, exes=exes, validated=validate)


def status() -> dict:
    """Return a dict with contract version and discovered binary version."""
    from flopy4.mf6._contract import (
        MF6_CONTRACT_VERSION,
        MF6_DFN_SCHEMA_VERSION,
    )

    exe = shutil.which("mf6")
    binary_version: str | None = None
    if exe is not None:
        try:
            binary_version = _query_mf6_version(exe)
        except MF6VersionError:
            pass

    return {
        "contract_version": MF6_CONTRACT_VERSION,
        "dfn_schema_version": MF6_DFN_SCHEMA_VERSION,
        "binary_version": binary_version,
        "binary_path": exe,
        "in_sync": binary_version == MF6_CONTRACT_VERSION if binary_version else None,
    }
