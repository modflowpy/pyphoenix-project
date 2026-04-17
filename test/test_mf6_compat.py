"""Tests for flopy4.mf6._compat (version query and compatibility check)."""

import subprocess
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import flopy4.mf6._compat as compat_module
from flopy4.mf6._compat import MF6VersionError, _query_mf6_version, _check_mf6_compatibility


@pytest.fixture(autouse=True)
def reset_compat_flag():
    """Reset the once-flag before each test so checks can be re-triggered."""
    original = compat_module._compat_checked
    compat_module._compat_checked = False
    yield
    compat_module._compat_checked = original


# ---------------------------------------------------------------------------
# _query_mf6_version
# ---------------------------------------------------------------------------


class TestQueryMf6Version:
    def test_parses_release_version(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="mf6: 6.6.0\n",
                stderr="",
                returncode=0,
            )
            version = _query_mf6_version(tmp_path / "mf6")
        assert version == "6.6.0"

    def test_parses_dev_version_with_sha_suffix(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="mf6: 6.8.0.dev0+abc1234 (preliminary) 04/16/2026\n",
                stderr="",
                returncode=0,
            )
            version = _query_mf6_version(tmp_path / "mf6")
        assert version == "6.8.0.dev0+abc1234"

    def test_parses_dev_version_without_sha_suffix(self, tmp_path):
        """Older dev builds that predate the vcs_tag change."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="mf6: 6.8.0.dev0 (preliminary) 04/16/2026\n",
                stderr="",
                returncode=0,
            )
            version = _query_mf6_version(tmp_path / "mf6")
        assert version == "6.8.0.dev0"

    def test_parses_semver_from_stderr(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="",
                stderr="mf6 version 6.5.0\n",
                returncode=0,
            )
            version = _query_mf6_version(tmp_path / "mf6")
        assert version == "6.5.0"

    def test_raises_on_file_not_found(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(MF6VersionError, match="Executable not found"):
                _query_mf6_version(tmp_path / "mf6")

    def test_raises_on_permission_error(self, tmp_path):
        with patch("subprocess.run", side_effect=PermissionError):
            with pytest.raises(MF6VersionError, match="Permission denied"):
                _query_mf6_version(tmp_path / "mf6")

    def test_raises_on_timeout(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="mf6", timeout=10),
        ):
            with pytest.raises(MF6VersionError, match="Timed out"):
                _query_mf6_version(tmp_path / "mf6")

    def test_raises_when_no_version_in_output(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="no version here\n",
                stderr="",
                returncode=0,
            )
            with pytest.raises(MF6VersionError, match="Could not parse version"):
                _query_mf6_version(tmp_path / "mf6")

    def test_accepts_str_path(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="6.6.0",
                stderr="",
                returncode=0,
            )
            version = _query_mf6_version("/usr/bin/mf6")
        assert version == "6.6.0"


# ---------------------------------------------------------------------------
# _check_mf6_compatibility
# ---------------------------------------------------------------------------


class TestCheckMf6Compatibility:
    def test_silent_when_no_binary(self):
        with patch("shutil.which", return_value=None):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                _check_mf6_compatibility()  # must not raise

    def test_silent_when_version_matches_contract(self):
        from flopy4.mf6._contract import MF6_CONTRACT_VERSION

        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6._compat._query_mf6_version",
                return_value=MF6_CONTRACT_VERSION,
            ),
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                _check_mf6_compatibility()  # must not raise

    def test_warns_when_version_differs(self):
        from flopy4.mf6._contract import MF6_CONTRACT_VERSION

        different = "0.0.1"
        assert different != MF6_CONTRACT_VERSION

        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6._compat._query_mf6_version",
                return_value=different,
            ),
        ):
            with pytest.warns(UserWarning, match="flopy4 is synced to MF6"):
                _check_mf6_compatibility()

    def test_silent_when_query_raises(self):
        with (
            patch("shutil.which", return_value="/usr/bin/mf6"),
            patch(
                "flopy4.mf6._compat._query_mf6_version",
                side_effect=MF6VersionError("parse failed"),
            ),
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                _check_mf6_compatibility()  # must not raise

    def test_runs_only_once(self):
        with (
            patch("shutil.which", return_value="/usr/bin/mf6") as mock_which,
            patch("flopy4.mf6._compat._query_mf6_version", return_value="0.0.1"),
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _check_mf6_compatibility()
                _check_mf6_compatibility()
                _check_mf6_compatibility()

        assert mock_which.call_count == 1
