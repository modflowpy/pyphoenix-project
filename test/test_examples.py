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


@pytest.mark.slow
def test_scripts(example_script):
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr
