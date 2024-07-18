"""Test example notebooks."""

import sys

from modflow_devtools.markers import requires_exe
from modflow_devtools.misc import run_cmd


def test_scripts(example_script):
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr


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
