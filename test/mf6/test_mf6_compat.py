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
        ("mf6: 6.7.0+g1a2b3c4", "6.7.0"),
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


def test_check_skips_branch_name(monkeypatch):
    """A branch-name sync (non-semver) must not warn about any binary."""
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "develop", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.7.0")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_mf6_compatibility(exe="mf6")


def test_check_warns_on_unknown(monkeypatch):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "unknown", raising=False)
    with pytest.warns(UserWarning, match="unknown MF6 version"):
        check_mf6_compatibility(exe="mf6")


def test_check_matching_semver_is_quiet(monkeypatch):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.7.0")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_mf6_compatibility(exe="mf6")


def test_check_mismatched_semver_warns(monkeypatch):
    monkeypatch.setattr("flopy4.mf6._contract.MF6_VERSION", "6.7.0", raising=False)
    monkeypatch.setattr(_compat, "_query_mf6_version", lambda exe: "6.6.1")
    with pytest.warns(UserWarning, match="reports 6.6.1"):
        check_mf6_compatibility(exe="mf6")
