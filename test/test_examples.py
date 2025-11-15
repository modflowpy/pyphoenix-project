"""Test example notebooks."""

import sys

import pytest
from conftest import EXAMPLES_PATH
from modflow_devtools.misc import run_cmd

EXCLUDE = ["quickstart_expanded"]


def pytest_generate_tests(metafunc):
    if "example_script" in metafunc.fixturenames:
        scripts = {
            file.name: file
            for file in sorted(EXAMPLES_PATH.glob("*.py"))
            if file.stem not in EXCLUDE
        }
        metafunc.parametrize("example_script", scripts.values(), ids=scripts.keys())


def check(example_script, snapshot):
    from pathlib import Path

    from flopy.utils import HeadFile

    check_path = Path(f"{example_script.parent}/{example_script.stem}")
    for f in check_path.rglob("*.hds"):
        hds = HeadFile(f, precision="double")
        assert hds.get_data() == pytest.approx(snapshot)


@pytest.mark.snapshot
@pytest.mark.slow
def test_scripts(example_script, array_snapshot):
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr
    check(example_script, array_snapshot)
