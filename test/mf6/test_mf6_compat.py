import os
import subprocess
import sys
import warnings

import pytest

from flopy4.mf6 import _compat
from flopy4.mf6._compat import _query_mf6_version, check_mf6_compatibility


class _FakeCompletedRun:
    def __init__(self, out):
        self._out = out

    def __call__(self, *args, **kwargs):
        return self._out


@pytest.mark.parametrize(
    "output, expected",
    [
        ("mf6: 6.7.0 02/05/2026", "6.7.0"),
        (" \nmf6: 6.7.0 02/05/2026\n \n", "6.7.0"),
        ("MODFLOW 6 VERSION 6.6.1 12/20/2024", "6.6.1"),
        ("mf6: 6.7.0.dev0", "6.7.0.dev0"),
        ("mf6: 6.7.0+g1a2b3c4", "6.7.0+g1a2b3c4"),
        ("mf6: 6.8.0.dev0+abc1234 10/01/2026", "6.8.0.dev0+abc1234"),
        ("mf6: 6.9.0.dev0+14b4a67.dirty 10/07/2026", "6.9.0.dev0+14b4a67.dirty"),
        ("no version here", None),
    ],
)
def test_query_mf6_version_parsing(monkeypatch, output, expected):
    monkeypatch.setattr(_compat.subprocess, "check_output", _FakeCompletedRun(output))
    assert _query_mf6_version("mf6") == expected


def test_query_mf6_version_swallows_errors(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("no such binary")

    monkeypatch.setattr(_compat.subprocess, "check_output", _boom)
    assert _query_mf6_version("mf6") is None


@pytest.fixture(autouse=True)
def no_commit(monkeypatch):
    """Tests assume a contract without a DFN commit unless they set one."""
    monkeypatch.setattr("flopy4.mf6._contract.DFN_COMMIT", None, raising=False)
    monkeypatch.setattr(_compat, "_versions", {})


@pytest.fixture
def exe(tmp_path):
    """An executable file for the check to resolve; tests fake its output."""
    path = tmp_path / "mf6"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


@pytest.mark.parametrize(
    "mf6_version, dfn_commit, binary, expected",
    [
        ("6.7.0", None, "6.7.0", False),
        ("6.7.0", None, "6.6.1", True),
        ("6.7.0", None, "6.7.0+abc1234", False),
        ("develop", None, "6.8.0.dev0+abc1234", None),
        ("develop", "abc1234def", "6.8.0.dev0+abc1234", False),
        ("develop", "abc1234def", "6.8.0.dev0+g0000000", True),
        ("develop", "abc1234def", "6.9.0.dev0+abc1234.dirty", False),
        ("develop", "abc1234def", "6.8.0.dev0", None),
        ("6.7.0", "abc1234def", "6.6.1", True),
    ],
)
def test_mismatch(mf6_version, dfn_commit, binary, expected):
    assert _compat._mismatch(mf6_version, dfn_commit, binary) is expected


def test_check_branch_commit_mismatch_warns(monkeypatch, exe):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "develop", raising=False)
    monkeypatch.setattr("flopy4.mf6._contract.DFN_COMMIT", "abc1234def", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.8.0.dev0+fff0000")
    with pytest.warns(UserWarning, match=r"develop \(abc1234\).*reports 6.8.0.dev0\+fff0000"):
        check_mf6_compatibility(exe=exe)


def test_check_skips_branch_name(monkeypatch, exe):
    """A branch-name sync (non-semver) must not warn about any binary."""
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "develop", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.7.0")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_mf6_compatibility(exe=exe)


def test_check_warns_on_unknown(monkeypatch, exe):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "unknown", raising=False)
    with pytest.warns(UserWarning, match="unknown MF6 version"):
        check_mf6_compatibility(exe=exe)


def test_check_matching_semver_is_quiet(monkeypatch, exe):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.7.0")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_mf6_compatibility(exe=exe)


def test_check_mismatched_semver_warns(monkeypatch, exe):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.6.1")
    with pytest.warns(UserWarning, match="reports 6.6.1"):
        check_mf6_compatibility(exe=exe)


def test_check_caches_version(monkeypatch, exe):
    """One process per binary, until the binary changes."""
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    calls = []
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda e: calls.append(e) or "6.7.0")
    check_mf6_compatibility(exe=exe)
    check_mf6_compatibility(exe=exe)
    assert len(calls) == 1
    os.utime(exe, ns=(0, 0))
    check_mf6_compatibility(exe=exe)
    assert len(calls) == 2


def test_check_missing_exe_is_quiet(monkeypatch, tmp_path):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_mf6_compatibility(exe=tmp_path / "nope")


@pytest.mark.skipif(sys.platform == "win32", reason="needs a shell script on PATH")
def test_import_does_not_query_binary(tmp_path):
    """Importing flopy4.mf6 doesn't run an mf6 on PATH."""
    marker = tmp_path / "ran"
    fake = tmp_path / "mf6"
    fake.write_text(f"#!/bin/sh\ntouch {marker}\necho 'mf6: 1.0.0'\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}
    subprocess.run([sys.executable, "-c", "import flopy4.mf6"], env=env, check=True)
    assert not marker.exists()


def test_run_checks_exe(monkeypatch, tmp_path):
    """Simulation.run checks the executable it runs, from the workspace."""
    from flopy4.mf6 import Simulation, simulation_methods

    checked = []
    monkeypatch.setattr(
        _compat, "check_mf6_compatibility", lambda exe: checked.append((exe, os.getcwd()))
    )
    monkeypatch.setattr(simulation_methods, "run_cmd", lambda exe, verbose: ("", "", 0))
    sim = Simulation(name="sim", workspace=tmp_path)
    sim.run(exe="bin/mf6")
    assert checked == [("bin/mf6", os.path.realpath(tmp_path))]


@pytest.mark.parametrize(
    "ostag, in_ci, expected_opts",
    [
        ("linux", False, ["--oversubscribe"]),
        ("linux", True, ["--oversubscribe"]),
        ("mac", False, ["--hostfile", "localhost"]),
        ("mac", True, ["--oversubscribe"]),
        ("win64", False, []),
        ("win64", True, []),
        ("win32", False, []),
        ("win32", True, []),
    ],
)
def test_run_parallel_command(monkeypatch, tmp_path, ostag, in_ci, expected_opts):
    """Simulation.run builds the right mpiexec invocation per platform, and
    cleans up the mac hostfile afterward."""
    from flopy4.mf6 import Simulation, simulation_methods

    monkeypatch.setattr(_compat, "check_mf6_compatibility", lambda exe: None)
    monkeypatch.setattr(simulation_methods, "get_ostag", lambda: ostag)
    monkeypatch.setattr(simulation_methods, "is_in_ci", lambda: in_ci)
    calls = []
    hostfile_contents_during_run = []

    def fake_run_cmd(*args, verbose):
        calls.append(args)
        hostfile = tmp_path / "localhost"
        hostfile_contents_during_run.append(hostfile.read_text() if hostfile.exists() else None)
        return "normal termination\n" * 2, "", 0

    monkeypatch.setattr(simulation_methods, "run_cmd", fake_run_cmd)
    sim = Simulation(name="sim", workspace=tmp_path)
    sim.run(exe="bin/mf6", ncpus=2)
    assert calls == [("mpiexec", *expected_opts, "-np", "2", "bin/mf6", "-p")]
    if ostag == "mac" and not in_ci:
        assert hostfile_contents_during_run == ["localhost slots=2\n"]
    else:
        assert hostfile_contents_during_run == [None]
    # the hostfile is cleaned up afterward, not left behind in the workspace
    assert not (tmp_path / "localhost").exists()


def test_run_parallel_requires_every_rank_to_succeed(monkeypatch, tmp_path):
    """A zero mpiexec return code isn't enough: every rank must report
    normal termination, since mpiexec can return 0 even if a rank failed.
    The failure message reports the rank count, not the (here misleadingly
    successful-looking) mpiexec return code."""
    from flopy4.mf6 import Simulation, simulation_methods

    monkeypatch.setattr(_compat, "check_mf6_compatibility", lambda exe: None)
    monkeypatch.setattr(simulation_methods, "get_ostag", lambda: "linux")
    monkeypatch.setattr(simulation_methods, "is_in_ci", lambda: True)
    monkeypatch.setattr(
        simulation_methods,
        "run_cmd",
        lambda *args, verbose: ("normal termination\n", "", 0),
    )
    sim = Simulation(name="sim", workspace=tmp_path)
    with pytest.raises(RuntimeError, match=r"1/2 ranks reported normal termination"):
        sim.run(exe="bin/mf6", ncpus=2)


def test_run_serial_failure_reports_return_code(monkeypatch, tmp_path):
    """For ncpus=1, the failure message reports the plain return code,
    since there's no per-rank count to report."""
    from flopy4.mf6 import Simulation, simulation_methods

    monkeypatch.setattr(_compat, "check_mf6_compatibility", lambda exe: None)
    monkeypatch.setattr(simulation_methods, "run_cmd", lambda exe, verbose: ("", "", 1))
    sim = Simulation(name="sim", workspace=tmp_path)
    with pytest.raises(RuntimeError, match=r"return code 1"):
        sim.run(exe="bin/mf6")


@pytest.mark.parametrize("ncpus", [0, -1])
def test_run_rejects_invalid_ncpus(tmp_path, ncpus):
    """ncpus must be a positive integer; 0 or negative must not silently
    fall back to a serial run."""
    from flopy4.mf6 import Simulation

    sim = Simulation(name="sim", workspace=tmp_path)
    with pytest.raises(ValueError, match="ncpus must be >= 1"):
        sim.run(exe="bin/mf6", ncpus=ncpus)
