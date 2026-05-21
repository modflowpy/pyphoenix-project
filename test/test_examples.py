"""Test example notebooks."""

import os
import sys

import numpy as np
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


def compare_hds(compare_fpth, check_path):
    from flopy.utils import HeadFile

    if compare_fpth.suffix == ".hds":
        hds_compare = HeadFile(compare_fpth, precision="double").get_data()
    elif compare_fpth.suffix == ".npy":
        hds_compare = np.load(compare_fpth)

    # check *.hds files
    for f in check_path.rglob("*.hds"):
        hds = HeadFile(f, precision="double")
        assert np.allclose(hds_compare, hds.get_data())


def compare_grb(compare_fpth, check_path):
    from flopy.mf6.utils import MfGrdFile

    grb_compare = MfGrdFile(compare_fpth)

    # check *.grb files
    for f in check_path.rglob("*.grb"):
        grb = MfGrdFile(f)
        np.testing.assert_equal(grb_compare._datadict, grb._datadict)


def compare_bud(compare_fpth, check_path):
    from flopy.utils.binaryfile import CellBudgetFile

    bud_compare = CellBudgetFile(compare_fpth)

    # check *.bud and *.cbc files
    pattern = ["*.bud", "*.cbc"]
    files = [f for p in pattern for f in check_path.rglob(p)]
    for f in files:
        bud = CellBudgetFile(f)
        names = bud_compare.get_unique_record_names()
        for n in names:
            bud_cmp = bud_compare.get_data(text=n)
            bud_chk = bud.get_data(text=n)
            if isinstance(bud_cmp[0], np.rec.recarray):
                assert len(bud_cmp) == len(bud_chk)
                for ra_cmp, ra in zip(bud_cmp, bud_chk):
                    assert len(ra_cmp) == len(ra)
                    for i, rec in enumerate(ra_cmp):
                        assert all(np.allclose(x, y) for x, y in zip(rec, ra[i]))
            else:
                assert np.allclose(bud_compare.get_data(text=n), bud.get_data(text=n))


def compare(example_script):
    from pathlib import Path

    check_path = Path(f"{example_script.parent}/{example_script.stem}")
    compare_path = Path(f"{example_script.parent.parent.parent}/test/__compare__/test_examples")

    for f in compare_path.glob(f"{example_script.stem}.*"):
        if f.suffix == ".bud" or f.suffix == ".cbc":
            compare_bud(f, check_path)
        if f.suffix == ".hds" or f.match("*hds.npy"):
            compare_hds(f, check_path)
        if f.suffix == ".grb":
            compare_grb(f, check_path)


@pytest.mark.slow
def test_scripts(example_script):
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    args = [sys.executable, example_script]
    stdout, stderr, retcode = run_cmd(*args, verbose=True, env=env)
    assert not retcode, stdout + stderr
    compare(example_script)
