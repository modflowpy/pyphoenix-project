import os
from pathlib import Path
from platform import system

import pytest
from modflow_devtools.download import download_and_unzip
from modflow_devtools.misc import is_in_ci

pytest_plugins = ["modflow_devtools.fixtures"]

PROJ_ROOT_PATH = Path(__file__).parents[1]
DOCS_PATH = PROJ_ROOT_PATH / "docs"
EXAMPLES_PATH = DOCS_PATH / "examples"
EXCLUDED_EXAMPLES = []


def _get_dfn_path(tmp_path_factory):
    """Get path to MF6 DFN files, checking local repos or downloading if needed."""

    # Check REPOS_PATH environment variable (modflow-devtools convention)
    repos_path = os.environ.get("REPOS_PATH")
    if repos_path:
        dfn_path = Path(repos_path) / "modflow6" / "doc" / "mf6io" / "mf6ivar" / "dfn"
        if dfn_path.exists():
            return dfn_path

    # Check if modflow6 repo exists as sibling to this project
    sibling_path = PROJ_ROOT_PATH.parent / "modflow6" / "doc" / "mf6io" / "mf6ivar" / "dfn"
    if sibling_path.exists():
        return sibling_path

    # Download from GitHub if not found locally
    tmp_dir = tmp_path_factory.mktemp("mf6_dfn")
    url = "https://github.com/MODFLOW-USGS/modflow6/archive/refs/heads/develop.zip"
    download_and_unzip(url, tmp_dir, verbose=False)

    # Find the extracted directory (will have a prefix like 'modflow6-develop')
    extracted_dirs = [d for d in tmp_dir.iterdir() if d.is_dir() and d.name.startswith("modflow6")]
    if not extracted_dirs:
        pytest.fail(f"Failed to extract modflow6 from {url}")

    dfn_path = extracted_dirs[0] / "doc" / "mf6io" / "mf6ivar" / "dfn"
    if not dfn_path.exists():
        pytest.fail("DFN directory not found in downloaded modflow6 repo")

    return dfn_path


@pytest.fixture(scope="session")
def dfn_path(tmp_path_factory):
    """Get the path to MF6 DFN files."""
    return _get_dfn_path(tmp_path_factory)


@pytest.fixture(scope="session", autouse=True)
def patch_macos_ci_matplotlib():
    # use noninteractive matplotlib backend if in Mac OS CI to avoid pytest-xdist node failure
    if is_in_ci() and system().lower() in ["darwin", "windows"]:
        import matplotlib

        matplotlib.use("agg")


def pytest_generate_tests(metafunc):
    if "example_script" in metafunc.fixturenames:
        scripts = {
            file.name: file
            for file in sorted(EXAMPLES_PATH.glob("*example.py"))
            if file.stem not in EXCLUDED_EXAMPLES
        }
        metafunc.parametrize("example_script", scripts.values(), ids=scripts.keys())
