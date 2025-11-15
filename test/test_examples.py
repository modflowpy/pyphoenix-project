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


def check_heads(compare_fpth, check_path):
    import numpy as np
    from flopy.utils import HeadFile

    if not compare_fpth.exists():
        return

    hds_compare = np.load(compare_fpth)

    # check *.hds files
    for f in check_path.rglob("*.hds"):
        hds = HeadFile(f, precision="double")
        assert np.allclose(hds_compare, hds.get_data())


def check(example_script):
    from pathlib import Path

    test_name = "test_examples"
    check_path = Path(f"{example_script.parent}/{example_script.stem}")
    test_dir = Path(f"{example_script.parent}/../../test")

    # checks; assume test output path parent has example name
    check_heads(
        test_dir / f"__compare__/{test_name}/{example_script.stem}.hds.npy",
        check_path,
    )


@pytest.mark.slow
def test_scripts(example_script):
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True)
    assert not retcode, stdout + stderr
    check(example_script)
