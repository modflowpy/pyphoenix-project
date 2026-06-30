"""
Smoke tests for docs/profile scripts.

Fast tests (no external model data) run unconditionally with --runs 1.
Tests requiring large model data are skipped unless MODFLOW6_LARGE_MODELS is set.

Run from the repo root:
    pixi run -e dev pytest docs/profile/test_profile_scripts.py -v

Or with large-model tests:
    MODFLOW6_LARGE_MODELS=/path/to/modflow6-largetestmodels \
        pixi run -e dev pytest docs/profile/test_profile_scripts.py -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
PYTHON = sys.executable
MODELS_ROOT = os.environ.get("MODFLOW6_LARGE_MODELS")


def run(script: str, args: list[str] = ()) -> subprocess.CompletedProcess:
    cmd = [PYTHON, str(HERE / script)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def assert_ok(result: subprocess.CompletedProcess, label: str = "") -> None:
    assert result.returncode == 0, f"{label}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


# ── Fast tests (no external deps) ───────────────────────────────────────────


def test_ff_write_basic():
    assert_ok(run("ff_write.py", ["--runs", "1"]))


def test_ff_read_basic():
    """ff_read.py exits 0 whether or not binary output files are present."""
    assert_ok(run("ff_read.py", ["--runs", "1"]))


def test_ff_read_memory():
    assert_ok(run("ff_read.py", ["--runs", "1", "--memory"]))


def test_chunked_profile_basic():
    assert_ok(run("chunked_profile.py", ["--runs", "1", "--small"]))


def test_chunked_profile_memory():
    assert_ok(run("chunked_profile.py", ["--runs", "1", "--small", "--memory"]))


def test_ff_write_flopy4_only():
    assert_ok(run("ff_write.py", ["--runs", "1", "--flopy4-only"]))


def test_ff_write_profile():
    assert_ok(run("ff_write.py", ["--runs", "1", "--profile"]))


def test_diag_list_scaling():
    assert_ok(run("diag_list_scaling.py"))


def test_run_all_ff_only():
    """run_all.py with --only ff_write.py should succeed without --models-root."""
    assert_ok(run("run_all.py", ["--only", "ff_write.py", "--runs", "1"]))


def test_run_all_flopy4_only():
    assert_ok(run("run_all.py", ["--only", "ff_write.py", "--runs", "1", "--flopy4-only"]))


def test_run_all_skip_large():
    """run_all.py without --models-root should skip large scripts and exit 0."""
    result = run("run_all.py", ["--runs", "1"])
    assert_ok(result, "run_all without models-root")
    assert "[SKIP]" in result.stdout or "ff_write" in result.stdout


# ── Large-model tests (skipped unless MODFLOW6_LARGE_MODELS is set) ─────────

requires_models = pytest.mark.skipif(
    MODELS_ROOT is None,
    reason="MODFLOW6_LARGE_MODELS env var not set (path to modflow6-largetestmodels repo)",
)


@requires_models
def test_test1000_scenario1_only():
    assert_ok(
        run(
            "test1000_write.py",
            ["--runs", "1", "--models-root", MODELS_ROOT, "--scenarios", "1"],
        )
    )


@requires_models
def test_test1000_flopy4_only():
    assert_ok(
        run(
            "test1000_write.py",
            ["--runs", "1", "--models-root", MODELS_ROOT, "--flopy4-only", "--scenarios", "1"],
        )
    )


@requires_models
def test_test1000_profile():
    assert_ok(
        run(
            "test1000_write.py",
            ["--runs", "1", "--models-root", MODELS_ROOT, "--scenarios", "1", "--profile"],
        )
    )


@requires_models
def test_test1005_flopy4_only():
    assert_ok(
        run(
            "test1005_write.py",
            ["--runs", "1", "--models-root", MODELS_ROOT, "--flopy4-only"],
        )
    )


@requires_models
def test_test1005_profile():
    assert_ok(
        run(
            "test1005_write.py",
            ["--runs", "1", "--models-root", MODELS_ROOT, "--profile"],
        )
    )
