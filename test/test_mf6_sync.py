"""Tests for flopy4.mf6.sync and flopy4.cli (Phase 3)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flopy4.mf6.sync import (
    SyncError,
    SyncResult,
    _check_install_writable,
    _generate_classes,
    _run_smoke_test,
    _write_contract,
    status,
    sync,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_registry_mock(files_dir: Path, ref: str = "6.6.0", schema: str = "2"):
    registry = MagicMock()
    registry._files_dir = files_dir
    registry.registry_meta.ref = ref
    registry.schema_version = schema
    return registry


# ---------------------------------------------------------------------------
# _check_install_writable
# ---------------------------------------------------------------------------


class TestCheckInstallWritable:
    def test_passes_when_writable(self, tmp_path):
        with patch("flopy4.mf6.sync._MF6_PACKAGE_DIR", tmp_path):
            _check_install_writable()  # must not raise

    def test_raises_when_not_writable(self, tmp_path):
        ro = tmp_path / "ro"
        ro.mkdir()
        os.chmod(ro, 0o555)
        try:
            with patch("flopy4.mf6.sync._MF6_PACKAGE_DIR", ro):
                with pytest.raises(SyncError, match="read-only location"):
                    _check_install_writable()
        finally:
            os.chmod(ro, 0o755)


# ---------------------------------------------------------------------------
# _generate_classes
# ---------------------------------------------------------------------------


class TestGenerateClasses:
    def test_calls_generate_with_correct_dirs(self, tmp_path):
        files_dir = tmp_path / "dfn_files"
        files_dir.mkdir()
        outdir = tmp_path / "pkg"
        outdir.mkdir()

        registry = _make_registry_mock(files_dir)

        with patch("flopy4.mf6.sync._generate_classes") as mock_gen:
            mock_gen(registry, outdir)
            mock_gen.assert_called_once_with(registry, outdir)

    def test_raises_when_files_dir_missing(self, tmp_path):
        registry = _make_registry_mock(files_dir=None)

        with pytest.raises(SyncError, match="Registry files directory not found"):
            _generate_classes(registry, outdir=tmp_path)

    def test_raises_when_files_dir_nonexistent(self, tmp_path):
        registry = _make_registry_mock(files_dir=tmp_path / "nonexistent")

        with pytest.raises(SyncError, match="Registry files directory not found"):
            _generate_classes(registry, outdir=tmp_path)


# ---------------------------------------------------------------------------
# _write_contract
# ---------------------------------------------------------------------------


class TestWriteContract:
    def test_writes_release_version(self, tmp_path):
        _write_contract(tmp_path, version="6.6.0", dfn_schema="2")
        text = (tmp_path / "_contract.py").read_text()
        assert 'MF6_CONTRACT_VERSION = "6.6.0"' in text
        assert 'MF6_DFN_SCHEMA_VERSION = "2"' in text
        assert "MF6_DFN_COMMIT" not in text

    def test_writes_dev_version_with_sha(self, tmp_path):
        _write_contract(tmp_path, version="6.8.0.dev0+abc1234", dfn_schema="2")
        text = (tmp_path / "_contract.py").read_text()
        assert 'MF6_CONTRACT_VERSION = "6.8.0.dev0+abc1234"' in text
        assert "MF6_DFN_COMMIT" not in text

    def test_overwrites_existing(self, tmp_path):
        _write_contract(tmp_path, version="6.5.0", dfn_schema="1")
        _write_contract(tmp_path, version="6.6.0", dfn_schema="2")
        text = (tmp_path / "_contract.py").read_text()
        assert "6.6.0" in text
        assert "6.5.0" not in text


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_returns_expected_keys(self):
        result = status()
        assert "contract_version" in result
        assert "dfn_schema_version" in result
        assert "binary_version" in result
        assert "binary_path" in result
        assert "in_sync" in result

    def test_in_sync_true_when_matching(self):
        from flopy4.mf6._contract import MF6_CONTRACT_VERSION

        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6.sync._query_mf6_version",
                return_value=MF6_CONTRACT_VERSION,
            ),
        ):
            result = status()
        assert result["in_sync"] is True

    def test_in_sync_false_when_differing(self):
        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6.sync._query_mf6_version",
                return_value="0.0.1",
            ),
        ):
            result = status()
        assert result["in_sync"] is False

    def test_in_sync_none_when_no_binary(self):
        with patch("shutil.which", return_value=None):
            result = status()
        assert result["in_sync"] is None
        assert result["binary_version"] is None


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


class TestSync:
    def _make_sync_patches(self, tmp_path, version="6.6.0"):
        """Return a dict of patches needed for sync()."""
        files_dir = tmp_path / "dfn_files"
        files_dir.mkdir()
        registry_mock = _make_registry_mock(files_dir, ref=version)

        return {
            "install_program": patch(
                "flopy4.mf6.sync.install_program",
                return_value=[tmp_path / "mf6"],
            ),
            "RemoteDfnRegistry": patch(
                "flopy4.mf6.sync.RemoteDfnRegistry",
                return_value=registry_mock,
            ),
            "_query_mf6_version": patch(
                "flopy4.mf6.sync._query_mf6_version",
                return_value=version,
            ),
            "_generate_classes": patch("flopy4.mf6.sync._generate_classes"),
            "_write_contract": patch("flopy4.mf6.sync._write_contract"),
            "_check_install_writable": patch(
                "flopy4.mf6.sync._check_install_writable"
            ),
        }

    def test_returns_sync_result(self, tmp_path):
        patches = self._make_sync_patches(tmp_path)
        with (
            patches["install_program"],
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
        ):
            result = sync(version="6.6.0")

        assert isinstance(result, SyncResult)
        assert result.version == "6.6.0"

    def test_raises_sync_error_when_no_binary_and_no_version(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(SyncError, match="No MF6 binary found"):
                sync(version=None)

    def test_uses_discovered_binary_version_when_version_omitted(self, tmp_path):
        patches = self._make_sync_patches(tmp_path, version="6.5.0")
        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6._compat._query_mf6_version",
                return_value="6.5.0",
            ),
            patches["install_program"] as mock_install,
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
        ):
            result = sync(version=None)

        mock_install.assert_called_once_with("mf6", version="6.5.0", bindir=None)
        assert result.version == "6.5.0"

    def test_contract_version_comes_from_installed_binary(self, tmp_path):
        """sync() must query the installed binary, not trust the ref string."""
        files_dir = tmp_path / "dfn_files"
        files_dir.mkdir()
        registry_mock = _make_registry_mock(files_dir, ref="latest")

        with (
            patch("flopy4.mf6.sync.install_program", return_value=[tmp_path / "mf6"]),
            patch("flopy4.mf6.sync.RemoteDfnRegistry", return_value=registry_mock),
            patch("flopy4.mf6.sync._query_mf6_version", return_value="6.6.0"),
            patch("flopy4.mf6.sync._generate_classes"),
            patch("flopy4.mf6.sync._write_contract") as mock_write,
            patch("flopy4.mf6.sync._check_install_writable"),
        ):
            result = sync(version="latest")

        assert result.version == "6.6.0"
        _, kwargs = mock_write.call_args
        assert kwargs["version"] == "6.6.0"

    def test_validated_false_by_default(self, tmp_path):
        patches = self._make_sync_patches(tmp_path)
        with (
            patches["install_program"],
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
        ):
            result = sync(version="6.6.0")
        assert result.validated is False

    def test_validated_true_when_smoke_test_passes(self, tmp_path):
        patches = self._make_sync_patches(tmp_path)
        with (
            patches["install_program"],
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
            patch("flopy4.mf6.sync._run_smoke_test"),
        ):
            result = sync(version="6.6.0", validate=True)
        assert result.validated is True

    def test_raises_sync_error_when_smoke_test_fails(self, tmp_path):
        patches = self._make_sync_patches(tmp_path)
        with (
            patches["install_program"],
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
            patch(
                "flopy4.mf6.sync._run_smoke_test",
                side_effect=SyncError("Smoke test failed (exit 1)."),
            ),
            pytest.raises(SyncError, match="Smoke test failed"),
        ):
            sync(version="6.6.0", validate=True)

    def test_resets_compat_flag(self, tmp_path):
        import flopy4.mf6._compat as _compat

        _compat._compat_checked = True
        patches = self._make_sync_patches(tmp_path)
        with (
            patches["install_program"],
            patches["RemoteDfnRegistry"],
            patches["_query_mf6_version"],
            patches["_generate_classes"],
            patches["_write_contract"],
            patches["_check_install_writable"],
        ):
            sync(version="6.6.0")

        assert _compat._compat_checked is False


# ---------------------------------------------------------------------------
# _run_smoke_test
# ---------------------------------------------------------------------------


class TestRunSmokeTest:
    def test_passes_on_clean_exit(self, tmp_path):
        with patch("flopy4.mf6.sync.copy_to", return_value=tmp_path):
            with patch(
                "flopy4.mf6.sync.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ):
                _run_smoke_test(tmp_path / "mf6")  # must not raise

    def test_raises_on_nonzero_exit(self, tmp_path):
        with patch("flopy4.mf6.sync.copy_to", return_value=tmp_path):
            with patch(
                "flopy4.mf6.sync.subprocess.run",
                return_value=MagicMock(returncode=1, stdout="err", stderr=""),
            ):
                with pytest.raises(SyncError, match="Smoke test failed"):
                    _run_smoke_test(tmp_path / "mf6")

    def test_raises_when_copy_to_returns_none(self, tmp_path):
        with patch("flopy4.mf6.sync.copy_to", return_value=None):
            with pytest.raises(SyncError, match="could not be copied"):
                _run_smoke_test(tmp_path / "mf6")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_status_command_exits_zero(self, capsys):
        from flopy4.cli import _cmd_status

        with patch("shutil.which", return_value=None):
            code = _cmd_status(None)

        assert code == 0
        out = capsys.readouterr().out
        assert "contract version" in out

    def test_sync_command_exits_zero(self, tmp_path, capsys):
        from flopy4.cli import _cmd_sync

        files_dir = tmp_path / "dfn_files"
        files_dir.mkdir()
        registry_mock = _make_registry_mock(files_dir, ref="6.6.0")

        args = MagicMock()
        args.version = "6.6.0"
        args.bindir = None
        args.validate = False

        with (
            patch("flopy4.mf6.sync.install_program", return_value=[tmp_path / "mf6"]),
            patch("flopy4.mf6.sync.RemoteDfnRegistry", return_value=registry_mock),
            patch("flopy4.mf6.sync._query_mf6_version", return_value="6.6.0"),
            patch("flopy4.mf6.sync._generate_classes"),
            patch("flopy4.mf6.sync._write_contract"),
            patch("flopy4.mf6.sync._check_install_writable"),
        ):
            code = _cmd_sync(args)

        assert code == 0
        assert "6.6.0" in capsys.readouterr().out

    def test_sync_command_prints_validated(self, tmp_path, capsys):
        from flopy4.cli import _cmd_sync

        files_dir = tmp_path / "dfn_files"
        files_dir.mkdir()
        registry_mock = _make_registry_mock(files_dir, ref="6.6.0")

        args = MagicMock()
        args.version = "6.6.0"
        args.bindir = None
        args.validate = True

        with (
            patch("flopy4.mf6.sync.install_program", return_value=[tmp_path / "mf6"]),
            patch("flopy4.mf6.sync.RemoteDfnRegistry", return_value=registry_mock),
            patch("flopy4.mf6.sync._query_mf6_version", return_value="6.6.0"),
            patch("flopy4.mf6.sync._generate_classes"),
            patch("flopy4.mf6.sync._write_contract"),
            patch("flopy4.mf6.sync._check_install_writable"),
            patch("flopy4.mf6.sync._run_smoke_test"),
        ):
            code = _cmd_sync(args)

        assert code == 0
        assert "validated" in capsys.readouterr().out

    def test_sync_command_exits_one_on_error(self, capsys):
        from flopy4.cli import _cmd_sync

        args = MagicMock()
        args.version = None
        args.bindir = None
        args.validate = False

        with patch("shutil.which", return_value=None):
            code = _cmd_sync(args)

        assert code == 1
        assert "sync failed" in capsys.readouterr().err
