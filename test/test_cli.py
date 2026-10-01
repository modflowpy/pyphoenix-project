from pathlib import Path

from flopy4.cli import _local_mf6_version


def _dfn_dir(root: Path) -> Path:
    dfn = root / "modflow6" / "doc" / "mf6io" / "mf6ivar" / "dfn"
    dfn.mkdir(parents=True)
    return dfn


def test_local_mf6_version_from_checkout(tmp_path):
    """DFNs in a modflow6 checkout get the checkout's version.txt."""
    dfn = _dfn_dir(tmp_path)
    (tmp_path / "modflow6" / "version.txt").write_text("6.9.0.dev0\n")
    assert _local_mf6_version(dfn) == "6.9.0.dev0"


def test_local_mf6_version_override(tmp_path):
    """An explicit --mf6-version wins over version.txt."""
    dfn = _dfn_dir(tmp_path)
    (tmp_path / "modflow6" / "version.txt").write_text("6.9.0.dev0\n")
    assert _local_mf6_version(dfn, "develop") == "develop"


def test_local_mf6_version_unknown(tmp_path):
    """No checkout or no version.txt: unknown, not an error."""
    assert _local_mf6_version(tmp_path) == "unknown"
    assert _local_mf6_version(_dfn_dir(tmp_path)) == "unknown"
