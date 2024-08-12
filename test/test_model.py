import pytest

from flopy4.ispec.gwf_model import GwfModel


def test_load_gwfdis(tmp_path):
    name = "gwf_1"

    nlay = 3
    nrow = 10
    ncol = 10

    dis_fpth = tmp_path / f"{name}.dis"
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

    nam_fpth = tmp_path / f"{name}.nam"
    with open(nam_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGES\n")
        f.write(f"  DIS6  {tmp_path}/{name}.dis  dis\n")
        f.write("END PACKAGES\n")

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

        # print(type(gwf.values))
        # print(type(gwf.values()))
        # print(gwf.values())

        assert (
            gwf.value["dis"]["dimensions"]["nlay"]
            == gwf.packages["dis"]["dimensions"]["nlay"]
        )
        assert nlay == gwf.packages["dis"]["dimensions"]["nlay"]
        assert nlay == gwf.dis["dimensions"]["nlay"]
        with pytest.raises(Exception):
            gwf.ic
