import os

import numpy as np
import pytest

from flopy4.ispec.gwf_model import GwfModel

name = "gwf_1"
nlay = 3
nrow = 10
ncol = 10


def write_inputs(tmp_path):
    dis_fpth = tmp_path / f"{name}.dis"
    ic_fpth = tmp_path / f"{name}.ic"
    nam_fpth = tmp_path / f"{name}.nam"

    with open(dis_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write(f"  NLAY  {nlay}\n")
        f.write(f"  NROW  {nrow}\n")
        f.write(f"  NCOL  {ncol}\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN GRIDDATA\n")
        f.write("  DELR\n    CONSTANT  1000.00000000\n")
        f.write("  DELC\n    CONSTANT  2000.00000000\n")
        f.write("  TOP\n    CONSTANT  0.00000000\n")
        f.write("  BOTM    LAYERED\n")
        f.write("    CONSTANT  -100.00000000\n")
        f.write("    CONSTANT  -150.00000000\n")
        f.write("    CONSTANT  -350.00000000\n")
        f.write("END GRIDDATA\nn\\n")

    strt = np.linspace(0.0, 30.0, num=300)
    array = " ".join(str(x) for x in strt)
    with open(ic_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  STRT\n    INTERNAL\n      {array}\n")
        f.write("END GRIDDATA\n")

    with open(nam_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGES\n")
        f.write(f"  DIS6  {tmp_path}/{name}.dis  dis\n")
        f.write(f"  IC6  {tmp_path}/{name}.ic  ic\n")
        f.write("END PACKAGES\n")


def test_load_gwfdis(tmp_path):
    nam_fpth = tmp_path / f"{name}.nam"

    write_inputs(tmp_path)

    # test model load
    kwargs = {}
    kwargs["mempath"] = "sim/gwf_1"
    with open(nam_fpth, "r") as f:
        gwf = GwfModel.load(f, **kwargs)
        assert nlay == gwf.packages["dis"]["dimensions"]["nlay"]
        assert nrow == gwf.packages["dis"]["dimensions"]["nrow"]
        assert ncol == gwf.packages["dis"]["dimensions"]["ncol"]

        assert str(gwf) == "gwf_1"
        assert gwf.name == "gwf_1"

        assert (
            gwf.value["dis"]["dimensions"]["nlay"]
            == gwf.packages["dis"]["dimensions"]["nlay"]
        )
        assert nlay == gwf.packages["dis"]["dimensions"]["nlay"]
        assert nlay == gwf.dis["dimensions"]["nlay"]
        with pytest.raises(Exception):
            gwf.npf


def test_write_gwfdis(tmp_path):
    # write input files
    write_inputs(tmp_path)

    kwargs = {}
    kwargs["mempath"] = "sim/gwf_1"
    gwf = None

    # load model
    nam_fpth = tmp_path / f"{name}.nam"
    with open(nam_fpth, "r") as f:
        gwf = GwfModel.load(f, **kwargs)

    write_dir = tmp_path / "write"
    os.makedirs(write_dir)
    gwf.write(write_dir)
