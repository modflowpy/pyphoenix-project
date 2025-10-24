from pathlib import Path
from platform import system

import pytest
from modflow_devtools.misc import is_in_ci

pytest_plugins = ["modflow_devtools.fixtures"]

PROJ_ROOT_PATH = Path(__file__).parents[1]
DOCS_PATH = PROJ_ROOT_PATH / "docs"
EXAMPLES_PATH = DOCS_PATH / "examples"
EXCLUDED_EXAMPLES = []


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
