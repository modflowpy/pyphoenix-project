import sys
from pathlib import Path

import pytest

import flopy4.mf6
from flopy4 import cli
from flopy4.mf6._sync import SyncResult, _resolve_release_id, sync


def _read_contract(outdir: Path) -> dict:
    ns: dict = {}
    exec((outdir / "_contract.py").read_text(), ns)
    return ns


def test_exported():
    assert flopy4.mf6.sync is sync
    assert flopy4.mf6.SyncResult is SyncResult


def test_sync_local_all_packages(dfn_path, tmp_path):
    """A local sync generates every component and writes the contract."""
    result = sync(dfn_path, mf6_version="6.9.0", all_packages=True, outdir=tmp_path)
    assert result.version == "6.9.0"
    assert result.source == str(dfn_path)
    assert result.outdir == tmp_path.resolve()
    assert result.files
    assert all(f.is_file() and f.is_relative_to(result.outdir) for f in result.files)
    contract = _read_contract(tmp_path)
    assert contract["MF6_VERSION"] == "6.9.0"
    assert contract["DFN_SCHEMA_VERSION"]


def test_sync_local_existing_only(dfn_path, tmp_path):
    """Without all_packages, an empty outdir gets only the contract."""
    result = sync(dfn_path, mf6_version="6.9.0", outdir=tmp_path)
    assert result.files == ()
    assert [p.name for p in tmp_path.iterdir()] == ["_contract.py"]


def test_sync_local_unknown_version_warns(dfn_path, tmp_path):
    """DFNs outside a modflow6 checkout have no version.txt to read."""
    local = tmp_path / "dfn"
    local.mkdir()
    for f in dfn_path.glob("*.dfn"):
        (local / f.name).write_text(f.read_text())
    with pytest.warns(UserWarning, match="MF6 version is unknown"):
        result = sync(local, outdir=tmp_path / "out")
    assert result.version == "unknown"


def test_sync_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        sync(tmp_path / "nope", outdir=tmp_path)
    with pytest.raises(FileNotFoundError):
        sync("./nope/dfn", outdir=tmp_path)


def test_sync_bad_release_id(tmp_path):
    with pytest.raises(ValueError, match="owner/repo@ref"):
        sync("modflow6@develop", outdir=tmp_path)


def test_sync_exe_not_supported(tmp_path):
    with pytest.raises(NotImplementedError, match="--spec"):
        sync(exe="mf6", outdir=tmp_path)
    with pytest.raises(ValueError, match="not both"):
        sync("develop", exe="mf6", outdir=tmp_path)


def test_resolve_release_id():
    assert _resolve_release_id("6.6.0") == "MODFLOW-ORG/modflow6@6.6.0"
    assert _resolve_release_id("me/modflow6@develop") == "me/modflow6@develop"


def test_cli_wraps_sync(monkeypatch, tmp_path, capsys):
    """The CLI passes its arguments through to sync()."""
    calls = []

    def fake_sync(source, **kwargs):
        calls.append((source, kwargs))
        return SyncResult(version="6.6.0", source="x", outdir=tmp_path, files=(tmp_path,))

    monkeypatch.setattr("flopy4.mf6._sync.sync", fake_sync)
    monkeypatch.setattr(
        sys, "argv", ["flopy4", "mf6", "sync", "6.6.0", "--all-packages", "--force"]
    )
    cli.main()
    assert calls == [
        (
            "6.6.0",
            {"mf6_version": None, "all_packages": True, "force": True, "verbose": False},
        )
    ]
    out = capsys.readouterr().out
    assert "Generated 1 component modules" in out
    assert "MF6 version: 6.6.0" in out
