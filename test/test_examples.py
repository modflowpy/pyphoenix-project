"""Test example notebooks."""

import sys

import pytest
from modflow_devtools.markers import requires_exe
from modflow_devtools.misc import run_cmd


@pytest.mark.slow
def test_scripts(example_script):
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr


@pytest.mark.slow
@requires_exe("jupytext")
def test_notebooks(example_script):
    args = [
        "jupytext",
        "--from",
        "py",
        "--to",
        "ipynb",
        "--execute",
        example_script,
    ]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr
